"""API de consultation (FastAPI) : sert les données déjà collectées par `pipeline.py`, et le
tableau de bord (`GET /`) qui les explore.

Ce service ne fait aucun appel réseau vers les sources macro : il lit les exports Parquet du
pipeline (`cache.ParquetReader`), sans jamais ouvrir `data/macro.duckdb` — le pipeline peut donc
tourner (cron) pendant que l'API est lancée. Lancer le pipeline au moins une fois avant
d'interroger cette API.

Sécurité (voir aussi `security.py` et le README, section « Sécurité ») :
- écoute sur 127.0.0.1 par défaut ; authentification HTTP Basic si `API_USERNAME`/`API_PASSWORD`
  sont définis (obligatoire pour exposer l'API sur le réseau, voir `serve.py`) ;
- en-tête `Host` vérifié (protection contre le DNS rebinding : sans cela, n'importe quel site web
  ouvert dans le navigateur pouvait interroger l'API locale) ;
- en-têtes de sécurité et Content-Security-Policy stricte sur le tableau de bord ;
- paramètres validés (motifs, tailles maximales) et messages d'erreur génériques côté client,
  le détail des exceptions restant dans les logs du serveur (secrets masqués).

Performance :
- les calculs lourds (prévision, portefeuille, Monte Carlo) et les lectures tournent HORS de la
  boucle asyncio, avec une limite de calculs simultanés ;
- les réponses Yahoo et les prévisions sont mises en cache quelques minutes (`livecache.py`) ;
- compression gzip des réponses volumineuses.
"""
from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool

from .cache import ParquetReader
from .config import load_settings
from .connectors.base import IndicatorSpec
from .connectors.yfin import _fetch_history_sync
from .forecast.pipeline import NoMarketData, run_forecast
from .forecast.weighting import run_weighted_ensemble_forecast
from .livecache import Busy, LiveCache
from .market_search import search_symbols
from .portfolio.optimizer import InfeasibleTarget
from .portfolio.pipeline import available_countries, available_sectors, build_portfolio
from .ohlc import YFinanceNotInstalled, fetch_ohlcv
from .ohlcv_cache import OhlcvCache
from .marketdata import get_daily_bars
from .quote import RANGE_PATTERN, fetch_chart, fetch_quote_summary, fetch_symbol_name, frame_to_bars
from .registry import INDICATORS, by_code
from .resample import align_panel
from .schemas import (
    EnsembleResponse,
    ForecastResponse,
    HealthResponse,
    IndicatorInfo,
    KronosEnabledResponse,
    LagReportRow,
    MarketActivateRequest,
    MarketLookupResult,
    MarketSearchResult,
    OhlcBar,
    PanelResponse,
    PortfolioResponse,
    PortfolioUniverseResponse,
    QuoteSummary,
    SYMBOL_PATTERN,
    SeriesRecord,
    clean_label,
)
from .security import (
    AuthFailureLimiter,
    check_basic_auth,
    inline_script_hashes,
    is_cross_site_request,
    setup_logging,
)

setup_logging()
log = logging.getLogger("api")
settings = load_settings()
store: ParquetReader | None = None
live: LiveCache | None = None
ohlcv_cache: OhlcvCache | None = None
STATIC = Path(__file__).parent / "static"

CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,99}$"
PERIOD_PATTERN = r"^(1mo|3mo|6mo|1y|2y|5y|10y|ytd|max)$"
MAX_PANEL_CODES = 50
MAX_FILTER_VALUES = 50
MAX_MC_CELLS = 5_000_000  # n_sims × horizon : borne la mémoire de la simulation (~40 Mo)
_FILTER_VALUE_RE = re.compile(r"^[\w .,'&/()\-]{1,60}$", re.UNICODE)
_CODE_RE = re.compile(CODE_PATTERN)
_CODE_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.\-]")
_auth_failures = AuthFailureLimiter(settings.api.auth_max_failures, settings.api.auth_failure_window_s)
# Sérialise les ajouts de tickers : sans verrou, deux POST /market-activate simultanés pour le
# même symbole (double clic) passaient tous deux le contrôle « déjà suivi ».
_activate_lock = asyncio.Lock()

# Tickers ajoutés à la volée via POST /market-activate (voir plus bas) : chargés depuis
# `ohlcv_cache.duckdb` au démarrage (`lifespan`), tenus à jour en mémoire ensuite. Séparé du
# catalogue déclaratif `INDICATORS` (registry.py), qui reste purement statique.
_custom_specs: dict[str, IndicatorSpec] = {}

# code -> symbole déclaré dans le registre statique, pour savoir si un ticker trouvé par
# /market-search correspond déjà à un indicateur existant (pas la peine de l'ajouter deux fois).
_SYMBOL_TO_CODE: dict[str, str] = {}
for _spec in INDICATORS:
    _sym = _spec.params.get("symbol")
    if _sym:
        _SYMBOL_TO_CODE.setdefault(_sym, _spec.code)
del _spec, _sym


def _existing_code_for_symbol(symbol: str) -> str | None:
    code = _SYMBOL_TO_CODE.get(symbol)
    if code:
        return code
    for spec in _custom_specs.values():
        if spec.params.get("symbol") == symbol:
            return spec.code
    return None

# Le tableau de bord est servi depuis la mémoire, avec une CSP qui n'autorise QUE son propre
# script inline (empreinte SHA-256), aucun script externe, et aucune connexion hors de l'origine.
_DASHBOARD_HTML = (STATIC / "dashboard.html").read_bytes()
_DASHBOARD_CSP = "; ".join([
    "default-src 'self'",
    "script-src " + " ".join(inline_script_hashes(_DASHBOARD_HTML.decode("utf-8"))),
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
# Réponses JSON / texte : rien à exécuter ni à charger, et jamais affichables dans un cadre.
# (/docs et /redoc gardent la politique de FastAPI : Swagger UI charge ses scripts d'un CDN.)
_DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_DOCS_PATHS = ("/docs", "/redoc")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store, live, ohlcv_cache
    store = ParquetReader(settings.data_dir)
    live = LiveCache(max_concurrent=settings.api.max_concurrent_jobs)
    ohlcv_cache = OhlcvCache(settings.data_dir)
    for row in ohlcv_cache.list_custom():
        _custom_specs[row["code"]] = IndicatorSpec(
            row["code"], row["country"], "yfinance", "D", row["unit"] or "USD", {"symbol": row["symbol"]}
        )
    if not settings.api.auth_enabled and settings.api.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("API exposée sur %s SANS authentification : définis API_USERNAME/API_PASSWORD", settings.api.host)
    try:
        yield
    finally:
        store.close()
        ohlcv_cache.close()


_docs = settings.api.enable_docs
app = FastAPI(
    title="Finance Bro",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)


# --------------------------------------------------------------------------- #
# Middlewares (le dernier ajouté s'exécute en premier)
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    path = request.url.path
    if path == "/":
        response.headers["Content-Security-Policy"] = _DASHBOARD_CSP
    elif not path.startswith(_DOCS_PATHS):
        response.headers.setdefault("Content-Security-Policy", _DEFAULT_CSP)
    response.headers.setdefault("Cache-Control", "no-store")
    return response


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "?"


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if settings.api.auth_enabled and request.url.path != "/health":
        key = _client_key(request)
        blocked = _auth_failures.blocked_for(key)
        if blocked:
            return Response(
                "trop de tentatives d'authentification, réessaie plus tard", status_code=429,
                headers={"Retry-After": str(int(blocked)), **_SECURITY_HEADERS},
            )
        header = request.headers.get("authorization")
        if not check_basic_auth(header, settings.api.username, settings.api.password):
            # Seule une tentative EFFECTIVE (en-tête présent mais faux) compte comme un échec : la
            # première requête du navigateur, sans identifiants, sert juste à afficher l'invite.
            if header:
                _auth_failures.record_failure(key)
                log.warning("échec d'authentification depuis %s", key)
            return Response(
                "authentification requise", status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Finance Bro", charset="UTF-8"', **_SECURITY_HEADERS},
            )
    return await call_next(request)


@app.middleware("http")
async def reject_cross_site(request: Request, call_next):
    """Refuse les requêtes émises par un autre site ouvert dans le navigateur (voir
    `security.is_cross_site_request`) — AVANT l'authentification, pour qu'une page tierce ne
    puisse ni déclencher de calcul ni réutiliser des identifiants Basic mémorisés."""
    if is_cross_site_request(request.method, request.headers, _allowed_hosts):
        return Response("requête intersite refusée", status_code=403, headers=_SECURITY_HEADERS)
    return await call_next(request)


app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)  # niveau 9 : 5x plus lent pour ~5 % de gain
_allowed_hosts = list(settings.api.allowed_hosts)
if settings.api.host not in ("0.0.0.0", "::", ""):
    _allowed_hosts.append(settings.api.host)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)


@app.exception_handler(Busy)
async def _busy_handler(_: Request, exc: Busy):
    return JSONResponse({"detail": str(exc)}, status_code=503, headers={"Retry-After": "10"})


def _upstream_error(what: str, exc: Exception) -> HTTPException:
    """Journalise le détail (secrets masqués par le filtre de logging) et renvoie un message
    générique : le texte brut d'une exception (chemins, URL, réponses de tiers) n'a rien à faire
    dans une réponse HTTP."""
    log.warning("%s : %s: %s", what, type(exc).__name__, exc)
    return HTTPException(502, f"{what} (détail dans les logs du serveur)")


Code = PathParam(..., pattern=CODE_PATTERN, description="code d'indicateur du registre")
Symbol = PathParam(..., pattern=SYMBOL_PATTERN, description="symbole Yahoo Finance (ex. ACME.PA, ^GSPC, EURUSD=X)")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
async def dashboard() -> Response:
    return Response(_DASHBOARD_HTML, media_type="text/html; charset=utf-8")


@app.get("/health", response_model=HealthResponse)
async def health() -> dict:
    return {"ok": True}


def _collected_stats() -> dict[str, dict]:
    """`list_indicators` groupe par (code, pays, source, fréquence, unité) : un même code servi
    par deux sources (source principale + repli Banque mondiale) donnait deux lignes, et le
    `dict` ne gardait que la dernière — n_obs/dernière date sous-estimés. Fusion par code ici."""
    out: dict[str, dict] = {}
    for r in store.list_indicators().to_dict(orient="records"):
        code = r["indicator_code"]
        prev = out.get(code)
        if prev is None:
            out[code] = {"n_obs": int(r["n_obs"]), "last_timestamp": r["last_timestamp"]}
        else:
            prev["n_obs"] += int(r["n_obs"])
            if r["last_timestamp"] is not None and (prev["last_timestamp"] is None or r["last_timestamp"] > prev["last_timestamp"]):
                prev["last_timestamp"] = r["last_timestamp"]
    return out


def _indicators_payload() -> list[dict]:
    collected = _collected_stats()
    out = []
    for spec in INDICATORS:
        row = collected.get(spec.code)
        last = row["last_timestamp"] if row is not None else None
        out.append(
            {
                "code": spec.code,
                "country": spec.country,
                "connector": spec.connector,
                "frequency": spec.frequency,
                "unit": spec.unit,
                "has_fallback": spec.fallback is not None,
                "n_obs": row["n_obs"] if row is not None else 0,
                "last_timestamp": last.isoformat() if last is not None else None,
            }
        )
    # Tickers ajoutés à la volée (POST /market-activate) : pas d'observations dans macro.duckdb/
    # Parquet (le pipeline cron ne les connaît pas), donc n_obs/dernière donnée viennent du cache
    # OHLCV local — en une seule requête agrégée pour tous les tickers.
    customs = list(_custom_specs.values())
    stats = ohlcv_cache.stats([spec.params["symbol"] for spec in customs])
    for spec in customs:
        n_obs, last = stats.get(spec.params["symbol"], (0, None))
        out.append(
            {
                "code": spec.code,
                "country": spec.country,
                "connector": spec.connector,
                "frequency": spec.frequency,
                "unit": spec.unit,
                "has_fallback": False,
                "n_obs": n_obs,
                "last_timestamp": last,
            }
        )
    return out


@app.get("/indicators", response_model=list[IndicatorInfo])
async def indicators() -> list[dict]:
    """Catalogue déclaré (registry.py) + statistiques réelles de ce qui a été collecté."""
    return await run_in_threadpool(_indicators_payload)


@app.get("/market-search", response_model=list[MarketSearchResult])
async def market_search(
    q: str = Query(..., min_length=1, max_length=80, description="nom ou symbole à rechercher auprès de Yahoo Finance"),
    limit: int = Query(8, ge=1, le=20),
) -> list[dict]:
    """Recherche libre auprès de Yahoo Finance (nom d'entreprise ou symbole), pour trouver une
    action absente du catalogue (`/indicators`) — onglet « rechercher et afficher des actions ».
    `already_tracked`/`code` indiquent qu'un indicateur existe déjà pour ce symbole (catalogue
    statique ou précédemment ajouté via `/market-activate`), pour éviter un doublon."""
    results = await _yahoo(
        "échec de la recherche auprès de Yahoo Finance",
        ("market-search", q, limit), settings.api.live_cache_ttl_s,
        lambda: search_symbols(q, limit),
    )
    # `results` est partagé entre requêtes (valeur mise en cache par `live`, voir livecache.py) :
    # on construit de nouveaux dict plutôt que de modifier les siens en place.
    out = []
    for r in results:
        code = _existing_code_for_symbol(r["symbol"])
        out.append({**r, "already_tracked": code is not None, "code": code})
    return out


@app.get("/market-lookup/{symbol}", response_model=MarketLookupResult)
async def market_lookup(symbol: str = Symbol) -> dict:
    """Aperçu « en direct » d'un symbole Yahoo Finance choisi dans les résultats de
    `/market-search` — rien n'est stocké ni mis en cache sur disque ici (comme `/quote`), que
    l'utilisateur choisisse ensuite de l'ajouter à la bibliothèque active ou de juste l'observer."""
    data = await _yahoo(
        "échec de la récupération auprès de Yahoo Finance",
        ("market-lookup", symbol), settings.api.live_cache_ttl_s,
        lambda: fetch_quote_summary(symbol),
    )
    if data is None:
        raise HTTPException(404, f"aucune donnée Yahoo Finance pour le symbole {symbol!r}")
    code = _existing_code_for_symbol(symbol)
    return {
        "symbol": symbol,
        "name": None,  # déjà connu côté appelant (résultat de /market-search) : pas redemandé ici
        "last": data.get("last"),
        "currency": data.get("currency"),
        "already_tracked": code is not None,
        "code": code,
    }


def _fetch_live_ohlc_sync(symbol: str, period: str) -> list[dict]:
    df = _fetch_history_sync(symbol, period)
    return frame_to_bars(df, intraday=False)


@app.get("/market-lookup/{symbol}/ohlc", response_model=list[OhlcBar])
async def market_lookup_ohlc(
    symbol: str = Symbol,
    period: str = Query("1y", pattern=PERIOD_PATTERN),
) -> list[dict]:
    """Historique O/H/L/C/V « pour juste observer » un symbole pas encore dans la bibliothèque
    active : appel Yahoo Finance direct (mémorisé quelques minutes, comme `/chart`), jamais écrit
    dans le cache disque `ohlcv_cache.duckdb` — seul `/market-activate` y rapatrie un historique."""
    data = await _yahoo(
        "échec de la récupération auprès de Yahoo Finance",
        ("market-lookup-ohlc", symbol, period), settings.api.live_cache_ttl_s,
        lambda: asyncio.to_thread(_fetch_live_ohlc_sync, symbol, period),
    )
    if not data:
        raise HTTPException(404, f"aucune donnée O/H/L/C/V pour le symbole {symbol!r}")
    return data


@app.post("/market-activate", response_model=IndicatorInfo)
async def market_activate(body: MarketActivateRequest) -> dict:
    """« Ajouter à la bibliothèque active » : déclare `body.symbol` comme un nouvel indicateur de
    marché (persisté dans `ohlcv_cache.duckdb`, survit au redémarrage) et rapatrie IMMÉDIATEMENT
    tout son historique dans le cache OHLCV local — contrairement à `/market-lookup`, qui ne fait
    qu'observer sans rien stocker. Le nouveau code apparaît ensuite dans `/indicators` comme
    n'importe quel indicateur du catalogue statique."""
    symbol = body.symbol  # déjà nettoyé et validé (SYMBOL_PATTERN) par MarketActivateRequest
    async with _activate_lock:
        existing = _existing_code_for_symbol(symbol)
        if existing is not None:
            raise HTTPException(409, f"{symbol} est déjà suivi sous le code {existing}")
        if len(_custom_specs) >= settings.api.max_custom_indicators:
            raise HTTPException(
                409, f"limite de {settings.api.max_custom_indicators} tickers ajoutés atteinte (API_MAX_CUSTOM_INDICATORS)"
            )

        preview = await _yahoo(
            "échec de la récupération auprès de Yahoo Finance",
            ("market-lookup", symbol), settings.api.live_cache_ttl_s,
            lambda: fetch_quote_summary(symbol),
        )
        if preview is None:
            raise HTTPException(404, f"aucune donnée Yahoo Finance pour le symbole {symbol!r} — vérifie le ticker")

        if body.code:
            code = body.code
            try:
                _resolve_spec(code)
            except KeyError:
                pass
            else:
                raise HTTPException(409, f"le code {code} existe déjà")
        else:
            base = _CODE_SANITIZE_RE.sub("_", symbol).strip("_").upper() or "TICKER"
            code = f"YF_{base}"[:100]
            suffix = 1
            while True:
                try:
                    _resolve_spec(code)
                except KeyError:
                    break
                suffix += 1
                code = f"YF_{base}_{suffix}"[:100]

        country = body.country or "GLOBAL"
        # Devise et nom viennent de Yahoo (donnée tierce) : bornés avant d'être persistés.
        unit = clean_label(preview.get("currency"), 12) or "USD"
        name = body.name or clean_label(
            await _yahoo("échec de la récupération auprès de Yahoo Finance", ("name", symbol),
                         settings.api.live_cache_ttl_s, lambda: fetch_symbol_name(symbol))
        )

        await run_in_threadpool(ohlcv_cache.add_custom, code, country, symbol, name, unit)
        _custom_specs[code] = IndicatorSpec(code, country, "yfinance", "D", unit, {"symbol": symbol})

    # Rapatriement de l'historique complet : soumis à la même limite de calculs simultanés que
    # le reste des appels Yahoo (il n'y était pas, d'où des rafales possibles via ce seul endpoint).
    try:
        bars = await live.run_limited(lambda: get_daily_bars(symbol, "max", ohlcv_cache))
    except Busy:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _upstream_error("ticker ajouté, mais échec du rapatriement de l'historique", exc)
    return {
        "code": code,
        "country": country,
        "connector": "yfinance",
        "frequency": "D",
        "unit": unit,
        "has_fallback": False,
        "n_obs": len(bars),
        "last_timestamp": bars[-1]["date"] if bars else None,
    }


@app.get("/series/{indicator_code}", response_model=list[SeriesRecord])
async def series(indicator_code: str = Code) -> list[dict]:
    rows = await run_in_threadpool(store.read_series_records, indicator_code)
    if not rows:
        raise HTTPException(404, f"aucune observation pour {indicator_code} (pipeline pas encore lancé ?)")
    return rows


def _panel_payload(code_list: list[str], freq: str) -> dict | None:
    df = store.read_panel(code_list)
    if df.empty:
        return None
    aligned = align_panel(df, target_freq=freq).reset_index()
    aligned["date"] = aligned["date"].astype(str)
    # NaN -> None (JSON valide)
    aligned = aligned.astype(object).where(aligned.notna(), None)
    return {"columns": list(aligned.columns), "rows": aligned.to_dict(orient="records")}


@app.get("/panel", response_model=PanelResponse)
async def panel(
    codes: str = Query(..., max_length=MAX_PANEL_CODES * 101, description="codes d'indicateurs séparés par des virgules"),
    freq: str = Query("M", pattern="^[DWMQA]$"),
) -> dict:
    """Panneau large aligné (une colonne par indicateur), sans biais de look-ahead."""
    code_list = list(dict.fromkeys(c.strip() for c in codes.split(",") if c.strip()))
    if not code_list:
        raise HTTPException(422, "au moins un code est requis")
    if len(code_list) > MAX_PANEL_CODES:
        raise HTTPException(422, f"{MAX_PANEL_CODES} codes au maximum par panneau")
    if any(not re.match(CODE_PATTERN, c) for c in code_list):
        raise HTTPException(422, "code d'indicateur invalide")
    result = await run_in_threadpool(_panel_payload, code_list, freq)
    if result is None:
        raise HTTPException(404, "aucune observation pour ces codes")
    return result


@app.get("/lag-report", response_model=list[LagReportRow])
async def lag_report() -> list[dict]:
    """Écart réel observé entre période décrite et date de publication estimée, par indicateur."""
    report = await run_in_threadpool(store.lag_report)
    return report.to_dict(orient="records")


def _resolve_spec(indicator_code: str) -> IndicatorSpec:
    """Comme `registry.by_code`, mais regarde d'abord les tickers ajoutés à la volée (voir
    `POST /market-activate`) avant le catalogue déclaratif statique."""
    spec = _custom_specs.get(indicator_code)
    if spec is not None:
        return spec
    return by_code(indicator_code)


def _market_spec(indicator_code: str):
    """Spec d'un indicateur de marché (connecteur yfinance), sinon 404 / 400. Les endpoints
    /ohlc, /quote et /chart n'ont de sens que pour ceux-là : les séries macro n'ont ni
    Open/High/Low/Close/Volume, ni cotation."""
    try:
        spec = _resolve_spec(indicator_code)
    except KeyError:
        raise HTTPException(404, f"indicateur inconnu : {indicator_code}")
    if spec.connector != "yfinance":
        raise HTTPException(
            400,
            f"{indicator_code} n'est pas un indicateur de marché (connecteur : {spec.connector}) "
            "— pas de notion de cotation ni d'Open/High/Low/Close/Volume.",
        )
    return spec


async def _yahoo(what: str, key: tuple, ttl: float, coro_factory):
    try:
        return await live.get(key, ttl, coro_factory)
    except (Busy, HTTPException):
        raise
    except YFinanceNotInstalled as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise _upstream_error(what, exc)


@app.get("/ohlc/{indicator_code}", response_model=list[OhlcBar])
async def ohlc(
    indicator_code: str = Code,
    period: str = Query("2y", pattern=PERIOD_PATTERN, description="fenêtre yfinance : 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max"),
) -> list[dict]:
    """Open/High/Low/Close/Volume — servi depuis le cache local (voir ohlcv_cache.py et
    marketdata.py), mis à jour de façon incrémentale auprès de Yahoo Finance (seuls les jours
    manquants depuis la dernière barre déjà en cache sont redemandés). Réservé aux indicateurs
    de marché (connecteur "yfinance")."""
    spec = _market_spec(indicator_code)
    symbol = spec.params["symbol"]
    data = await _yahoo(
        "échec de la récupération auprès de Yahoo Finance",
        ("ohlc", symbol, period), max(settings.api.live_cache_ttl_s, 300),
        lambda: fetch_ohlcv(symbol, period, ohlcv_cache),
    )
    if not data:
        raise HTTPException(404, f"aucune donnée O/H/L/C/V renvoyée pour {indicator_code}")
    return data


@app.get("/quote/{indicator_code}", response_model=QuoteSummary)
async def quote(indicator_code: str = Code) -> dict:
    """Résumé de cotation façon page Euronext — appel direct à Yahoo Finance (cache mémoire
    court), rien n'est stocké (voir quote.py pour ce qui est approximatif ou absent)."""
    spec = _market_spec(indicator_code)
    symbol = spec.params["symbol"]

    async def compute():
        data = await fetch_quote_summary(symbol)
        if data is not None:
            data["currency"] = data.get("currency") or spec.unit
            data["symbol"] = symbol
        return data

    data = await _yahoo("échec de la récupération auprès de Yahoo Finance", ("quote", symbol), settings.api.live_cache_ttl_s, compute)
    if data is None:
        raise HTTPException(404, f"aucune donnée de cotation renvoyée pour {indicator_code}")
    return data


@app.get("/forecast/{indicator_code}", response_model=ForecastResponse)
async def forecast(
    indicator_code: str = Code,
    period: str = Query("5y", pattern=PERIOD_PATTERN, description="fenêtre d'historique utilisée pour l'entraînement, ex. 2y, 5y, max"),
    horizon: str = Query("1w", pattern="^(1w|1m)$", description="'1w' (~1 semaine) ou '1m' (~1 mois, ajoute le contexte macro du pays)"),
    kronos: bool = Query(False, description="ajoute une prévision par le modèle de fondation Kronos auto-hébergé (voir KRONOS_BASE_URL) ; ignoré si non configuré"),
) -> dict:
    """Système de prévision à court/moyen terme (voir app/forecast/) : volatilité GARCH(1,1) +
    modèle XGBoost sur indicateurs techniques — et, à horizon '1m', le contexte macro du pays
    DÉJÀ COLLECTÉ par le pipeline principal — validé en walk-forward, plus le régime de marché
    (HMM) et l'analyse des options. OUTIL DE RECHERCHE, pas un signal de trading. Calcul fait à
    la demande (quelques secondes, hors de la boucle de l'API), mis en cache quelques minutes."""
    spec = _market_spec(indicator_code)
    symbol = spec.params["symbol"]

    async def compute():
        result = await run_forecast(
            symbol, period, horizon=horizon, country=spec.country, store=store,
            use_kronos=kronos, settings=settings, ohlcv_cache=ohlcv_cache,
        )
        result["indicator_code"] = indicator_code
        return result

    try:
        return await live.get(("forecast", symbol, period, horizon, kronos), settings.api.forecast_cache_ttl_s, compute)
    except Busy:
        raise
    except NoMarketData as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise _upstream_error("échec du calcul de prévision", exc)


@app.get("/ensemble/{indicator_code}", response_model=EnsembleResponse)
async def ensemble(
    indicator_code: str = Code,
    horizon: str = Query("1m", pattern="^(1w|1m)$", description="'1w' (~1 semaine) ou '1m' (~1 mois)"),
    method: str = Query("hedge", pattern="^(hedge|naive)$", description="pondération : 'hedge' (poids exponentiels) ou 'naive' (1/erreur récente)"),
) -> dict:
    """Prévision d'ensemble pondérée par backtest walk-forward (voir app/forecast/weighting.py) :
    les 8 modèles court/moyen terme « own-series » + GARCH sont rejoués hors échantillon sur
    l'historique de CE titre, pondérés selon leur CRPS face à une baseline naïve (poids nul s'ils
    ne la battent pas), puis combinés en UN mu/sigma. Calcul LOURD (de l'ordre d'une minute, hors
    de la boucle de l'API), mis en cache comme /forecast. OUTIL DE RECHERCHE, pas un signal de
    trading."""
    spec = _market_spec(indicator_code)
    symbol = spec.params["symbol"]

    async def compute():
        result = await run_weighted_ensemble_forecast(symbol, horizon, ohlcv_cache, method=method)
        result["indicator_code"] = indicator_code
        result["horizon"] = horizon
        return result

    try:
        return await live.get(("ensemble", symbol, horizon, method), settings.api.forecast_cache_ttl_s, compute)
    except Busy:
        raise
    except ValueError as exc:  # historique insuffisant / aucune barre : pas une panne amont
        raise HTTPException(422, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise _upstream_error("échec du calcul de la prévision d'ensemble", exc)


@app.get("/forecast-kronos-enabled", response_model=KronosEnabledResponse)
async def forecast_kronos_enabled() -> dict:
    """Permet au dashboard de masquer l'option Kronos si `KRONOS_BASE_URL` n'est pas configuré,
    sans devoir lancer un calcul de prévision complet juste pour le savoir."""
    return {"enabled": settings.kronos.enabled}


@app.get("/chart/{indicator_code}", response_model=list[OhlcBar])
async def chart(
    indicator_code: str = Code,
    range_key: str = Query("1D", alias="range", pattern=RANGE_PATTERN, description="1D, 5D, 1M, 3M, 1Y, 5Y, YTD ou MAX"),
) -> list[dict]:
    """Barres de prix + volume pour la période demandée (intraday pour 1D/5D). Les plages
    quotidiennes (1M/3M/1Y/5Y/YTD) sont servies par le même cache local que /ohlc et /forecast."""
    spec = _market_spec(indicator_code)
    symbol = spec.params["symbol"]
    data = await _yahoo(
        "échec de la récupération auprès de Yahoo Finance",
        ("chart", symbol, range_key), settings.api.live_cache_ttl_s,
        lambda: fetch_chart(symbol, range_key, ohlcv_cache),
    )
    if not data:
        raise HTTPException(404, f"aucune donnée pour {indicator_code} sur la période {range_key}")
    return data


@app.get("/portfolio/universe", response_model=PortfolioUniverseResponse)
def portfolio_universe() -> dict:
    """Pays et secteurs disponibles pour filtrer l'univers du constructeur de portefeuille —
    à utiliser pour peupler les filtres côté tableau de bord plutôt que de les coder en dur."""
    return {"countries": available_countries(), "sectors": available_sectors()}


def _check_filter_values(name: str, values: list[str]) -> None:
    if len(values) > MAX_FILTER_VALUES:
        raise HTTPException(422, f"trop de valeurs pour « {name} » ({MAX_FILTER_VALUES} maximum)")
    if any(not _FILTER_VALUE_RE.match(v) for v in values):
        raise HTTPException(422, f"valeur invalide pour « {name} »")


@app.get("/portfolio", response_model=PortfolioResponse)
async def portfolio(
    country: list[str] = Query(default=[], description="pays à inclure (vide = tous)"),
    sector: list[str] = Query(default=[], description="secteurs à inclure (vide = tous)"),
    risk: str = Query("modere", pattern="^(faible|modere|eleve)$"),
    target_return: float | None = Query(None, ge=-100, le=1000, description="rendement annuel cible en %, optionnel"),
    max_weight: float = Query(25.0, gt=0, le=100, description="poids maximal par titre, en %"),
    monte_carlo: bool = Query(False, description="active la simulation de Monte Carlo (bootstrap par blocs)"),
    mc_horizon_days: int = Query(252, gt=0, le=2520, description="horizon de simulation, en jours de bourse"),
    mc_n_sims: int = Query(2000, gt=0, le=10000, description="nombre de trajectoires simulées"),
) -> dict:
    """Construit un portefeuille (optimisation moyenne-variance, long seulement) sur l'univers
    d'actions déjà collecté par le pipeline, filtré par pays/secteur. OUTIL D'AIDE À LA RÉFLEXION,
    PAS UN CONSEIL EN INVESTISSEMENT — voir app/portfolio/optimizer.py et le README pour les
    limites. Lit uniquement ce qui est déjà en base, aucun appel réseau.

    `monte_carlo=true` ajoute une évaluation par bootstrap par blocs (`app/portfolio/montecarlo.py`)
    de la distribution des performances futures possibles du portefeuille obtenu."""
    _check_filter_values("country", country)
    _check_filter_values("sector", sector)
    if monte_carlo and mc_n_sims * mc_horizon_days > MAX_MC_CELLS:
        raise HTTPException(
            422, f"simulation trop volumineuse : n_sims × horizon ≤ {MAX_MC_CELLS:,} (réduis l'un des deux)".replace(",", " ")
        )

    def compute():
        return build_portfolio(
            store, countries=country or None, sectors=sector or None,
            risk_level=risk, target_return_pct=target_return, max_weight=max_weight / 100,
            monte_carlo=monte_carlo, mc_horizon_days=mc_horizon_days, mc_n_sims=mc_n_sims,
        )

    try:
        return await live.run_limited(lambda: asyncio.to_thread(compute))
    except Busy:
        raise
    except InfeasibleTarget as exc:
        raise HTTPException(422, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise _upstream_error("échec de la construction du portefeuille", exc)
