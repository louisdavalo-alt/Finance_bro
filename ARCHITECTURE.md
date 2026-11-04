# Architecture technique — schéma, look-ahead, extension du catalogue

Ce document complète `README.md` (installation et exploitation) avec les détails de conception :
schéma unifié, biais de look-ahead, cache/rate limiting, et comment étendre le catalogue.

```
Registre (registry.py) ──► Connecteurs (async, un par source) ──► Schéma unifié (schema.py)
                                    │  ▲                                    │
                              cache │  │ repli si échec              DuckDB + Parquet
                          (DuckDB) │  │ (registry.fallback)                 │
                                    ▼  │                                    ▼
                              Rate limiter                    API de consultation (FastAPI)
                                                          lit UNIQUEMENT les Parquet (ParquetReader),
                                                          jamais macro.duckdb -> aucun conflit de verrou
```

## Schéma unifié

Table `observations` (DuckDB, exportée aussi en Parquet dans `data/parquet/<code>.parquet`) :

| Colonne | Description |
|---|---|
| `timestamp` | date de la période décrite (ex. "janvier 2024" pour un CPI mensuel) |
| `country` | ISO3 ou zone (`USA`, `FRA`, `DEU`, `JPN`, `CHN`, `IND`, `EA`) |
| `indicator_code` | code interne, ex. `US_CPI` |
| `value` | valeur numérique |
| `frequency` | `D`/`W`/`M`/`Q`/`A` |
| `unit` | unité (indice, %, M USD, ...) |
| `source` | connecteur d'origine |
| `release_date` | date à laquelle la donnée était réellement connue (voir ci-dessous) |
| `ingested_at` | horodatage de la collecte |

## Le point important : `release_date` et le biais de look-ahead

Un CPI daté "janvier" n'est publié que mi-février. Si un modèle est entraîné en alignant
naïvement les séries sur `timestamp`, il "voit" en janvier une donnée qu'il n'aurait pas pu
connaître à l'époque : c'est le biais de look-ahead, et c'est le genre d'erreur qui rend un
backtest excellent et un déploiement réel décevant.

Chaque `IndicatorSpec` (`registry.py`) déclare un `publication_lag_days` (estimation du délai
réel de publication). `schema.build_frame` calcule `release_date = timestamp + lag` quand la
source ne fournit pas cette date elle-même. `resample.align_panel` construit ensuite un panneau
large où, à la date T, seules les observations dont `release_date <= T` apparaissent —
peu importe la période qu'elles décrivent :

```python
from app.cache import Store
from app.resample import align_panel

df = Store(settings.data_dir).read_panel(["US_CPI", "US_FEDFUNDS"])
panel = align_panel(df, target_freq="M")   # une colonne par indicateur, alignée sans look-ahead
```

`GET /lag-report` (API) donne l'écart médian réellement observé entre `timestamp` et
`release_date` par indicateur : à comparer aux `publication_lag_days` déclarés dans
`registry.py`, et à ajuster si l'écart réel diffère (le lag par défaut est une estimation, pas
une garantie contractuelle des agences statistiques).

## Cache et limites de requêtes

- **Cache** : DuckDB (`raw_cache`), avec un TTL par fréquence (`CACHE_TTL_D/M/Q/A` dans `.env`) —
  inutile d'interroger un CPI mensuel toutes les heures. Pas de Redis à administrer pour un usage
  personnel ; si le pipeline tourne un jour sur plusieurs machines en parallèle, seule la classe
  `Store` (`app/cache.py`) serait à remplacer.
- **Rate limiting** : un seau à jetons asynchrone par source (`app/ratelimit.py`), réglable dans
  `.env` (`FRED_RATE_MAX`, etc.). Les 429/5xx sont retentés avec un backoff exponentiel et jitter
  (`app/httpclient.py`), en respectant l'en-tête `Retry-After` quand il est présent (secondes ou
  date HTTP, borné à 120 s).
- **Export Parquet incrémental et atomique** : après chaque upsert, seules les séries réellement
  modifiées (ou dont l'export manque) sont ré-exportées, directement par DuckDB (`COPY ... TO`),
  dans un fichier temporaire renommé ensuite. Une exécution horaire où tout vient du cache ne
  ré-écrit plus aucun fichier (avant : les ~700, à chaque fois).
- **Séparation lecture/écriture** : `Store` (pipeline) est le seul à ouvrir `macro.duckdb`.
  L'API utilise `ParquetReader`, une base DuckDB en mémoire qui lit les exports, avec un curseur
  par thread (une connexion DuckDB n'est pas utilisable depuis plusieurs threads à la fois) et un
  cache des agrégats (`/indicators`, `/lag-report`) invalidé par le mtime du répertoire.
- **Résilience** : l'échec d'un indicateur n'interrompt jamais les autres (`pipeline.run_one`
  isole chaque erreur) ; un indicateur avec `fallback` bascule automatiquement dessus (utilisé
  pour la Chine et l'Inde vers la Banque mondiale).

## Pourquoi l'O/H/L/C/V n'est pas dans le schéma unifié

Le schéma unifié (ci-dessus) ne garde qu'une seule `value` par observation — suffisant pour
toutes les séries macro, et pour un graphique en ligne simple. Mais les graphiques financiers
avancés du tableau de bord (bougies, barres OHLC, Heikin Ashi, Kagi, Line Break, Range) ont
besoin d'Open/High/Low/Close/Volume complets, que le connecteur `yfinance` n'extrait pourtant pas
(il ne garde que `Close`, voir `connectors/yfin.py`).

Plutôt que de migrer tout le schéma DuckDB pour un seul usage d'affichage — ce qui aurait
touché `schema.py`, `cache.py` et tous les connecteurs pour un besoin qui ne concerne que les
indicateurs `yfinance` vus depuis le tableau de bord — l'endpoint `GET /ohlc/{code}` (`app/ohlc.py`)
appelle directement `yfinance` **à la demande**, sans rien stocker en base ni mettre en cache.
C'est un compromis délibéré : plus simple et moins invasif qu'une migration de schéma, mais qui
signifie que cette vue a besoin d'un accès réseau à chaque ouverture (contrairement au reste du
tableau de bord, qui ne lit que DuckDB) — voir README, section 5. Le même principe vaut pour la
fiche cotation (`app/quote.py`, endpoints `/quote` et `/chart`) : un résumé calculé à partir de
barres quotidiennes et de barres 5 minutes de Yahoo, avec un VWAP et des capitaux volontairement
présentés comme approximatifs, et sans les champs propres à Euronext (transactions, seuils).

## Volet A du système de prévision (`app/forecast/`)

Même principe d'accès à la demande que `ohlc.py`/`quote.py`, mais pour un calcul plutôt qu'une
simple mise en forme : `features.py` calcule les indicateurs techniques (RSI, MACD, Bollinger,
momentum, volatilité réalisée) à partir de l'OHLCV récupéré en direct, `garch.py` ajuste un
GARCH(1,1)-t (paquet `arch`) pour la volatilité à court terme, et `model.py` entraîne un XGBoost
pour prévoir le rendement à 5 jours de bourse. Le point le plus important architecturalement :
`model.py` valide en **walk-forward** (`TimeSeriesSplit` avec un `gap` de 5 jours), jamais en
validation croisée aléatoire — un mélange aléatoire des dates fuiterait de l'information future
dans l'entraînement à cause de l'autocorrélation des séries financières, exactement le genre de
biais de look-ahead que `resample.py` évite déjà pour l'alignement des séries macro. Le test
`test_backtest_on_pure_noise_is_close_to_random` (`tests/test_forecast.py`) sert de garde-fou :
il ajuste tout le pipeline sur une marche aléatoire sans signal et vérifie que la précision
mesurée reste proche de 50 %, ce qui aurait détecté ce type de fuite s'il y en avait une.

Volontairement absents de ce module : le flux
d'ordres, pour lequel ce projet n'a aucune source de données, et le sentiment (actualités,
réseaux sociaux), prévu pour un lot séparé.

## Constructeur de portefeuille (`app/portfolio/`)

Différence structurelle avec `app/forecast/` : ce module ne fait AUCUN appel réseau, il lit
exclusivement ce que le pipeline principal a déjà collecté en base (comme `macro_context.py`,
même raison — pas besoin d'une deuxième connexion DuckDB, le lecteur `ParquetReader` déjà ouvert par `api.py`
est transmis à `build_portfolio`).

`sectors.py` encode une classification manuelle (pas de source API gratuite pour le GICS/ICB).
`stats.py` calcule rendement et covariance annualisés sur l'intersection des dates valides pour
tous les titres gardés (pas une union avec `ffill`, contrairement à `macro_context.py` : ici, une
covariance calculée sur des paires de dates partiellement manquantes serait franchement fausse,
pas juste approximative — la rigueur exigée est différente de l'alignement d'une seule série macro
contre des prix quotidiens). `optimizer.py` utilise `scipy.optimize.minimize` (SLSQP), déjà présent
comme dépendance transitive de `scikit-learn`/`arch` : pas de nouvelle bibliothèque ajoutée pour
ce lot. Le test `test_min_variance_two_uncorrelated_assets_closed_form` vérifie l'optimiseur
contre une solution à forme fermée connue (poids inversement proportionnels à la variance pour
deux actifs non corrélés) — le genre de test qui aurait détecté une erreur de signe ou de
formulation du problème quadratique, bien plus fiable qu'un test structurel seul.

Piège rencontré en testant l'intégration HTTP complète : avec 711 indicateurs enregistrés,
`./run_api.sh` mettait jusqu'à 8-10 secondes à répondre à sa première requête. Un test qui suppose un démarrage en 2 secondes échoue par pur artefact de timing, pas
à cause d'un bug — d'où l'attente active sur `/health` plutôt qu'un délai fixe dans les scripts de
test de ce module.

### Évaluation par Monte Carlo (`montecarlo.py`)

Bootstrap PAR BLOCS (pas i.i.d. jour par jour) sur les rendements quotidiens réels déjà calculés
par `stats.compute_return_stats` (son 4e élément de retour, ajouté pour ce lot — signature
changée de 3 à 4 éléments, un seul appelant réel donc migration sans risque). Rééchantillonner
des LIGNES complètes de la matrice de rendements (toutes les actions d'un même jour historique
ensemble), plutôt que chaque colonne séparément, est ce qui préserve la corrélation entre actifs
dans chaque trajectoire simulée — vérifié par
`test_bootstrap_preserves_cross_asset_correlation` (deux actifs en relation B=2×A stricte dans
l'historique : cette relation doit survivre exactement dans les trajectoires rééchantillonnées).

Piège rencontré en écrivant le test de plausibilité contre l'approximation log-normale
analytique : comparer la médiane simulée à la moyenne THÉORIQUE utilisée pour générer les données
de test échouait largement, alors que le code était correct — sur un historique fini, la moyenne
EMPIRIQUE réalisée peut s'écarter significativement de la moyenne théorique par pur bruit
d'échantillonnage (ici, -0,07 % réalisé contre 0,04 % théorique sur 800 tirages). Le bootstrap
reflète fidèlement l'historique qu'on lui donne, pas le processus sous-jacent qui l'a généré —
exactement la limite documentée du module, retombée sur le test lui-même. Corrigé en comparant à
l'approximation log-normale calculée sur la moyenne empirique réelle des données fournies.

### Extension : régime de marché (HMM) et options

`regime.py` ajuste un `GaussianHMM` (`hmmlearn`) avec `covariance_type="diag"` plutôt que
`"full"` : avec seulement 2 variables (rendement, volatilité réalisée), une covariance pleine
devient facilement numériquement singulière faute de données assez distinctes entre états — un
vrai bug rencontré en testant (`'covars' must be symmetric, positive-definite`), corrigé en
passant en diagonale (perd la modélisation de la corrélation rendement/volatilité entre états,
ce qui n'est pas ce qu'on cherche à capturer ici).

`options.py` calcule PCR, Max Pain et un skew d'IV à partir de `Ticker.option_chain()` de
`yfinance`. Un deuxième bug réel trouvé en testant : `pandas.Index` n'a pas de méthode `.clip()`
dans la version installée (contrairement à une `Series`) — corrigé en convertissant en tableaux
NumPy avant de calculer les paiements par strike dans `max_pain()`. Pas de Gamma Exposure : voir
le README.

### Extension : horizon 1 mois et contexte macro (`macro_context.py`)

Différence structurelle avec le reste de `app/forecast/` : tous les autres modules font un appel
DIRECT à `yfinance`, rien n'est stocké. `macro_context.py` lit au contraire ce que le pipeline
PRINCIPAL a déjà collecté dans DuckDB (via le lecteur `ParquetReader` déjà ouvert par `api.py`, transmis à
`run_forecast` plutôt que d'ouvrir une deuxième connexion — le piège du verrou DuckDB documenté
plus haut s'applique aussi ici, une deuxième connexion n'est pas nécessaire et aurait été un
risque pour rien).

L'alignement réutilise `resample.align_panel` tel quel (merge_asof sur `release_date`) plutôt que
de réinventer un mécanisme similaire — cohérence avec le reste du projet, et évite de refaire les
erreurs déjà corrigées une fois dans `resample.py`.

Un problème d'architecture pré-existant, repéré en construisant ce module, méritait d'être
corrigé ici : quand un indicateur n'a que son repli (`fallback`) qui a réellement des données en
base (ex. `IN_REPO_RATE`, dont le fichier manuel n'a jamais été déposé — seul `IN_REPO_RATE_WB`
existe), `store.read_series("IN_REPO_RATE")` renvoie vide alors que l'information existe bel et
bien, juste sous un autre code. `macro_context._resolve_codes` interroge donc systématiquement le
code déclaré ET son repli, et fusionne les deux sous le nom du code déclaré. Cette même ambiguïté
affecte aussi `/indicators` (qui n'affiche jamais le repli comme sa propre ligne) — non corrigée
ailleurs pour l'instant, seulement contournée ici où elle aurait silencieusement fait disparaître
du contexte macro pourtant disponible.

## Planification : pourquoi pas Celery

`python -m app.pipeline` s'exécute une fois puis se termine : c'est fait pour être planifié par
cron, pas pour tourner en tant que service. Celery a été volontairement écarté pour cet usage : il
demande un broker (Redis/RabbitMQ) qui tourne en permanence, pertinent pour plusieurs workers
distribués, pas pour un pipeline personnel mono-machine. `app/scheduler.py` propose une
alternative en un seul processus (APScheduler, bibliothèque Python pure) si tu préfères éviter
cron ; si tu passes un jour à plusieurs machines, remplacer ce fichier par des tâches Celery ne
changerait rien au reste du code (`pipeline.run_all()` resterait la fonction appelée).

## Étendre le catalogue

Ajouter un indicateur = ajouter une ligne dans `registry.py` (`IndicatorSpec`), pas une ligne de
code. Les `params` attendus par chaque connecteur sont documentés en tête de son fichier
(`app/connectors/<source>.py`).

## Historique des sources vérifiées vs. devinées

Pour ne pas répéter les erreurs déjà rencontrées :

- **FRED, BCE, e-Stat, FMI (SDMX 3.0)** : formats d'API stables et documentés. BCE et e-Stat ont
  été confirmés en conditions réelles (des dizaines de milliers d'observations obtenues). Le
  connecteur FMI a été construit directement à partir du fichier OpenAPI officiel fourni par
  l'utilisateur (`idata-sdmx-api-3-0.json`) — remplace l'INSEE pour la France, avec un code
  confirmé pour le CPI (`FR_CPI`, dataflow `IMF.STA:CPI`, clé `FRA.CPI.*.IX.M`, reprise de
  l'exemple officiel de la doc). PIB et chômage n'ont pas d'exemple documenté équivalent : ils
  restent sur la Banque mondiale en attendant qu'un code soit trouvé via le navigateur de données
  du FMI (même méthode que pour la BOJ, section suivante).
- **BOJ** : l'API REST documentée (`/api/v1/getDataCode`) renvoie systématiquement
  `"Invalid input parameters"` en usage réel, y compris avec un code de série confirmé par
  ailleurs (le site utilise en interne un script CGI hérité, non prévu pour un usage externe). Le
  connecteur a été réécrit pour lire un export CSV téléchargé à la main, et testé avec de vrais
  fichiers (`tests/fixtures/*.csv`, `data/manual/boj/README.md`).
- **JGB 10 ans** : la BOJ ne publie pas de courbe de rendements par échéance dans son catalogue de
  séries temporelles (vérifié : la section "Financial Markets" va de FM01 à FM09, aucune n'est un
  rendement obligataire par maturité). Repli sur FRED (`IRLTLT01JPM156N`, source OCDE).
- **e-Stat, tables invalides (26/09/2026)** : les `statsDataId` devinés pour `JP_CPI_TOKYO` et
  `JP_TRADE_BALANCE` n'existaient pas côté e-Stat (`STATUS: 300`, "l'ID n'existe pas"), alors que
  ceux de `JP_GDP` et `JP_CPI_NATIONAL` se sont révélés corrects par chance. Remplacés par des
  fichiers déposés manuellement : `JP_CPI_TOKYO` par un export du portail métropolitain de Tokyo
  (`connectors/tmi_tokyo.py`, format "tableau large" différent de la BOJ et d'e-Stat), et
  `JP_TRADE_BALANCE` par la BOJ (`BP01'BPBP6JYNCB`, solde du compte courant de la balance des
  paiements) — un proxy macro proche mais pas identique à une balance commerciale douanière
  stricte, car le compte courant inclut aussi services, revenus et transferts.
- **INSEE** : retiré du projet (remplacé par le FMI, voir ci-dessus) — le flux d'authentification
  de l'INSEE avait changé plusieurs fois et n'a jamais pu être confirmé en conditions réelles.
- **Destatis — abandonné (25/09/2026).** L'API a changé deux fois de suite en cours
  d'investigation : d'abord une désactivation confirmée des GET avec identifiants dans l'URL
  (30/06/2025, redirection vers une page d'annonce plutôt qu'une erreur propre), corrigée en
  passant en POST + authentification HTTP Basic sur le nouveau domaine `genesis.destatis.de` —
  puis un deuxième échec (`401`, code d'erreur GENESIS 15 : "access data cannot be recognised")
  qui a résisté à quatre formats d'authentification testés en `curl` (identifiants en corps de
  formulaire, en en-têtes bruts `username`/`password`, en Basic Auth standard). Plutôt que de
  continuer à deviner un cinquième format sans documentation fiable, le connecteur a été retiré.
  Remplacé par **Yahoo Finance** (`app/connectors/yfin.py`) pour deux indicateurs de marché
  (`DE_DAX`, `EA_EURUSD`) et par la **Banque mondiale** pour l'inflation et la production
  industrielle allemandes (`DE_IPI_WB`, `DE_HICP_WB`, annuelles). Ce ne sont **pas** des
  équivalents à l'indice de production mensuel ou au HICP mensuel que Destatis aurait fourni —
  si ces séries précises redeviennent nécessaires, il faudra soit un vrai compte GENESIS (pas
  GAST) pour retester l'authentification, soit une autre source.
- **Yahoo Finance (yfinance)** : bibliothèque non officielle (Yahoo n'a plus d'API publique
  depuis 2017), qui imite l'empreinte TLS d'un navigateur (`curl_cffi`) pour accéder aux points
  d'accès internes du site — aucune garantie de stabilité, peut casser sans préavis si Yahoo
  change ses pages. Le connecteur délègue tout le réseau à `yfinance.Ticker(...).history(...)`
  (appelé dans un thread via `asyncio.to_thread`, la bibliothèque étant synchrone) plutôt que de
  ré-implémenter l'authentification par cookie/jeton "crumb" qu'elle gère déjà. Non testé en
  conditions réelles dans cet environnement de développement (domaine `finance.yahoo.com`
  hors de la liste blanche du pare-feu) — le câblage (thread, cache, non-blocage du pipeline en
  cas d'échec) a en revanche été vérifié : l'appel réseau réel a bien été tenté et a échoué
  proprement sur le pare-feu, sans faire planter le reste du pipeline.
- **NBS Chine, RBI, MOSPI** : pas d'API publique stable — best effort avec repli Banque mondiale
  (Chine), dépôt CSV manuel (Inde).

## Sécurité et performances (revue d'octobre 2026)

Résumé des changements ; le détail utilisateur est dans le README, section 12.

| Problème constaté | Correctif | Fichier(s) |
|---|---|---|
| Clés FRED / e-Stat en clair dans les logs (`httpx` journalise l'URL complète au niveau INFO ; messages `HTTPStatusError`) | Filtre de masquage sur tous les handlers, `httpx` en WARNING, URL masquées dans les erreurs | `security.py`, `httpclient.py` |
| Redirection vers un autre domaine = clé (query string, en-tête FMI) envoyée à ce domaine | Redirections suivies manuellement, même hôte uniquement, jamais HTTPS→HTTP | `httpclient.py` |
| `Retry-After` en date HTTP faisait planter, valeur énorme bloquait le pipeline | Analyse secondes/date, borne 120 s | `httpclient.py` |
| API locale joignable par DNS rebinding depuis n'importe quel site | `TrustedHostMiddleware` | `api.py` |
| Aucune authentification si l'API est exposée | HTTP Basic optionnelle ; refus de démarrer sur une IP publique sans elle | `security.py`, `serve.py` |
| Messages d'exception bruts renvoyés au client et insérés en `innerHTML` | Erreurs génériques côté API, `esc()` côté tableau de bord, CSP stricte (empreinte du script) | `api.py`, `dashboard.html` |
| Paramètres libres transmis à yfinance, panneaux et Monte Carlo non bornés | Motifs de validation, plafonds | `api.py` |
| Lecture possible hors de `data/manual/` via un `filename` du registre | `safe_join` | `connectors/base.py` |
| API et pipeline ne pouvaient pas tourner ensemble (verrou DuckDB) | API sur les exports Parquet | `cache.py`, `api.py` |
| Connexion DuckDB partagée entre la boucle asyncio et le pool de threads (non sûr) | Curseur par thread | `cache.py` |
| Prévision (XGBoost ×6, GARCH, HMM) exécutée DANS la boucle asyncio : serveur figé plusieurs centaines de ms à chaque calcul | Calcul dans un thread, options récupérées en parallèle, cache 15 min, concurrence limitée | `forecast/pipeline.py`, `livecache.py` |
| `/lag-report` chargeait toute la base dans pandas à chaque appel (~2 s) | Agrégat SQL mis en cache (~5 ms) | `cache.py` |
| Monte Carlo : boucle Python par trajectoire | Vectorisé, résultats identiques à graine égale (3-4× plus rapide) | `portfolio/montecarlo.py` |
| Optimiseur : gradients estimés par différences finies | Gradients analytiques (jusqu'à 7× plus rapide sur 30 titres) | `portfolio/optimizer.py` |
| Planificateur : `max_instances=1` inopérant (tâche lancée puis rendue aussitôt) | Tâche coroutine + verrou | `scheduler.py` |
