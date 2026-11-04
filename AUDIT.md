# Audit sécurité & performance — 4 novembre 2026

Périmètre : API FastAPI (`app/`), tableau de bord historique (`app/static/dashboard.html`),
frontend React (`frontend/`), scripts de lancement, dépendances Python et npm.

Méthode : relecture manuelle de l'ensemble des modules exposés (api, security, config, serve,
caches, connecteurs, client HTTP, client Kronos), analyse statique (`bandit`), audit des
dépendances (`pip-audit`, `npm audit`), suite de tests existante (267 tests) puis tests de
non-régression dédiés (`tests/test_security_hardening.py`, 24 tests), test à chaud du serveur.

Résultat : **291 tests passent**, 0 vulnérabilité de dépendance connue restante.

Point de départ : le projet était déjà bien protégé (masquage des secrets dans les logs, contrôle
du `Host`, CSP par empreinte sur le tableau de bord, redirections même-hôte, HTTPS obligatoire,
`safe_join` contre la traversée de chemin, SQL paramétré). Les constats ci-dessous sont ce qui
restait.

## Constats et corrections

| # | Gravité | Constat | Correction |
|---|---|---|---|
| 1 | **Élevée** | **XSS stockée** : `POST /market-activate` acceptait un `country` libre, persisté puis injecté sans échappement dans les filtres pays et la répartition par pays du tableau de bord (`innerHTML`). | Validation stricte côté serveur (`MarketActivateRequest` : `symbol`, `code`, `country` par motif, `name` ≤ 120 caractères nettoyé, champs inconnus refusés) **et** échappement `esc()` des valeurs concernées côté tableau de bord. |
| 2 | **Élevée** | **Requêtes intersites** : le contrôle du `Host` bloque le DNS rebinding, mais n'importe quel site ouvert dans le navigateur pouvait appeler `http://127.0.0.1:8100/...` directement — déclencher en boucle `/ensemble` (≈ 1 min de calcul), des appels Yahoo en ton nom, ou ajouter des tickers. Avec l'auth Basic, le navigateur renvoie même les identifiants mémorisés. | Middleware `reject_cross_site` : 403 si `Sec-Fetch-Site: cross-site`, ou si `Origin` est étranger sur une méthode qui modifie l'état. Clients hors navigateur et proxy Vite non affectés. |
| 3 | Moyenne | **Force brute** : aucune limite sur les essais de mot de passe Basic. | `AuthFailureLimiter` : 10 échecs / 5 min par IP → 429 avec `Retry-After` (réglable). Les requêtes sans identifiants (invite du navigateur) ne comptent pas. Refus au démarrage d'un mot de passe trivial ou égal à l'identifiant. |
| 4 | Moyenne | **Symboles non validés** sur `/market-lookup/{symbol}` (longueur seule) : texte arbitraire transmis à yfinance et utilisé comme clé de cache. | Motif `SYMBOL_PATTERN` (`^[A-Za-z0-9^=._-]{1,20}$`) sur les paramètres de chemin et le corps de requête. |
| 5 | Moyenne | **Épuisement de ressources** : tickers ajoutables sans limite (disque) ; le rapatriement d'historique de `/market-activate` échappait à la limite de calculs simultanés ; course entre deux ajouts simultanés du même symbole. | Quota `API_MAX_CUSTOM_INDICATORS` (200), verrou d'ajout, historique rapatrié via `live.run_limited`, uvicorn borné (`limit_concurrency`, keep-alive 5 s). |
| 6 | Moyenne | **Dépendance vulnérable** : `certifi 2026.7.22` (PYSEC-2026-4320). | `requirements.lock` → `certifi==2026.10.18`. `npm audit` : rien à signaler. |
| 7 | Faible | `KRONOS_BASE_URL` non validée (reçoit l'historique en POST). | Schéma `http(s)` obligatoire, identifiants dans l'URL refusés, avertissement si HTTP hors boucle locale. |
| 8 | Faible | Réponses JSON sans CSP ; en-têtes `Server`/`Date` envoyés. | CSP `default-src 'none'; frame-ancestors 'none'` sur tout sauf `/` et `/docs`; `server_header`/`date_header` désactivés. |
| 9 | Info | `bandit` signale 9 « SQL par f-string » (B608) et 1 « bind 0.0.0.0 » (B104). | Faux positifs vérifiés : colonnes issues d'une liste blanche, valeurs toujours en paramètres liés ; B104 est une comparaison de chaîne. |

## Optimisations

| Zone | Avant | Après |
|---|---|---|
| Synchro OHLCV Yahoo (`marketdata.py`) | Quand la dernière barre est antérieure à aujourd'hui (week-end, férié, avant l'ouverture), **chaque** appel `/ohlc`, `/chart`, `/forecast`, `/ensemble` relançait un téléchargement Yahoo. Deux vues simultanées téléchargeaient deux fois. | Une synchro au plus toutes les 15 min par symbole (`OHLCV_MIN_RESYNC_S`), verrou par symbole contre les téléchargements en double. Moins de latence et moins de risque de blocage IP par Yahoo. |
| `/indicators` | Lecture de l'historique **complet** de chaque ticker ajouté, juste pour compter ses barres (N requêtes). | Une seule requête agrégée `OhlcvCache.stats()`. |
| `/indicators` (exactitude) | Un code servi par deux sources (principale + repli Banque mondiale) donnait deux lignes ; seule la dernière était gardée → `n_obs` et dernière date faux. | Fusion par code (somme des observations, date la plus récente). |

## Risques résiduels et recommandations

- **TLS** : l'API ne chiffre pas. Si elle sort de ta machine, reverse proxy HTTPS obligatoire
  (Caddy le fait en deux lignes) ; ajoute-y `Strict-Transport-Security`.
- **`/docs` activé par défaut** : passer `API_ENABLE_DOCS=false` dès que l'API est exposée.
- **Tableau de bord historique** : il construit beaucoup de HTML par `innerHTML`. Tout passe
  maintenant par `esc()` et la CSP bloque les scripts injectés, mais le nouveau frontend React
  (échappement automatique) reste la cible à terme.
- **`style-src 'unsafe-inline'`** reste nécessaire pour le tableau de bord (styles inline
  générés) ; impact limité tant que les scripts sont verrouillés par empreinte.
- **yfinance** est non officiel : sa disponibilité n'est pas garantie (déjà documenté).
- **Rotation des clés** : si un ancien `pipeline.log` (avant le masquage) a circulé, régénère
  `FRED_API_KEY` / `ESTAT_APP_ID`.

## Fichiers modifiés

`app/api.py`, `app/security.py`, `app/schemas.py`, `app/config.py`, `app/serve.py`,
`app/marketdata.py`, `app/ohlcv_cache.py`, `app/static/dashboard.html`, `requirements.lock`,
`.env.example`, `README.md` (section 12) — nouveaux : `tests/test_security_hardening.py`, `AUDIT.md`.
