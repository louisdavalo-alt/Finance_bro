"""Catalogue déclaratif des indicateurs à ingérer, un par pays/zone demandé.

Ajouter un indicateur = ajouter une ligne ici, pas une ligne de code. Les codes de série
(`series_id`, `key`, `zb`, ...) sont donnés à titre d'exemple représentatif de chaque source ;
certains (FMI, NBS Chine) dépendent de la structure exacte du tableau et
doivent être vérifiés/adaptés après inscription aux API concernées (voir les commentaires de
chaque connecteur et le README).
"""
from __future__ import annotations

from .connectors.base import IndicatorSpec

INDICATORS: list[IndicatorSpec] = [
    # ===================================================================== #
    # États-Unis — FRED
    # ===================================================================== #
    IndicatorSpec("US_FEDFUNDS", "USA", "fred", "M", "%", {"series_id": "FEDFUNDS"}, publication_lag_days=5),
    IndicatorSpec("US_DGS10", "USA", "fred", "D", "%", {"series_id": "DGS10"}, publication_lag_days=1),
    IndicatorSpec("US_CPI", "USA", "fred", "M", "indice (1982-84=100)", {"series_id": "CPIAUCSL"}, publication_lag_days=15),
    IndicatorSpec("US_UNRATE", "USA", "fred", "M", "%", {"series_id": "UNRATE"}, publication_lag_days=7),
    IndicatorSpec("US_WALCL", "USA", "fred", "W", "M USD", {"series_id": "WALCL"}, publication_lag_days=3),

    # ===================================================================== #
    # Zone euro — BCE (taux, M3, rendements souverains) + FMI SDMX 3.0 (France)
    # ===================================================================== #
    IndicatorSpec("EA_DFR", "EA", "ecb", "D", "%", {"dataflow": "FM", "key": "D.U2.EUR.4F.KR.DFR.LEV"}, publication_lag_days=1),
    IndicatorSpec("EA_M3", "EA", "ecb", "M", "M EUR", {"dataflow": "BSI", "key": "M.U2.Y.V.M30.X.I.U2.2300.Z01.E"}, publication_lag_days=28),
    IndicatorSpec("EA_YIELD_10Y", "EA", "ecb", "D", "%", {"dataflow": "YC", "key": "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"}, publication_lag_days=1),

    IndicatorSpec(
        "FR_CPI", "FRA", "imf", "M", "indice", {"agency_id": "IMF.STA", "resource_id": "CPI", "version": "+", "key": "FRA.CPI.*.IX.M"},
        publication_lag_days=15,
        fallback=IndicatorSpec("FR_CPI_WB", "FRA", "worldbank", "A", "%", {"iso3": "FRA", "indicator": "FP.CPI.TOTL.ZG"}),
    ),
    # ⚠️ Pas de code FMI confirmé pour le PIB/chômage français (seul l'exemple CPI est documenté
    # dans la spec officielle) — reste sur la Banque mondiale en attendant. Pour trouver le bon
    # dataflow/clé : navigateur de données du FMI (data.imf.org), onglet Réseau du navigateur,
    # même méthode que pour la BOJ (voir ARCHITECTURE.md).
    IndicatorSpec("FR_GDP", "FRA", "worldbank", "A", "%", {"iso3": "FRA", "indicator": "NY.GDP.MKTP.KD.ZG"}, publication_lag_days=270),
    IndicatorSpec("FR_UNRATE", "FRA", "worldbank", "A", "%", {"iso3": "FRA", "indicator": "SL.UEM.TOTL.ZS"}, publication_lag_days=270),

    # ===================================================================== #
    # Allemagne — retiré : voir ARCHITECTURE.md (Destatis a désactivé les requêtes GET avec
    # identifiants dans l'URL le 30/06/2025 ; les tentatives de correction via POST + différents
    # formats d'authentification ont toutes échoué en conditions réelles le 25/09/2026). Les
    # indicateurs suivants (DAX, EUR/USD) sont des données de MARCHÉ via yfinance, pas des
    # statistiques officielles : ils ne remplacent pas l'indice de production, le HICP ou la
    # balance commerciale allemande, qui restent absents du catalogue pour l'instant.
    IndicatorSpec("DE_DAX", "DEU", "yfinance", "D", "points d'indice", {"symbol": "^GDAXI"}, publication_lag_days=0),
    IndicatorSpec("EA_EURUSD", "EA", "yfinance", "D", "USD par EUR", {"symbol": "EURUSD=X"}, publication_lag_days=0),
    IndicatorSpec("DE_IPI_WB", "DEU", "worldbank", "A", "%", {"iso3": "DEU", "indicator": "NV.IND.MANF.KD.ZG"}, publication_lag_days=270),
    IndicatorSpec("DE_HICP_WB", "DEU", "worldbank", "A", "%", {"iso3": "DEU", "indicator": "FP.CPI.TOTL.ZG"}, publication_lag_days=270),

    # ===================================================================== #
    # Marché — indices, actions, matières premières, crypto (yfinance)
    # ===================================================================== #
    # "GLOBAL" : pseudo-zone utilisée pour les actifs qui ne sont pas rattachés à un seul pays
    # (matières premières, cryptomonnaies). Ce ne sont pas des statistiques officielles — voir
    # ARCHITECTURE.md et docs/TICKERS.md. Seul FR_TOTALENERGIES a été confirmé en conditions
    # réelles (25/09/2026, 6869 observations) ; les autres suivent les mêmes conventions Yahoo
    # Finance mais n'ont pas été testés un par un.
    IndicatorSpec("FR_TOTALENERGIES", "FRA", "yfinance", "D", "EUR", {"symbol": "TTE.PA"}, publication_lag_days=0),
    IndicatorSpec("FR_AIRBUS", "FRA", "yfinance", "D", "EUR", {"symbol": "AIR.PA"}, publication_lag_days=0),
    IndicatorSpec("FR_LVMH", "FRA", "yfinance", "D", "EUR", {"symbol": "MC.PA"}, publication_lag_days=0),
    IndicatorSpec("INDEX_CAC40", "FRA", "yfinance", "D", "points d'indice", {"symbol": "^FCHI"}, publication_lag_days=0),
    IndicatorSpec("INDEX_SP500", "USA", "yfinance", "D", "points d'indice", {"symbol": "^GSPC"}, publication_lag_days=0),
    IndicatorSpec("INDEX_NASDAQ", "USA", "yfinance", "D", "points d'indice", {"symbol": "^IXIC"}, publication_lag_days=0),
    IndicatorSpec("INDEX_NIKKEI", "JPN", "yfinance", "D", "points d'indice", {"symbol": "^N225"}, publication_lag_days=0),
    IndicatorSpec("INDEX_FTSE100", "GBR", "yfinance", "D", "points d'indice", {"symbol": "^FTSE"}, publication_lag_days=0),
    IndicatorSpec("INDEX_HANGSENG", "HKG", "yfinance", "D", "points d'indice", {"symbol": "^HSI"}, publication_lag_days=0),
    IndicatorSpec("INDEX_SENSEX", "IND", "yfinance", "D", "points d'indice", {"symbol": "^BSESN"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_GOLD", "GLOBAL", "yfinance", "D", "USD/once", {"symbol": "GC=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_OIL_WTI", "GLOBAL", "yfinance", "D", "USD/baril", {"symbol": "CL=F"}, publication_lag_days=0),
    IndicatorSpec("CRYPTO_BTC", "GLOBAL", "yfinance", "D", "USD", {"symbol": "BTC-USD"}, publication_lag_days=0),

    # ===================================================================== #
    # Marché — extension massive (26/09/2026) : indices, forex, ~25-35 actions par pays
    # (USA, Japon, France, Allemagne, Chine, Corée du Sud, Royaume-Uni, Canada, Inde, Italie,
    # Pologne, Mexique), crypto, fonds, obligations, matières premières.
    # ⚠️ Conventions de tickers Yahoo Finance standard (stables, bien documentées pour les
    # grandes capitalisations), mais AUCUN de ces 347 indicateurs n'a été testé individuellement
    # en conditions réelles avant packaging — seul un échantillon initial (indices majeurs,
    # quelques actions françaises, or, pétrole, Bitcoin) l'avait été lors d'un lot précédent.
    # Avant de t'appuyer dessus : lance le pipeline complet et transmets le log, exactement
    # comme pour les lots précédents — on corrigera un par un les tickers qui échouent.
    # --- Indices supplémentaires ---
    IndicatorSpec("INDEX_DOWJONES", "USA", "yfinance", "D", "points d'indice", {"symbol": "^DJI"}, publication_lag_days=0),
    IndicatorSpec("INDEX_RUSSELL2000", "USA", "yfinance", "D", "points d'indice", {"symbol": "^RUT"}, publication_lag_days=0),
    IndicatorSpec("INDEX_VIX", "USA", "yfinance", "D", "points d'indice", {"symbol": "^VIX"}, publication_lag_days=0),
    IndicatorSpec("INDEX_EUROSTOXX50", "EA", "yfinance", "D", "points d'indice", {"symbol": "^STOXX50E"}, publication_lag_days=0),
    IndicatorSpec("INDEX_IBEX35", "ESP", "yfinance", "D", "points d'indice", {"symbol": "^IBEX"}, publication_lag_days=0),
    # Format corrigé le 26/09/2026 : "^FTSEMIB.MI" mélangeait à tort le préfixe indice et le
    # suffixe de place (erreur de génération initiale) — non revérifié après correction.
    IndicatorSpec("INDEX_FTSEMIB", "ITA", "yfinance", "D", "points d'indice", {"symbol": "FTSEMIB.MI"}, publication_lag_days=0),
    IndicatorSpec("INDEX_SHANGHAI", "CHN", "yfinance", "D", "points d'indice", {"symbol": "000001.SS"}, publication_lag_days=0),
    IndicatorSpec("INDEX_SHENZHEN", "CHN", "yfinance", "D", "points d'indice", {"symbol": "399001.SZ"}, publication_lag_days=0),
    IndicatorSpec("INDEX_KOSPI", "KOR", "yfinance", "D", "points d'indice", {"symbol": "^KS11"}, publication_lag_days=0),
    IndicatorSpec("INDEX_TSX", "CAN", "yfinance", "D", "points d'indice", {"symbol": "^GSPTSE"}, publication_lag_days=0),
    IndicatorSpec("INDEX_BMV_IPC", "MEX", "yfinance", "D", "points d'indice", {"symbol": "^MXX"}, publication_lag_days=0),
    # INDEX_WIG20 retiré le 26/09/2026 : "WIG20.WA" ne supporte que des périodes courtes sur
    # Yahoo Finance ("Period 'max' is invalid, must be one of: 1d, 5d") — mauvais symbole,
    # probablement une cotation intrajournalière plutôt que l'indice historique. À rechercher.
    # --- Taux de change supplémentaires ---
    IndicatorSpec("FX_USDJPY", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDJPY=X"}, publication_lag_days=0),
    IndicatorSpec("FX_GBPUSD", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "GBPUSD=X"}, publication_lag_days=0),
    IndicatorSpec("FX_USDCHF", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDCHF=X"}, publication_lag_days=0),
    IndicatorSpec("FX_USDCNY", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDCNY=X"}, publication_lag_days=0),
    IndicatorSpec("FX_USDINR", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDINR=X"}, publication_lag_days=0),
    IndicatorSpec("FX_USDCAD", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDCAD=X"}, publication_lag_days=0),
    IndicatorSpec("FX_USDMXN", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDMXN=X"}, publication_lag_days=0),
    IndicatorSpec("FX_USDPLN", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDPLN=X"}, publication_lag_days=0),
    IndicatorSpec("FX_USDKRW", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "USDKRW=X"}, publication_lag_days=0),
    IndicatorSpec("FX_EURGBP", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "EURGBP=X"}, publication_lag_days=0),
    IndicatorSpec("FX_EURJPY", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "EURJPY=X"}, publication_lag_days=0),
    IndicatorSpec("FX_AUDUSD", "GLOBAL", "yfinance", "D", "taux de change", {"symbol": "AUDUSD=X"}, publication_lag_days=0),
    # --- Actions USA ---
    IndicatorSpec("USA_APPLE", "USA", "yfinance", "D", "USD", {"symbol": "AAPL"}, publication_lag_days=0),
    IndicatorSpec("USA_MICROSOFT", "USA", "yfinance", "D", "USD", {"symbol": "MSFT"}, publication_lag_days=0),
    IndicatorSpec("USA_AMAZON", "USA", "yfinance", "D", "USD", {"symbol": "AMZN"}, publication_lag_days=0),
    IndicatorSpec("USA_ALPHABET", "USA", "yfinance", "D", "USD", {"symbol": "GOOGL"}, publication_lag_days=0),
    IndicatorSpec("USA_META", "USA", "yfinance", "D", "USD", {"symbol": "META"}, publication_lag_days=0),
    IndicatorSpec("USA_NVIDIA", "USA", "yfinance", "D", "USD", {"symbol": "NVDA"}, publication_lag_days=0),
    IndicatorSpec("USA_TESLA", "USA", "yfinance", "D", "USD", {"symbol": "TSLA"}, publication_lag_days=0),
    IndicatorSpec("USA_BERKSHIRE", "USA", "yfinance", "D", "USD", {"symbol": "BRK-B"}, publication_lag_days=0),
    IndicatorSpec("USA_JPMORGAN", "USA", "yfinance", "D", "USD", {"symbol": "JPM"}, publication_lag_days=0),
    IndicatorSpec("USA_JOHNSON_JOHNSON", "USA", "yfinance", "D", "USD", {"symbol": "JNJ"}, publication_lag_days=0),
    IndicatorSpec("USA_VISA", "USA", "yfinance", "D", "USD", {"symbol": "V"}, publication_lag_days=0),
    IndicatorSpec("USA_PROCTER_GAMBLE", "USA", "yfinance", "D", "USD", {"symbol": "PG"}, publication_lag_days=0),
    IndicatorSpec("USA_UNITEDHEALTH", "USA", "yfinance", "D", "USD", {"symbol": "UNH"}, publication_lag_days=0),
    IndicatorSpec("USA_HOME_DEPOT", "USA", "yfinance", "D", "USD", {"symbol": "HD"}, publication_lag_days=0),
    IndicatorSpec("USA_MASTERCARD", "USA", "yfinance", "D", "USD", {"symbol": "MA"}, publication_lag_days=0),
    IndicatorSpec("USA_DISNEY", "USA", "yfinance", "D", "USD", {"symbol": "DIS"}, publication_lag_days=0),
    IndicatorSpec("USA_BANK_OF_AMERICA", "USA", "yfinance", "D", "USD", {"symbol": "BAC"}, publication_lag_days=0),
    IndicatorSpec("USA_EXXONMOBIL", "USA", "yfinance", "D", "USD", {"symbol": "XOM"}, publication_lag_days=0),
    IndicatorSpec("USA_CHEVRON", "USA", "yfinance", "D", "USD", {"symbol": "CVX"}, publication_lag_days=0),
    IndicatorSpec("USA_COCACOLA", "USA", "yfinance", "D", "USD", {"symbol": "KO"}, publication_lag_days=0),
    IndicatorSpec("USA_PEPSICO", "USA", "yfinance", "D", "USD", {"symbol": "PEP"}, publication_lag_days=0),
    IndicatorSpec("USA_ABBVIE", "USA", "yfinance", "D", "USD", {"symbol": "ABBV"}, publication_lag_days=0),
    IndicatorSpec("USA_MERCK", "USA", "yfinance", "D", "USD", {"symbol": "MRK"}, publication_lag_days=0),
    IndicatorSpec("USA_PFIZER", "USA", "yfinance", "D", "USD", {"symbol": "PFE"}, publication_lag_days=0),
    IndicatorSpec("USA_COSTCO", "USA", "yfinance", "D", "USD", {"symbol": "COST"}, publication_lag_days=0),
    IndicatorSpec("USA_WALMART", "USA", "yfinance", "D", "USD", {"symbol": "WMT"}, publication_lag_days=0),
    IndicatorSpec("USA_NETFLIX", "USA", "yfinance", "D", "USD", {"symbol": "NFLX"}, publication_lag_days=0),
    IndicatorSpec("USA_ADOBE", "USA", "yfinance", "D", "USD", {"symbol": "ADBE"}, publication_lag_days=0),
    IndicatorSpec("USA_SALESFORCE", "USA", "yfinance", "D", "USD", {"symbol": "CRM"}, publication_lag_days=0),
    IndicatorSpec("USA_INTEL", "USA", "yfinance", "D", "USD", {"symbol": "INTC"}, publication_lag_days=0),
    IndicatorSpec("USA_CISCO", "USA", "yfinance", "D", "USD", {"symbol": "CSCO"}, publication_lag_days=0),
    IndicatorSpec("USA_VERIZON", "USA", "yfinance", "D", "USD", {"symbol": "VZ"}, publication_lag_days=0),
    IndicatorSpec("USA_ATT", "USA", "yfinance", "D", "USD", {"symbol": "T"}, publication_lag_days=0),
    IndicatorSpec("USA_ORACLE", "USA", "yfinance", "D", "USD", {"symbol": "ORCL"}, publication_lag_days=0),
    IndicatorSpec("USA_IBM", "USA", "yfinance", "D", "USD", {"symbol": "IBM"}, publication_lag_days=0),
    # --- Actions JPN ---
    IndicatorSpec("JPN_TOYOTA", "JPN", "yfinance", "D", "JPY", {"symbol": "7203.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SONY", "JPN", "yfinance", "D", "JPY", {"symbol": "6758.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SOFTBANK_GROUP", "JPN", "yfinance", "D", "JPY", {"symbol": "9984.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_HITACHI", "JPN", "yfinance", "D", "JPY", {"symbol": "6501.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_HONDA", "JPN", "yfinance", "D", "JPY", {"symbol": "7267.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MITSUBISHI_UFJ", "JPN", "yfinance", "D", "JPY", {"symbol": "8306.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_DENSO", "JPN", "yfinance", "D", "JPY", {"symbol": "6902.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_RECRUIT", "JPN", "yfinance", "D", "JPY", {"symbol": "6098.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_NTT", "JPN", "yfinance", "D", "JPY", {"symbol": "9432.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SHIN_ETSU_CHEMICAL", "JPN", "yfinance", "D", "JPY", {"symbol": "4063.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_TOKYO_ELECTRON", "JPN", "yfinance", "D", "JPY", {"symbol": "8035.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_DAIKIN", "JPN", "yfinance", "D", "JPY", {"symbol": "6367.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_CHUGAI_PHARMA", "JPN", "yfinance", "D", "JPY", {"symbol": "4519.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MITSUBISHI_CORP", "JPN", "yfinance", "D", "JPY", {"symbol": "8058.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MITSUI_CO", "JPN", "yfinance", "D", "JPY", {"symbol": "8031.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_KEYENCE", "JPN", "yfinance", "D", "JPY", {"symbol": "6861.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_CANON", "JPN", "yfinance", "D", "JPY", {"symbol": "7751.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_KDDI", "JPN", "yfinance", "D", "JPY", {"symbol": "9433.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_DAIICHI_SANKYO", "JPN", "yfinance", "D", "JPY", {"symbol": "4568.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MITSUBISHI_ELECTRIC", "JPN", "yfinance", "D", "JPY", {"symbol": "6503.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MITSUI_FUDOSAN", "JPN", "yfinance", "D", "JPY", {"symbol": "8801.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MITSUBISHI_ESTATE", "JPN", "yfinance", "D", "JPY", {"symbol": "8802.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_TAKEDA", "JPN", "yfinance", "D", "JPY", {"symbol": "4502.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_BRIDGESTONE", "JPN", "yfinance", "D", "JPY", {"symbol": "5108.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SUZUKI", "JPN", "yfinance", "D", "JPY", {"symbol": "7269.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SMC_CORP", "JPN", "yfinance", "D", "JPY", {"symbol": "6273.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_JR_CENTRAL", "JPN", "yfinance", "D", "JPY", {"symbol": "9022.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_JR_EAST", "JPN", "yfinance", "D", "JPY", {"symbol": "9020.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SUMITOMO_MITSUI", "JPN", "yfinance", "D", "JPY", {"symbol": "8316.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MIZUHO", "JPN", "yfinance", "D", "JPY", {"symbol": "8411.T"}, publication_lag_days=0),
    # --- Actions FRA ---
    IndicatorSpec("FRA_LOREAL", "FRA", "yfinance", "D", "EUR", {"symbol": "OR.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SANOFI", "FRA", "yfinance", "D", "EUR", {"symbol": "SAN.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_BNP_PARIBAS", "FRA", "yfinance", "D", "EUR", {"symbol": "BNP.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_AIR_LIQUIDE", "FRA", "yfinance", "D", "EUR", {"symbol": "AI.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SCHNEIDER_ELECTRIC", "FRA", "yfinance", "D", "EUR", {"symbol": "SU.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_DANONE", "FRA", "yfinance", "D", "EUR", {"symbol": "BN.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_RENAULT", "FRA", "yfinance", "D", "EUR", {"symbol": "RNO.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_AXA", "FRA", "yfinance", "D", "EUR", {"symbol": "CS.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_VINCI", "FRA", "yfinance", "D", "EUR", {"symbol": "DG.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_ESSILORLUXOTTICA", "FRA", "yfinance", "D", "EUR", {"symbol": "EL.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_KERING", "FRA", "yfinance", "D", "EUR", {"symbol": "KER.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_CAPGEMINI", "FRA", "yfinance", "D", "EUR", {"symbol": "CAP.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SAINT_GOBAIN", "FRA", "yfinance", "D", "EUR", {"symbol": "SGO.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_STELLANTIS", "FRA", "yfinance", "D", "EUR", {"symbol": "STLAP.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_ORANGE", "FRA", "yfinance", "D", "EUR", {"symbol": "ORA.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_ENGIE", "FRA", "yfinance", "D", "EUR", {"symbol": "ENGI.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_VEOLIA", "FRA", "yfinance", "D", "EUR", {"symbol": "VIE.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_DASSAULT_SYSTEMES", "FRA", "yfinance", "D", "EUR", {"symbol": "DSY.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_PUBLICIS", "FRA", "yfinance", "D", "EUR", {"symbol": "PUB.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_THALES", "FRA", "yfinance", "D", "EUR", {"symbol": "HO.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_LEGRAND", "FRA", "yfinance", "D", "EUR", {"symbol": "LR.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_MICHELIN", "FRA", "yfinance", "D", "EUR", {"symbol": "ML.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_PERNOD_RICARD", "FRA", "yfinance", "D", "EUR", {"symbol": "RI.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SODEXO", "FRA", "yfinance", "D", "EUR", {"symbol": "SW.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_CREDIT_AGRICOLE", "FRA", "yfinance", "D", "EUR", {"symbol": "ACA.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SOCIETE_GENERALE", "FRA", "yfinance", "D", "EUR", {"symbol": "GLE.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_WORLDLINE", "FRA", "yfinance", "D", "EUR", {"symbol": "WLN.PA"}, publication_lag_days=0),
    # --- Actions DEU ---
    IndicatorSpec("DEU_BMW", "DEU", "yfinance", "D", "EUR", {"symbol": "BMW.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_DEUTSCHE_TELEKOM", "DEU", "yfinance", "D", "EUR", {"symbol": "DTE.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_DEUTSCHE_BANK", "DEU", "yfinance", "D", "EUR", {"symbol": "DBK.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_MUNICH_RE", "DEU", "yfinance", "D", "EUR", {"symbol": "MUV2.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_INFINEON", "DEU", "yfinance", "D", "EUR", {"symbol": "IFX.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_ADIDAS", "DEU", "yfinance", "D", "EUR", {"symbol": "ADS.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_BAYER", "DEU", "yfinance", "D", "EUR", {"symbol": "BAYN.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_HENKEL", "DEU", "yfinance", "D", "EUR", {"symbol": "HEN3.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_DHL_GROUP", "DEU", "yfinance", "D", "EUR", {"symbol": "DHL.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_RWE", "DEU", "yfinance", "D", "EUR", {"symbol": "RWE.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_EON", "DEU", "yfinance", "D", "EUR", {"symbol": "EOAN.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_FRESENIUS", "DEU", "yfinance", "D", "EUR", {"symbol": "FRE.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_CONTINENTAL", "DEU", "yfinance", "D", "EUR", {"symbol": "CON.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_HEIDELBERG_MATERIALS", "DEU", "yfinance", "D", "EUR", {"symbol": "HEI.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_PUMA", "DEU", "yfinance", "D", "EUR", {"symbol": "PUM.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_VONOVIA", "DEU", "yfinance", "D", "EUR", {"symbol": "VNA.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_ZALANDO", "DEU", "yfinance", "D", "EUR", {"symbol": "ZAL.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_SYMRISE", "DEU", "yfinance", "D", "EUR", {"symbol": "SY1.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_BEIERSDORF", "DEU", "yfinance", "D", "EUR", {"symbol": "BEI.DE"}, publication_lag_days=0),
    # DEU_COVESTRO retiré le 26/09/2026 : une seule observation renvoyée (suspect), probablement
    # lié au rachat/à la sortie de cote de Covestro — à rechercher avant de le réintégrer.
    IndicatorSpec("DEU_MTU_AERO_ENGINES", "DEU", "yfinance", "D", "EUR", {"symbol": "MTX.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_DEUTSCHE_BOERSE", "DEU", "yfinance", "D", "EUR", {"symbol": "DB1.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_QIAGEN", "DEU", "yfinance", "D", "EUR", {"symbol": "QIA.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_SIEMENS_HEALTHINEERS", "DEU", "yfinance", "D", "EUR", {"symbol": "SHL.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_PORSCHE_AG", "DEU", "yfinance", "D", "EUR", {"symbol": "P911.DE"}, publication_lag_days=0),
    # --- Actions CHN ---
    IndicatorSpec("CHN_ALIBABA_ADR", "CHN", "yfinance", "D", "USD", {"symbol": "BABA"}, publication_lag_days=0),
    IndicatorSpec("CHN_JD_ADR", "CHN", "yfinance", "D", "USD", {"symbol": "JD"}, publication_lag_days=0),
    IndicatorSpec("CHN_PINDUODUO_ADR", "CHN", "yfinance", "D", "USD", {"symbol": "PDD"}, publication_lag_days=0),
    IndicatorSpec("CHN_BAIDU_ADR", "CHN", "yfinance", "D", "USD", {"symbol": "BIDU"}, publication_lag_days=0),
    IndicatorSpec("CHN_NETEASE_ADR", "CHN", "yfinance", "D", "USD", {"symbol": "NTES"}, publication_lag_days=0),
    IndicatorSpec("CHN_TENCENT", "CHN", "yfinance", "D", "HKD", {"symbol": "0700.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_MEITUAN", "CHN", "yfinance", "D", "HKD", {"symbol": "3690.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_XIAOMI", "CHN", "yfinance", "D", "HKD", {"symbol": "1810.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_PING_AN", "CHN", "yfinance", "D", "HKD", {"symbol": "2318.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CCB", "CHN", "yfinance", "D", "HKD", {"symbol": "0939.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_ICBC", "CHN", "yfinance", "D", "HKD", {"symbol": "1398.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_BANK_OF_CHINA", "CHN", "yfinance", "D", "HKD", {"symbol": "3988.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_HKEX", "CHN", "yfinance", "D", "HKD", {"symbol": "0388.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_PETROCHINA", "CHN", "yfinance", "D", "HKD", {"symbol": "0857.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_SINOPEC", "CHN", "yfinance", "D", "HKD", {"symbol": "0386.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CNOOC", "CHN", "yfinance", "D", "HKD", {"symbol": "0883.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_BYD", "CHN", "yfinance", "D", "HKD", {"symbol": "1211.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_ANTA_SPORTS", "CHN", "yfinance", "D", "HKD", {"symbol": "2020.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_LI_NING", "CHN", "yfinance", "D", "HKD", {"symbol": "2331.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_GEELY_AUTO", "CHN", "yfinance", "D", "HKD", {"symbol": "0175.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_KWEICHOW_MOUTAI", "CHN", "yfinance", "D", "CNY", {"symbol": "600519.SS"}, publication_lag_days=0),
    IndicatorSpec("CHN_PING_AN_A", "CHN", "yfinance", "D", "CNY", {"symbol": "601318.SS"}, publication_lag_days=0),
    IndicatorSpec("CHN_WULIANGYE", "CHN", "yfinance", "D", "CNY", {"symbol": "000858.SZ"}, publication_lag_days=0),
    IndicatorSpec("CHN_CATL", "CHN", "yfinance", "D", "CNY", {"symbol": "300750.SZ"}, publication_lag_days=0),
    # --- Actions KOR ---
    IndicatorSpec("KOR_SAMSUNG_ELECTRONICS", "KOR", "yfinance", "D", "KRW", {"symbol": "005930.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SK_HYNIX", "KOR", "yfinance", "D", "KRW", {"symbol": "000660.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_LG_ENERGY_SOLUTION", "KOR", "yfinance", "D", "KRW", {"symbol": "373220.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SAMSUNG_BIOLOGICS", "KOR", "yfinance", "D", "KRW", {"symbol": "207940.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_HYUNDAI_MOTOR", "KOR", "yfinance", "D", "KRW", {"symbol": "005380.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SAMSUNG_SDI", "KOR", "yfinance", "D", "KRW", {"symbol": "006400.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_LG_CHEM", "KOR", "yfinance", "D", "KRW", {"symbol": "051910.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_NAVER", "KOR", "yfinance", "D", "KRW", {"symbol": "035420.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_KAKAO", "KOR", "yfinance", "D", "KRW", {"symbol": "035720.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_KB_FINANCIAL", "KOR", "yfinance", "D", "KRW", {"symbol": "105560.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SHINHAN_FINANCIAL", "KOR", "yfinance", "D", "KRW", {"symbol": "055550.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_POSCO_HOLDINGS", "KOR", "yfinance", "D", "KRW", {"symbol": "005490.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_HYUNDAI_MOBIS", "KOR", "yfinance", "D", "KRW", {"symbol": "012330.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_KIA", "KOR", "yfinance", "D", "KRW", {"symbol": "000270.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_LG_ELECTRONICS", "KOR", "yfinance", "D", "KRW", {"symbol": "066570.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SK_INC", "KOR", "yfinance", "D", "KRW", {"symbol": "034730.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SAMSUNG_SDS", "KOR", "yfinance", "D", "KRW", {"symbol": "018260.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SAMSUNG_LIFE", "KOR", "yfinance", "D", "KRW", {"symbol": "032830.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_KOREA_ZINC", "KOR", "yfinance", "D", "KRW", {"symbol": "010130.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_HANA_FINANCIAL", "KOR", "yfinance", "D", "KRW", {"symbol": "086790.KS"}, publication_lag_days=0),
    # --- Actions GBR ---
    IndicatorSpec("GBR_HSBC", "GBR", "yfinance", "D", "GBP", {"symbol": "HSBA.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_SHELL", "GBR", "yfinance", "D", "GBP", {"symbol": "SHEL.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_ASTRAZENECA", "GBR", "yfinance", "D", "GBP", {"symbol": "AZN.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_UNILEVER", "GBR", "yfinance", "D", "GBP", {"symbol": "ULVR.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_BP", "GBR", "yfinance", "D", "GBP", {"symbol": "BP.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_GSK", "GBR", "yfinance", "D", "GBP", {"symbol": "GSK.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_RIO_TINTO", "GBR", "yfinance", "D", "GBP", {"symbol": "RIO.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_DIAGEO", "GBR", "yfinance", "D", "GBP", {"symbol": "DGE.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_BRITISH_AMERICAN_TOBACCO", "GBR", "yfinance", "D", "GBP", {"symbol": "BATS.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_RELX", "GBR", "yfinance", "D", "GBP", {"symbol": "REL.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_NATIONAL_GRID", "GBR", "yfinance", "D", "GBP", {"symbol": "NG.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_LLOYDS_BANKING", "GBR", "yfinance", "D", "GBP", {"symbol": "LLOY.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_BARCLAYS", "GBR", "yfinance", "D", "GBP", {"symbol": "BARC.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_VODAFONE", "GBR", "yfinance", "D", "GBP", {"symbol": "VOD.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_PRUDENTIAL", "GBR", "yfinance", "D", "GBP", {"symbol": "PRU.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_COMPASS_GROUP", "GBR", "yfinance", "D", "GBP", {"symbol": "CPG.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_ANGLO_AMERICAN", "GBR", "yfinance", "D", "GBP", {"symbol": "AAL.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_GLENCORE", "GBR", "yfinance", "D", "GBP", {"symbol": "GLEN.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_TESCO", "GBR", "yfinance", "D", "GBP", {"symbol": "TSCO.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_RECKITT_BENCKISER", "GBR", "yfinance", "D", "GBP", {"symbol": "RKT.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_IMPERIAL_BRANDS", "GBR", "yfinance", "D", "GBP", {"symbol": "IMB.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_NATWEST_GROUP", "GBR", "yfinance", "D", "GBP", {"symbol": "NWG.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_STANDARD_CHARTERED", "GBR", "yfinance", "D", "GBP", {"symbol": "STAN.L"}, publication_lag_days=0),
    # Ferguson a transféré sa cotation principale au NYSE (plus de .L sur Londres) : corrigé le 26/09/2026.
    IndicatorSpec("GBR_FERGUSON", "GBR", "yfinance", "D", "USD", {"symbol": "FERG"}, publication_lag_days=0),
    # Ashtead a transféré sa cotation principale au NYSE : corrigé le 26/09/2026.
    IndicatorSpec("GBR_ASHTEAD", "GBR", "yfinance", "D", "USD", {"symbol": "AHT"}, publication_lag_days=0),
    IndicatorSpec("GBR_BAE_SYSTEMS", "GBR", "yfinance", "D", "GBP", {"symbol": "BA.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_ROLLS_ROYCE", "GBR", "yfinance", "D", "GBP", {"symbol": "RR.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_LSEG", "GBR", "yfinance", "D", "GBP", {"symbol": "LSEG.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_SSE", "GBR", "yfinance", "D", "GBP", {"symbol": "SSE.L"}, publication_lag_days=0),
    # CRH (groupe irlandais de matériaux de construction) a transféré sa cotation principale au NYSE : corrigé le 26/09/2026.
    IndicatorSpec("GBR_CRH", "GBR", "yfinance", "D", "USD", {"symbol": "CRH"}, publication_lag_days=0),
    # --- Actions CAN ---
    IndicatorSpec("CAN_ROYAL_BANK_CANADA", "CAN", "yfinance", "D", "CAD", {"symbol": "RY.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_TD_BANK", "CAN", "yfinance", "D", "CAD", {"symbol": "TD.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_SHOPIFY", "CAN", "yfinance", "D", "CAD", {"symbol": "SHOP.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_ENBRIDGE", "CAN", "yfinance", "D", "CAD", {"symbol": "ENB.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CANADIAN_NATURAL_RESOURCES", "CAN", "yfinance", "D", "CAD", {"symbol": "CNQ.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_BANK_NOVA_SCOTIA", "CAN", "yfinance", "D", "CAD", {"symbol": "BNS.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_BANK_MONTREAL", "CAN", "yfinance", "D", "CAD", {"symbol": "BMO.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CIBC", "CAN", "yfinance", "D", "CAD", {"symbol": "CM.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CANADIAN_NATIONAL_RAILWAY", "CAN", "yfinance", "D", "CAD", {"symbol": "CNR.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_TC_ENERGY", "CAN", "yfinance", "D", "CAD", {"symbol": "TRP.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_SUNCOR_ENERGY", "CAN", "yfinance", "D", "CAD", {"symbol": "SU.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_BCE", "CAN", "yfinance", "D", "CAD", {"symbol": "BCE.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_MANULIFE", "CAN", "yfinance", "D", "CAD", {"symbol": "MFC.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_ALIMENTATION_COUCHE_TARD", "CAN", "yfinance", "D", "CAD", {"symbol": "ATD.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CANADIAN_PACIFIC_KC", "CAN", "yfinance", "D", "CAD", {"symbol": "CP.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_WASTE_CONNECTIONS", "CAN", "yfinance", "D", "CAD", {"symbol": "WCN.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_THOMSON_REUTERS", "CAN", "yfinance", "D", "CAD", {"symbol": "TRI.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_FORTIS", "CAN", "yfinance", "D", "CAD", {"symbol": "FTS.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_AGNICO_EAGLE_MINES", "CAN", "yfinance", "D", "CAD", {"symbol": "AEM.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_NUTRIEN", "CAN", "yfinance", "D", "CAD", {"symbol": "NTR.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_BROOKFIELD_ASSET_MGMT", "CAN", "yfinance", "D", "CAD", {"symbol": "BAM.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_POWER_CORP", "CAN", "yfinance", "D", "CAD", {"symbol": "POW.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_LOBLAW", "CAN", "yfinance", "D", "CAD", {"symbol": "L.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_RESTAURANT_BRANDS_INTL", "CAN", "yfinance", "D", "CAD", {"symbol": "QSR.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CGI_INC", "CAN", "yfinance", "D", "CAD", {"symbol": "GIB-A.TO"}, publication_lag_days=0),
    # --- Actions IND ---
    IndicatorSpec("IND_RELIANCE", "IND", "yfinance", "D", "INR", {"symbol": "RELIANCE.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_TCS", "IND", "yfinance", "D", "INR", {"symbol": "TCS.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_HDFC_BANK", "IND", "yfinance", "D", "INR", {"symbol": "HDFCBANK.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_INFOSYS", "IND", "yfinance", "D", "INR", {"symbol": "INFY.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ICICI_BANK", "IND", "yfinance", "D", "INR", {"symbol": "ICICIBANK.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_HINDUSTAN_UNILEVER", "IND", "yfinance", "D", "INR", {"symbol": "HINDUNILVR.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_SBI", "IND", "yfinance", "D", "INR", {"symbol": "SBIN.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_BHARTI_AIRTEL", "IND", "yfinance", "D", "INR", {"symbol": "BHARTIARTL.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ITC", "IND", "yfinance", "D", "INR", {"symbol": "ITC.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_KOTAK_MAHINDRA_BANK", "IND", "yfinance", "D", "INR", {"symbol": "KOTAKBANK.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_LARSEN_TOUBRO", "IND", "yfinance", "D", "INR", {"symbol": "LT.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_AXIS_BANK", "IND", "yfinance", "D", "INR", {"symbol": "AXISBANK.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_BAJAJ_FINANCE", "IND", "yfinance", "D", "INR", {"symbol": "BAJFINANCE.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ASIAN_PAINTS", "IND", "yfinance", "D", "INR", {"symbol": "ASIANPAINT.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_MARUTI_SUZUKI", "IND", "yfinance", "D", "INR", {"symbol": "MARUTI.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_HCL_TECH", "IND", "yfinance", "D", "INR", {"symbol": "HCLTECH.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_SUN_PHARMA", "IND", "yfinance", "D", "INR", {"symbol": "SUNPHARMA.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_TITAN", "IND", "yfinance", "D", "INR", {"symbol": "TITAN.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ULTRATECH_CEMENT", "IND", "yfinance", "D", "INR", {"symbol": "ULTRACEMCO.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_WIPRO", "IND", "yfinance", "D", "INR", {"symbol": "WIPRO.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_NTPC", "IND", "yfinance", "D", "INR", {"symbol": "NTPC.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ONGC", "IND", "yfinance", "D", "INR", {"symbol": "ONGC.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_POWER_GRID", "IND", "yfinance", "D", "INR", {"symbol": "POWERGRID.NS"}, publication_lag_days=0),
    # IND_TATA_MOTORS retiré le 26/09/2026 : "possibly delisted" — Tata Motors a été scindée fin
    # 2025 en deux entités (véhicules commerciaux / particuliers) ; les nouveaux tickers ne sont
    # pas encore confirmés.
    IndicatorSpec("IND_TATA_STEEL", "IND", "yfinance", "D", "INR", {"symbol": "TATASTEEL.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ADANI_ENTERPRISES", "IND", "yfinance", "D", "INR", {"symbol": "ADANIENT.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ADANI_PORTS", "IND", "yfinance", "D", "INR", {"symbol": "ADANIPORTS.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_JSW_STEEL", "IND", "yfinance", "D", "INR", {"symbol": "JSWSTEEL.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_NESTLE_INDIA", "IND", "yfinance", "D", "INR", {"symbol": "NESTLEIND.NS"}, publication_lag_days=0),
    # --- Actions ITA ---
    IndicatorSpec("ITA_ENI", "ITA", "yfinance", "D", "EUR", {"symbol": "ENI.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_ENEL", "ITA", "yfinance", "D", "EUR", {"symbol": "ENEL.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_INTESA_SANPAOLO", "ITA", "yfinance", "D", "EUR", {"symbol": "ISP.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_UNICREDIT", "ITA", "yfinance", "D", "EUR", {"symbol": "UCG.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_FERRARI", "ITA", "yfinance", "D", "EUR", {"symbol": "RACE.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_GENERALI", "ITA", "yfinance", "D", "EUR", {"symbol": "G.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_TELECOM_ITALIA", "ITA", "yfinance", "D", "EUR", {"symbol": "TIT.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_PIRELLI", "ITA", "yfinance", "D", "EUR", {"symbol": "PIRC.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_MEDIOBANCA", "ITA", "yfinance", "D", "EUR", {"symbol": "MB.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_BANCO_BPM", "ITA", "yfinance", "D", "EUR", {"symbol": "BAMI.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_MONCLER", "ITA", "yfinance", "D", "EUR", {"symbol": "MONC.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_CAMPARI", "ITA", "yfinance", "D", "EUR", {"symbol": "CPR.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_RECORDATI", "ITA", "yfinance", "D", "EUR", {"symbol": "REC.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_POSTE_ITALIANE", "ITA", "yfinance", "D", "EUR", {"symbol": "PST.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_A2A", "ITA", "yfinance", "D", "EUR", {"symbol": "A2A.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_SNAM", "ITA", "yfinance", "D", "EUR", {"symbol": "SRG.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_TERNA", "ITA", "yfinance", "D", "EUR", {"symbol": "TRN.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_BPER_BANCA", "ITA", "yfinance", "D", "EUR", {"symbol": "BPE.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_AMPLIFON", "ITA", "yfinance", "D", "EUR", {"symbol": "AMP.MI"}, publication_lag_days=0),
    # --- Actions POL ---
    IndicatorSpec("POL_PKO_BANK_POLSKI", "POL", "yfinance", "D", "PLN", {"symbol": "PKO.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_ORLEN", "POL", "yfinance", "D", "PLN", {"symbol": "PKN.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_PZU", "POL", "yfinance", "D", "PLN", {"symbol": "PZU.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_BANK_PEKAO", "POL", "yfinance", "D", "PLN", {"symbol": "PEO.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_KGHM", "POL", "yfinance", "D", "PLN", {"symbol": "KGH.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_CD_PROJEKT", "POL", "yfinance", "D", "PLN", {"symbol": "CDR.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_LPP", "POL", "yfinance", "D", "PLN", {"symbol": "LPP.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_DINO_POLSKA", "POL", "yfinance", "D", "PLN", {"symbol": "DNP.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_ALLEGRO", "POL", "yfinance", "D", "PLN", {"symbol": "ALE.WA"}, publication_lag_days=0),
    # POL_SANTANDER_BANK_POLSKA retiré le 26/09/2026 : "possibly delisted" — ticker "SPL.WA"
    # incertain, à rechercher.
    IndicatorSpec("POL_MBANK", "POL", "yfinance", "D", "PLN", {"symbol": "MBK.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_CYFROWY_POLSAT", "POL", "yfinance", "D", "PLN", {"symbol": "CPS.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_ORANGE_POLSKA", "POL", "yfinance", "D", "PLN", {"symbol": "OPL.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_JSW", "POL", "yfinance", "D", "PLN", {"symbol": "JSW.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_TAURON", "POL", "yfinance", "D", "PLN", {"symbol": "TPE.WA"}, publication_lag_days=0),
    # --- Actions MEX ---
    # MEX_AMERICA_MOVIL retiré le 26/09/2026 : "possibly delisted" — ticker "AMXL.MX" incertain,
    # à rechercher (peut-être "AMX" côté ADR NYSE).
    IndicatorSpec("MEX_WALMEX", "MEX", "yfinance", "D", "MXN", {"symbol": "WALMEX.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_FEMSA", "MEX", "yfinance", "D", "MXN", {"symbol": "FEMSAUBD.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_FINANCIERO_BANORTE", "MEX", "yfinance", "D", "MXN", {"symbol": "GFNORTEO.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_CEMEX", "MEX", "yfinance", "D", "MXN", {"symbol": "CEMEXCPO.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_MEXICO", "MEX", "yfinance", "D", "MXN", {"symbol": "GMEXICOB.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_BIMBO", "MEX", "yfinance", "D", "MXN", {"symbol": "BIMBOA.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_TELEVISA", "MEX", "yfinance", "D", "MXN", {"symbol": "TLEVISACPO.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_KIMBERLY_CLARK_MEXICO", "MEX", "yfinance", "D", "MXN", {"symbol": "KIMBERA.MX"}, publication_lag_days=0),
    # MEX_ALFA retiré le 26/09/2026 : "possibly delisted" — Alfa S.A.B. a connu des
    # restructurations/scissions ; ticker "ALFAA.MX" incertain, à rechercher.
    IndicatorSpec("MEX_GRUPO_AEROPORTUARIO_PACIFICO", "MEX", "yfinance", "D", "MXN", {"symbol": "GAPB.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_AEROPORTUARIO_SURESTE", "MEX", "yfinance", "D", "MXN", {"symbol": "ASURB.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_ORBIA", "MEX", "yfinance", "D", "MXN", {"symbol": "ORBIA.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_CARSO", "MEX", "yfinance", "D", "MXN", {"symbol": "GCARSOA1.MX"}, publication_lag_days=0),
    # --- Cryptomonnaies supplémentaires ---
    IndicatorSpec("CRYPTO_ETH", "GLOBAL", "yfinance", "D", "USD", {"symbol": "ETH-USD"}, publication_lag_days=0),
    IndicatorSpec("CRYPTO_SOL", "GLOBAL", "yfinance", "D", "USD", {"symbol": "SOL-USD"}, publication_lag_days=0),
    IndicatorSpec("CRYPTO_XRP", "GLOBAL", "yfinance", "D", "USD", {"symbol": "XRP-USD"}, publication_lag_days=0),
    IndicatorSpec("CRYPTO_ADA", "GLOBAL", "yfinance", "D", "USD", {"symbol": "ADA-USD"}, publication_lag_days=0),
    IndicatorSpec("CRYPTO_DOGE", "GLOBAL", "yfinance", "D", "USD", {"symbol": "DOGE-USD"}, publication_lag_days=0),
    # --- Fonds / ETF ---
    IndicatorSpec("FUND_SPY", "USA", "yfinance", "D", "USD", {"symbol": "SPY"}, publication_lag_days=0),
    IndicatorSpec("FUND_QQQ", "USA", "yfinance", "D", "USD", {"symbol": "QQQ"}, publication_lag_days=0),
    IndicatorSpec("FUND_MSCI_WORLD", "GLOBAL", "yfinance", "D", "USD", {"symbol": "URTH"}, publication_lag_days=0),
    IndicatorSpec("FUND_MSCI_EM", "GLOBAL", "yfinance", "D", "USD", {"symbol": "EEM"}, publication_lag_days=0),
    IndicatorSpec("FUND_GOLD_ETF", "GLOBAL", "yfinance", "D", "USD", {"symbol": "GLD"}, publication_lag_days=0),
    IndicatorSpec("FUND_TREASURY_20Y", "USA", "yfinance", "D", "USD", {"symbol": "TLT"}, publication_lag_days=0),
    IndicatorSpec("FUND_MSCI_EUROPE", "EA", "yfinance", "D", "USD", {"symbol": "IEUR"}, publication_lag_days=0),
    IndicatorSpec("FUND_TOTAL_BOND_US", "USA", "yfinance", "D", "USD", {"symbol": "BND"}, publication_lag_days=0),
    # --- Obligations / taux souverains (proxies de marché) ---
    IndicatorSpec("BOND_US_13W", "USA", "yfinance", "D", "%", {"symbol": "^IRX"}, publication_lag_days=0),
    IndicatorSpec("BOND_US_5Y", "USA", "yfinance", "D", "%", {"symbol": "^FVX"}, publication_lag_days=0),
    IndicatorSpec("BOND_US_10Y_YFIN", "USA", "yfinance", "D", "%", {"symbol": "^TNX"}, publication_lag_days=0),
    IndicatorSpec("BOND_US_30Y", "USA", "yfinance", "D", "%", {"symbol": "^TYX"}, publication_lag_days=0),
    # BOND_EA_AGGREGATE_ETF retiré le 26/09/2026 : "possibly delisted" — ticker "IEAG.L"
    # probablement discontinué ou incorrect, à rechercher (alternative possible : "IEAG.AS").
    IndicatorSpec("BOND_JP_JGB_ETF", "JPN", "yfinance", "D", "JPY", {"symbol": "2510.T"}, publication_lag_days=0),
    # --- Matières premières ---
    IndicatorSpec("COMMODITY_SILVER", "GLOBAL", "yfinance", "D", "USD", {"symbol": "SI=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_COPPER", "GLOBAL", "yfinance", "D", "USD", {"symbol": "HG=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_PLATINUM", "GLOBAL", "yfinance", "D", "USD", {"symbol": "PL=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_OIL_BRENT", "GLOBAL", "yfinance", "D", "USD", {"symbol": "BZ=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_NATGAS", "GLOBAL", "yfinance", "D", "USD", {"symbol": "NG=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_CORN", "GLOBAL", "yfinance", "D", "USD", {"symbol": "ZC=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_WHEAT", "GLOBAL", "yfinance", "D", "USD", {"symbol": "ZW=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_SOYBEAN", "GLOBAL", "yfinance", "D", "USD", {"symbol": "ZS=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_SUGAR", "GLOBAL", "yfinance", "D", "USD", {"symbol": "SB=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_COFFEE", "GLOBAL", "yfinance", "D", "USD", {"symbol": "KC=F"}, publication_lag_days=0),
    IndicatorSpec("COMMODITY_COTTON", "GLOBAL", "yfinance", "D", "USD", {"symbol": "CT=F"}, publication_lag_days=0),

    # --- Actions USA (lot 2, 26/09/2026) ---
    IndicatorSpec("USA_PAYPAL", "USA", "yfinance", "D", "USD", {"symbol": "PYPL"}, publication_lag_days=0),
    IndicatorSpec("USA_AIRBNB", "USA", "yfinance", "D", "USD", {"symbol": "ABNB"}, publication_lag_days=0),
    IndicatorSpec("USA_UBER", "USA", "yfinance", "D", "USD", {"symbol": "UBER"}, publication_lag_days=0),
    IndicatorSpec("USA_QUALCOMM", "USA", "yfinance", "D", "USD", {"symbol": "QCOM"}, publication_lag_days=0),
    IndicatorSpec("USA_TEXAS_INSTRUMENTS", "USA", "yfinance", "D", "USD", {"symbol": "TXN"}, publication_lag_days=0),
    IndicatorSpec("USA_AMD", "USA", "yfinance", "D", "USD", {"symbol": "AMD"}, publication_lag_days=0),
    IndicatorSpec("USA_BROADCOM", "USA", "yfinance", "D", "USD", {"symbol": "AVGO"}, publication_lag_days=0),
    IndicatorSpec("USA_HONEYWELL", "USA", "yfinance", "D", "USD", {"symbol": "HON"}, publication_lag_days=0),
    IndicatorSpec("USA_CATERPILLAR", "USA", "yfinance", "D", "USD", {"symbol": "CAT"}, publication_lag_days=0),
    IndicatorSpec("USA_DEERE", "USA", "yfinance", "D", "USD", {"symbol": "DE"}, publication_lag_days=0),
    IndicatorSpec("USA_GENERAL_ELECTRIC", "USA", "yfinance", "D", "USD", {"symbol": "GE"}, publication_lag_days=0),
    IndicatorSpec("USA_BOEING", "USA", "yfinance", "D", "USD", {"symbol": "BA"}, publication_lag_days=0),
    IndicatorSpec("USA_LOCKHEED_MARTIN", "USA", "yfinance", "D", "USD", {"symbol": "LMT"}, publication_lag_days=0),
    IndicatorSpec("USA_RTX", "USA", "yfinance", "D", "USD", {"symbol": "RTX"}, publication_lag_days=0),
    IndicatorSpec("USA_UPS", "USA", "yfinance", "D", "USD", {"symbol": "UPS"}, publication_lag_days=0),
    IndicatorSpec("USA_FEDEX", "USA", "yfinance", "D", "USD", {"symbol": "FDX"}, publication_lag_days=0),
    IndicatorSpec("USA_3M", "USA", "yfinance", "D", "USD", {"symbol": "MMM"}, publication_lag_days=0),
    IndicatorSpec("USA_LINDE", "USA", "yfinance", "D", "USD", {"symbol": "LIN"}, publication_lag_days=0),
    IndicatorSpec("USA_NIKE", "USA", "yfinance", "D", "USD", {"symbol": "NKE"}, publication_lag_days=0),
    IndicatorSpec("USA_STARBUCKS", "USA", "yfinance", "D", "USD", {"symbol": "SBUX"}, publication_lag_days=0),
    IndicatorSpec("USA_MCDONALDS", "USA", "yfinance", "D", "USD", {"symbol": "MCD"}, publication_lag_days=0),
    IndicatorSpec("USA_TARGET", "USA", "yfinance", "D", "USD", {"symbol": "TGT"}, publication_lag_days=0),
    IndicatorSpec("USA_LOWES", "USA", "yfinance", "D", "USD", {"symbol": "LOW"}, publication_lag_days=0),
    IndicatorSpec("USA_COLGATE_PALMOLIVE", "USA", "yfinance", "D", "USD", {"symbol": "CL"}, publication_lag_days=0),
    IndicatorSpec("USA_KIMBERLY_CLARK_US", "USA", "yfinance", "D", "USD", {"symbol": "KMB"}, publication_lag_days=0),
    IndicatorSpec("USA_ALTRIA", "USA", "yfinance", "D", "USD", {"symbol": "MO"}, publication_lag_days=0),
    IndicatorSpec("USA_PHILIP_MORRIS_INTL", "USA", "yfinance", "D", "USD", {"symbol": "PM"}, publication_lag_days=0),
    IndicatorSpec("USA_T_MOBILE_US", "USA", "yfinance", "D", "USD", {"symbol": "TMUS"}, publication_lag_days=0),
    IndicatorSpec("USA_COMCAST", "USA", "yfinance", "D", "USD", {"symbol": "CMCSA"}, publication_lag_days=0),
    IndicatorSpec("USA_SP_GLOBAL", "USA", "yfinance", "D", "USD", {"symbol": "SPGI"}, publication_lag_days=0),
    IndicatorSpec("USA_MOODYS", "USA", "yfinance", "D", "USD", {"symbol": "MCO"}, publication_lag_days=0),
    IndicatorSpec("USA_BLACKROCK", "USA", "yfinance", "D", "USD", {"symbol": "BLK"}, publication_lag_days=0),
    IndicatorSpec("USA_GOLDMAN_SACHS", "USA", "yfinance", "D", "USD", {"symbol": "GS"}, publication_lag_days=0),
    IndicatorSpec("USA_MORGAN_STANLEY", "USA", "yfinance", "D", "USD", {"symbol": "MS"}, publication_lag_days=0),
    IndicatorSpec("USA_WELLS_FARGO", "USA", "yfinance", "D", "USD", {"symbol": "WFC"}, publication_lag_days=0),
    IndicatorSpec("USA_CITIGROUP", "USA", "yfinance", "D", "USD", {"symbol": "C"}, publication_lag_days=0),
    IndicatorSpec("USA_AMERICAN_EXPRESS", "USA", "yfinance", "D", "USD", {"symbol": "AXP"}, publication_lag_days=0),
    IndicatorSpec("USA_CHARLES_SCHWAB", "USA", "yfinance", "D", "USD", {"symbol": "SCHW"}, publication_lag_days=0),
    IndicatorSpec("USA_UNION_PACIFIC", "USA", "yfinance", "D", "USD", {"symbol": "UNP"}, publication_lag_days=0),
    IndicatorSpec("USA_CSX", "USA", "yfinance", "D", "USD", {"symbol": "CSX"}, publication_lag_days=0),
    IndicatorSpec("USA_ADP", "USA", "yfinance", "D", "USD", {"symbol": "ADP"}, publication_lag_days=0),
    IndicatorSpec("USA_SERVICENOW", "USA", "yfinance", "D", "USD", {"symbol": "NOW"}, publication_lag_days=0),
    IndicatorSpec("USA_INTUITIVE_SURGICAL", "USA", "yfinance", "D", "USD", {"symbol": "ISRG"}, publication_lag_days=0),
    IndicatorSpec("USA_MEDTRONIC", "USA", "yfinance", "D", "USD", {"symbol": "MDT"}, publication_lag_days=0),
    IndicatorSpec("USA_STRYKER", "USA", "yfinance", "D", "USD", {"symbol": "SYK"}, publication_lag_days=0),
    IndicatorSpec("USA_VERTEX_PHARMA", "USA", "yfinance", "D", "USD", {"symbol": "VRTX"}, publication_lag_days=0),
    IndicatorSpec("USA_REGENERON", "USA", "yfinance", "D", "USD", {"symbol": "REGN"}, publication_lag_days=0),
    IndicatorSpec("USA_GILEAD_SCIENCES", "USA", "yfinance", "D", "USD", {"symbol": "GILD"}, publication_lag_days=0),
    IndicatorSpec("USA_BRISTOL_MYERS", "USA", "yfinance", "D", "USD", {"symbol": "BMY"}, publication_lag_days=0),
    IndicatorSpec("USA_ELI_LILLY", "USA", "yfinance", "D", "USD", {"symbol": "LLY"}, publication_lag_days=0),
    IndicatorSpec("USA_AMGEN", "USA", "yfinance", "D", "USD", {"symbol": "AMGN"}, publication_lag_days=0),
    IndicatorSpec("USA_CVS_HEALTH", "USA", "yfinance", "D", "USD", {"symbol": "CVS"}, publication_lag_days=0),
    IndicatorSpec("USA_DUKE_ENERGY", "USA", "yfinance", "D", "USD", {"symbol": "DUK"}, publication_lag_days=0),
    IndicatorSpec("USA_NEXTERA_ENERGY", "USA", "yfinance", "D", "USD", {"symbol": "NEE"}, publication_lag_days=0),
    IndicatorSpec("USA_PALANTIR", "USA", "yfinance", "D", "USD", {"symbol": "PLTR"}, publication_lag_days=0),
    IndicatorSpec("USA_SNOWFLAKE", "USA", "yfinance", "D", "USD", {"symbol": "SNOW"}, publication_lag_days=0),
    # --- Actions JPN (lot 2, 26/09/2026) ---
    IndicatorSpec("JPN_NINTENDO", "JPN", "yfinance", "D", "JPY", {"symbol": "7974.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_PANASONIC", "JPN", "yfinance", "D", "JPY", {"symbol": "6752.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_NISSAN", "JPN", "yfinance", "D", "JPY", {"symbol": "7201.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SUBARU", "JPN", "yfinance", "D", "JPY", {"symbol": "7270.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_KOMATSU", "JPN", "yfinance", "D", "JPY", {"symbol": "6301.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_NIDEC", "JPN", "yfinance", "D", "JPY", {"symbol": "6594.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_FUJITSU", "JPN", "yfinance", "D", "JPY", {"symbol": "6702.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_NEC", "JPN", "yfinance", "D", "JPY", {"symbol": "6701.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_ORIENTAL_LAND", "JPN", "yfinance", "D", "JPY", {"symbol": "4661.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SECOM", "JPN", "yfinance", "D", "JPY", {"symbol": "9735.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_KAO", "JPN", "yfinance", "D", "JPY", {"symbol": "4452.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SHISEIDO", "JPN", "yfinance", "D", "JPY", {"symbol": "4911.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_JAPAN_TOBACCO", "JPN", "yfinance", "D", "JPY", {"symbol": "2914.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_ANA_HOLDINGS", "JPN", "yfinance", "D", "JPY", {"symbol": "9202.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_JAPAN_AIRLINES", "JPN", "yfinance", "D", "JPY", {"symbol": "9201.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_ORIX", "JPN", "yfinance", "D", "JPY", {"symbol": "8591.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SOMPO", "JPN", "yfinance", "D", "JPY", {"symbol": "8630.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MSAD_INSURANCE", "JPN", "yfinance", "D", "JPY", {"symbol": "8725.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_NOMURA", "JPN", "yfinance", "D", "JPY", {"symbol": "8604.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_ASTELLAS_PHARMA", "JPN", "yfinance", "D", "JPY", {"symbol": "4503.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_EISAI", "JPN", "yfinance", "D", "JPY", {"symbol": "4523.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_BANDAI_NAMCO", "JPN", "yfinance", "D", "JPY", {"symbol": "7832.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_FAST_RETAILING", "JPN", "yfinance", "D", "JPY", {"symbol": "9983.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_OLYMPUS", "JPN", "yfinance", "D", "JPY", {"symbol": "7733.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_TDK", "JPN", "yfinance", "D", "JPY", {"symbol": "6762.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_KYOCERA", "JPN", "yfinance", "D", "JPY", {"symbol": "6971.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SEVEN_AND_I", "JPN", "yfinance", "D", "JPY", {"symbol": "3382.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_AJINOMOTO", "JPN", "yfinance", "D", "JPY", {"symbol": "2802.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_ASAHI_GROUP", "JPN", "yfinance", "D", "JPY", {"symbol": "2502.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_KIRIN", "JPN", "yfinance", "D", "JPY", {"symbol": "2503.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_OTSUKA_HOLDINGS", "JPN", "yfinance", "D", "JPY", {"symbol": "4578.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_NITORI", "JPN", "yfinance", "D", "JPY", {"symbol": "9843.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_DENTSU", "JPN", "yfinance", "D", "JPY", {"symbol": "4324.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_RICOH", "JPN", "yfinance", "D", "JPY", {"symbol": "7752.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_YAMAHA_MOTOR", "JPN", "yfinance", "D", "JPY", {"symbol": "7272.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_ISUZU_MOTORS", "JPN", "yfinance", "D", "JPY", {"symbol": "7202.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_SHARP", "JPN", "yfinance", "D", "JPY", {"symbol": "6753.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_CASIO", "JPN", "yfinance", "D", "JPY", {"symbol": "6952.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_MAZDA", "JPN", "yfinance", "D", "JPY", {"symbol": "7261.T"}, publication_lag_days=0),
    IndicatorSpec("JPN_TOKIO_MARINE", "JPN", "yfinance", "D", "JPY", {"symbol": "8766.T"}, publication_lag_days=0),
    # --- Actions FRA (lot 2, 26/09/2026) ---
    IndicatorSpec("FRA_HERMES", "FRA", "yfinance", "D", "EUR", {"symbol": "RMS.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_BOUYGUES", "FRA", "yfinance", "D", "EUR", {"symbol": "EN.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_CARREFOUR", "FRA", "yfinance", "D", "EUR", {"symbol": "CA.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_EIFFAGE", "FRA", "yfinance", "D", "EUR", {"symbol": "FGR.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_VIVENDI", "FRA", "yfinance", "D", "EUR", {"symbol": "VIV.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_EDENRED", "FRA", "yfinance", "D", "EUR", {"symbol": "EDEN.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_TELEPERFORMANCE", "FRA", "yfinance", "D", "EUR", {"symbol": "TEP.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_ALSTOM", "FRA", "yfinance", "D", "EUR", {"symbol": "ALO.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SAFRAN", "FRA", "yfinance", "D", "EUR", {"symbol": "SAF.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_DASSAULT_AVIATION", "FRA", "yfinance", "D", "EUR", {"symbol": "AM.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_REXEL", "FRA", "yfinance", "D", "EUR", {"symbol": "RXL.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_IPSEN", "FRA", "yfinance", "D", "EUR", {"symbol": "IPN.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SARTORIUS_STEDIM", "FRA", "yfinance", "D", "EUR", {"symbol": "DIM.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_GETLINK", "FRA", "yfinance", "D", "EUR", {"symbol": "GET.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_ELIS", "FRA", "yfinance", "D", "EUR", {"symbol": "ELIS.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_ARKEMA", "FRA", "yfinance", "D", "EUR", {"symbol": "AKE.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_AIR_FRANCE_KLM", "FRA", "yfinance", "D", "EUR", {"symbol": "AF.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_EUTELSAT", "FRA", "yfinance", "D", "EUR", {"symbol": "ETL.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_ICADE", "FRA", "yfinance", "D", "EUR", {"symbol": "ICAD.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_UNIBAIL_RODAMCO", "FRA", "yfinance", "D", "EUR", {"symbol": "URW.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_GECINA", "FRA", "yfinance", "D", "EUR", {"symbol": "GFC.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_COVIVIO", "FRA", "yfinance", "D", "EUR", {"symbol": "COV.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_JCDECAUX", "FRA", "yfinance", "D", "EUR", {"symbol": "DEC.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_RUBIS", "FRA", "yfinance", "D", "EUR", {"symbol": "RUI.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_IMERYS", "FRA", "yfinance", "D", "EUR", {"symbol": "NK.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_VALLOUREC", "FRA", "yfinance", "D", "EUR", {"symbol": "VK.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_NEXANS", "FRA", "yfinance", "D", "EUR", {"symbol": "NEX.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SCOR", "FRA", "yfinance", "D", "EUR", {"symbol": "SCR.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_BUREAU_VERITAS", "FRA", "yfinance", "D", "EUR", {"symbol": "BVI.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_KLEPIERRE", "FRA", "yfinance", "D", "EUR", {"symbol": "LI.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_EURONEXT", "FRA", "yfinance", "D", "EUR", {"symbol": "ENX.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_TECHNIP_ENERGIES", "FRA", "yfinance", "D", "EUR", {"symbol": "TE.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_VALEO", "FRA", "yfinance", "D", "EUR", {"symbol": "FR.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_FORVIA", "FRA", "yfinance", "D", "EUR", {"symbol": "FRVIA.PA"}, publication_lag_days=0),
    IndicatorSpec("FRA_SOITEC", "FRA", "yfinance", "D", "EUR", {"symbol": "SOI.PA"}, publication_lag_days=0),
    # --- Actions DEU (lot 2, 26/09/2026) ---
    IndicatorSpec("DEU_RHEINMETALL", "DEU", "yfinance", "D", "EUR", {"symbol": "RHM.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_HANNOVER_RUCK", "DEU", "yfinance", "D", "EUR", {"symbol": "HNR1.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_BRENNTAG", "DEU", "yfinance", "D", "EUR", {"symbol": "BNR.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_MERCK_KGAA", "DEU", "yfinance", "D", "EUR", {"symbol": "MRK.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_DAIMLER_TRUCK", "DEU", "yfinance", "D", "EUR", {"symbol": "DTG.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_SARTORIUS_AG", "DEU", "yfinance", "D", "EUR", {"symbol": "SRT3.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_LUFTHANSA", "DEU", "yfinance", "D", "EUR", {"symbol": "LHA.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_COMMERZBANK", "DEU", "yfinance", "D", "EUR", {"symbol": "CBK.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_FRESENIUS_MEDICAL_CARE", "DEU", "yfinance", "D", "EUR", {"symbol": "FME.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_KNORR_BREMSE", "DEU", "yfinance", "D", "EUR", {"symbol": "KBX.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_EVONIK", "DEU", "yfinance", "D", "EUR", {"symbol": "EVK.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_DELIVERY_HERO", "DEU", "yfinance", "D", "EUR", {"symbol": "DHER.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_HELLOFRESH", "DEU", "yfinance", "D", "EUR", {"symbol": "HFG.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_SIXT", "DEU", "yfinance", "D", "EUR", {"symbol": "SIX2.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_KRONES", "DEU", "yfinance", "D", "EUR", {"symbol": "KRN.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_JENOPTIK", "DEU", "yfinance", "D", "EUR", {"symbol": "JEN.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_WACKER_CHEMIE", "DEU", "yfinance", "D", "EUR", {"symbol": "WCH.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_LANXESS", "DEU", "yfinance", "D", "EUR", {"symbol": "LXS.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_GEA_GROUP", "DEU", "yfinance", "D", "EUR", {"symbol": "G1A.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_TALANX", "DEU", "yfinance", "D", "EUR", {"symbol": "TLX.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_FRAPORT", "DEU", "yfinance", "D", "EUR", {"symbol": "FRA.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_HYPOPORT", "DEU", "yfinance", "D", "EUR", {"symbol": "HYQ.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_NORDEX", "DEU", "yfinance", "D", "EUR", {"symbol": "NDX1.DE"}, publication_lag_days=0),
    # DEU_ENCAVIS (ECV.DE) retiré : rachetée et sortie de cote par un consortium KKR/Viessmann en 2024.
    IndicatorSpec("DEU_VOSSLOH", "DEU", "yfinance", "D", "EUR", {"symbol": "VOS.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_GERRESHEIMER", "DEU", "yfinance", "D", "EUR", {"symbol": "GXI.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_AIXTRON", "DEU", "yfinance", "D", "EUR", {"symbol": "AIXA.DE"}, publication_lag_days=0),
    IndicatorSpec("DEU_CARL_ZEISS_MEDITEC", "DEU", "yfinance", "D", "EUR", {"symbol": "AFX.DE"}, publication_lag_days=0),
    # --- Actions GBR (lot 2, 26/09/2026) ---
    IndicatorSpec("GBR_NEXT", "GBR", "yfinance", "D", "GBP", {"symbol": "NXT.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_WHITBREAD", "GBR", "yfinance", "D", "GBP", {"symbol": "WTB.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_INTERCONTINENTAL_HOTELS", "GBR", "yfinance", "D", "GBP", {"symbol": "IHG.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_EXPERIAN", "GBR", "yfinance", "D", "GBP", {"symbol": "EXPN.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_SMITH_NEPHEW", "GBR", "yfinance", "D", "GBP", {"symbol": "SN.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_CRODA", "GBR", "yfinance", "D", "GBP", {"symbol": "CRDA.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_SPIRAX_GROUP", "GBR", "yfinance", "D", "GBP", {"symbol": "SPX.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_HALMA", "GBR", "yfinance", "D", "GBP", {"symbol": "HLMA.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_INTERTEK", "GBR", "yfinance", "D", "GBP", {"symbol": "ITRK.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_PEARSON", "GBR", "yfinance", "D", "GBP", {"symbol": "PSON.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_ITV", "GBR", "yfinance", "D", "GBP", {"symbol": "ITV.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_WPP", "GBR", "yfinance", "D", "GBP", {"symbol": "WPP.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_INFORMA", "GBR", "yfinance", "D", "GBP", {"symbol": "INF.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_BURBERRY", "GBR", "yfinance", "D", "GBP", {"symbol": "BRBY.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_ADMIRAL_GROUP", "GBR", "yfinance", "D", "GBP", {"symbol": "ADM.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_LEGAL_GENERAL", "GBR", "yfinance", "D", "GBP", {"symbol": "LGEN.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_AVIVA", "GBR", "yfinance", "D", "GBP", {"symbol": "AV.L"}, publication_lag_days=0),
    # GBR_PHOENIX_GROUP (PHNX.L) : échec au dernier lancement ("no timezone found") alors que
    # c'est une grande valeur du FTSE 100 a priori toujours cotée — possible incident ponctuel
    # côté Yahoo plutôt qu'une vraie disparition. Laissé en l'état : à surveiller au prochain lancement.
    IndicatorSpec("GBR_PHOENIX_GROUP", "GBR", "yfinance", "D", "GBP", {"symbol": "PHNX.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_THREEI_GROUP", "GBR", "yfinance", "D", "GBP", {"symbol": "III.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_SCHRODERS", "GBR", "yfinance", "D", "GBP", {"symbol": "SDR.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_ST_JAMES_PLACE", "GBR", "yfinance", "D", "GBP", {"symbol": "STJ.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_SEGRO", "GBR", "yfinance", "D", "GBP", {"symbol": "SGRO.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_LAND_SECURITIES", "GBR", "yfinance", "D", "GBP", {"symbol": "LAND.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_BRITISH_LAND", "GBR", "yfinance", "D", "GBP", {"symbol": "BLND.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_CENTRICA", "GBR", "yfinance", "D", "GBP", {"symbol": "CNA.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_UNITED_UTILITIES", "GBR", "yfinance", "D", "GBP", {"symbol": "UU.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_SEVERN_TRENT", "GBR", "yfinance", "D", "GBP", {"symbol": "SVT.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_PENNON", "GBR", "yfinance", "D", "GBP", {"symbol": "PNN.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_BABCOCK_INTL", "GBR", "yfinance", "D", "GBP", {"symbol": "BAB.L"}, publication_lag_days=0),
    IndicatorSpec("GBR_MARKS_SPENCER", "GBR", "yfinance", "D", "GBP", {"symbol": "MKS.L"}, publication_lag_days=0),
    # --- Actions IND (lot 2, 26/09/2026) ---
    IndicatorSpec("IND_BAJAJ_AUTO", "IND", "yfinance", "D", "INR", {"symbol": "BAJAJ-AUTO.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_BAJAJ_FINSERV", "IND", "yfinance", "D", "INR", {"symbol": "BAJAJFINSV.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_BHARAT_ELECTRONICS", "IND", "yfinance", "D", "INR", {"symbol": "BEL.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_BRITANNIA", "IND", "yfinance", "D", "INR", {"symbol": "BRITANNIA.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_CIPLA", "IND", "yfinance", "D", "INR", {"symbol": "CIPLA.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_COAL_INDIA", "IND", "yfinance", "D", "INR", {"symbol": "COALINDIA.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_DIVIS_LAB", "IND", "yfinance", "D", "INR", {"symbol": "DIVISLAB.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_DR_REDDYS", "IND", "yfinance", "D", "INR", {"symbol": "DRREDDY.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_EICHER_MOTORS", "IND", "yfinance", "D", "INR", {"symbol": "EICHERMOT.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_GRASIM", "IND", "yfinance", "D", "INR", {"symbol": "GRASIM.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_HDFC_LIFE", "IND", "yfinance", "D", "INR", {"symbol": "HDFCLIFE.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_HERO_MOTOCORP", "IND", "yfinance", "D", "INR", {"symbol": "HEROMOTOCO.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_HINDALCO", "IND", "yfinance", "D", "INR", {"symbol": "HINDALCO.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_INDUSIND_BANK", "IND", "yfinance", "D", "INR", {"symbol": "INDUSINDBK.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_SBI_LIFE", "IND", "yfinance", "D", "INR", {"symbol": "SBILIFE.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_SHRIRAM_FINANCE", "IND", "yfinance", "D", "INR", {"symbol": "SHRIRAMFIN.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_TATA_CONSUMER", "IND", "yfinance", "D", "INR", {"symbol": "TATACONSUM.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_TECH_MAHINDRA", "IND", "yfinance", "D", "INR", {"symbol": "TECHM.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_TRENT", "IND", "yfinance", "D", "INR", {"symbol": "TRENT.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_VEDANTA", "IND", "yfinance", "D", "INR", {"symbol": "VEDL.NS"}, publication_lag_days=0),
    # IND_ZOMATO : la société s'est renommée "Eternal Limited" — nouveau ticker essayé ci-dessous,
    # NON VÉRIFIÉ, à confirmer au prochain lancement du pipeline.
    IndicatorSpec("IND_ZOMATO", "IND", "yfinance", "D", "INR", {"symbol": "ETERNAL.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_SIEMENS_INDIA", "IND", "yfinance", "D", "INR", {"symbol": "SIEMENS.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_ABB_INDIA", "IND", "yfinance", "D", "INR", {"symbol": "ABB.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_PIDILITE", "IND", "yfinance", "D", "INR", {"symbol": "PIDILITIND.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_DLF", "IND", "yfinance", "D", "INR", {"symbol": "DLF.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_GODREJ_CONSUMER", "IND", "yfinance", "D", "INR", {"symbol": "GODREJCP.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_HAVELLS", "IND", "yfinance", "D", "INR", {"symbol": "HAVELLS.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_BANK_OF_BARODA", "IND", "yfinance", "D", "INR", {"symbol": "BANKBARODA.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_PUNJAB_NATIONAL_BANK", "IND", "yfinance", "D", "INR", {"symbol": "PNB.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_INDIGO", "IND", "yfinance", "D", "INR", {"symbol": "INDIGO.NS"}, publication_lag_days=0),
    IndicatorSpec("IND_APOLLO_HOSPITALS", "IND", "yfinance", "D", "INR", {"symbol": "APOLLOHOSP.NS"}, publication_lag_days=0),
    # --- Actions ITA (lot 2, 26/09/2026) ---
    IndicatorSpec("ITA_LEONARDO", "ITA", "yfinance", "D", "EUR", {"symbol": "LDO.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_PRYSMIAN", "ITA", "yfinance", "D", "EUR", {"symbol": "PRY.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_INWIT", "ITA", "yfinance", "D", "EUR", {"symbol": "INW.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_NEXI", "ITA", "yfinance", "D", "EUR", {"symbol": "NEXI.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_INTERPUMP", "ITA", "yfinance", "D", "EUR", {"symbol": "IP.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_DIASORIN", "ITA", "yfinance", "D", "EUR", {"symbol": "DIA.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_BANCA_MEDIOLANUM", "ITA", "yfinance", "D", "EUR", {"symbol": "BMED.MI"}, publication_lag_days=0),
    # ITA_BANCA_POP_SONDRIO (BPSO.MI) retiré : rachetée par BPER Banca, sortie de cote.
    IndicatorSpec("ITA_IVECO_GROUP", "ITA", "yfinance", "D", "EUR", {"symbol": "IVG.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_SAIPEM", "ITA", "yfinance", "D", "EUR", {"symbol": "SPM.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_TENARIS", "ITA", "yfinance", "D", "EUR", {"symbol": "TEN.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_BUZZI_UNICEM", "ITA", "yfinance", "D", "EUR", {"symbol": "BZU.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_AZIMUT_HOLDING", "ITA", "yfinance", "D", "EUR", {"symbol": "AZM.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_FINECOBANK", "ITA", "yfinance", "D", "EUR", {"symbol": "FBK.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_HERA", "ITA", "yfinance", "D", "EUR", {"symbol": "HER.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_ITALGAS", "ITA", "yfinance", "D", "EUR", {"symbol": "IG.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_ERG", "ITA", "yfinance", "D", "EUR", {"symbol": "ERG.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_BRUNELLO_CUCINELLI", "ITA", "yfinance", "D", "EUR", {"symbol": "BC.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_TECHNOGYM", "ITA", "yfinance", "D", "EUR", {"symbol": "TGYM.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_MAIRE_TECNIMONT", "ITA", "yfinance", "D", "EUR", {"symbol": "MAIRE.MI"}, publication_lag_days=0),
    IndicatorSpec("ITA_MONDADORI", "ITA", "yfinance", "D", "EUR", {"symbol": "MN.MI"}, publication_lag_days=0),
    # --- Actions POL (lot 2, 26/09/2026) ---
    IndicatorSpec("POL_BUDIMEX", "POL", "yfinance", "D", "PLN", {"symbol": "BDX.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_GRUPA_KETY", "POL", "yfinance", "D", "PLN", {"symbol": "KTY.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_ASSECO_POLAND", "POL", "yfinance", "D", "PLN", {"symbol": "ACP.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_PEPCO_GROUP", "POL", "yfinance", "D", "PLN", {"symbol": "PCO.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_ZABKA_GROUP", "POL", "yfinance", "D", "PLN", {"symbol": "ZAB.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_GRUPA_AZOTY", "POL", "yfinance", "D", "PLN", {"symbol": "ATT.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_KRUK", "POL", "yfinance", "D", "PLN", {"symbol": "KRU.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_BENEFIT_SYSTEMS", "POL", "yfinance", "D", "PLN", {"symbol": "BFT.WA"}, publication_lag_days=0),
    # POL_LIVECHAT_SOFTWARE : restructurée en "Text S.A." — nouveau ticker essayé ci-dessous,
    # NON VÉRIFIÉ, à confirmer au prochain lancement du pipeline.
    IndicatorSpec("POL_LIVECHAT_SOFTWARE", "POL", "yfinance", "D", "PLN", {"symbol": "TXT.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_ING_BANK_SLASKI", "POL", "yfinance", "D", "PLN", {"symbol": "ING.WA"}, publication_lag_days=0),
    IndicatorSpec("POL_ENEA", "POL", "yfinance", "D", "PLN", {"symbol": "ENA.WA"}, publication_lag_days=0),
    # --- Actions MEX (lot 2, 26/09/2026) ---
    # MEX_GRUPO_ELEKTRA (ELEKTRA.MX) retiré : litige fiscal avec le SAT mexicain, cotation suspendue.
    IndicatorSpec("MEX_GRUMA", "MEX", "yfinance", "D", "MXN", {"symbol": "GRUMAB.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_ARCA_CONTINENTAL", "MEX", "yfinance", "D", "MXN", {"symbol": "AC.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_FIBRA_UNO", "MEX", "yfinance", "D", "MXN", {"symbol": "FUNO11.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_FINANCIERO_INBURSA", "MEX", "yfinance", "D", "MXN", {"symbol": "GFINBURO.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_AEROPORTUARIO_CENTRO_NORTE", "MEX", "yfinance", "D", "MXN", {"symbol": "OMAB.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_COMERCIAL_CHEDRAUI", "MEX", "yfinance", "D", "MXN", {"symbol": "CHDRAUIB.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_HERDEZ", "MEX", "yfinance", "D", "MXN", {"symbol": "HERDEZ.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_MEGACABLE", "MEX", "yfinance", "D", "MXN", {"symbol": "MEGACPO.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_QUALITAS", "MEX", "yfinance", "D", "MXN", {"symbol": "Q.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GRUPO_ROTOPLAS", "MEX", "yfinance", "D", "MXN", {"symbol": "AGUA.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_ALPEK", "MEX", "yfinance", "D", "MXN", {"symbol": "ALPEKA.MX"}, publication_lag_days=0),
    IndicatorSpec("MEX_GENOMMA_LAB", "MEX", "yfinance", "D", "MXN", {"symbol": "LABB.MX"}, publication_lag_days=0),
    # --- Actions CAN (lot 2, 26/09/2026) ---
    IndicatorSpec("CAN_BARRICK_GOLD", "CAN", "yfinance", "D", "CAD", {"symbol": "ABX.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CANADIAN_TIRE", "CAN", "yfinance", "D", "CAD", {"symbol": "CTC-A.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_MAGNA_INTERNATIONAL", "CAN", "yfinance", "D", "CAD", {"symbol": "MG.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_OPEN_TEXT", "CAN", "yfinance", "D", "CAD", {"symbol": "OTEX.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_TELUS", "CAN", "yfinance", "D", "CAD", {"symbol": "T.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_ROGERS_COMMUNICATIONS", "CAN", "yfinance", "D", "CAD", {"symbol": "RCI-B.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CENOVUS_ENERGY", "CAN", "yfinance", "D", "CAD", {"symbol": "CVE.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_IMPERIAL_OIL", "CAN", "yfinance", "D", "CAD", {"symbol": "IMO.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_FRANCO_NEVADA", "CAN", "yfinance", "D", "CAD", {"symbol": "FNV.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_WHEATON_PRECIOUS_METALS", "CAN", "yfinance", "D", "CAD", {"symbol": "WPM.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_KINROSS_GOLD", "CAN", "yfinance", "D", "CAD", {"symbol": "K.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_FIRST_QUANTUM_MINERALS", "CAN", "yfinance", "D", "CAD", {"symbol": "FM.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_TECK_RESOURCES", "CAN", "yfinance", "D", "CAD", {"symbol": "TECK-B.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_INTACT_FINANCIAL", "CAN", "yfinance", "D", "CAD", {"symbol": "IFC.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_SUN_LIFE_FINANCIAL", "CAN", "yfinance", "D", "CAD", {"symbol": "SLF.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_GREAT_WEST_LIFECO", "CAN", "yfinance", "D", "CAD", {"symbol": "GWO.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_IGM_FINANCIAL", "CAN", "yfinance", "D", "CAD", {"symbol": "IGM.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_NATIONAL_BANK_CANADA", "CAN", "yfinance", "D", "CAD", {"symbol": "NA.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_DOLLARAMA", "CAN", "yfinance", "D", "CAD", {"symbol": "DOL.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_METRO_INC", "CAN", "yfinance", "D", "CAD", {"symbol": "MRU.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_SAPUTO", "CAN", "yfinance", "D", "CAD", {"symbol": "SAP.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_GEORGE_WESTON", "CAN", "yfinance", "D", "CAD", {"symbol": "WN.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CANADIAN_UTILITIES", "CAN", "yfinance", "D", "CAD", {"symbol": "CU.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_EMERA", "CAN", "yfinance", "D", "CAD", {"symbol": "EMA.TO"}, publication_lag_days=0),
    IndicatorSpec("CAN_CCL_INDUSTRIES", "CAN", "yfinance", "D", "CAD", {"symbol": "CCL-B.TO"}, publication_lag_days=0),
    # --- Actions CHN (lot 2, 26/09/2026) ---
    IndicatorSpec("CHN_CHINA_MOBILE", "CHN", "yfinance", "D", "HKD", {"symbol": "0941.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CHINA_LIFE_INSURANCE", "CHN", "yfinance", "D", "HKD", {"symbol": "2628.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CHINA_MERCHANTS_BANK", "CHN", "yfinance", "D", "HKD", {"symbol": "3968.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CHINA_UNICOM", "CHN", "yfinance", "D", "HKD", {"symbol": "0762.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_HAIER_SMART_HOME", "CHN", "yfinance", "D", "HKD", {"symbol": "6690.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_LENOVO_GROUP", "CHN", "yfinance", "D", "HKD", {"symbol": "0992.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CHINA_RESOURCES_BEER", "CHN", "yfinance", "D", "HKD", {"symbol": "0291.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CHINA_RESOURCES_LAND", "CHN", "yfinance", "D", "HKD", {"symbol": "1109.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_SHENZHOU_INTERNATIONAL", "CHN", "yfinance", "D", "HKD", {"symbol": "2313.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_ZIJIN_MINING", "CHN", "yfinance", "D", "HKD", {"symbol": "2899.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_CHINA_OVERSEAS_LAND", "CHN", "yfinance", "D", "HKD", {"symbol": "0688.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_WANT_WANT_CHINA", "CHN", "yfinance", "D", "HKD", {"symbol": "0151.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_YUM_CHINA", "CHN", "yfinance", "D", "USD", {"symbol": "YUMC"}, publication_lag_days=0),
    IndicatorSpec("CHN_TRIP_COM", "CHN", "yfinance", "D", "USD", {"symbol": "TCOM"}, publication_lag_days=0),
    IndicatorSpec("CHN_FULL_TRUCK_ALLIANCE", "CHN", "yfinance", "D", "USD", {"symbol": "YMM"}, publication_lag_days=0),
    IndicatorSpec("CHN_BILIBILI", "CHN", "yfinance", "D", "USD", {"symbol": "BILI"}, publication_lag_days=0),
    IndicatorSpec("CHN_LI_AUTO", "CHN", "yfinance", "D", "USD", {"symbol": "LI"}, publication_lag_days=0),
    IndicatorSpec("CHN_NIO", "CHN", "yfinance", "D", "USD", {"symbol": "NIO"}, publication_lag_days=0),
    IndicatorSpec("CHN_XPENG", "CHN", "yfinance", "D", "USD", {"symbol": "XPEV"}, publication_lag_days=0),
    IndicatorSpec("CHN_SMIC", "CHN", "yfinance", "D", "HKD", {"symbol": "0981.HK"}, publication_lag_days=0),
    IndicatorSpec("CHN_WUXI_BIOLOGICS", "CHN", "yfinance", "D", "HKD", {"symbol": "2269.HK"}, publication_lag_days=0),
    # --- Actions KOR (lot 2, 26/09/2026) ---
    IndicatorSpec("KOR_CELLTRION", "KOR", "yfinance", "D", "KRW", {"symbol": "068270.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_LG_DISPLAY", "KOR", "yfinance", "D", "KRW", {"symbol": "034220.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SK_INNOVATION", "KOR", "yfinance", "D", "KRW", {"symbol": "096770.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SK_TELECOM", "KOR", "yfinance", "D", "KRW", {"symbol": "017670.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_KT_CORP", "KOR", "yfinance", "D", "KRW", {"symbol": "030200.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_HD_HYUNDAI", "KOR", "yfinance", "D", "KRW", {"symbol": "267250.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_HANWHA_SOLUTIONS", "KOR", "yfinance", "D", "KRW", {"symbol": "009830.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_S_OIL", "KOR", "yfinance", "D", "KRW", {"symbol": "010950.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_HYUNDAI_GLOVIS", "KOR", "yfinance", "D", "KRW", {"symbol": "086280.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_HYUNDAI_STEEL", "KOR", "yfinance", "D", "KRW", {"symbol": "004020.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_DOOSAN_ENERBILITY", "KOR", "yfinance", "D", "KRW", {"symbol": "034020.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SAMSUNG_FIRE_MARINE", "KOR", "yfinance", "D", "KRW", {"symbol": "000810.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_MERITZ_FINANCIAL", "KOR", "yfinance", "D", "KRW", {"symbol": "138040.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_LG_UPLUS", "KOR", "yfinance", "D", "KRW", {"symbol": "032640.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_LOTTE_CHEMICAL", "KOR", "yfinance", "D", "KRW", {"symbol": "011170.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_AMOREPACIFIC", "KOR", "yfinance", "D", "KRW", {"symbol": "090430.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_CJ_CORP", "KOR", "yfinance", "D", "KRW", {"symbol": "001040.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_SK_BIOPHARMACEUTICALS", "KOR", "yfinance", "D", "KRW", {"symbol": "326030.KS"}, publication_lag_days=0),
    IndicatorSpec("KOR_COUPANG", "KOR", "yfinance", "D", "KRW", {"symbol": "CPNG"}, publication_lag_days=0),
    IndicatorSpec("KOR_KAKAO_BANK", "KOR", "yfinance", "D", "KRW", {"symbol": "323410.KS"}, publication_lag_days=0),
# TOTAL lot 2 : 331 nouvelles actions

    # ===================================================================== #
    # Japon — e-Stat (PIB, CPI, balance commerciale) + BOJ (taux, JGB)
    # ===================================================================== #
    IndicatorSpec("JP_GDP", "JPN", "estat", "Q", "Md JPY, volume", {"stats_data_id": "0003348423"}, publication_lag_days=45),
    IndicatorSpec("JP_CPI_NATIONAL", "JPN", "estat", "M", "indice (2020=100)", {"stats_data_id": "0003427113"}, publication_lag_days=20),
    # ⚠️ Le statsDataId d'origine n'existait pas côté e-Stat ("STATUS: 300", vérifié le
    # 26/09/2026) : remplacé par le fichier CSV du portail métropolitain de Tokyo, déposé
    # manuellement (voir data/manual/tmi/README.md et connectors/tmi_tokyo.py). Code "0901" =
    # "tous postes, CVS" (corrigé des variations saisonnières).
    IndicatorSpec("JP_CPI_TOKYO", "JPN", "tmi_tokyo", "M", "indice", {"filename": "tmi2025c.csv", "code": "0901"}, publication_lag_days=5),
    # ⚠️ Le statsDataId d'origine n'existait pas côté e-Stat ("STATUS: 300", vérifié le
    # 26/09/2026). Remplacé par la BOJ : solde du compte courant de la balance des paiements
    # (BP01'BPBP6JYNCB) — un proxy macro proche, mais PAS identique à une balance commerciale
    # douanière stricte (le compte courant inclut aussi services, revenus et transferts, pas
    # seulement les biens). Voir data/manual/boj/README.md.
    IndicatorSpec("JP_TRADE_BALANCE", "JPN", "boj", "M", "100M JPY", {"filename": "bp01_m_1_en.csv", "code": "BP01'BPBP6JYNCB"}, publication_lag_days=20),

    # Code confirmé le 25/09/2026 par export CSV depuis stat-search.boj.or.jp (fm01_d_1.csv) :
    # taux au jour le jour sans garantie ("uncollateralized overnight call rate"), l'outil de
    # politique monétaire concret de la BOJ depuis la sortie des taux négatifs. L'API REST
    # renvoyant systématiquement une erreur en usage réel, ce connecteur lit un CSV téléchargé
    # manuellement (voir connectors/boj.py et data/manual/boj/README.md).
    IndicatorSpec(
        "JP_POLICY_RATE", "JPN", "boj", "D", "%",
        {"filename": "fm01_d_1.csv", "code": "FM01'STRDCLUCON"},
        publication_lag_days=1,
        # Pas de repli automatique : le seul candidat FRED trouvé (INTDSRJPM193N) est arrêté
        # depuis 2017 et renverrait une valeur figée sans le signaler comme telle — pire que
        # pas de donnée du tout pour un taux censé être à jour.
    ),
    # La BOJ ne publie pas de courbe de rendements JGB par échéance dans son catalogue de séries
    # temporelles (vérifié le 25/09/2026 : la section "Financial Markets" va de FM01 à FM09,
    # aucune n'est un rendement obligataire par maturité — cette donnée provient plutôt du
    # Ministère des Finances / JSDA). On utilise donc FRED, qui republie cette série (source
    # OCDE) sous un code confirmé.
    IndicatorSpec("JP_JGB_10Y", "JPN", "fred", "M", "%", {"series_id": "IRLTLT01JPM156N"}, publication_lag_days=20),

    # ===================================================================== #
    # Chine — NBS (best effort) avec repli Banque mondiale automatique
    # ===================================================================== #
    IndicatorSpec(
        "CN_INDUSTRIAL_PRODUCTION", "CHN", "nbs_china", "M", "% glissement annuel", {"db": "hgyd", "zb": "A020101"},
        publication_lag_days=15,
        fallback=IndicatorSpec("CN_IP_WB", "CHN", "worldbank", "A", "%", {"iso3": "CHN", "indicator": "NV.IND.MANF.KD.ZG"}),
    ),
    IndicatorSpec(
        "CN_PMI_MANUF", "CHN", "nbs_china", "M", "indice", {"db": "hgyd", "zb": "A0B0101"},
        publication_lag_days=1,
        # Pas d'équivalent PMI à la Banque mondiale : pas de repli pour cet indicateur précis.
    ),
    IndicatorSpec(
        "CN_EXPORTS", "CHN", "nbs_china", "M", "M USD", {"db": "hgyd", "zb": "A0D0101"},
        publication_lag_days=10,
        fallback=IndicatorSpec("CN_EXPORTS_WB", "CHN", "worldbank", "A", "% du PIB", {"iso3": "CHN", "indicator": "NE.EXP.GNFS.ZS"}),
    ),

    # ===================================================================== #
    # Inde — RBI (DBIE) et MOSPI : dépôt manuel + repli Banque mondiale
    # Délais de publication (publication_lag_days) confirmés le 26/09/2026 via le catalogue de
    # métadonnées officiel du MOSPI (feuille "META DATA") : CPI 12 jours, PIB (comptes
    # nationaux) 60 jours, réserves de change RBI ~1 semaine. Le PMI manufacturier indien est
    # publié par S&P Global (source privée), pas par le MOSPI — aucun délai officiel disponible
    # ici, et pas d'équivalent Banque mondiale non plus. Ce catalogue donne aussi des liens vers
    # les communiqués de presse PDF de chaque indicateur, mais pas de données chiffrées
    # exploitables directement : les fichiers CSV manuels restent à déposer.
    # ===================================================================== #
    IndicatorSpec(
        "IN_REPO_RATE", "IND", "manual", "D", "%", {"filename": "rbi_repo_rate.csv"},
        fallback=IndicatorSpec("IN_REPO_RATE_WB", "IND", "worldbank", "A", "%", {"iso3": "IND", "indicator": "FR.INR.RINR"}),
    ),
    IndicatorSpec(
        "IN_FX_RESERVES", "IND", "manual", "W", "M USD", {"filename": "rbi_fx_reserves.csv"}, publication_lag_days=7,
        fallback=IndicatorSpec("IN_FX_RESERVES_WB", "IND", "worldbank", "A", "M USD", {"iso3": "IND", "indicator": "FI.RES.TOTL.CD"}),
    ),
    IndicatorSpec(
        "IN_CPI", "IND", "manual", "M", "indice", {"filename": "rbi_cpi.csv"}, publication_lag_days=12,
        fallback=IndicatorSpec("IN_CPI_WB", "IND", "worldbank", "A", "%", {"iso3": "IND", "indicator": "FP.CPI.TOTL.ZG"}),
    ),
    # IN_GDP corrigé le 26/09/2026 : fichier RBI réel ("Components of Gross Domestic Product"),
    # série de croissance du PIB réel (prix constants) en glissement annuel, base 2011-12,
    # continue et cohérente sur 75 ans (exercices fiscaux indiens 1951-52 à 2025-26). Fréquence
    # ANNUELLE, pas trimestrielle comme initialement prévu — RBI/DBIE propose aussi une table
    # trimestrielle séparée ("Real GDP Growth - Expenditure Approach, Quarterly Data") si une
    # granularité plus fine est souhaitée un jour. Date = fin d'exercice fiscal (31 mars).
    IndicatorSpec(
        "IN_GDP", "IND", "manual", "A", "% glissement annuel", {"filename": "mospi_gdp.csv"}, publication_lag_days=60,
        fallback=IndicatorSpec("IN_GDP_WB", "IND", "worldbank", "A", "%", {"iso3": "IND", "indicator": "NY.GDP.MKTP.KD.ZG"}),
    ),
    IndicatorSpec(
        "IN_PMI_MANUF", "IND", "manual", "M", "indice", {"filename": "mospi_pmi.csv"},
        # Publié par S&P Global (source privée), pas le MOSPI : pas de délai officiel confirmé,
        # pas d'équivalent Banque mondiale.
    ),
    # IN_WPI : ajouté le 26/09/2026 à partir d'un vrai fichier RBI (Weekly Statistical
    # Supplement, table "Major Price Indices") — indice des prix de gros, base 2022-23=100,
    # "All Commodities". Pas d'équivalent Banque mondiale pour le WPI (concept propre à l'Inde).
    IndicatorSpec(
        "IN_WPI", "IND", "manual", "M", "indice", {"filename": "rbi_wpi.csv"}, publication_lag_days=14,
    ),
]


# Index code -> spec, construit une fois à l'import : `by_code` est appelé à chaque requête de
# l'API (et en boucle par le portefeuille / le contexte macro) ; un parcours linéaire des ~700
# entrées à chaque appel était inutile. Même sémantique qu'avant : premier code gagnant, replis
# (`fallback`) non inclus.
_BY_CODE: dict[str, IndicatorSpec] = {}
for _spec in INDICATORS:
    _BY_CODE.setdefault(_spec.code, _spec)
del _spec


def by_code(code: str) -> IndicatorSpec:
    try:
        return _BY_CODE[code]
    except KeyError:
        raise KeyError(f"indicateur inconnu : {code}") from None


def enabled(settings) -> list[IndicatorSpec]:
    """Filtre le catalogue aux indicateurs dont le connecteur est activé (clé API présente)."""
    return [s for s in INDICATORS if settings.source(s.connector).enabled]
