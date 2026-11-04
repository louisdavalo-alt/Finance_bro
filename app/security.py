"""Outils de sécurité transverses : masquage des secrets dans les logs et messages d'erreur,
authentification HTTP Basic optionnelle de l'API, en-têtes de sécurité du tableau de bord.

Pourquoi ce module existe :

- **Fuite de clés API dans les logs.** FRED (`api_key`) et e-Stat (`appId`) exigent la clé dans
  la QUERY STRING. Or `httpx` journalise chaque requête au niveau INFO avec l'URL complète, et
  les messages d'erreur (`HTTPStatusError`, `SourceUnavailable`) la reprennent aussi : la clé
  finissait en clair dans `data/pipeline.log` (cron) et dans la console. `redact_url` et
  `SecretRedactingFilter` masquent ces valeurs partout où elles pourraient sortir.
- **API ouverte au réseau.** Par défaut l'API écoute sur 127.0.0.1 (seul l'utilisateur local y a
  accès). Si `HOST` est changé pour l'exposer, `API_USERNAME`/`API_PASSWORD` activent une
  authentification HTTP Basic — gérée nativement par le navigateur, donc sans aucune
  modification du tableau de bord (les `fetch` de même origine renvoient automatiquement les
  identifiants).
"""
from __future__ import annotations

import base64
import binascii
import collections
import hashlib
import logging
import re
import secrets
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Noms de paramètres/en-têtes considérés comme secrets (comparaison insensible à la casse).
SECRET_PARAM_NAMES = frozenset({
    "api_key", "apikey", "appid", "app_id", "key", "token", "access_token",
    "subscription-key", "password", "secret",
})
SECRET_HEADER_NAMES = frozenset({"authorization", "ocp-apim-subscription-key", "x-api-key"})
MASK = "***"

# Valeurs explicitement enregistrées (clés lues dans .env) : masquées partout dans les logs, même
# hors d'une URL (ex. dans le texte d'une exception renvoyée par une bibliothèque tierce).
_known_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Déclare une valeur secrète à masquer dans tous les messages de log. Ignore les valeurs
    trop courtes (< 6 caractères) pour ne pas masquer des fragments de texte banals."""
    if value and len(value) >= 6:
        _known_secrets.add(value)


def redact_text(text: str) -> str:
    for s in _known_secrets:
        if s in text:
            text = text.replace(s, MASK)
    return _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}={MASK}", text)


_QUERY_SECRET_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(n) for n in sorted(SECRET_PARAM_NAMES, key=len, reverse=True)) + r")=([^&\s\"'#]+)"
)


def redact_url(url) -> str:
    """Renvoie l'URL avec la valeur des paramètres secrets remplacée par `***`."""
    url = str(url)
    try:
        parts = urlsplit(url)
    except ValueError:
        return redact_text(url)
    if not parts.query:
        return redact_text(url)
    query = urlencode(
        [(k, MASK if k.lower() in SECRET_PARAM_NAMES else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)],
        safe="*:,[]{}\"'",
    )
    netloc = parts.netloc.split("@")[-1]  # retire d'éventuels identifiants user:pass@
    return redact_text(urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment)))


class SecretRedactingFilter(logging.Filter):
    """Filtre de logging : masque les secrets connus et les paramètres sensibles d'URL dans le
    message final. À installer sur les HANDLERS (pas sur un logger), pour couvrir aussi les
    messages des bibliothèques tierces (httpx, yfinance, apscheduler...)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - un message mal formé ne doit pas casser le logging
            return True
        redacted = redact_text(msg)
        if redacted != msg:
            record.msg, record.args = redacted, None
        if record.exc_info and record.exc_info[1] is not None and not record.exc_text:
            # Le texte de l'exception est formaté plus tard par le handler : on le précalcule
            # ici, masqué, pour qu'aucune clé ne ressorte dans une trace d'erreur.
            record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configuration commune des logs (pipeline, API, planificateur) : format homogène, filtre
    de masquage des secrets, et `httpx`/`httpcore` ramenés au niveau WARNING (leur INFO
    contient l'URL complète de chaque requête, donc les clés passées en query string)."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    root.setLevel(level)
    for handler in root.handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            handler.addFilter(SecretRedactingFilter())
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# --------------------------------------------------------------------------- #
# Authentification HTTP Basic (optionnelle)
# --------------------------------------------------------------------------- #
def check_basic_auth(header_value: str | None, username: str, password: str) -> bool:
    """Vérifie un en-tête `Authorization: Basic ...` en temps constant."""
    if not header_value or not header_value.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header_value[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, sep, pwd = decoded.partition(":")
    if not sep:
        return False
    # Les deux comparaisons sont toujours évaluées (pas de court-circuit) : temps constant.
    ok_user = secrets.compare_digest(user.encode(), username.encode())
    ok_pwd = secrets.compare_digest(pwd.encode(), password.encode())
    return ok_user & ok_pwd


def inline_script_hashes(html: str) -> list[str]:
    """Empreintes SHA-256 (format CSP) de chaque `<script>` inline de la page, pour autoriser
    exactement ce script-là dans la Content-Security-Policy sans recourir à 'unsafe-inline'."""
    out = []
    for body in re.findall(r"<script>(.*?)</script>", html, flags=re.S):
        digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        out.append(f"'sha256-{digest}'")
    return out


# --------------------------------------------------------------------------- #
# Anti force brute (authentification Basic)
# --------------------------------------------------------------------------- #
class AuthFailureLimiter:
    """Compte les échecs d'authentification par adresse IP sur une fenêtre glissante et bloque
    l'adresse (429) au-delà de `max_failures`. Sans cela, un mot de passe Basic exposé sur le
    réseau pouvait être essayé à la vitesse du serveur. Mémoire bornée (`max_tracked` adresses)."""

    def __init__(self, max_failures: int = 10, window_s: float = 300.0, max_tracked: int = 10_000):
        self._time = time.monotonic
        self.max_failures = max_failures
        self.window_s = window_s
        self._max_tracked = max_tracked
        self._failures: collections.OrderedDict[str, list[float]] = collections.OrderedDict()
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._failures.get(key, ()) if now - t < self.window_s]
        if hits:
            self._failures[key] = hits
        else:
            self._failures.pop(key, None)
        return hits

    def blocked_for(self, key: str) -> float:
        """Secondes restantes de blocage pour `key` (0 si non bloquée)."""
        with self._lock:
            now = self._time()
            hits = self._recent(key, now)
            if len(hits) < self.max_failures:
                return 0.0
            return max(1.0, self.window_s - (now - hits[0]))

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._time()
            hits = self._recent(key, now)
            hits.append(now)
            self._failures[key] = hits
            self._failures.move_to_end(key)
            while len(self._failures) > self._max_tracked:
                self._failures.popitem(last=False)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


# --------------------------------------------------------------------------- #
# Requêtes intersites (CSRF / « drive-by » vers l'API locale)
# --------------------------------------------------------------------------- #
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_cross_site_request(method: str, headers, allowed_hosts) -> bool:
    """Vrai si la requête vient manifestement d'un AUTRE site ouvert dans le navigateur.

    La vérification de l'en-tête `Host` bloque le DNS rebinding, mais pas une page malveillante
    qui appelle directement `http://127.0.0.1:8100/...` : le navigateur envoie alors un `Host`
    légitime. La réponse reste illisible pour cette page (pas de CORS), mais la requête est
    EXÉCUTÉE — de quoi lancer en boucle des calculs lourds (/ensemble, /portfolio), des appels
    Yahoo en ton nom, ou ajouter des tickers (POST /market-activate). Les navigateurs récents
    indiquent l'origine via `Sec-Fetch-Site` ; à défaut, `Origin` est comparé aux hôtes autorisés
    pour les méthodes qui modifient l'état. Les clients hors navigateur (curl, scripts), qui
    n'envoient aucun de ces en-têtes, ne sont pas concernés."""
    site = (headers.get("sec-fetch-site") or "").lower()
    if site == "cross-site":
        return True
    if site in ("same-origin", "same-site", "none"):
        return False
    if method.upper() in UNSAFE_METHODS:
        origin = headers.get("origin")
        if origin:
            if origin == "null":
                return True
            host = (urlsplit(origin).hostname or "").lower()
            allowed = {h.strip("[]").lower() for h in allowed_hosts}
            return host not in allowed
    return False
