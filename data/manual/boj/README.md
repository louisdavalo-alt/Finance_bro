# Dépôts manuels — Banque du Japon (BOJ)

L'API REST documentée de la BOJ (`/api/v1/getDataCode`) a été testée en conditions réelles le
25/09/2026 : elle renvoie systématiquement `"Invalid input parameters"`, y compris avec un code
de série confirmé par ailleurs. Le site web utilise en interne un script CGI hérité, non prévu
pour un usage externe. Ce connecteur lit donc un export CSV téléchargé à la main.

## Comment obtenir un fichier

1. Va sur https://www.stat-search.boj.or.jp
2. Dans "Search by statistics", déplie la catégorie qui t'intéresse (ex. "Financial Markets")
3. Clique sur l'icône de téléchargement CSV à côté de la série
4. Dépose le fichier ici, sous le nom attendu par `registry.py` (`params["filename"]`)

Le fichier `fm01_d_1.csv` (taux au jour le jour sans garantie, `JP_POLICY_RATE`) est déjà présent
— vérifié fonctionnel avec le connecteur (`tests/test_connectors_normalize.py`).

## Format (vérifié sur des fichiers réels)

Exactement 9 lignes de métadonnées, puis les données :
```
ligne 5 : "Series code" / "データコード", <code>[,<code2>,...]   <- une colonne par série
ligne 10+ : 1998/01/05,0.49                                     <- date, valeur[, valeur2, ...]
```
Accepté en anglais (UTF-8) ou en japonais (Shift-JIS) : le connecteur détecte l'encodage tout
seul. "NA" = valeur manquante (jours sans cotation).

Un fichier à colonnes multiples (plusieurs séries dans un même export) fonctionne aussi : indique
le `code` exact à extraire dans `IndicatorSpec.params`, le connecteur retrouve la bonne colonne.
