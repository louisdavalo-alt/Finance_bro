# Finance Bro

Plateforme personnelle d'analyse macroéconomique et de marchés : un pipeline collecte les
statistiques officielles de plusieurs grandes économies, une API les expose, et un tableau de
bord permet de les explorer, de produire des prévisions et de construire des portefeuilles.

> ⚠️ **Outil de recherche et d'apprentissage, pas un conseil en investissement.** Les prévisions et
> les portefeuilles proposés sont des sorties de modèles statistiques, avec leurs limites
> (documentées dans le guide ci-dessous). Ne prenez aucune décision financière sur cette seule base.

## Fonctionnalités

- **Collecte multi-sources** : FRED (États-Unis), BCE (zone euro), FMI, e-Stat et Banque du Japon,
  Institut de statistique de Tokyo, NBS (Chine), Banque mondiale, RBI et MOSPI (Inde), Yahoo Finance.
  Stockage DuckDB + exports Parquet, avec gestion du biais de look-ahead (dates de publication réelles).
- **API FastAPI** : séries, panels comparables, rapport de délais de publication, cotations et
  graphiques OHLCV.
- **Tableau de bord** : exploration et comparaison d'indicateurs, fiche de cotation, 10 types de
  graphiques financiers (bougies, Heikin Ashi, Kagi, Line Break, Range bars…).
- **Prévision** : GARCH, XGBoost, détection de régimes par HMM, une quinzaine de modèles classiques
  court, moyen et long terme (ARIMA, filtre de Kalman, HAR-RV, momentum, Fama-French, CAPE, Gordon…),
  backtest walk-forward et méta-pondération (Hedge). Option : modèle de fondation Kronos auto-hébergé.
- **Portefeuille** : optimisation moyenne-variance (Markowitz) sur un univers de 619 actions filtrable par pays et secteur, et évaluation par Monte Carlo (bootstrap par blocs).
- **Sécurité** : authentification HTTP Basic, protection DNS rebinding et requêtes intersites,
  anti force brute, CSP, masquage des secrets dans les journaux — voir [`AUDIT.md`](AUDIT.md).

## Stack

**Backend** : Python 3.13, FastAPI, DuckDB, pandas, statsmodels, arch, scikit-learn, XGBoost,
hmmlearn, vectorbt · **Frontend** : React 19, TypeScript, Vite, TanStack Query, Tailwind CSS,
lightweight-charts · **Tests** : 291 tests pytest + tests JavaScript, exécutés par GitHub Actions.

## Démarrage rapide

Prérequis : Linux ou macOS (sous Windows, utilisez [WSL](https://learn.microsoft.com/fr-fr/windows/wsl/install)),
Python 3.13, et Node.js 22 pour le nouveau frontend.

```bash
git clone https://github.com/<votre-pseudo>/finance-bro.git
cd finance-bro
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock

cp .env.example .env && chmod 600 .env   # puis renseignez vos clés (voir ci-dessous)

./run_pipeline.sh    # collecte les données (une fois, puis s'arrête)
./run_api.sh         # API + tableau de bord sur http://127.0.0.1:8100
```

## Clés API

**Aucune clé n'est fournie dans ce dépôt.** Toutes sont gratuites et **toutes sont optionnelles** :
une source sans clé est simplement désactivée, et le pipeline fonctionne dès le départ avec les
sources ouvertes (BCE, Banque mondiale, Banque du Japon, Yahoo Finance).

| Variable dans `.env` | Source | Où l'obtenir |
|---|---|---|
| `FRED_API_KEY` | FRED — données américaines | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `IMF_API_KEY` | FMI — inflation française | [portail développeur du FMI](https://api.imf.org) |
| `ESTAT_APP_ID` | e-Stat — statistiques japonaises | [e-stat.go.jp](https://www.e-stat.go.jp/mypage/user/preregister) |

Copiez `.env.example` en `.env` et collez vos clés après le signe `=`. Le fichier `.env` est
ignoré par Git : vos clés ne seront jamais publiées. Si vous exposez l'API au-delà de votre
machine, `API_USERNAME` et `API_PASSWORD` deviennent obligatoires (voir section 12).

## Documentation

| Document | Contenu |
|---|---|
| Guide complet (ci-dessous) | Installation détaillée, configuration source par source, exploitation, dépannage, sécurité |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Schéma des données, biais de look-ahead, cache, choix techniques |
| [`AUDIT.md`](AUDIT.md) | Audit de sécurité et de performance |
| [`docs/TICKERS.md`](docs/TICKERS.md) | Tickers Yahoo Finance disponibles |
| [`frontend/README.md`](frontend/README.md) | Nouveau frontend React |
| [`deploy/`](deploy/) | Exemple de planification cron, correctif pour le serveur Kronos |

## Licence

Tous droits réservés. Ce code est publié à titre de consultation ; aucune réutilisation sans autorisation.
Les fichiers de `data/manual/` proviennent des publications officielles de leurs organismes
(Banque du Japon, Gouvernement métropolitain de Tokyo, Reserve Bank of India, MOSPI).

---

# Guide complet d'installation, de test et d'exploitation

Ce document réunit toutes les actions nécessaires pour faire tourner le pipeline et l'API, de
zéro jusqu'à un usage quotidien, ainsi que les pièges déjà rencontrés en conditions réelles.

## Sommaire

1. Comprendre ce qui est fourni
2. Installation
3. Configuration (`.env`), source par source
4. Premier lancement du pipeline
5. Lancer l'API de consultation
6. Pipeline et API en parallèle (l'ancien piège du verrou DuckDB, résolu)
7. Vérifier une source individuellement (méthode de débogage)
8. Sources à fichier manuel : BOJ, Tokyo, RBI, MOSPI
9. Consulter les données via l'API
10. Planifier l'exécution automatique (cron)
11. Dépannage
12. Sécurité

---

## 1. Comprendre ce qui est fourni

> Pour le schéma des données, le traitement du biais de look-ahead, le cache et le choix
> d'architecture (pourquoi pas Celery), voir `ARCHITECTURE.md`. Ce document-ci couvre uniquement
> les actions concrètes pour installer, configurer et faire tourner le projet. Pour la liste des
> tickers Yahoo Finance disponibles (indices, actions, forex, crypto, matières premières), voir
> `docs/TICKERS.md`.

Le projet a deux parties qui tournent **séparément** :

- **Le pipeline** (`run_pipeline.sh`) : se connecte aux sources, télécharge, normalise, écrit dans
  une base DuckDB (`data/macro.duckdb`) et exporte en Parquet. Il s'exécute **une fois puis
  s'arrête**. C'est lui qui fait le travail réseau.
- **L'API** (`run_api.sh`) : sert ce qui a déjà été collecté par le pipeline, via des endpoints
  JSON (`/series`, `/panel`, etc.). Elle ne fait **aucun appel réseau externe** : si le pipeline
  n'a jamais tourné, l'API n'a rien à montrer.

Le pipeline est le seul à ouvrir `data/macro.duckdb` ; l'API lit uniquement les exports Parquet
(`data/parquet/`). Les deux peuvent donc tourner en même temps (voir section 6).

## 2. Installation

Dans le dossier du projet, terminal intégré de VS Code (`` Ctrl+` ``) :

```bash
cd ~/finance-bro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock   # versions exactes testées (ou requirements.txt pour les dernières)
```

Vérifie que l'invite de commande affiche bien `(.venv)` au début de la ligne à partir de
maintenant — c'est le signe que l'environnement virtuel est actif. Toutes les commandes de ce
guide supposent qu'il l'est.

## 3. Configuration (`.env`), source par source

```bash
cp .env.example .env
chmod 600 .env   # le fichier contient tes clés API : lisible par toi seul
```

Ouvre `.env` dans VS Code. Chaque source peut rester vide : elle est alors simplement désactivée
(le pipeline continue avec les autres, sans planter). Voici l'état réel de chaque source, tel que
vérifié en conditions réelles pendant le développement :

| Source | Variable(s) à renseigner | Statut vérifié |
|---|---|---|
| **FRED** (États-Unis) | `FRED_API_KEY` | Clé gratuite sur https://fred.stlouisfed.org/docs/api/api_key.html |
| **BCE** (zone euro) | — (aucune) | ✅ Confirmé en conditions réelles : des dizaines de milliers d'observations obtenues |
| **e-Stat** (Japon) | `ESTAT_APP_ID` | ✅ Confirmé en conditions réelles (PIB, CPI national) — clé gratuite sur https://www.e-stat.go.jp/mypage/user/preregister. Deux tables devinées à l'origine (CPI Tokyo, balance commerciale) n'existaient pas et ont été remplacées (voir ligne BOJ et Tokyo ci-dessous) |
| **BOJ** (Japon, taux + balance des paiements) | — (fichiers déjà fournis) | ✅ Confirmé : `data/manual/boj/fm01_d_1.csv` et `bp01_m_1_en.csv` déjà présents et fonctionnels — voir section 8 |
| **Portail métropolitain de Tokyo** (CPI Tokyo) | — (fichier déjà fourni) | ✅ Confirmé : `data/manual/tmi/tmi2025c.csv` déjà présent et fonctionnel — remplace une table e-Stat qui n'existait pas |
| **FMI (SDMX 3.0)** (France, ou tout pays couvert) | `IMF_API_KEY` | ✅ Connecteur vérifié contre la spec officielle du FMI ; seul `FR_CPI` a un code confirmé, PIB/chômage restent sur la Banque mondiale (voir `ARCHITECTURE.md`) |
| **Yahoo Finance** (DAX, EUR/USD) | `YFINANCE_ENABLED` (aucune clé) | ⚠️ Non testé en conditions réelles ici (domaine bloqué par le pare-feu de l'environnement de développement) — données de MARCHÉ, pas des statistiques officielles (voir `ARCHITECTURE.md`) |
| **NBS Chine** | — (aucune, mais fragile) | ⚠️ Endpoint non officiel, échecs attendus depuis certains serveurs — repli Banque mondiale automatique |
| **Banque mondiale** | — (aucune) | Sert de repli pour la Chine et l'Inde |
| **RBI / MOSPI** (Inde) | — (fichiers CSV à déposer) | Voir section 8 |

Pour commencer simplement, tu peux laisser toutes les clés vides sauf celles que tu as déjà : le
pipeline collectera ce qu'il peut (au minimum BCE, sans aucune configuration).

## 4. Premier lancement du pipeline

```bash
chmod +x run_pipeline.sh run_api.sh   # une seule fois : restaure les droits d'exécution
./run_pipeline.sh
```

*(Si `chmod` ne suffit pas ou que tu préfères ne pas en dépendre : `bash run_pipeline.sh`
fonctionne toujours, avec ou sans droits d'exécution sur le fichier.)*

À la fin, tu dois voir une ligne comme :
```
INFO pipeline: pipeline terminé : 15234 observations enregistrées sur 22 indicateurs
```

**Pour garder une trace de tout ce qui s'est passé** (recommandé, surtout si des sources
échouent) :

```bash
./run_pipeline.sh 2>&1 | tee data/pipeline_debug.log
```

- `2>&1` : capture aussi les erreurs, pas seulement les messages normaux.
- `tee data/pipeline_debug.log` : affiche à l'écran **et** enregistre dans un fichier, en même
  temps — pratique pour diagnostiquer une source qui échoue.

## 5. Lancer l'API de consultation — et le tableau de bord

Dans un **autre terminal** (`Terminal > New Terminal` dans VS Code) :

```bash
cd ~/finance-bro
source .venv/bin/activate
./run_api.sh
```

Tu dois voir `Uvicorn running on http://127.0.0.1:8100`. **Ce terminal reste occupé** tant que
l'API tourne : c'est normal, ne le ferme pas et n'essaie pas d'y taper d'autres commandes.

Ouvre ensuite **http://127.0.0.1:8100** dans un navigateur (via Remote-SSH, l'onglet **Ports**
de VS Code redirige automatiquement) : c'est le tableau de bord (`app/static/dashboard.html`),
qui lit ce que le pipeline a déjà collecté — sauf pour la vue graphique avancée (ci-dessous), qui
fait un appel réseau en direct. Il propose quatre vues :
- **Aperçu** : une sélection d'indicateurs clés avec leur dernière valeur, et la répartition du
  catalogue par pays et par source.
- **Explorer** : recherche et filtre parmi tous les indicateurs, avec le graphique de la série
  choisie. Molette pour zoomer (centré sur le curseur), glisser pour déplacer la vue, double-clic
  pour réinitialiser — sur tous les graphiques du tableau de bord.
- **Comparer** : superposer jusqu'à 5 indicateurs, normalisés à 100 sur leur première date
  commune (via `/panel`, donc sans biais de look-ahead).
- **Qualité** : le délai de publication réellement observé par indicateur (`/lag-report`).

Les endpoints JSON bruts (`/indicators`, `/series/{code}`, `/panel`, `/lag-report`) restent
disponibles pour un usage programmatique — voir section 9.

### Nouveau frontend (React + TypeScript), en cours de remplacement

Un nouveau tableau de bord, plus structuré pour accueillir les futures couches de la plateforme
(sentiment, modèles, portefeuilles, paper trading), est en cours de construction dans
`frontend/` — voir `frontend/README.md` pour le détail (stack, démarrage, ce qui est déjà porté).
Il cohabite avec `dashboard.html` ci-dessus tant que tous les onglets n'ont pas été portés :

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173, proxifie vers l'API locale
```

### Fiche d'un indicateur de marché : onglets « Fiche cotation » et « Graphiques avancés »

Pour un indicateur de marché (connecteur `yfinance` : indices, actions, forex, matières
premières, crypto), la fiche d'Explorer affiche **trois onglets sous le titre** : *Série* (la
série stockée, comme pour tous les indicateurs), *Fiche cotation* et *Graphiques avancés*.

**Fiche cotation** — sur le modèle des pages de cotation d'Euronext : à gauche un tableau (devise,
dernier traité horodaté, variation, clôture veille, volume, capitaux, VWAP, ouvert, haut et bas
avec leur heure, 52 semaines, capitalisation), à droite le graphique prix (aire) + volume avec les
périodes 1D, 5D, 1M, 3M, 1Y, 5Y, YTD et MAX (zoom molette / glisser, comme partout).
- **Approximatifs** : le VWAP et les capitaux sont calculés à partir de barres de 5 minutes, pas de
  toutes les transactions ; la capitalisation vient de Yahoo (non officiel).
- **Absents** : nombre de transactions, seuils de réservation, clôture de valorisation — notions
  propres à Euronext que Yahoo ne fournit pas. Une note l'indique sous le tableau.
- Les données de Yahoo peuvent être différées.

**Graphiques avancés** — 10 types de rendu financier : bougies japonaises, barres OHLC, ligne avec
marqueurs, ligne en escalier, colonnes de volume, Line Break (nombre de lignes réglable), Heikin
Ashi, Range bars (taille de bloc réglable), Kagi (seuil de retournement en montant fixe ou en
pourcentage, réglable) et zone HLC.

### Onglet « Prévision » (Volet A : microstructure quantitative)

Un quatrième onglet, **Prévision**, calcule à la demande (bouton « Lancer le calcul », quelques
secondes) :
- une **volatilité GARCH(1,1)** (`arch`, distribution de Student) sur les rendements log
  quotidiens, avec prévision de la volatilité cumulée sur les 5 prochains jours de bourse ;
- une **prévision de rendement à 5 jours de bourse** (~1 semaine) par **XGBoost**, entraîné sur
  des indicateurs techniques (RSI, MACD, Bollinger, momentum, volatilité réalisée, volume
  relatif) — voir `app/forecast/features.py` ;
- une **validation walk-forward** (`TimeSeriesSplit`, jamais de mélange aléatoire des dates, avec
  un écart de 5 jours entre entraînement et test pour éviter toute fuite) qui compare la
  précision directionnelle du modèle à une référence naïve, fenêtre par fenêtre — voir
  `app/forecast/model.py`.

⚠️ **C'est un outil de recherche, pas un signal de trading.** Prévoir le rendement d'une action à
une semaine est notoirement difficile (un marché liquide est proche de l'efficience à cet
horizon), et une précision mesurée en backtest ne garantit rien pour l'avenir. Le tableau de bord
affiche toujours la précision du backtest à côté de la référence naïve, précisément pour éviter
de faire confiance à un modèle qui ne fait pas mieux que le hasard.

Ce volet n'inclut **ni flux d'ordres** (aucune source de carnet d'ordres n'est intégrée à ce
projet) **ni sentiment** (actualités, réseaux sociaux) — ce dernier est prévu pour un lot séparé.
Pour rendre l'analyse honnête sur ce point, `tests/test_forecast.py` inclut un test qui ajuste
tout le pipeline sur du bruit pur (une marche aléatoire sans aucun signal) et vérifie que la
précision directionnelle mesurée reste proche de 50 % — un score anormalement bon sur du bruit
serait presque toujours le signe d'une fuite de données (biais de look-ahead), pas d'un vrai
pouvoir prédictif.

Deux volets supplémentaires accompagnent GARCH/XGBoost dans ce même onglet :
- **Régime de marché** : un Hidden Markov Model à 3 états (`app/forecast/regime.py`,
  `hmmlearn`), ajusté sur le rendement et la volatilité réalisée, classe la période actuelle en
  Haussier / Baissier / Range-haute volatilité. Les états bruts d'un HMM n'ont pas d'ordre ni de
  nom : l'étiquetage se fait après coup en triant par rendement moyen, donc stable d'un
  ajustement à l'autre sur un même titre.
- **Options** : Put/Call Ratio (volume et open interest), Max Pain (le strike où les vendeurs
  d'options paieraient le moins aux détenteurs si le sous-jacent s'y réglait), et un skew de
  volatilité implicite (put ~10% hors-la-monnaie moins call ~10% hors-la-monnaie) — via
  `Ticker.option_chain()` de `yfinance` (`app/forecast/options.py`). **Pas de Gamma Exposure
  (GEX)** : Yahoo Finance ne fournit pas les Grecques par contrat, seulement la volatilité
  implicite ; un GEX exact empilerait une approximation (Black-Scholes à partir de l'IV) sur une
  donnée déjà approximative, volontairement pas fait plutôt que de l'implémenter sans le signaler.

### Modèles court terme, non liés à une IA (`app/forecast/short_term/`)

En complément de GARCH/XGBoost, cinq modèles classiques de la littérature quantitative, **aucun
n'étant une IA/un modèle entraîné** (régressions linéaires, filtre de Kalman, OLS), tous ajustés
sur le même horizon (5 jours à ~1 semaine, 21 jours à ~1 mois) via une interface commune
`HorizonModel`/`PredictionResult` (`app/forecast/model_base.py`) :

- **HAR-RV** (Corsi, 2009) — régresse la volatilité réalisée de demain sur ses composantes
  jour/semaine/mois. Modèle de **volatilité pure** : pas de vue directionnelle (`mu_pct` toujours
  à 0). Proxy de volatilité journalière : carré du rendement log (pas de vraie RV intrajournalière,
  faute de données à cette granularité dans ce projet).
- **ARIMA** sur les rendements log quotidiens — référence de rendement simple (proche d'une
  marche aléatoire avec l'ordre par défaut (1,0,0)).
- **Filtre de Kalman** (tendance locale linéaire, via `statsmodels.tsa.statespace.structural.
  UnobservedComponents` — le package `pykalman` n'étant pas installé dans ce projet) — sépare un
  niveau et une pente qui dérivent lentement dans le log-prix.
- **Ornstein-Uhlenbeck** — ⚠️ simplification à un seul actif : la version classique s'applique au
  spread de deux actifs cointégrés (paires de trading), pas au prix d'une action seule. Ce module
  applique l'OU à l'écart entre le log-prix et sa moyenne glissante (60 jours), qui a bien un
  retour à la moyenne par construction.
- **Retournement à court terme** ("short-term reversal") — ⚠️ simplification à un seul actif : le
  signal classique (Jegadeesh, 1990) est transversal (univers de titres comparés entre eux). Ce
  module régresse le rendement futur d'un titre sur son propre rendement des 5 derniers jours.

Chaque modèle échoue indépendamment des autres (un historique trop court pour l'un n'empêche pas
les autres de s'afficher), exposé dans `/forecast/{code}` sous `short_term_models` (résultats) et
`short_term_errors` (échecs). Les modèles long terme (CAPE de Shiller, Gordon/DDM,
cointégration...) de l'architecture du projet ne sont volontairement pas dans ce lot — ils
nécessitent un univers multi-titres que ce projet ne collecte pas encore en lot.

### Modèles moyen terme, non liés à une IA (`app/forecast/medium_term/`)

À horizon « 1 mois » **uniquement** (un lookback de 12 mois ou une dérive post-résultats n'a pas
de sens sur 5 jours de bourse), six modèles classiques du moyen terme (1-12 mois) s'ajoutent,
exposés sous `medium_term_models`/`medium_term_errors` (vides à horizon « 1 semaine ») :

- **Momentum 12-1** (Jegadeesh & Titman, 1993) — ⚠️ simplification à un seul actif : la version
  classique classe un UNIVERS de titres par leur rendement passé sur 12 mois (dernier mois
  exclu) ; ce module régresse le rendement futur d'un titre sur SON PROPRE rendement 12-1.
- **Time-series momentum** (Moskowitz, Ooi & Pedersen, 2012) — momentum ABSOLU : régresse sur le
  SIGNE (pas la magnitude) du rendement passé sur 12 mois, sans comparaison cross-sectionnelle.
  Pas de ciblage de volatilité (dimensionnement de position, hors scope de ce module).
- **Markov switching** (Hamilton, 1989) — `statsmodels.tsa.regime_switching.MarkovRegression` à 2
  régimes (moyenne et variance basculent) ; le rendement attendu projette la distribution de
  probabilité des régimes sur l'horizon via la matrice de transition, pas seulement le régime
  courant figé. Distinct du HMM de `regime.py` (même famille, usage différent : prévoir plutôt
  qu'étiqueter).
- **Fama-French 5 + momentum** (Fama & French, 2015 ; Carhart, 1997) — ⚠️ simplification majeure :
  les vraies séries Fama-French (Kenneth French Data Library) ne sont disponibles ni via
  `yfinance` ni ailleurs dans ce projet. Les 6 facteurs sont APPROXIMÉS par des ETF cotés (SPY,
  IWM, VTV, VUG, QUAL, USMV, MTUM, récupérés via `yfinance`) — des approximations de style, pas
  les vraies séries académiques.
- **Post-earnings announcement drift (PEAD)** (Ball & Brown, 1968) — ⚠️ double simplification :
  surprises de résultats via `Ticker.get_earnings_dates()` de `yfinance` (couverture/qualité
  variables) ; faute d'assez de surprises passées pour CE titre pour ajuster une pente propre
  (moins de 8), se rabat sur un coefficient calibré sur la littérature, PAS ajusté sur ce titre
  (signalé explicitement dans `diagnostics["fit_mode"]`).
- **VAR** (Vector AutoRegression) titre/indice de marché (^GSPC) — ⚠️ simplification : la version
  complète de l'architecture envisage un panier de séries macro/actifs ; ce module se limite à
  deux séries (titre + marché, la seule systématiquement disponible).

Les trois premiers (own-series, pas d'appel réseau) tournent dans le même thread CPU que les
modèles court terme ; les trois derniers (réseau : ETF proxys, dates de résultats, indice de
marché) tournent en tâches asyncio parallèles, comme le carnet d'options et Kronos.

### Modèles long terme, non liés à une IA (`app/forecast/long_term/`)

Toujours à horizon « 1 mois » uniquement, six modèles classiques du long terme (1-10 ans)
s'ajoutent, exposés sous `long_term_models`/`long_term_errors` (vides à horizon « 1 semaine »).
Ils raisonnent nativement en rendement/écart-type ANNUELS, mis à l'échelle de l'horizon demandé
(`app/forecast/long_term/_common.py`) — projeter un rendement annuel sur quelques jours de bourse
reste une approximation grossière, documentée comme telle. Les six ont besoin d'un appel réseau
(fondamentaux du titre, ETF proxys, taux sans risque) et tournent en tâches asyncio parallèles,
comme les modèles moyen terme réseau — il n'y a pas de volet « own-series » pour le long terme.

- **CAPE de Shiller** (Shiller, 1988/2000) — ⚠️ simplification majeure : le vrai CAPE lisse les
  bénéfices sur 10 ans ajustés à l'inflation (jeu de données Case-Shiller, indisponible dans ce
  projet). Ce module utilise le P/E trailing courant comme proxy, combiné à l'heuristique
  simplifiée « rendement réel attendu ≈ earnings yield (1/P/E) ».
- **Régression dividend yield** — ⚠️ simplification à un seul actif : la version classique est une
  régression de panel sur plusieurs décennies et centaines de titres ; ce module régresse le
  rendement futur (~1 an) d'un titre sur SON PROPRE rendement de dividende glissant. Échoue
  explicitement pour un titre sans dividende.
- **Gordon / DDM** (Gordon, 1962) — r = rendement du dividende + taux de croissance (TCAC des
  dividendes versés sur l'historique `yfinance`) ; un calcul direct, pas une régression. Échoue
  explicitement pour un titre sans dividende, ou avec moins de 3 ans d'historique de dividendes.
- **Prime de risque implicite** (façon Damodaran) — rendement attendu = taux sans risque (^TNX)
  + bêta × prime de risque du marché (earnings yield de SPY moins le taux sans risque). ⚠️ Le P/E
  de SPY est un proxy grossier des flux futurs projetés de la vraie méthode Damodaran.
- **Facteurs value/profitabilité** — même logique que Fama-French 5 + momentum (moyen terme),
  restreinte aux 2 facteurs value/profitabilité (ETF proxys VLUE, QUAL), régression long terme.
- **Cointégration / VECM** (Engle & Granger, 1987) — teste si le titre est cointégré avec l'indice
  de marché (^GSPC, test d'Engle-Granger), et si oui ajuste un VECM pour prévoir le retour vers
  l'équilibre de long terme. ⚠️ Beaucoup de titres ne sont PAS cointégrés avec le marché au sens
  statistique strict : ce modèle échoue explicitement dans ce cas plutôt que de forcer une
  relation qui n'existe pas — un échec de ce modèle est un résultat statistique légitime.

### Feature store point-in-time et interface `predict(ticker, as_of, horizon)`

Étape 1 du document d'architecture (« Feature store point-in-time + interface `predict()`
commune ») — construite SANS nouvelle table : `app/ohlcv_cache.py` (le cache incrémental de
barres OHLCV déjà utilisé par `/ohlc`/`/forecast`/`/chart`, voir plus haut) joue déjà le rôle de
`raw_prices` (une ligne par (symbole, date), upsert idempotent, persistant entre redémarrages) ;
il lui manquait juste une borne haute sur la date. `app/forecast/feature_store.py` l'ajoute
(`end=` sur `OhlcvCache.read`) et expose `read_point_in_time_bars(symbol, as_of, cache)` : les
barres de `symbol` **comme si on était à `as_of`**, jamais au-delà — aucun délai de publication à
modéliser pour une barre de marché (à la différence des séries macro et de `release_date`,
section « contexte macro » ci-dessous), donc `date <= as_of` suffit à garantir l'absence de
biais de look-ahead. Un seul cas déclenche un appel réseau : `as_of` = aujourd'hui (usage en
direct), ou rien n'est encore en cache pour ce symbole (premier backfill complet,
`period="max"`) — interroger ensuite le même titre sur plusieurs `as_of` passés différents ne
coûte plus qu'UN appel réseau au total, jamais un par date testée.

`app/forecast/predict.py` expose l'adaptateur `predict(ticker, as_of, horizon)` annoncé par le
docstring de `model_base.py` : `predict_one(model_cls, ticker, as_of, horizon, cache)` pour un
modèle précis, et `predict_all(ticker, as_of, horizon, cache)` pour les 8 modèles
point-in-time-compatibles à la fois (les 5 modèles court terme + les 3 modèles moyen terme
« own-series », qui ne lisent que `bars["Close"]` — voir plus haut), avec la même isolation des
échecs que partout ailleurs (`(résultats, erreurs)`, indexés par `HorizonModel.name`). Les 9
modèles réseau (FF5+momentum/PEAD/VAR en moyen terme, les 6 modèles long terme) restent hors de
cette interface : rendre leurs données annexes (ETF proxys, dividendes, taux sans risque) aussi
point-in-time demanderait de les stocker elles aussi dans le feature store, hors de portée de
cette étape — ils continuent de tourner « en direct » via `pipeline.run_forecast`.

⚠️ Rien ne consomme encore cette interface directement via un endpoint HTTP : elle est écrite
pour être appelée en Python — exactement ce que fait le backtest walk-forward ci-dessous.

### Backtest walk-forward (`app/forecast/backtest.py`)

Étape 2 de l'architecture (« Backtesting walk-forward (CPU) : fenêtres glissantes, frais/
slippage, IC, hit ratio, CRPS, Sharpe déflaté (vectorbt), toujours hors échantillon »), appliquée
aux 9 modèles qui peuvent tourner sur UN ticker sans appel réseau répété : les 8 modèles
point-in-time (`predict.ALL_SYNC_MODELS`) + GARCH (qui n'avait pas encore de validation hors
échantillon, contrairement à XGBoost — `model.walk_forward_backtest`, antérieur). `run_walk_forward_backtest(ticker, horizon, cache)` (consommé par `GET /ensemble/{code}`, voir plus bas) renvoie, par modèle : `ic`, `hit_ratio`, `mae_pct`, `crps_pct`, `sharpe`,
`deflated_sharpe`, et les erreurs rencontrées (jamais bloquantes pour les autres modèles).

⚠️ Hors du champ de ce backtest : les 9 modèles réseau (FF5+momentum/PEAD/VAR, les 6 modèles long
terme) coûteraient un appel réseau par point de test — bien trop lent sur une grille de dizaines
de points —, et XGBoost garde sa propre validation séparée.

Garde-fous repris du document d'architecture :

- **Fenêtre EXPANSIVE, toujours hors échantillon** : à chaque point de test `as_of`, un modèle ne
  voit que l'historique jusque-là (troncature en mémoire d'une série déjà récupérée UNE FOIS via
  `feature_store.py`, jamais de nouvel appel réseau par point testé).
- **Baseline naïve** : prévision toujours nulle (`mu_pct=0`), avec pour écart-type la volatilité
  historique réalisée jusque-là (PAS une baseline à variance nulle, qui perdrait trivialement sur
  CRPS/Sharpe) — chaque modèle doit la battre pour être jugé utile.
- **Pas entre deux points de test = l'horizon demandé** (jamais un pas fixe indépendant de
  l'horizon) : les fenêtres de réalisation ne se chevauchent JAMAIS, nécessaire pour que
  Sharpe/Sharpe déflaté (qui supposent des rendements de période indépendants) ne soient pas
  artificiellement gonflés par l'autocorrélation de fenêtres partiellement communes.
- **GARCH est volontairement non directionnel** (`mu_pct=0`, comme la baseline, mais avec SA
  PROPRE prévision de risque `sigma_pct`) : son `hit_ratio`/`ic` sont `None` (« non applicable »,
  jamais un échec), seul CRPS/Sharpe le juge sur la qualité de son estimation du risque.

Métriques, par modèle, sur les points de test réussis :
- **IC** : corrélation de rang (Spearman) entre les prévisions `mu_pct` successives d'UN modèle
  sur UN ticker et leurs réalisations — une version « dans le temps », pas cross-sectionnelle (ce
  projet n'a pas de score comparant plusieurs titres à la même date).
- **hit_ratio** : % de points où le signe de `mu_pct` a été le bon, seulement parmi les points où
  le modèle a pris position (`mu_pct != 0`) — `None` sinon.
- **mae_pct** / **crps_pct** : erreur absolue moyenne, et score de probabilité continue (CRPS,
  forme fermée pour une loi normale `N(mu_pct, sigma_pct)` — Gneiting & Raftery, 2007), qui note
  la prévision ENTIÈRE (position ET dispersion) — la seule métrique ici sensible à un `sigma_pct`
  mal calibré, donc la plus pertinente pour GARCH.
- **sharpe** / **deflated_sharpe** : sur le P&L d'une stratégie qui suit le signe de `mu_pct`
  (frais+slippage déduits à chaque position prise, ⚠️ hypothèse générique de 0,15 % aller-retour,
  non calibrée sur un courtier précis), calculés par `vectorbt` sur TOUS les modèles à la fois
  (`nb_trials` = nombre réel de modèles comparés sur ce ticker, pas une valeur arbitraire).

Vérifié par `tests/test_backtest.py` : garde-fou anti-look-ahead (des barres ajoutées plus tard
ne changent jamais une lecture passée), isolation des échecs modèle par modèle, cohérence des
métriques, non-applicabilité correcte de `hit_ratio`/`ic` pour les modèles non directionnels.

### Méta-pondération : 1/erreur récente, puis Hedge (`app/forecast/weighting.py`)

Étape 3 de l'architecture (« Pondération simple, puis Hedge ») : combine les 9 modèles du
backtest ci-dessus en UNE prévision d'ensemble par ticker, pondérée par leur performance passée
— PAS de stacking (régression sur les prévisions, citée dans la même phrase par l'architecture
mais pas encore demandée).

- **`naive_weights(models)`** : « 1/erreur récente » — poids proportionnel à `1/crps_pct` moyen
  (sur l'ensemble du backtest), nul pour tout modèle dont le CRPS moyen est >= celui de la
  baseline naïve. Si personne ne la bat, tout le poids retombe sur elle.
- **`hedge_weights(crps_series, eta=0.5)`** : poids exponentiels (Freund & Schapire, 1997),
  mis à jour point de test par point de test (`w_i *= exp(-eta * perte_i,t)`, puis
  renormalisation) — s'adapte plus vite qu'une simple moyenne aux modèles récemment performants.
  Un modèle absent à un point (historique encore trop court...) hérite de la PIRE perte observée
  ce jour-là parmi tous les modèles, pas d'une perte neutre. Le garde-fou « poids nul si la
  baseline n'est pas battue » s'applique à la fin, sur la perte CUMULÉE sur toute la période.
- **`combine_predictions(weights, predictions)`** : applique les poids aux prévisions COURANTES
  (pas historiques) des modèles pour produire un `mu_pct`/`sigma_pct` d'ensemble — `sigma_pct`
  combine la dispersion *intra*-modèle (moyenne pondérée des variances) ET la dispersion
  *inter*-modèle (variance pondérée des `mu_pct` autour de la moyenne), via la loi des variances
  totales : des modèles en désaccord rendent l'ensemble plus incertain, même si chacun est
  confiant isolément.
- **`run_weighted_ensemble_forecast(ticker, horizon, cache, method="hedge"|"naive")`** : bout en
  bout — backtest → poids → prévisions courantes des mêmes modèles → prévision combinée.

Exposé par **`GET /ensemble/{code}?horizon=1w|1m&method=hedge|naive`** (codes de marché
uniquement ; réponse mise en cache `forecast_cache_ttl_s`) : `combined` (mu/sigma d'ensemble),
`weights`, et les métriques du backtest par modèle. Appel lourd (backtest complet, environ une
minute) ; historique insuffisant → 422. Le frontend le lance à la demande (carte « Ensemble
pondéré par backtest » de l'onglet Prévision). C'est aussi la forme réutilisable comme « vue » pour
un futur optimiseur Black-Litterman (étape 6 de l'architecture). Vérifié par `tests/test_weighting.py`
et `tests/test_ensemble_api.py`.

### Horizon ~1 mois : le contexte macro déjà collecté

Un sélecteur **~1 semaine / ~1 mois** en haut de l'onglet change l'horizon du modèle XGBoost (5
jours de bourse contre 21). Ce n'est pas qu'un changement de fenêtre : à ~1 mois, le modèle reçoit
en plus le **contexte macro du pays** de l'indicateur — taux directeur, rendement souverain,
inflation — lu dans **ce que le pipeline principal a déjà collecté en base** (`app/forecast/macro_context.py`),
sans aucun appel réseau pour cette partie précise. À 1 semaine, ce contexte ne change
essentiellement pas d'un jour à l'autre et n'apporterait rien ; à 1 mois, il devient pertinent.

L'alignement passe par `resample.align_panel` (le même mécanisme anti-look-ahead que les
panneaux macro du tableau de bord) : une inflation « de janvier » publiée mi-février n'est
utilisable comme feature qu'à partir de sa date de publication réelle, jamais avant — vérifié par
`tests/test_forecast.py::test_build_macro_features_respects_release_date_no_lookahead`.

⚠️ Aucune série macro n'est disponible dans ce projet pour certains pays (Royaume-Uni, Corée du
Sud, Canada, Pologne, Mexique...) : dans ce cas, le modèle à 1 mois se rabat silencieusement sur
les seuls indicateurs techniques, comme à 1 semaine. Le statut affiché sous le bouton de calcul
indique toujours explicitement les codes macro effectivement utilisés (`macro_codes_used`), ou
leur absence — à vérifier plutôt qu'à supposer pour chaque titre.

### Prévision Kronos (modèle de fondation, auto-hébergé — optionnel)

Si tu as déployé [Kronos](https://github.com/shiyu-coder/Kronos) (modèle de fondation spécialisé
séries financières) sur ton propre serveur, une case « Ajouter une prévision Kronos » apparaît
dans l'onglet Prévision (`app/forecast/kronos_client.py`) : les dernières barres OHLCV connues
sont envoyées à un point d'accès dédié (`POST /api/forecast`, un correctif additif à ajouter à ton
fork de `webui/app.py` — voir `deploy/kronos_patch.md`), et la clôture prévue est affichée à côté
du reste.

Cette case ne s'affiche que si `KRONOS_BASE_URL` est défini (vérifié par le dashboard via
`GET /forecast-kronos-enabled`) — par défaut, cette fonctionnalité est invisible et n'a aucun
effet. L'inférence tourne sur CPU côté serveur Kronos et peut prendre une à quelques minutes :
contrairement à GARCH/XGBoost (quelques secondes), ce n'est pas instantané.

⚠️ Comme pour XGBoost, **c'est un outil de recherche** : Kronos ne « connaît » que la forme des
prix qu'on lui envoie (OHLC), pas le contexte macro ni les news — à comparer, jamais à substituer,
aux volets GARCH/XGBoost/régime déjà présents dans cet onglet.

⚠️ **`/quote` et `/chart` font un appel réseau EN DIRECT à Yahoo Finance** à chaque ouverture : le
pipeline principal ne stocke qu'une seule valeur par observation dans DuckDB (voir
`ARCHITECTURE.md`), ce qui est insuffisant pour une cotation ou pour des graphiques qui ont
besoin d'Open/High/Low/Close/Volume complets, et rien n'y est mis en cache ni stocké en base
(voir `app/quote.py`).

`/ohlc`, `/forecast` et les plages QUOTIDIENNES de `/chart` (`1M`, `3M`, `1Y`, `5Y`, `YTD`) font
exception : leur historique est mis en cache localement par l'API elle-même, dans
`data/ohlcv_cache.duckdb` (séparé de `data/macro.duckdb`, jamais touché par le pipeline — voir
`app/ohlcv_cache.py` et `app/marketdata.py`). La première fois qu'un symbole est demandé, tout
l'historique disponible est rapatrié une bonne fois pour toutes ; ensuite, un appel Yahoo Finance
n'est refait que pour les jours effectivement manquants depuis la dernière barre déjà connue — et
aucun si le cache est déjà à jour pour la journée en cours. Les fenêtres (`period=1y`, `5y`, etc.)
sont alors servies en tronquant localement cet historique, sans retélécharger quoi que ce soit.
Les trois endpoints partagent le même cache par symbole : ouvrir le graphique puis lancer une
prévision pour le même titre ne redemande l'historique qu'une fois. `1D`/`5D` (intraday, barres
de 5/30 min) et `MAX` (barres hebdomadaires) restent en appel direct — granularités différentes
de celle stockée dans le cache (quotidienne).

Les transformations (Heikin Ashi, Kagi, Line Break, Range) sont des fonctions JavaScript pures,
vérifiées par des tests unitaires avec des valeurs calculées à la main :
```bash
node tests/js/test_transforms.js
```

### Onglet « Portefeuille » : constructeur de portefeuille

Un cinquième onglet principal, **Portefeuille**, construit un portefeuille optimisé (moyenne-
variance, type Markowitz) à partir de l'historique **déjà collecté** en base — aucun appel réseau
pour cette vue, contrairement aux onglets Fiche cotation / Graphiques avancés / Prévision.

Paramètres disponibles :
- **Niveau de risque** (Faible / Modéré / Élevé) : contrôle l'arbitrage rendement/risque quand
  aucun rendement cible n'est fixé — "Faible" privilégie fortement la réduction de variance.
- **Rendement annuel cible** (optionnel) : si fixé, minimise la variance sous contrainte
  d'atteindre au moins ce rendement (moyenne historique) ; une erreur claire s'affiche si la
  cible dépasse ce que l'univers filtré permet d'atteindre.
- **Poids maximal par titre** : évite qu'un seul titre domine le portefeuille (25 % par défaut).
- **Pays** et **Secteur** : filtrent l'univers de 619 actions du registre. La classification
  sectorielle (`app/portfolio/sectors.py`) est faite manuellement à partir de ma connaissance de
  chaque entreprise, pas depuis une source officielle (GICS, ICB) — fiable dans l'ensemble, à
  vérifier toi-même si un secteur te semble étrange pour un titre précis.

⚠️ **Outil d'aide à la réflexion, pas un conseil en investissement.** Les rendements attendus
affichés sont des **moyennes historiques** — un estimateur connu pour être instable et peu fiable
(voir `app/portfolio/optimizer.py`), pas une prévision. Aucun frais, aucune fiscalité, aucune
devise de référence n'est pris en compte. L'univers réellement disponible dépend uniquement de ce
que `run_pipeline.sh` a collecté : un titre filtré par pays/secteur mais sans assez d'historique
en base (moins de ~9 mois) est exclu et listé comme tel dans la réponse, jamais silencieusement.

⚠️ **Démarrage lent de l'API avec 711 indicateurs enregistrés** : `./run_api.sh` peut prendre
jusqu'à 8-10 secondes avant de répondre (chargement du registre). Patiente avant de considérer
que ça n'a pas démarré — ce n'est pas un bug, juste le volume d'indicateurs à charger en mémoire.

#### Évaluation par Monte Carlo (bootstrap par blocs)

Une case « Évaluer par Monte Carlo » dans l'onglet Portefeuille ajoute, pour le portefeuille
obtenu, une évaluation de la distribution des performances futures possibles sur un horizon
choisi (1, 3 ou 5 ans) : percentiles du rendement final, probabilité de perte, VaR et CVaR à 95 %,
et un graphique en éventail montrant comment cette distribution s'élargit avec le temps.

La méthode (`app/portfolio/montecarlo.py`) est un **bootstrap par blocs** sur les rendements
quotidiens réels du portefeuille, pas un tirage dans une loi normale : des blocs contigus de 21
jours historiques réels (toutes les actions ensemble, pour garder leur corrélation du jour) sont
rééchantillonnés et mis bout à bout pour simuler des trajectoires plausibles. Préserver les
LIGNES complètes (plutôt que de rééchantillonner chaque action séparément) est ce qui garde la
corrélation entre actifs intacte dans chaque trajectoire simulée.

⚠️ **Un bootstrap historique reflète fidèlement ce qui s'est passé dans l'historique utilisé, pas
une prévision de l'avenir.** Un choc sans précédent dans les données (un krach plus sévère que
tout ce qui s'est produit dans la fenêtre d'historique, par exemple) n'est pas capturé. Plus
l'historique en base est long, plus la simulation a de scénarios différents à piocher.

## 6. Pipeline et API en parallèle (l'ancien piège du verrou DuckDB, résolu)

DuckDB n'autorise qu'**un seul processus à la fois** à ouvrir `data/macro.duckdb` en écriture.
Avant, l'API gardait ce fichier ouvert tant qu'elle tournait : lancer `run_pipeline.sh` (ou le
cron horaire) pendant ce temps échouait avec `Conflicting lock is held`.

**Ce n'est plus le cas.** L'API ne lit plus que les exports Parquet (`data/parquet/<code>.parquet`),
via une base DuckDB en mémoire, et n'ouvre jamais `macro.duckdb`. Le pipeline écrit chaque export
dans un fichier temporaire puis le renomme (opération atomique) : l'API voit toujours une version
complète d'une série, jamais un fichier à moitié écrit. Tu peux donc laisser `run_api.sh` tourner
en permanence et planifier le pipeline par cron.

Le verrou reste en revanche valable **entre deux pipelines** (ou un pipeline et un script de
débogage, section 7) : `run_pipeline.sh` et la ligne cron fournie utilisent `flock`, une seconde
exécution qui démarrerait pendant la première est simplement sautée.

Si tu restaures une ancienne copie de `macro.duckdb`, régénère les exports pour que l'API les voie :
`python -c "from app.config import load_settings; from app.cache import Store; s=Store(load_settings().data_dir); print(s.export_all_parquet()); s.close()"`.

## 7. Vérifier une source individuellement (méthode de débogage)

Quand un indicateur échoue et que le message du pipeline ne suffit pas à comprendre pourquoi,
inspecte la réponse brute directement — **en t'assurant d'abord que le pipeline n'est pas en train de
tourner** (section 6 ; l'API, elle, peut rester lancée). Crée un fichier, par exemple `debug_source.py`, à la racine du projet
(pas dans `app/` ni `tests/`) :

```python
import asyncio
import httpx
from app.config import load_settings
from app.cache import Store
from app.httpclient import ApiClient
from app.connectors.fred import FredConnector   # remplace par la source à tester
from app.registry import by_code

async def main():
    settings = load_settings()
    store = Store(settings.data_dir)
    async with ApiClient(settings) as client:
        conn = FredConnector(client, store, settings.cache_ttl_s)
        spec = by_code("US_FEDFUNDS")            # remplace par le code à tester
        try:
            raw = await conn.fetch_raw(spec)
            print(raw)
        except httpx.HTTPStatusError as exc:
            print("Statut :", exc.response.status_code)
            print("Corps de la réponse :", exc.response.text)

asyncio.run(main())
```

Lance-le avec `python debug_source.py`. Colle-moi le résultat (JSON, erreur HTTP, ou traceback
Python) si tu veux que je corrige le connecteur concerné — c'est exactement comme ça qu'on a
diagnostiqué et corrigé le connecteur BOJ.

## 8. Sources à fichier manuel : BOJ, Tokyo, RBI, MOSPI

Ces sources n'ont pas d'API publique stable (voir le README pour le détail par source). Elles
fonctionnent en déposant un export CSV téléchargé à la main :

| Dossier | Fichiers attendus | Instructions détaillées |
|---|---|---|
| `data/manual/boj/` | `fm01_d_1.csv`, `bp01_m_1_en.csv` (déjà fournis et fonctionnels) | `data/manual/boj/README.md` |
| `data/manual/tmi/` | `tmi2025c.csv` (déjà fourni et fonctionnel) | `data/manual/tmi/README.md` |
| `data/manual/` | `rbi_repo_rate.csv`, `rbi_fx_reserves.csv`, `rbi_cpi.csv`, `mospi_gdp.csv`, `mospi_pmi.csv` | `data/manual/README.md` |

Tant qu'un fichier n'est pas déposé, l'indicateur correspondant bascule automatiquement sur son
repli Banque mondiale quand un repli existe (annuel, moins réactif mais toujours disponible) —
sinon il est simplement absent, sans faire échouer le reste du pipeline.

## 9. Consulter les données via l'API

Une fois le pipeline exécuté au moins une fois et l'API lancée (section 5) :

```bash
curl http://127.0.0.1:8100/health
curl http://127.0.0.1:8100/indicators
curl "http://127.0.0.1:8100/series/EA_DFR"
curl "http://127.0.0.1:8100/panel?codes=EA_DFR,EA_M3&freq=M"
curl http://127.0.0.1:8100/lag-report
curl "http://127.0.0.1:8100/ohlc/DE_DAX?period=1y"
curl "http://127.0.0.1:8100/quote/FR_AIRBUS"
curl "http://127.0.0.1:8100/chart/FR_AIRBUS?range=1M"
curl "http://127.0.0.1:8100/forecast/FR_AIRBUS?period=5y"
```

- `/indicators` : liste tout le catalogue avec le nombre d'observations réellement collectées
  par indicateur (`n_obs`) — le premier réflexe pour voir ce qui a fonctionné.
- `/panel` : le tableau aligné dans le temps, sans biais de look-ahead (voir README principal,
  section sur `release_date`).
- `/lag-report` : l'écart réel observé entre la période décrite et sa date de publication
  estimée, par indicateur.
- `/quote/{code}` : résumé de cotation façon page Euronext (dernier, ouverture, haut/bas avec
  heure, volume, VWAP et capitaux approximatifs, clôture veille, 52 semaines, capitalisation),
  **à la demande** (appel direct à Yahoo Finance) — indicateurs `yfinance` uniquement.
- `/chart/{code}?range=1D|5D|1M|3M|1Y|5Y|YTD|MAX` : barres de prix + volume pour la période
  (intraday pour 1D et 5D). Les plages quotidiennes (1M/3M/1Y/5Y/YTD) partagent le même cache
  local que `/ohlc` et `/forecast` (voir section 9bis) ; 1D/5D (intraday) et MAX (hebdomadaire)
  restent en appel direct à Yahoo Finance.
- `/ensemble/{code}` : prévision d'ensemble pondérée par backtest walk-forward (CRPS, Hedge ou 1/erreur), voir « Méta-pondération » plus haut.
- `/forecast/{code}` : Volet A du système de prévision — GARCH(1,1) + XGBoost walk-forward
  (voir `app/forecast/`), **à la demande**, quelques secondes de calcul. Son historique
  (paramètre `period`) est servi par le même cache local que `/ohlc` : un même titre redemandé
  plusieurs fois dans la journée (horizons différents, pays différent pour le contexte macro...)
  ne refait aucun appel réseau pour l'historique. Indicateurs `yfinance` uniquement. Paramètre
  `kronos=true` : ajoute une prévision par le modèle de fondation Kronos auto-hébergé (voir
  `deploy/kronos_patch.md`), ignoré si `KRONOS_BASE_URL` n'est pas configuré. La réponse inclut
  aussi `short_term_models`/`short_term_errors` : les cinq modèles court terme non-IA
  (HAR-RV, ARIMA, filtre de Kalman, Ornstein-Uhlenbeck, retournement — voir
  `app/forecast/short_term/`), et, à horizon `1m` seulement, `medium_term_models`/
  `medium_term_errors` (Momentum 12-1, time-series momentum, Markov switching, Fama-French 5 +
  momentum, PEAD, VAR titre/marché — `app/forecast/medium_term/`) et `long_term_models`/
  `long_term_errors` (CAPE de Shiller, rendement du dividende, Gordon/DDM, prime de risque
  implicite, facteurs value/profitabilité, cointégration/VECM — `app/forecast/long_term/`).
- `/forecast-kronos-enabled` : indique si `KRONOS_BASE_URL` est configuré, pour que le dashboard
  masque l'option sans lancer un calcul de prévision complet juste pour le savoir.
- `/ohlc/{code}` : Open/High/Low/Close/Volume pour un indicateur de marché, servi depuis un
  **cache local** (`data/ohlcv_cache.duckdb`, mis à jour de façon incrémentale — voir section 9bis
  ci-dessus) — réservé aux indicateurs dont le connecteur est `yfinance` ; répond `400` sinon.
  Alimente la vue graphique avancée du tableau de bord (bougies, OHLC, Heikin Ashi, Kagi, Line
  Break, Range, zone HLC).

### Rechercher et ajouter une action absente du catalogue

`registry.py` est un catalogue **statique** (~700 indicateurs). Ces trois endpoints permettent de
sortir de ce catalogue, pour une action qui n'y figure pas :

```bash
curl "http://127.0.0.1:8100/market-search?q=rivian"
curl "http://127.0.0.1:8100/market-lookup/RIVN"
curl "http://127.0.0.1:8100/market-lookup/RIVN/ohlc?period=1y"
curl -X POST http://127.0.0.1:8100/market-activate -H "Content-Type: application/json" \
  -d '{"symbol": "RIVN", "name": "Rivian Automotive, Inc."}'
```

- `/market-search?q=...` : recherche libre (nom ou symbole) auprès de Yahoo Finance
  (`yfinance.Search`, même point d'accès que la barre de recherche du site). Chaque résultat
  indique `already_tracked`/`code` s'il correspond déjà à un indicateur existant (catalogue
  statique ou précédemment activé), pour éviter un doublon.
- `/market-lookup/{symbol}` et `/market-lookup/{symbol}/ohlc` : aperçu « en direct » d'un symbole
  Yahoo Finance choisi dans les résultats de recherche — appel direct, mémorisé quelques minutes
  comme `/quote`/`/chart`, **rien n'est écrit sur disque**. C'est le chemin « juste observer » :
  on regarde sans ajouter l'action à la bibliothèque active.
- `POST /market-activate` (`{symbol, code?, country?, name?}`) : **« ajouter à la bibliothèque
  active »** — déclare `symbol` comme un nouvel indicateur de marché, persisté dans
  `data/ohlcv_cache.duckdb` (table `custom_indicators`, survit au redémarrage de l'API) et
  rapatrie IMMÉDIATEMENT tout son historique dans le cache OHLCV local (section 9bis). `code` est
  dérivé du symbole si non fourni (ex. `RIVN` → `YF_RIVN`). Le nouveau code apparaît ensuite dans
  `/indicators` et fonctionne avec `/ohlc`, `/quote`, `/chart`, `/forecast` comme n'importe quel
  indicateur du catalogue statique — sans attendre le prochain passage du pipeline cron, qui ne
  connaît pas ces tickers ajoutés à la volée (ils n'ont donc pas d'observations dans
  `macro.duckdb`/Parquet, seulement dans le cache OHLCV).

## 10. Planifier l'exécution automatique (cron)

Une fois que tu es satisfait du résultat manuel, évite de relancer `run_pipeline.sh` toi-même :

```bash
crontab -e
```

Ajoute la ligne de `deploy/crontab.example` :
```
0 * * * * cd $HOME/finance-bro && umask 077 && flock -n data/.pipeline.lock .venv/bin/python -m app.pipeline >> data/pipeline.log 2>&1
```

Une exécution horaire suffit largement : aucun indicateur macro n'est publié plus vite que le
quotidien, et le cache DuckDB absorbe les appels superflus. Avec cron, plus besoin de garder un
terminal ouvert. `flock -n` garantit qu'une exécution n'en chevauche jamais une autre, et l'API
peut rester lancée pendant ce temps (section 6). Les clés API n'apparaissent plus dans
`data/pipeline.log` (elles sont masquées, voir section 12).

---

## 11. Dépannage
12. Sécurité

### `bash: ./run_pipeline.sh: Permission non accordée`
Le bit d'exécution ne survit pas toujours au transfert/dézippage.
```bash
chmod +x run_pipeline.sh run_api.sh
```
Ou, sans en dépendre : `bash run_pipeline.sh`.

### `_duckdb.IOException: ... Conflicting lock is held ...`
Ne devrait plus arriver entre l'API et le pipeline (section 6). Si le message apparaît, c'est
qu'un **autre pipeline** ou un script de débogage tient `data/macro.duckdb` : le PID est indiqué
dans le message ; attends sa fin ou arrête-le.

### `400 Invalid host header` dans le navigateur
L'API vérifie le nom d'hôte utilisé (protection contre le DNS rebinding). Par défaut seuls
`127.0.0.1` et `localhost` sont acceptés : ajoute le nom ou l'IP utilisé(e) dans
`API_ALLOWED_HOSTS` (section 12).

### `503 serveur occupé`
Trop de calculs lourds simultanés (prévision, portefeuille) : réessaie quelques secondes plus tard,
ou augmente `API_MAX_CONCURRENT_JOBS` dans `.env`.

### `curl http://127.0.0.1:8100/` renvoie une erreur ou une page vide
`GET /` sert maintenant le tableau de bord HTML (section 5), pas du JSON — un `curl` brut
affichera juste le code source de la page, ce qui est normal. Ouvre plutôt cette adresse dans un
navigateur. Pour du JSON directement, utilise un vrai endpoint (`/indicators`, `/series/{code}`,
section 9).

### Un indicateur a `"n_obs": 0` dans `/indicators`
Trois causes possibles, dans cet ordre de fréquence :
1. La source est désactivée faute de clé dans `.env` (voir le tableau de la section 3).
2. Le pipeline a rencontré une erreur pour cet indicateur précis : relance-le avec
   `./run_pipeline.sh 2>&1 | tee data/pipeline_debug.log` et regarde la ligne `WARNING` qui
   mentionne son code.
3. Pour le FMI, Yahoo Finance ou toute source où le nom exact d'une colonne/d'un ticker est
   incertain (signalé dans le tableau de la section 3) : utilise la méthode de la section 7 pour
   inspecter la réponse brute.

### `ModuleNotFoundError` en lançant un script Python
L'environnement virtuel n'est pas activé, ou le terminal n'est pas dans le bon dossier.
```bash
pwd                          # doit afficher .../finance-bro
source .venv/bin/activate    # l'invite doit afficher (.venv)
```

### Le pipeline échoue sur une source avec une erreur `403`
Peut venir soit d'un vrai blocage de la source (rare), soit — si tu testes depuis un environnement
avec un pare-feu sortant restrictif — du réseau du serveur lui-même. Vérifie avec :
```bash
curl -I https://api.worldbank.org/v2/country/FRA/indicator/NY.GDP.MKTP.KD.ZG?format=json
```
Si cette commande échoue aussi en dehors du projet, c'est le réseau du serveur qui bloque le
domaine, pas le code.

### Je veux comprendre pourquoi un connecteur échoue mais je ne sais pas lire une trace Python
Colle-moi l'intégralité du message d'erreur (tout le bloc `Traceback (most recent call last):
...` jusqu'à la dernière ligne) — c'est exactement ce format qui a permis de diagnostiquer et de
corriger le connecteur BOJ pendant le développement.

---

## 12. Sécurité

Ce qui est en place, et ce qu'il te reste à faire selon ton usage.

**Par défaut (usage local, rien à configurer)**
- L'API n'écoute que sur `127.0.0.1` : personne d'autre sur le réseau ne peut s'y connecter.
- L'en-tête `Host` est vérifié : une page web malveillante ouverte dans ton navigateur ne peut pas
  interroger ton API locale par « DNS rebinding » (avant : possible, et chaque requête pouvait
  déclencher des calculs lourds et des appels Yahoo en ton nom).
- Le tableau de bord est servi avec une Content-Security-Policy stricte (seul son propre script
  est autorisé, aucune ressource externe, pas d'affichage dans un cadre) et les chaînes venant du
  serveur sont échappées avant affichage.
- Les clés API (`FRED_API_KEY`, `ESTAT_APP_ID`, `IMF_API_KEY`) sont masquées (`***`) dans tous les
  logs et messages d'erreur. Avant, `httpx` journalisait l'URL complète de chaque requête FRED et
  e-Stat — clé comprise — dans la console et dans `data/pipeline.log`. **Si tu as déjà partagé ou
  versionné un ancien `pipeline.log`, régénère ces clés** sur les sites des fournisseurs.
- Les redirections HTTP vers un autre domaine sont refusées (elles auraient transmis la clé au
  domaine de destination), les URL de base des sources doivent être en `https://`.
- Les erreurs renvoyées par l'API sont génériques ; le détail reste dans les logs du serveur.
- Les paramètres sont validés (codes, périodes, nombre de codes par panneau, taille des
  simulations de Monte Carlo) et les calculs lourds sont limités en concurrence.
- Les fichiers déposés manuellement ne peuvent pas être lus hors de `data/manual/`.
- Scripts et cron créent base, exports et journaux avec `umask 077` (lisibles par toi seul).
- Les requêtes émises par **un autre site** ouvert dans ton navigateur (en-tête `Sec-Fetch-Site:
  cross-site`, ou `Origin` étranger sur un POST) sont refusées (403). Le contrôle du `Host` ne
  suffisait pas : une page tierce pouvait appeler `http://127.0.0.1:8100/ensemble/...` en boucle
  ou ajouter des tickers via `POST /market-activate`. curl et les scripts ne sont pas concernés.
- Tout ce que `POST /market-activate` enregistre est validé (symbole, code, pays, nom) : un champ
  `country` libre permettait auparavant d'injecter du HTML stocké dans le tableau de bord.
  Le nombre de tickers ajoutés est plafonné (`API_MAX_CUSTOM_INDICATORS`, 200 par défaut).
- Les réponses JSON portent une CSP `default-src 'none'` ; uvicorn n'envoie ni `Server` ni `Date`
  et borne les connexions simultanées (`API_LIMIT_CONCURRENCY`, 64 par défaut).

**Si tu exposes l'API sur ton réseau (`HOST=0.0.0.0`)**
1. Définis `API_USERNAME` et `API_PASSWORD` (12 caractères minimum) dans `.env` : le navigateur
   demandera ces identifiants (authentification HTTP Basic). Sans eux, `run_api.sh` refuse de
   démarrer.
   Au-delà de `API_AUTH_MAX_FAILURES` (10) mots de passe faux en `API_AUTH_FAILURE_WINDOW_S`
   (300 s) depuis une même adresse, celle-ci est bloquée temporairement (429).
2. Ajoute dans `API_ALLOWED_HOSTS` le nom ou l'IP que tu tapes dans le navigateur.
3. Mets l'API derrière un reverse proxy HTTPS (Caddy, nginx) dès qu'elle sort de ta machine :
   l'authentification Basic n'est pas chiffrée sans TLS.
4. Optionnel : `API_ENABLE_DOCS=false` masque `/docs` et `/openapi.json`.

**Dépendances**
`requirements.lock` fixe les versions exactes testées. Pour vérifier les vulnérabilités connues :
`pip install pip-audit && pip-audit -r requirements.lock` (audit du 04/11/2026 : `certifi` mis à
jour en 2026.10.18 pour PYSEC-2026-4320, plus aucune vulnérabilité connue ; `npm audit` du
frontend : aucune).
