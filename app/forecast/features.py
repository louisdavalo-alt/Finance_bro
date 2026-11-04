"""Indicateurs techniques calculés à partir de barres OHLCV — RSI, MACD, Bollinger, momentum,
volatilité réalisée. Même discipline anti-look-ahead que `resample.py` pour les séries macro :
chaque valeur à la ligne t n'utilise que des données <= t (fenêtres glissantes `rolling`/`ewm`,
jamais de décalage vers le futur). Vérifié par `tests/test_forecast.py`, notamment
`test_features_do_not_look_ahead`, qui confirme qu'ajouter des lignes futures ne change aucune
valeur déjà calculée.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder. Renvoie NaN tant que la fenêtre de `period` observations n'est pas
    remplie ; 100 si aucune perte n'est survenue dans la fenêtre lissée (division par zéro
    volontairement laissée à NaN par `replace(0, np.nan)` puis reconvertie)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.where(avg_loss != 0, 100.0).where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Renvoie (ligne MACD, ligne de signal, histogramme)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def bollinger(close: pd.Series, period: int = 20, n_std: float = 2.0):
    """Renvoie (bande médiane, bande haute, bande basse, %B, largeur de bande).
    %B = position du cours dans la bande (0 = bande basse, 1 = bande haute, peut sortir de
    [0,1] si le cours dépasse les bandes)."""
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    pct_b = (close - lower) / (upper - lower)
    bandwidth = (upper - lower) / mid
    return mid, upper, lower, pct_b, bandwidth


def realized_vol(returns: pd.Series, window: int) -> pd.Series:
    """Écart-type des rendements log sur `window` jours, annualisé (racine de 252)."""
    return returns.rolling(window).std() * np.sqrt(252)


FEATURE_COLUMNS = [
    "rsi_14", "macd", "macd_signal", "macd_hist", "bb_pct_b", "bb_bandwidth",
    "vol_10d", "vol_20d", "vol_chg_1d", "vol_rel_20d", "mom_5d", "mom_10d", "mom_20d",
]


def build_feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """`bars` : DataFrame indexé par date avec colonnes Open/High/Low/Close/Volume (format
    `yfinance`). Renvoie `bars` enrichi des colonnes de `FEATURE_COLUMNS`, plus `ret_1d` et
    `log_ret_1d`. Aucune colonne ne dépend d'une ligne future."""
    df = bars.copy()
    df["ret_1d"] = df["Close"].pct_change()
    df["log_ret_1d"] = np.log(df["Close"]).diff()
    df["rsi_14"] = rsi(df["Close"], 14)
    macd_line, signal_line, hist = macd(df["Close"])
    df["macd"], df["macd_signal"], df["macd_hist"] = macd_line, signal_line, hist
    _, _, _, pct_b, bandwidth = bollinger(df["Close"])
    df["bb_pct_b"], df["bb_bandwidth"] = pct_b, bandwidth
    df["vol_10d"] = realized_vol(df["log_ret_1d"], 10)
    df["vol_20d"] = realized_vol(df["log_ret_1d"], 20)
    df["vol_chg_1d"] = df["Volume"].pct_change()
    df["vol_rel_20d"] = df["Volume"] / df["Volume"].rolling(20).mean()
    df["mom_5d"] = df["Close"].pct_change(5)
    df["mom_10d"] = df["Close"].pct_change(10)
    df["mom_20d"] = df["Close"].pct_change(20)
    return df
