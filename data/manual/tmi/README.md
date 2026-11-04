# Dépôt manuel — CPI de Tokyo (portail métropolitain)

e-Stat n'a pas fonctionné pour cette table : le `statsDataId` deviné à l'origine n'existait pas
("STATUS: 300", vérifié le 26/09/2026). Ce connecteur lit donc un export CSV du portail
statistique métropolitain de Tokyo, déposé manuellement.

## Fichier déjà présent

`tmi2025c.csv` — vérifié fonctionnel avec `JP_CPI_TOKYO` (code catégorie `"0901"`, "tous postes,
CVS").

## Format (vérifié sur un fichier réel)

Tableau large : une colonne par catégorie de dépense, encodage Shift-JIS (repli UTF-8 automatique).

```
ligne 3 : "Group/Item code", 0901, 0902, 0906, 0921, 0924, ...   <- une colonne par catégorie
ligne 7+: 201001,86.9,88.3,89.4,78.6,94.2                         <- AAAAMM, valeur par catégorie
```

Quelques codes de catégorie utiles (voir la ligne 2, "Group/Item", pour la liste complète du
fichier) :
- `0901` : tous postes, CVS (corrigé des variations saisonnières)
- `0902` : hors frais alimentaires frais, CVS
- `0906` : hors frais alimentaires frais et énergie, CVS
- `0921` : biens, CVS
- `0924` : services, CVS

Pour mettre à jour ce fichier avec des données plus récentes, redépose un export équivalent du
portail métropolitain de Tokyo sous le même nom (ou change `params["filename"]` dans
`registry.py`).
