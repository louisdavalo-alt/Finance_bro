"""Client pour le service Kronos auto-hébergé (modèle de fondation pour séries financières,
https://github.com/shiyu-coder/Kronos, déployé par l'utilisateur sur son propre serveur).

Appelle un point d'accès dédié, `POST /api/forecast`, à ajouter au fork Flask de l'utilisateur
(`webui/app.py` — voir `deploy/kronos_patch.md` pour le correctif exact et pourquoi). Ce point
d'accès est volontairement SÉPARÉ de celui de l'UI web existante (`/api/predict`, qui dépend d'un
état posé au préalable par `/api/load-data` puis `/api/load-model` — un enchaînement conçu pour un
humain qui clique, pas pour un appel machine-à-machine) : il reçoit un CSV brut dans le corps de la
requête et renvoie directement la prévision, en réutilisant le modèle déjà chargé en mémoire côté
serveur Kronos.

Comme le reste de ce projet, rien n'est stocké ici : les barres sont récupérées à la demande
(`forecast/pipeline.py`, qui appelle déjà Yahoo Finance pour GARCH/XGBoost), ce module se contente
de les reformater et de les envoyer.

Format attendu par Kronos (`KronosTokenizer`/`KronosPredictor`, voir le README HuggingFace du
modèle) : colonnes `open, high, low, close` en minuscules, plus une colonne `timestamps` — Kronos
utilise LES `lookback` DERNIÈRES lignes du CSV envoyé comme contexte, donc le CSV ne doit contenir
AUCUNE barre postérieure à la date de prévision (sinon la réponse serait un backtest, pas une
vraie prévision du futur)."""
from __future__ import annotations

import logging

import httpx
import pandas as pd

from ..config import KronosSettings  # noqa: F401 - réexporté pour les tests/typing
from ..security import redact_url

log = logging.getLogger("forecast.kronos")

REQUIRED_COLUMNS = ("Open", "High", "Low", "Close")


class KronosUnavailable(RuntimeError):
    """Le service Kronos est configuré mais n'a pas répondu correctement (réseau, modèle non
    chargé côté serveur, historique insuffisant...)."""


class KronosNotConfigured(KronosUnavailable):
    """`KRONOS_BASE_URL` n'est pas défini : fonctionnalité désactivée, le dashboard masque
    simplement l'option plutôt que d'afficher une erreur."""


def _build_csv(bars: pd.DataFrame, lookback: int) -> bytes:
    """Les `lookback` dernières barres exploitables, colonnes renommées en minuscules + une
    colonne `timestamps` — le format que lit `load_data_file` côté serveur Kronos."""
    missing = [c for c in REQUIRED_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(f"colonnes manquantes dans les barres OHLCV : {missing}")

    tail = bars[list(REQUIRED_COLUMNS)].dropna().tail(lookback)
    if len(tail) < lookback:
        raise ValueError(
            f"historique insuffisant pour Kronos : {len(tail)} barres exploitables, "
            f"{lookback} (lookback) requises — essaie une période plus longue"
        )

    out = tail.rename(columns=str.lower).reset_index()
    out = out.rename(columns={out.columns[0]: "timestamps"})
    return out.to_csv(index=False).encode("utf-8")


async def kronos_forecast(bars: pd.DataFrame, settings) -> dict:
    """Envoie les dernières barres à Kronos et renvoie sa prévision OHLC jour par jour (brute,
    telle que renvoyée par `/api/forecast` — mise en forme laissée à l'appelant).

    Lève `KronosNotConfigured` si `KRONOS_BASE_URL` est vide, `KronosUnavailable` pour toute autre
    erreur (réseau, HTTP, historique insuffisant)."""
    ks: KronosSettings = settings.kronos
    if not ks.enabled:
        raise KronosNotConfigured("KRONOS_BASE_URL non défini")

    try:
        csv_bytes = _build_csv(bars, ks.lookback)
    except ValueError as exc:
        raise KronosUnavailable(str(exc)) from exc

    url = f"{ks.base_url.rstrip('/')}/api/forecast"
    params = {
        "lookback": ks.lookback,
        "pred_len": ks.pred_len,
        "temperature": ks.temperature,
        "top_p": ks.top_p,
        "sample_count": ks.sample_count,
    }
    try:
        async with httpx.AsyncClient(timeout=ks.timeout_s) as client:
            resp = await client.post(url, params=params, content=csv_bytes, headers={"Content-Type": "text/csv"})
    except httpx.TransportError as exc:
        raise KronosUnavailable(f"{type(exc).__name__} sur {redact_url(url)}") from exc

    if resp.is_error:
        detail = ""
        try:
            detail = f" : {resp.json().get('error', '')}"
        except Exception:  # noqa: BLE001 - réponse non JSON, tant pis pour le détail
            pass
        raise KronosUnavailable(f"{resp.status_code} sur {redact_url(url)}{detail}")

    return resp.json()
