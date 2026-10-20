# Analyse de dégradation : méthode, résultats, limites

Tables : `marts.fact_degradation` (trajectoires), `marts.cell_degradation_summary` (une ligne par cellule),
`marts.cell_lifetime` et `marts.rul_backtest` (genou et fin de vie, écrites par `make analyze`).

## Méthode

1. **Décharges retenues** : valides uniquement (cf. `docs/dataset.md`), soit 2 541 sur 2 794.
2. **Condition principale** : la capacité dépend de la température et du courant. Pour chaque cellule on ne garde que
   la condition (température arrondie, courant de crête arrondi) la plus fréquente. 6 cellules ont plusieurs
   conditions (B0038-40 : 24/44 °C et 1/2/4 A ; B0042-44 : 22 °C/2 A puis 4 °C/1 A). Résultat : 2 419 points de
   trajectoire, 122 décharges valides écartées. Sans cela un changement de régime ressemblerait à du vieillissement.
3. **Lissage et pic** : médiane glissante sur 5 décharges. Plusieurs cellules *montent* d'abord en capacité
   (conditionnement : B0033 passe de 1,16 à 1,61 Ah, B0007 et B0033 culminent après 20 décharges). La référence n'est
   donc pas la première mesure mais le **pic de la capacité lissée** ; la dégradation se mesure après (`is_post_peak`).
4. **Pente de perte** : régression linéaire de la capacité mesurée sur le rang de décharge, après le pic, exprimée en %
   de la capacité nominale (2,0 Ah) pour 100 décharges. `fade_estimate_quality` : `reliable` si au moins 20 points et
   r2 >= 0,5 ; `insufficient` sous 10 points ; sinon `weak`. **Les pentes `weak` et `insufficient` ne sont pas
   exploitables** (B0049-51 affichent 130 à 170 %/100 décharges, B0052 -712 % sur 4 points).
5. **Seuil de fin de vie** : NASA donne des Ah absolus (1,4 Ah = 30 % ou 1,6 Ah = 20 % de 2,0 Ah). Cela n'a de sens que
   si la cellule démarre nettement au-dessus : à 4 °C, plusieurs cellules sont sous 1,4 Ah dès la première décharge, à
   cause de la température. Règle : seuil absolu si le pic >= 1,15 x le seuil NASA (`eol_basis = nasa_absolute`),
   sinon la même perte relative appliquée au pic de la cellule (`relative_to_peak`). **Le facteur 1,15 est une
   heuristique** (variable dbt `eol_absolute_margin`). 12 cellules n'ont aucun seuil (B0025-32 : non précisé par
   NASA ; B0049-52 : essai arrêté par un plantage logiciel).
6. **Genou** (Python, `src/analytics/knee.py`) : régression continue à une cassure (hinge) sur la capacité lissée,
   avec balayage de la position. Retenu si la pente après est négative et au moins 1,5x plus raide, et si l'erreur
   baisse d'au moins 20 % par rapport à une droite. Appliqué aux cellules avec au moins 30 points après le pic (22).
7. **Prévision de fin de vie** (`src/analytics/eol.py`) : droite sur la capacité lissée après le pic, extrapolée
   jusqu'au seuil. Une prévision n'est publiée (`extrapolated`) que si l'ajustement est `reliable` ET si la fin de vie
   prévue est plus proche que la durée déjà observée. Sinon `unreliable_forecast`, sans chiffre. Un RUL négatif
   (droite qui franchit le seuil avant la dernière mesure) est ramené à 0 : fin de vie imminente.

## Résultats

- **Fin de vie franchie** pour 6 cellules sur 22 ayant un seuil : B0005 (décharge 125), B0006 (109), B0018 (97),
  B0033 (179), B0034 (150), B0045 (50).
- **Prévision publiée** pour 9 cellules (B0007, B0036, B0041, B0043, B0044, B0046, B0047, B0048, B0054), **refusée** pour
  7 (B0038, B0039, B0040, B0042, B0053, B0055, B0056).
- **Genou détecté** dans 2 cellules sur 22 : B0005 (décharge 27 après le pic, pente 5,3x plus raide) et B0036
  (décharge 177, 2,9x). Les autres courbes sont proches d'une droite ou trop bruitées : ce n'est pas un résultat de
  "pas de genou", c'est "pas de cassure détectable avec ces seuils".
- **Pente de perte** (cellules `reliable`) : 17 à 25 %/100 décharges à 24 °C et 2 A (B0005-18) ; 16 à 27 %/100 à 43 °C
  (B0029-32) ; 19 à 31 %/100 à 22 °C (B0042-44). Aucun effet net de la température n'apparaît, et il n'est pas
  identifiable ici : les groupes diffèrent aussi par la tension de coupure (2,0 à 2,7 V) et le courant.

## Précision de la prévision (backtest, 6 cellules)

On rejoue la prévision comme si l'on n'avait observé que la fraction f de la vie, puis on compare à la vraie fin de vie.

| Fraction observée | Erreur absolue moyenne | Erreur relative moyenne | Intervalle à 95 % contient la vérité |
|---|---|---|---|
| 50 % | 35,7 décharges | 29 % | 2 sur 6 |
| 70 % | 19,8 | 16 % | 1 sur 6 |
| 90 % | 10,0 | 9 % | 2 sur 6 |

- L'erreur baisse avec la part observée, mais **n = 6** : ce sont des ordres de grandeur, pas une validation.
- **Les intervalles sont trop étroits** : ils ne reflètent que l'incertitude sur la pente, pas l'erreur de modèle. À 70 %,
  la vraie valeur n'est dans l'intervalle qu'une fois sur six. Ne pas les lire comme des intervalles à 95 %.
- Cas extrême : B0005 prévue à 200 pour une fin de vie réelle à 125 (observé 50 %), car sa perte s'accélère après un
  début lent. Une droite sous-estime la perte future quand la courbe s'accélère.

## Limites à garder en tête

- Heuristiques assumées : seuil de validité des capacités (25 % du nominal), condition principale, marge 1,15 sur le
  seuil NASA, seuils de qualité (20 points, r2 0,5), seuils du genou. Aucun n'est calibré sur une vérité terrain.
- La capacité est mesurée avec des tensions de coupure différentes selon les cellules : les comparaisons entre
  cellules sont indicatives.
- Cellules froides (4 °C) : capacité très basse, comportement mal compris même par NASA (les README le disent).
- Le lissage médian sur 5 décharges déplace légèrement le franchissement du seuil de fin de vie.
