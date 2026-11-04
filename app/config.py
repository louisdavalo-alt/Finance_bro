"""Configuration : variables d'environnement, un bloc par source de données.

Chaque source déclare son URL de base et ses limites de requêtes (rate limit),
réglables sans toucher au code. Les clés manquantes désactivent simplement
la source concernée (voir `registry.py` : `enabled_sources()`).
"""
from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .security import register_secret

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("config")


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    _warn_if_world_readable(path)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _warn_if_world_readable(path: Path) -> None:
    """`.env` contient des clés API : on signale (sans bloquer) s'il est lisible par les autres
    utilisateurs de la machine. Correctif : `chmod 600 .env`."""
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if os.name == "posix" and mode & (stat.S_IRGRP | stat.S_IROTH):
        log.warning("%s est lisible par d'autres utilisateurs (mode %o) : exécute `chmod 600 %s`", path, stat.S_IMODE(mode), path)


def _https_url(name: str, default: str) -> str:
    """URL de base d'une source réseau : HTTPS obligatoire (les clés API transitent dans la
    requête). `ALLOW_INSECURE_HTTP=true` lève la contrainte, pour un proxy local de test."""
    value = _str(name, default)
    scheme = urlsplit(value).scheme.lower()
    if scheme != "https" and _str("ALLOW_INSECURE_HTTP", "false").lower() != "true":
        raise ValueError(f"{name}={value!r} : seules les URL https:// sont acceptées (ALLOW_INSECURE_HTTP=true pour forcer)")
    return value


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _kronos_url(value: str) -> str:
    """`KRONOS_BASE_URL` reçoit l'historique OHLCV en POST : schéma http(s) obligatoire (un
    `file://` ou une valeur mal formée est refusé au démarrage), et avertissement si le trafic
    part en clair vers une autre machine que celle-ci."""
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError(f"KRONOS_BASE_URL={value!r} : URL http(s):// attendue")
    if parts.username or parts.password:
        raise ValueError("KRONOS_BASE_URL ne doit pas contenir d'identifiants (user:pass@)")
    if parts.scheme.lower() == "http" and parts.hostname not in _LOOPBACK_HOSTS:
        log.warning("KRONOS_BASE_URL en HTTP vers %s : trafic non chiffré sur le réseau", parts.hostname)
    return value


def _bool(name: str, default: bool) -> bool:
    return _str(name, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


def _str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class RateLimit:
    """Un jeton toutes les `per_seconds / max_calls` secondes, avec une réserve de `max_calls`."""

    max_calls: int
    per_seconds: float


@dataclass(frozen=True)
class SourceConfig:
    name: str
    base_url: str
    rate_limit: RateLimit
    enabled: bool
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ApiSettings:
    """Réglages de l'API de consultation (serve.py / api.py)."""

    host: str = "127.0.0.1"
    port: int = 8100
    username: str = ""  # API_USERNAME + API_PASSWORD : active l'authentification HTTP Basic
    password: str = ""
    allowed_hosts: tuple = ("127.0.0.1", "localhost", "::1", "[::1]", "testserver")
    enable_docs: bool = True  # /docs, /redoc, /openapi.json
    max_concurrent_jobs: int = 2  # calculs lourds simultanés (prévision, portefeuille, Yahoo)
    live_cache_ttl_s: int = 60  # cache mémoire des réponses Yahoo (cotation, graphiques)
    forecast_cache_ttl_s: int = 900
    auth_max_failures: int = 10  # échecs d'authentification tolérés par IP et par fenêtre...
    auth_failure_window_s: int = 300  # ... avant blocage temporaire (429)
    max_custom_indicators: int = 200  # tickers ajoutés via POST /market-activate (quota disque)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.username and self.password)


@dataclass(frozen=True)
class KronosSettings:
    """Service Kronos auto-hébergé (modèle de fondation pour séries financières, voir
    app/forecast/kronos_client.py) : un point d'accès `/api/forecast` dédié, ajouté au fork
    Flask de l'utilisateur (webui/app.py), distinct de l'UI existante. Désactivé si
    `KRONOS_BASE_URL` est vide — le dashboard masque alors simplement l'option."""

    base_url: str = ""
    timeout_s: float = 180.0  # inférence CPU sur Kronos-base : plus lent qu'un simple appel réseau
    lookback: int = 400
    pred_len: int = 120
    temperature: float = 1.0
    top_p: float = 0.9
    sample_count: int = 1

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cache_ttl_s: dict  # par fréquence : D/M/Q/A -> secondes
    http_timeout_s: float
    http_max_retries: int
    sources: dict  # nom -> SourceConfig
    api: ApiSettings = field(default_factory=ApiSettings)
    kronos: KronosSettings = field(default_factory=KronosSettings)

    def source(self, name: str) -> SourceConfig:
        return self.sources[name]


def load_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    data_dir = Path(_str("DATA_DIR", str(ROOT / "data")))

    sources = {
        # --- États-Unis --------------------------------------------------
        "fred": SourceConfig(
            name="fred",
            base_url=_https_url("FRED_BASE_URL", "https://api.stlouisfed.org/fred"),
            rate_limit=RateLimit(_int("FRED_RATE_MAX", 100), _float("FRED_RATE_WINDOW", 60)),
            enabled=bool(_str("FRED_API_KEY")),
            extra={"api_key": _str("FRED_API_KEY")},
        ),
        # --- Zone euro (BCE) ----------------------------------------------
        "ecb": SourceConfig(
            name="ecb",
            base_url=_https_url("ECB_BASE_URL", "https://data-api.ecb.europa.eu/service"),
            rate_limit=RateLimit(_int("ECB_RATE_MAX", 20), _float("ECB_RATE_WINDOW", 10)),
            enabled=True,  # aucune clé nécessaire
        ),
        # --- FMI — nouvelle API SDMX 3.0 (remplace l'INSEE pour les indicateurs français) -----
        # Clé gratuite via le portail développeur du FMI (https://api.imf.org), transmise en
        # en-tête Ocp-Apim-Subscription-Key (spec confirmée depuis le fichier OpenAPI officiel).
        "imf": SourceConfig(
            name="imf",
            base_url=_https_url("IMF_BASE_URL", "https://api.imf.org/external/sdmx/3.0"),
            rate_limit=RateLimit(_int("IMF_RATE_MAX", 30), _float("IMF_RATE_WINDOW", 60)),
            enabled=bool(_str("IMF_API_KEY")),
            extra={"api_key": _str("IMF_API_KEY")},
        ),
        # --- Japon : Bureau métropolitain des statistiques de Tokyo (CPI Tokyo) --------------
        # e-Stat n'a pas fonctionné pour cette table (statsDataId deviné invalide, "STATUS: 300"
        # vérifié le 26/09/2026) : fichier CSV du portail métropolitain déposé manuellement.
        "tmi_tokyo": SourceConfig(
            name="tmi_tokyo",
            base_url=_str("MANUAL_DIR", str(data_dir / "manual")) + "/tmi",
            rate_limit=RateLimit(1000, 1.0),
            enabled=True,
        ),
        # yfinance n'est pas une API officielle (Yahoo a fermé la sienne en 2017) : c'est une
        # bibliothèque qui imite un navigateur pour accéder aux points d'accès internes du site.
        # Sert ici à compléter les indicateurs macro avec des données de marché (indices
        # boursiers, taux de change) là où aucune agence statistique n'en publie l'équivalent —
        # ce n'est PAS un substitut aux séries officielles (IPI, HICP, balance commerciale, etc.)
        # retirées avec Destatis (voir ARCHITECTURE.md).
        "yfinance": SourceConfig(
            name="yfinance",
            base_url="",  # non pertinent : yfinance gère son propre réseau (curl_cffi)
            rate_limit=RateLimit(_int("YFINANCE_RATE_MAX", 30), _float("YFINANCE_RATE_WINDOW", 60)),
            enabled=_str("YFINANCE_ENABLED", "true").lower() != "false",
        ),
        # --- Japon : e-Stat -------------------------------------------------
        "estat": SourceConfig(
            name="estat",
            base_url=_https_url("ESTAT_BASE_URL", "https://api.e-stat.go.jp/rest/3.0/app/json"),
            rate_limit=RateLimit(_int("ESTAT_RATE_MAX", 60), _float("ESTAT_RATE_WINDOW", 60)),
            enabled=bool(_str("ESTAT_APP_ID")),
            extra={"app_id": _str("ESTAT_APP_ID")},
        ),
        # --- Japon : Banque du Japon -----------------------------------------
        # L'API REST documentée renvoie systématiquement "Invalid input parameters" en usage
        # réel (vérifié le 25/09/2026), y compris avec un code de série confirmé par ailleurs.
        # Connecteur basé sur les exports CSV téléchargés manuellement (voir
        # connectors/boj.py et data/manual/boj/README.md), même principe que RBI/MOSPI.
        "boj": SourceConfig(
            name="boj",
            base_url=_str("MANUAL_DIR", str(data_dir / "manual")),
            rate_limit=RateLimit(1000, 1.0),
            enabled=True,
        ),
        # --- Chine : Bureau national des statistiques ------------------------
        # Endpoint interne non documenté officiellement (utilisé par plusieurs
        # bibliothèques tierces), donc marqué "best effort" avec repli automatique
        # vers la Banque mondiale en cas d'échec (voir connectors/nbs_china.py).
        "nbs_china": SourceConfig(
            name="nbs_china",
            base_url=_https_url("NBS_CHINA_BASE_URL", "https://data.stats.gov.cn/easyquery.htm"),
            rate_limit=RateLimit(_int("NBS_RATE_MAX", 6), _float("NBS_RATE_WINDOW", 60)),
            enabled=_str("NBS_CHINA_ENABLED", "true").lower() != "false",
        ),
        # --- Banque mondiale (repli universel, notamment Chine/Inde) ----------
        "worldbank": SourceConfig(
            name="worldbank",
            base_url=_https_url("WORLDBANK_BASE_URL", "https://api.worldbank.org/v2"),
            rate_limit=RateLimit(_int("WB_RATE_MAX", 30), _float("WB_RATE_WINDOW", 60)),
            enabled=True,
        ),
        # --- Inde : RBI (DBIE) et MOSPI ---------------------------------------
        # Ni la RBI ni le MOSPI n'exposent d'API JSON publique stable : ce
        # connecteur lit des fichiers CSV que tu exportes toi-même depuis DBIE/MOSPI
        # dans data/manual/. Voir connectors/manual_csv.py et le README.
        "manual": SourceConfig(
            name="manual",
            base_url=_str("MANUAL_DIR", str(data_dir / "manual")),
            rate_limit=RateLimit(1000, 1.0),
            enabled=True,
        ),
    }

    for secret_name in ("FRED_API_KEY", "IMF_API_KEY", "ESTAT_APP_ID", "API_PASSWORD"):
        register_secret(_str(secret_name))

    default_hosts = ApiSettings.allowed_hosts
    extra_hosts = tuple(h.strip() for h in _str("API_ALLOWED_HOSTS").split(",") if h.strip())
    api = ApiSettings(
        host=_str("HOST", "127.0.0.1"),
        port=_int("PORT", 8100),
        username=_str("API_USERNAME"),
        password=_str("API_PASSWORD"),
        allowed_hosts=default_hosts + extra_hosts,
        enable_docs=_bool("API_ENABLE_DOCS", True),
        max_concurrent_jobs=max(1, _int("API_MAX_CONCURRENT_JOBS", 2)),
        live_cache_ttl_s=max(0, _int("API_LIVE_CACHE_TTL_S", 60)),
        forecast_cache_ttl_s=max(0, _int("API_FORECAST_CACHE_TTL_S", 900)),
        auth_max_failures=max(1, _int("API_AUTH_MAX_FAILURES", 10)),
        auth_failure_window_s=max(1, _int("API_AUTH_FAILURE_WINDOW_S", 300)),
        max_custom_indicators=max(0, _int("API_MAX_CUSTOM_INDICATORS", 200)),
    )

    kronos = KronosSettings(
        base_url=_kronos_url(_str("KRONOS_BASE_URL", "")),
        timeout_s=_float("KRONOS_TIMEOUT_S", 180.0),
        lookback=_int("KRONOS_LOOKBACK", 400),
        pred_len=_int("KRONOS_PRED_LEN", 120),
        temperature=_float("KRONOS_TEMPERATURE", 1.0),
        top_p=_float("KRONOS_TOP_P", 0.9),
        sample_count=_int("KRONOS_SAMPLE_COUNT", 1),
    )

    return Settings(
        api=api,
        kronos=kronos,
        data_dir=data_dir,
        cache_ttl_s={
            "D": _int("CACHE_TTL_D", 6 * 3600),
            "M": _int("CACHE_TTL_M", 24 * 3600),
            "Q": _int("CACHE_TTL_Q", 3 * 24 * 3600),
            "A": _int("CACHE_TTL_A", 7 * 24 * 3600),
        },
        http_timeout_s=_float("HTTP_TIMEOUT_S", 20.0),
        http_max_retries=_int("HTTP_MAX_RETRIES", 4),
        sources=sources,
    )
