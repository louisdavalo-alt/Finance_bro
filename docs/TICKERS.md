# Référence des tickers Yahoo Finance (connecteur `yfinance`)

Cette liste sert à étendre `registry.py` avec de nouveaux `IndicatorSpec` utilisant le
connecteur `yfinance` (`app/connectors/yfin.py`). Rappel du format :

```python
IndicatorSpec("MON_CODE", "PAYS", "yfinance", "D", "unité", {"symbol": "TICKER"}, publication_lag_days=0)
```

`field` (optionnel, "Close" par défaut) et `period` (optionnel, "max" par défaut) peuvent être
ajoutés aux `params`.

⚠️ **Statut de vérification** : `^GDAXI` (DAX), `EURUSD=X` (EUR/USD) et `TTE.PA` (TotalEnergies,
6869 observations) ont été confirmés fonctionnels en conditions réelles à ce jour (25-26/09/2026).
Le reste de cette liste suit les conventions Yahoo Finance standard, stables depuis des années,
mais n'a pas été testé un par un dans ce projet — vérifie avec `debug_source.py` (voir README,
section 7) avant d'ajouter en masse. Yahoo Finance n'est pas une API officielle : un ticker qui
existe aujourd'hui peut disparaître ou changer de format sans préavis.

---

## Taux de change (forex)

Format : `DEVISE_BASE + DEVISE_COTATION + "=X"`

| Paire | Ticker |
|---|---|
| EUR/USD | `EURUSD=X` |
| USD/JPY | `USDJPY=X` |
| GBP/USD | `GBPUSD=X` |
| USD/CHF | `USDCHF=X` |
| USD/CNY | `USDCNY=X` |
| USD/INR | `USDINR=X` |
| EUR/GBP | `EURGBP=X` |
| EUR/JPY | `EURJPY=X` |
| AUD/USD | `AUDUSD=X` |
| USD/CAD | `USDCAD=X` |

## Indices actions

| Indice | Pays/zone | Ticker |
|---|---|---|
| CAC 40 | France | `^FCHI` |
| DAX | Allemagne | `^GDAXI` |
| FTSE 100 | Royaume-Uni | `^FTSE` |
| Euro Stoxx 50 | Zone euro | `^STOXX50E` |
| IBEX 35 | Espagne | `^IBEX` |
| FTSE MIB | Italie | `FTSEMIB.MI` |
| S&P 500 | États-Unis | `^GSPC` |
| Dow Jones Industrial Average | États-Unis | `^DJI` |
| Nasdaq Composite | États-Unis | `^IXIC` |
| Nasdaq 100 | États-Unis | `^NDX` |
| Russell 2000 | États-Unis | `^RUT` |
| Nikkei 225 | Japon | `^N225` |
| TOPIX | Japon | `^TOPX` |
| Hang Seng | Hong Kong | `^HSI` |
| Shanghai Composite | Chine | `000001.SS` |
| Shenzhen Component | Chine | `399001.SZ` |
| Sensex | Inde | `^BSESN` |
| Nifty 50 | Inde | `^NSEI` |
| VIX (volatilité) | États-Unis | `^VIX` |

## Actions individuelles

Suffixe de place boursière : `.PA` (Paris), `.DE` (Francfort/Xetra), `.L` (Londres), `.MI` (Milan),
`.AS` (Amsterdam), `.T` (Tokyo), `.HK` (Hong Kong), `.SS`/`.SZ` (Shanghai/Shenzhen), `.BO`/`.NS`
(Bombay/NSE Inde) — sans suffixe pour les cotations américaines natives.

**France (CAC 40, exemples)**

| Entreprise | Ticker |
|---|---|
| TotalEnergies | `TTE.PA` |
| Airbus | `AIR.PA` |
| LVMH | `MC.PA` |
| L'Oréal | `OR.PA` |
| Sanofi | `SAN.PA` |
| BNP Paribas | `BNP.PA` |
| Air Liquide | `AI.PA` |
| Schneider Electric | `SU.PA` |
| Danone | `BN.PA` |
| Renault | `RNO.PA` |

**Allemagne (DAX, exemples)**

| Entreprise | Ticker |
|---|---|
| SAP | `SAP.DE` |
| Siemens | `SIE.DE` |
| Volkswagen | `VOW3.DE` |
| Allianz | `ALV.DE` |
| BASF | `BAS.DE` |
| Mercedes-Benz Group | `MBG.DE` |

**États-Unis (exemples)**

| Entreprise | Ticker |
|---|---|
| Apple | `AAPL` |
| Microsoft | `MSFT` |
| Amazon | `AMZN` |
| Alphabet (Google) | `GOOGL` |
| NVIDIA | `NVDA` |
| Tesla | `TSLA` |
| ExxonMobil | `XOM` |

**Japon / Asie (exemples)**

| Entreprise | Ticker |
|---|---|
| Toyota | `7203.T` |
| Sony | `6758.T` |
| Samsung Electronics | `005930.KS` |
| Alibaba | `BABA` (ADR US) ou `9988.HK` |
| Tencent | `0700.HK` |

Pour n'importe quelle autre action : cherche "[nom de l'entreprise] stock" sur le web, la page
Yahoo Finance affiche le ticker exact en haut de la fiche.

## Cryptomonnaies

Format : `CRYPTO-USD` (ou `-EUR`)

| Actif | Ticker |
|---|---|
| Bitcoin | `BTC-USD` |
| Ethereum | `ETH-USD` |
| Solana | `SOL-USD` |
| XRP | `XRP-USD` |
| Cardano | `ADA-USD` |
| Dogecoin | `DOGE-USD` |

## Fonds / ETF

| Fonds | Ce qu'il suit | Ticker |
|---|---|---|
| SPDR S&P 500 ETF | S&P 500 | `SPY` |
| Invesco QQQ | Nasdaq 100 | `QQQ` |
| iShares MSCI World | Actions monde | `URTH` |
| iShares MSCI Emerging Markets | Marchés émergents | `EEM` |
| SPDR Gold Shares | Or physique | `GLD` |
| iShares 20+ Year Treasury Bond | Obligations d'État US long terme | `TLT` |
| iShares Core MSCI Europe | Actions Europe | `IEUR` |
| Vanguard Total Bond Market | Obligations US diversifiées | `BND` |

## Obligations / taux souverains (proxies de marché)

Yahoo Finance ne propose pas de courbe des taux complète par pays ; ces tickers sont des proxies
usuels pour les taux américains, et des ETF pour l'exposition obligataire européenne/japonaise :

| Indicateur | Ticker | Remarque |
|---|---|---|
| Rendement 13 semaines US | `^IRX` | En points de %, diviser par 10 pour le taux réel |
| Rendement 5 ans US | `^FVX` | Idem |
| Rendement 10 ans US | `^TNX` | Idem |
| Rendement 30 ans US | `^TYX` | Idem |
| ETF obligations zone euro | `IEAG.L` | iShares Euro Aggregate Bond (Londres) |
| ETF JGB (Japon) | `2510.T` | Nomura JGB ETF |

⚠️ Pas d'équivalent fiable pour un taux souverain français ou allemand précis : pour ça, rester
sur la BCE (déjà en place, `EA_DFR`/`EA_YIELD_10Y`) plutôt que Yahoo Finance.

## Matières premières (contrats à terme continus)

Format général : `CODE=F`

| Matière première | Ticker |
|---|---|
| Or | `GC=F` |
| Argent | `SI=F` |
| Cuivre | `HG=F` |
| Platine | `PL=F` |
| Pétrole brut WTI | `CL=F` |
| Pétrole brut Brent | `BZ=F` |
| Gaz naturel | `NG=F` |
| Maïs | `ZC=F` |
| Blé | `ZW=F` |
| Soja | `ZS=F` |
| Sucre | `SB=F` |
| Café | `KC=F` |
| Coton | `CT=F` |

⚠️ **Minerai de fer** : pas de ticker fiable et stable sur Yahoo Finance (contrats négociés
principalement à Singapour/Dalian, mal couverts). Si besoin, chercher un ETF minier comme proxy
(ex. `PICK` — iShares MSCI Global Metals & Mining) plutôt qu'un contrat à terme direct.

---

## Comment ajouter un de ces tickers au projet

1. Choisis un code interne (`registry.py` utilise des majuscules avec underscores, ex. `FR_TOTALENERGIES`).
2. Ajoute une ligne dans `INDICATORS` (`app/registry.py`) :
   ```python
   IndicatorSpec("FR_TOTALENERGIES", "FRA", "yfinance", "D", "EUR", {"symbol": "TTE.PA"}, publication_lag_days=0),
   ```
3. Teste-le isolément avant de relancer tout le pipeline (méthode `debug_source.py`, README section 7).
4. Une fois confirmé, relance `./run_pipeline.sh` normalement.
