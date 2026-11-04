"""Client HTTP asynchrone partagé : retries avec backoff, respect des rate limits,
gestion homogène des erreurs 429/5xx pour toutes les sources.

Sécurité :
- les URL apparaissant dans les logs et les messages d'erreur sont MASQUÉES (`security.redact_url`) :
  FRED et e-Stat transmettent leur clé en query string, qui finissait sinon en clair dans
  `data/pipeline.log` ;
- les redirections ne sont suivies que vers le MÊME hôte (et jamais d'HTTPS vers HTTP) : httpx ne
  retire que l'en-tête `Authorization` lors d'une redirection vers un autre domaine, pas une clé
  en query string ni l'en-tête `Ocp-Apim-Subscription-Key` du FMI, qui auraient sinon été
  envoyés tels quels au domaine de destination ;
- l'attente imposée par `Retry-After` est bornée (`MAX_RETRY_AFTER_S`) : une valeur aberrante
  (ou une date HTTP, que l'ancien `float(...)` faisait planter) ne peut plus bloquer le pipeline.
"""
from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import time

import httpx

from .config import Settings, SourceConfig
from .ratelimit import RateLimiterRegistry, TokenBucket
from .security import redact_url

log = logging.getLogger("http")

RETRY_STATUS = {429, 500, 502, 503, 504}
REDIRECT_STATUS = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
MAX_RETRY_AFTER_S = 120.0


class SourceUnavailable(RuntimeError):
    """Levée après épuisement des tentatives : la source est temporairement indisponible."""


class UnsafeRedirect(RuntimeError):
    """Redirection refusée (autre hôte, ou passage d'HTTPS à HTTP)."""


def parse_retry_after(value: str | None, now: float | None = None) -> float | None:
    """`Retry-After` en secondes (entier/décimal) ou en date HTTP (RFC 9110), borné à
    [0, MAX_RETRY_AFTER_S]. `None` si absent ou illisible."""
    if not value:
        return None
    value = value.strip()
    try:
        delay = float(value)
    except ValueError:
        try:
            dt = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if dt is None:
            return None
        delay = dt.timestamp() - (now if now is not None else time.time())
    return max(0.0, min(delay, MAX_RETRY_AFTER_S))


def _same_origin_redirect(current: httpx.URL, target: httpx.URL) -> bool:
    if target.host != current.host:
        return False
    if current.scheme == "https" and target.scheme != "https":
        return False
    return True


class ApiClient:
    """Enveloppe httpx.AsyncClient : un seul client partagé, un seau à jetons par source."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._limiters = RateLimiterRegistry()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ApiClient":
        self._client = httpx.AsyncClient(
            timeout=self.settings.http_timeout_s,
            follow_redirects=False,  # suivies manuellement, et seulement vers le même hôte (voir _send)
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={"User-Agent": "finance-bro/1.0 (+usage personnel)"},
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    def rate_limiter(self, src: SourceConfig) -> TokenBucket:
        """Seau à jetons de cette source, réutilisable par un connecteur qui ne passe pas par
        `get`/`post` (ex. yfinance, qui gère son propre client réseau)."""
        return self._limiters.get(src.name, src.rate_limit)

    async def get(self, src: SourceConfig, path: str, *, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
        return await self._request("GET", src, path, params=params, headers=headers)

    async def post(
        self,
        src: SourceConfig,
        path: str,
        *,
        data: dict | None = None,
        headers: dict | None = None,
        auth: tuple[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request("POST", src, path, data=data, headers=headers, auth=auth)

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Envoie la requête et suit au plus MAX_REDIRECTS redirections, uniquement vers le même
        hôte (sinon `UnsafeRedirect`)."""
        assert self._client is not None
        resp = await self._client.request(method, url, **kwargs)
        for _ in range(MAX_REDIRECTS):
            if resp.status_code not in REDIRECT_STATUS or "location" not in resp.headers:
                return resp
            target = resp.request.url.join(resp.headers["location"])
            if not _same_origin_redirect(resp.request.url, target):
                await resp.aclose()
                raise UnsafeRedirect(
                    f"redirection refusée de {redact_url(resp.request.url)} vers {redact_url(target)} "
                    "(autre hôte ou passage en HTTP : les identifiants auraient été transmis)"
                )
            await resp.aclose()
            if resp.status_code == 303 or (resp.status_code in (301, 302) and method == "POST"):
                method, kwargs = "GET", {k: v for k, v in kwargs.items() if k in ("headers", "auth")}
            else:
                kwargs = {k: v for k, v in kwargs.items() if k != "params"}  # déjà inclus dans `target`
            resp = await self._client.request(method, target, **kwargs)
        raise UnsafeRedirect(f"trop de redirections ({MAX_REDIRECTS}) depuis {redact_url(url)}")

    async def _request(
        self,
        method: str,
        src: SourceConfig,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
        auth: tuple[str, str] | None = None,
    ) -> httpx.Response:
        assert self._client is not None, "utiliser `async with ApiClient(settings) as client:`"
        bucket = self._limiters.get(src.name, src.rate_limit)
        url = path if path.startswith(("http://", "https://")) else f"{src.base_url.rstrip('/')}/{path.lstrip('/')}"

        last_exc: Exception | None = None
        for attempt in range(self.settings.http_max_retries + 1):
            await bucket.acquire()
            try:
                resp = await self._send(method, url, params=params, data=data, headers=headers, auth=auth)
            except httpx.TransportError as exc:
                # Le texte des exceptions httpx peut contenir l'URL complète : on ne garde que le type.
                last_exc = SourceUnavailable(f"{type(exc).__name__} sur {redact_url(url)}")
            else:
                if resp.status_code not in RETRY_STATUS:
                    if resp.is_error:
                        raise httpx.HTTPStatusError(
                            f"{resp.status_code} {resp.reason_phrase} sur {redact_url(resp.request.url)}",
                            request=resp.request, response=resp,
                        )
                    return resp
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code} sur {redact_url(resp.request.url)}", request=resp.request, response=resp
                )
                retry_after = parse_retry_after(resp.headers.get("Retry-After"))
                if retry_after is not None and attempt < self.settings.http_max_retries:
                    log.warning("%s : %s, Retry-After %.1fs", src.name, resp.status_code, retry_after)
                    await asyncio.sleep(retry_after)
                    continue

            if attempt >= self.settings.http_max_retries:
                break  # pas d'attente inutile après la dernière tentative
            wait = min(2**attempt, 30) + random.random()
            log.warning("échec %s (%s/%s), nouvelle tentative dans %.1fs : %s", src.name, attempt + 1, self.settings.http_max_retries, wait, last_exc)
            await asyncio.sleep(wait)

        raise SourceUnavailable(f"{src.name} indisponible après {self.settings.http_max_retries + 1} tentatives : {last_exc}") from None
