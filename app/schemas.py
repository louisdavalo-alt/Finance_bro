"""Modèles de réponse (Pydantic) de l'API de consultation.

Pourquoi ce module existe : les endpoints de `api.py` renvoyaient des `dict`/`list[dict]` nus
(`-> dict`), ce qui fonctionne mais laisse le contrat de chaque endpoint implicite — seul le code
Python qui les construit en fait foi. En leur donnant un `response_model` explicite :

- FastAPI valide CHAQUE réponse avant de l'envoyer (un champ manquant ou mal typé devient une
  erreur serveur détectée tout de suite, pas un bug découvert côté client des mois plus tard) ;
- `/openapi.json` décrit exactement la forme de chaque réponse, avec les champs optionnels
  explicites (`| None`) — ce qui permet de générer un client TypeScript fidèle pour le futur
  frontend (`openapi-typescript`), au lieu de deviner les types à la main ;
- les docs interactives (`/docs`) deviennent lisibles comme référence, pas seulement comme
  bac à sable de test.

Ces modèles DÉCRIVENT les dict déjà renvoyés par `forecast/`, `portfolio/`, `ohlc.py`, `quote.py`,
etc. — aucun de ces modules n'est modifié ici, uniquement la couche de sérialisation HTTP.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# Symbole Yahoo Finance : lettres, chiffres et les seuls caractères que Yahoo utilise réellement
# (^GSPC, EURUSD=X, BRK-B, 0700.HK, GC=F). Partagé avec les paramètres de chemin de `api.py`.
SYMBOL_PATTERN = r"^[A-Za-z0-9^=._\-]{1,20}$"
CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,99}$"
COUNTRY_PATTERN = r"^[A-Za-z]{2,6}$"  # ISO 3166 alpha-2/3, EA, GLOBAL


class HealthResponse(BaseModel):
    ok: bool


class IndicatorInfo(BaseModel):
    code: str
    country: str
    connector: str
    frequency: str
    unit: str
    has_fallback: bool
    n_obs: int
    last_timestamp: str | None = None


class SeriesRecord(BaseModel):
    timestamp: str | None = None
    country: str | None = None
    indicator_code: str | None = None
    value: float | None = None
    frequency: str | None = None
    unit: str | None = None
    source: str | None = None
    release_date: str | None = None
    ingested_at: str | None = None


class PanelResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]  # une colonne par indicateur demandé : forme dynamique


class LagReportRow(BaseModel):
    indicator_code: str
    median_lag_days: float | None = None
    n_obs: int


class OhlcBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class QuoteSummary(BaseModel):
    intraday: bool
    last: float
    last_time: str
    open: float
    high: float
    high_time: str | None = None
    low: float
    low_time: str | None = None
    volume: float | None = None
    turnover: float | None = None
    vwap: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    week52_high: float
    week52_low: float
    market_cap: float | None = None
    currency: str | None = None
    symbol: str


class KronosEnabledResponse(BaseModel):
    enabled: bool


# --------------------------------------------------------------------------- #
# Recherche libre de tickers hors catalogue (voir app/market_search.py)
# --------------------------------------------------------------------------- #
class MarketSearchResult(BaseModel):
    symbol: str
    name: str
    exchange: str | None = None
    type: str | None = None
    already_tracked: bool = False
    code: str | None = None  # code existant dans le catalogue, si already_tracked


class MarketLookupResult(BaseModel):
    symbol: str
    name: str | None = None
    last: float | None = None
    currency: str | None = None
    already_tracked: bool = False
    code: str | None = None


class MarketActivateRequest(BaseModel):
    """Corps de `POST /market-activate`. Tous les champs sont PERSISTÉS puis réaffichés dans le
    tableau de bord : ils sont donc strictement validés ici (un `country` libre permettait
    d'injecter du HTML stocké dans les filtres du tableau de bord)."""

    model_config = {"extra": "forbid"}

    symbol: str = Field(..., pattern=SYMBOL_PATTERN)
    code: str | None = Field(None, pattern=CODE_PATTERN)
    country: str | None = Field(None, pattern=COUNTRY_PATTERN)
    name: str | None = Field(None, max_length=120)  # nom déjà connu (ex. résultat de /market-search) ; sinon redemandé

    @field_validator("symbol", mode="before")
    @classmethod
    def _strip_symbol(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v):
        return v.upper() if v else v

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v):
        return clean_label(v)


def clean_label(v: str | None, max_len: int = 120) -> str | None:
    """Libellé affichable : caractères de contrôle retirés, espaces normalisés, longueur bornée."""
    if v is None:
        return None
    v = " ".join("".join(ch for ch in str(v) if ch.isprintable()).split())[:max_len]
    return v or None


# --------------------------------------------------------------------------- #
# Prévision (voir app/forecast/)
# --------------------------------------------------------------------------- #
class GarchResult(BaseModel):
    daily_vol_forecast_pct: list[float]
    weekly_vol_forecast_pct: float
    current_conditional_vol_annualized_pct: float
    n_obs: int


class MlForecastResult(BaseModel):
    as_of_date: str
    horizon_days: int
    predicted_return_pct: float
    feature_importances: dict[str, float]
    feature_values: dict[str, float | None]


class MlBacktestFold(BaseModel):
    n_train: int
    n_test: int
    mae: float
    direction_accuracy: float
    naive_up_rate: float


class MlBacktestResult(BaseModel):
    folds: list[MlBacktestFold]
    mean_direction_accuracy: float
    mean_mae_pct: float


class RegimeStateSummary(BaseModel):
    mean_daily_return_pct: float
    std_daily_return_pct: float
    n_days_observed: int


class RegimeSequencePoint(BaseModel):
    date: str
    regime: str


class RegimeResult(BaseModel):
    n_states: int
    current_regime: str
    current_regime_since: str
    state_summary: dict[str, RegimeStateSummary]
    transition_matrix: list[list[float]]
    recent_regime_sequence: list[RegimeSequencePoint]
    n_obs: int


class OptionsPcr(BaseModel):
    pcr_volume: float | None = None
    pcr_open_interest: float | None = None
    call_volume: float
    put_volume: float
    call_open_interest: float
    put_open_interest: float


class OptionsMaxPain(BaseModel):
    max_pain_strike: float
    strikes: list[float]
    total_payout_by_strike: list[float]


class OptionsIvSkew(BaseModel):
    otm_put_iv_pct: float
    otm_call_iv_pct: float
    skew_pct_points: float
    atm_call_iv_pct: float | None = None
    atm_put_iv_pct: float | None = None


class OptionsResult(BaseModel):
    expiration_used: str
    available_expirations: list[str]
    spot_price: float | None = None
    pcr: OptionsPcr
    max_pain: OptionsMaxPain
    iv_skew: OptionsIvSkew | None = None


class KronosPredictedBar(BaseModel):
    open: float
    high: float
    low: float
    close: float


class KronosResult(BaseModel):
    timestamps: list[str]
    predictions: list[KronosPredictedBar]
    lookback: int
    pred_len: int
    last_known_close: float


class ShortTermModelResult(BaseModel):
    """Résultat d'un des modèles « court terme » non liés à une IA (`app/forecast/short_term/`) :
    `mu_pct`/`sigma_pct` sont le rendement moyen et l'écart-type prévus sur l'horizon demandé, en
    %. `diagnostics` est spécifique à chaque modèle (voir leur docstring) — affiché tel quel, pas
    de contrat de forme au-delà de « c'est un dict JSON-sérialisable »."""

    mu_pct: float
    sigma_pct: float
    quantiles_pct: dict[str, float] = {}
    diagnostics: dict[str, Any] = {}


class ForecastResponse(BaseModel):
    symbol: str
    horizon: str
    n_bars: int
    history_start: str
    history_end: str
    garch: GarchResult | None = None
    garch_error: str | None = None
    ml_forecast: MlForecastResult | None = None
    ml_backtest: MlBacktestResult | None = None
    ml_error: str | None = None
    macro_codes_used: list[str] = []
    regime: RegimeResult | None = None
    regime_error: str | None = None
    short_term_models: dict[str, ShortTermModelResult] = {}
    short_term_errors: dict[str, str] = {}
    # Même forme que les modèles court terme (`ShortTermModelResult`) ; type réutilisé tel quel,
    # voir `app/forecast/medium_term/` — ne tournent qu'à horizon "1m" (dicts vides sinon).
    medium_term_models: dict[str, ShortTermModelResult] = {}
    medium_term_errors: dict[str, str] = {}
    # Idem, voir `app/forecast/long_term/` — ne tournent qu'à horizon "1m" (dicts vides sinon).
    long_term_models: dict[str, ShortTermModelResult] = {}
    long_term_errors: dict[str, str] = {}
    options: OptionsResult | None = None
    options_error: str | None = None
    kronos: KronosResult | None = None
    kronos_error: str | None = None
    indicator_code: str


# --------------------------------------------------------------------------- #
# Prévision d'ensemble pondérée par backtest (voir app/forecast/weighting.py)
# --------------------------------------------------------------------------- #
class EnsembleCombined(BaseModel):
    mu_pct: float
    sigma_pct: float
    weights_used: dict[str, float]  # modèles à poids > 0 effectivement mélangés


class EnsembleModelMetrics(BaseModel):
    """Métriques walk-forward d'un modèle (voir `backtest.py`). `None` = non applicable (ex.
    `hit_ratio`/`ic` d'un modèle non directionnel, `sharpe` d'un P&L constamment nul)."""

    n_points: int
    mae_pct: float
    crps_pct: float
    hit_ratio: float | None = None
    n_bets: int
    ic: float | None = None
    sharpe: float | None = None
    deflated_sharpe: float | None = None


class EnsembleResponse(BaseModel):
    indicator_code: str
    horizon: str
    method: str
    combined: EnsembleCombined
    weights: dict[str, float]
    backtest_n_test_points: int
    backtest_models: dict[str, EnsembleModelMetrics]
    backtest_errors: dict[str, str] = {}


# --------------------------------------------------------------------------- #
# Portefeuille (voir app/portfolio/)
# --------------------------------------------------------------------------- #
class PortfolioUniverseResponse(BaseModel):
    countries: list[str]
    sectors: list[str]


class PortfolioHolding(BaseModel):
    code: str
    country: str
    sector: str
    weight_pct: float
    expected_return_pct: float
    volatility_pct: float


class MonteCarloResult(BaseModel):
    n_sims: int
    horizon_days: int
    block_size: int
    n_history_days: int
    percentiles_final_return_pct: dict[str, float]
    probability_of_loss_pct: float
    var_95_pct: float
    cvar_95_pct: float
    fan_chart_pct: dict[str, list[float]]


class PortfolioResponse(BaseModel):
    holdings: list[PortfolioHolding]
    n_candidates: int
    n_used: int
    excluded_for_insufficient_history: list[str]
    risk_level: str
    target_return_pct: float | None = None
    max_weight_pct: float
    monte_carlo: MonteCarloResult | None = None
    monte_carlo_error: str | None = None
    expected_return_pct: float
    expected_vol_pct: float
    return_over_vol: float | None = None
