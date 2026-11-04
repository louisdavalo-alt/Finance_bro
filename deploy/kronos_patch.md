# Correctif à appliquer sur `~/kronos/webui/app.py`

But : exposer un point d'accès `POST /api/forecast` que `finance-bro` appelle directement
(`app/forecast/kronos_client.py`), sans dépendre de l'enchaînement pensé pour l'UI web
(`/api/load-data` → `/api/load-model` → `/api/predict`, qui s'appuie sur un état global posé par
des clics successifs). Ce correctif est **additif** : il n'enlève ni ne modifie aucune route
existante, l'UI web continue de fonctionner à l'identique.

## Pourquoi un nouveau point d'accès plutôt que réutiliser `/api/predict`

`/api/predict` lit `df` à partir de l'état déjà chargé en mémoire par un appel précédent à
`/api/load-data` (lequel attend un fichier déjà présent côté serveur, sous `data/`). Reproduire
cet enchaînement depuis finance-bro demanderait de déposer d'abord un fichier (le conteneur Kronos
n'a pas de volume partagé avec l'hôte), puis de reproduire exactement le
contrat de `/api/load-data` — non documenté au-delà de ce que montre l'UI. Un point d'accès dédié,
qui reçoit le CSV dans le corps de la requête et répond directement, évite cette dépendance et le
risque de rejouer un contrat mal deviné.

## Patch

Ajouter en haut du fichier, si absent :

```python
import io
```

Ajouter la route (n'importe où après la définition de `app = Flask(...)` et du chargement du
modèle global `predictor`, par exemple juste après `/api/predict`) :

```python
@app.route('/api/forecast', methods=['POST'])
def api_forecast():
    """Point d'accès machine-à-machine (ex. depuis finance-bro) : reçoit un CSV OHLCV brut dans le
    corps de la requête et renvoie directement la prévision, en réutilisant le modèle déjà chargé
    en mémoire (`predictor` global) — sans dépendre de l'état posé par /api/load-data côté UI."""
    global predictor
    if predictor is None:
        return jsonify({'error': 'modèle Kronos non chargé côté serveur'}), 503

    try:
        df = pd.read_csv(io.BytesIO(request.get_data()))
    except Exception as exc:
        return jsonify({'error': f'CSV illisible : {exc}'}), 400

    required_cols = ['open', 'high', 'low', 'close']
    if not all(c in df.columns for c in required_cols):
        return jsonify({'error': f'colonnes manquantes : {required_cols}'}), 400
    if 'timestamps' not in df.columns:
        return jsonify({'error': "colonne 'timestamps' manquante"}), 400
    df['timestamps'] = pd.to_datetime(df['timestamps'])
    df = df.sort_values('timestamps').reset_index(drop=True)

    try:
        lookback = int(request.args.get('lookback', 400))
        pred_len = int(request.args.get('pred_len', 120))
        temperature = float(request.args.get('temperature', 1.0))
        top_p = float(request.args.get('top_p', 0.9))
        sample_count = int(request.args.get('sample_count', 1))
    except ValueError as exc:
        return jsonify({'error': f'paramètre invalide : {exc}'}), 400

    if len(df) < lookback:
        return jsonify({'error': f'{len(df)} lignes reçues, {lookback} (lookback) requises'}), 400

    # Les `lookback` DERNIÈRES lignes : le contexte le plus récent, pour une vraie prévision du
    # futur (pas un backtest sur les premières lignes comme le ferait /api/predict sans start_date).
    x_df = df.iloc[-lookback:][required_cols].reset_index(drop=True)
    x_timestamp = df.iloc[-lookback:]['timestamps'].reset_index(drop=True)
    last_ts = x_timestamp.iloc[-1]
    freq = pd.infer_freq(x_timestamp.tail(10)) or 'B'
    y_timestamp = pd.date_range(start=last_ts, periods=pred_len + 1, freq=freq)[1:]

    try:
        pred_df = predictor.predict(
            df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp,
            pred_len=pred_len, T=temperature, top_p=top_p, sample_count=sample_count,
        )
    except Exception as exc:
        return jsonify({'error': f'échec de la prévision Kronos : {exc}'}), 500

    return jsonify({
        'timestamps': [t.isoformat() for t in y_timestamp],
        'predictions': pred_df[required_cols].to_dict(orient='records'),
        'lookback': lookback,
        'pred_len': pred_len,
        'last_known_close': float(x_df['close'].iloc[-1]),
    })
```

## Déploiement

Deux questions, propres à ton installation, conditionnent la marche à suivre exacte :

1. **Comment ce fork est-il habituellement redéployé après une modification ?** Édition en place
   du fichier + redémarrage de gunicorn, ou passage par un pipeline de déploiement (build
   d'image + redéploiement complet) ?
2. **gunicorn recharge-t-il le modèle Kronos automatiquement au redémarrage**, ou faut-il rappeler
   `/api/load-model` après chaque redémarrage du processus Flask ?

Dans le doute, l'hypothèse la plus sûre : après avoir appliqué le patch, redémarrer le
process gunicorn (`--workers 1`, donc un simple redémarrage suffit, pas de rolling restart à
gérer) et vérifier `GET /api/model-status` avant de tester `/api/forecast` — si `loaded: false`,
rappeler `/api/load-model` comme le ferait l'UI au premier chargement.

## Vérification manuelle après déploiement

```bash
curl -s http://127.0.0.1:3021/api/model-status
# puis, avec un petit CSV de test (colonnes timestamps,open,high,low,close, >= lookback lignes) :
curl -s -X POST "http://127.0.0.1:3021/api/forecast?lookback=400&pred_len=10" \
     -H "Content-Type: text/csv" --data-binary @test.csv
```

## Côté finance-bro

Une fois ce correctif en place et vérifié, ajouter dans `.env` (ou l'environnement du service) :

```
KRONOS_BASE_URL=http://127.0.0.1:3021
```

(IP/port internes, pas une éventuelle URL publique protégée par un proxy d'authentification (OAuth2 Proxy…) —
un appel serveur-à-serveur n'a pas de session de navigateur pour s'authentifier dessus ; adapter si
le service Kronos écoute ailleurs vu depuis le serveur finance-bro.) Les autres réglages
(`KRONOS_LOOKBACK`, `KRONOS_PRED_LEN`, `KRONOS_TEMPERATURE`, `KRONOS_TOP_P`,
`KRONOS_SAMPLE_COUNT`, `KRONOS_TIMEOUT_S`) ont des valeurs par défaut raisonnables (voir
`app/config.py`) et n'ont besoin d'être définis que pour les changer.

L'option « Ajouter une prévision Kronos » n'apparaît dans le tableau de bord (onglet Prévision)
que si `KRONOS_BASE_URL` est configuré (`GET /forecast-kronos-enabled`).
