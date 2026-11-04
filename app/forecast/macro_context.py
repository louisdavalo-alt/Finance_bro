"""Contexte macro pour le modèle à horizon 1 mois. Contrairement au reste de `app/forecast/`
(appels directs à `yfinance`, rien de stocké), ce module lit exclusivement ce que le pipeline
principal a déjà collecté dans DuckDB — aucun appel réseau ici. Si `run_pipeline.sh` n'a pas
tourné récemment, ou si une source a échoué pour tel pays, le contexte macro peut être absent ou
périmé ; c'est volontairement visible dans la réponse (`macro_codes_used`) plutôt que masqué.

L'alignement passe par `resample.align_panel` (merge_asof sur `release_date`, jamais sur
`timestamp`) — la même discipline anti-look-ahead que pour les panneaux macro du tableau de
bord : une inflation « de janvier » publiée mi-février n'est utilisable comme feature qu'à partir
de sa date de publication réelle, pas de la période qu'elle décrit.
"""
from __future__ import annotations

import pandas as pd

from ..registry import by_code
from ..resample import align_panel

# Codes déjà présents dans `registry.py`, par pays/zone — rien d'inventé : seulement ce qui
# existe réellement dans ce projet aujourd'hui. Les pays absents (GBR, KOR, CAN, POL, MEX...)
# n'ont tout simplement aucune série macro collectée par ce projet à ce jour.
COUNTRY_MACRO_CODES: dict[str, list[str]] = {
    "USA": ["US_FEDFUNDS", "US_DGS10", "US_CPI", "US_UNRATE"],
    "FRA": ["EA_DFR", "EA_YIELD_10Y", "FR_CPI"],
    "DEU": ["EA_DFR", "EA_YIELD_10Y", "DE_HICP_WB"],
    "ITA": ["EA_DFR", "EA_YIELD_10Y"],
    "EA": ["EA_DFR", "EA_YIELD_10Y"],
    "JPN": ["JP_POLICY_RATE", "JP_JGB_10Y", "JP_CPI_NATIONAL"],
    "IND": ["IN_REPO_RATE", "IN_CPI", "IN_GDP"],
    "CHN": ["CN_EXPORTS"],  # le seul code CHN avec une donnée un tant soit peu régulière (repli Banque mondiale, annuel) ; signal faible
}

MACRO_CHANGE_WINDOW_DAYS = 63  # ~3 mois de bourse : variation récente de chaque série macro


def macro_codes_for_country(country: str) -> list[str]:
    return list(COUNTRY_MACRO_CODES.get(country, []))


def _resolve_codes(codes: list[str]) -> list[str]:
    """Un indicateur dont le fichier manuel n'a jamais été déposé (ex. `IN_REPO_RATE`, en
    attente d'un export RBI) peut n'exister en base que sous le code de son REPLI (ex.
    `IN_REPO_RATE_WB`) plutôt que sous son propre code (voir app/registry.py, champ `fallback`).
    On interroge donc le code déclaré ET son repli, quand il existe."""
    resolved = list(codes)
    for code in codes:
        try:
            spec = by_code(code)
        except KeyError:
            continue
        if spec.fallback is not None:
            resolved.append(spec.fallback.code)
    return resolved


def build_macro_features(store, country: str, dates: pd.DatetimeIndex) -> tuple[pd.DataFrame, list[str]]:
    """Renvoie `(macro_df, codes_used)` : `macro_df` est indexé exactement sur `dates` (les
    dates du modèle de prix), avec une colonne « niveau » et une colonne « variation sur
    `MACRO_CHANGE_WINDOW_DAYS` jours » par série macro réellement disponible pour `country`.
    `codes_used` liste les codes qui ont effectivement fourni des données (pour affichage/
    transparence) — DataFrame et liste vides si aucune série macro n'est disponible pour ce
    pays, ou si aucune des séries candidates n'a de données en base."""
    declared = macro_codes_for_country(country)
    if not declared:
        return pd.DataFrame(index=dates), []

    long_df = store.read_panel(_resolve_codes(declared))
    if long_df.empty:
        return pd.DataFrame(index=dates), []

    panel = align_panel(long_df, target_freq="D", start=dates.min().strftime("%Y-%m-%d"), end=dates.max().strftime("%Y-%m-%d"))
    if panel.empty:
        return pd.DataFrame(index=dates), []

    # Un code et son repli ne sont (presque) jamais tous les deux non vides en même temps : on
    # les fusionne sous le nom du code déclaré plutôt que de garder deux colonnes creuses.
    merged: dict[str, pd.Series] = {}
    for code in declared:
        try:
            spec = by_code(code)
        except KeyError:
            continue
        series = panel[code] if code in panel.columns else pd.Series(index=panel.index, dtype=float)
        if spec.fallback is not None and spec.fallback.code in panel.columns:
            series = series.fillna(panel[spec.fallback.code])
        if series.notna().any():
            merged[f"macro_{code}"] = series

    if not merged:
        return pd.DataFrame(index=dates), []

    macro = pd.DataFrame(merged)
    for col in list(macro.columns):
        macro[f"{col}_chg_63d"] = macro[col].diff(MACRO_CHANGE_WINDOW_DAYS)

    # Report sur le calendrier exact des dates de prix demandées : réindexer sur l'union puis
    # ne garder QUE les dates demandées, avec un simple "forward fill" — jamais de "backward
    # fill", qui ferait remonter une valeur future vers le passé.
    macro = macro.reindex(macro.index.union(dates)).ffill().reindex(dates)
    return macro, [c for c in declared if f"macro_{c}" in merged]
