"""Modèle XGBoost pour la prévision du rendement à `horizon_days` jours de bourse, validé en
« walk-forward » (`TimeSeriesSplit`) : chaque pli d'entraînement ne voit que des dates
strictement antérieures à son pli de test, avec un écart (`gap`) de `horizon_days` entre les
deux pour qu'aucune ligne d'entraînement ne « voie » une partie de la fenêtre de rendement-cible
d'une ligne de test — la même discipline anti-look-ahead que `resample.py`, appliquée ici à la
validation croisée plutôt qu'à l'alignement de séries macro. Vérifié par
`tests/test_forecast.py::test_backtest_on_pure_noise_is_close_to_random` : sur des rendements
purement aléatoires, la précision directionnelle mesurée doit rester proche de 50 % — un modèle
qui « prédirait » du bruit avec un bon score signalerait presque toujours une fuite de données.

`feature_columns` est paramétrable (par défaut `features.FEATURE_COLUMNS`, les seuls indicateurs
techniques) pour permettre au modèle à horizon 1 mois (`pipeline.py`) d'y ajouter le contexte
macro (`macro_context.py`) sans dupliquer cette logique de validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from .features import FEATURE_COLUMNS

HORIZON_WEEK_DAYS = 5   # ~1 semaine de bourse
HORIZON_MONTH_DAYS = 21  # ~1 mois de bourse (21 jours ouvrés)


class XGBoostNotInstalled(ImportError):
    pass


def _xgb_regressor():
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise XGBoostNotInstalled("le paquet 'xgboost' n'est pas installé : `pip install xgboost`") from exc
    return XGBRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=0,
    )


def build_dataset(feat: pd.DataFrame, horizon_days: int = HORIZON_WEEK_DAYS) -> pd.DataFrame:
    """Ajoute la colonne cible `target_fwd_return` = rendement entre le jour t et
    t+`horizon_days`. Les `horizon_days` dernières lignes n'ont pas de cible connue (NaN) : c'est
    normal, ce sont elles qui serviront à produire la vraie prévision dans `fit_final_and_predict`."""
    df = feat.copy()
    df["target_fwd_return"] = df["Close"].shift(-horizon_days) / df["Close"] - 1
    return df


def walk_forward_backtest(
    df: pd.DataFrame, horizon_days: int = HORIZON_WEEK_DAYS,
    feature_columns: list[str] = FEATURE_COLUMNS, n_splits: int = 5,
) -> dict:
    """Validation honnête : entraîne et teste sur des fenêtres temporelles disjointes et
    ordonnées, jamais un mélange aléatoire (qui fuiterait de l'information future dans
    l'entraînement à cause de l'autocorrélation des séries financières)."""
    valid = df.dropna(subset=feature_columns + ["target_fwd_return"])
    min_rows = (n_splits + 1) * 20
    if len(valid) < min_rows:
        raise ValueError(f"pas assez de lignes exploitables ({len(valid)}, {min_rows} recommandées pour {n_splits} plis)")

    X, y = valid[feature_columns].values, valid["target_fwd_return"].values
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=horizon_days)

    folds = []
    for train_idx, test_idx in tscv.split(X):
        model = _xgb_regressor()
        model.fit(X[train_idx], y[train_idx])
        pred = model.predict(X[test_idx])
        actual = y[test_idx]
        folds.append({
            "n_train": int(len(train_idx)), "n_test": int(len(test_idx)),
            "mae": float(np.mean(np.abs(pred - actual))),
            "direction_accuracy": float(np.mean(np.sign(pred) == np.sign(actual))),
            "naive_up_rate": float(np.mean(actual > 0)),  # taux de hausse réel sur ce pli : la référence à battre
        })

    return {
        "folds": folds,
        "mean_direction_accuracy": float(np.mean([f["direction_accuracy"] for f in folds])),
        "mean_mae_pct": float(np.mean([f["mae"] for f in folds]) * 100),
    }


def fit_final_and_predict(
    df: pd.DataFrame, horizon_days: int = HORIZON_WEEK_DAYS, feature_columns: list[str] = FEATURE_COLUMNS,
) -> dict:
    """Réentraîne sur TOUT l'historique disponible (plus de raison de garder un pli de test une
    fois la fiabilité mesurée par `walk_forward_backtest`) et prédit le rendement à
    `horizon_days` jours à partir de la toute dernière ligne de features disponible."""
    valid = df.dropna(subset=feature_columns + ["target_fwd_return"])
    model = _xgb_regressor()
    model.fit(valid[feature_columns].values, valid["target_fwd_return"].values)

    latest_rows = df.dropna(subset=feature_columns)
    if latest_rows.empty:
        raise ValueError("aucune ligne récente n'a toutes les features renseignées")
    latest = latest_rows.iloc[[-1]]
    pred_return = float(model.predict(latest[feature_columns].values)[0])

    idx = latest.index[0]
    as_of = idx.date().isoformat() if hasattr(idx, "date") else str(idx)
    importances = dict(zip(feature_columns, (float(v) for v in model.feature_importances_)))
    feature_values = {k: (None if pd.isna(v) else float(v)) for k, v in latest[feature_columns].iloc[0].items()}

    return {
        "as_of_date": as_of,
        "horizon_days": horizon_days,
        "predicted_return_pct": pred_return * 100,
        "feature_importances": importances,
        "feature_values": feature_values,
    }
