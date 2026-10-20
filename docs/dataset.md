# Dataset : NASA PCoE Li-ion Battery Aging

## Source
- Portail : https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/ (entrée 5, "Battery Data Set")
- Fichier : https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip
- Zip : 209 708 670 octets, sha256 `82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e` (Last-Modified 2022-09-18)
- Licence : non précisée sur la page NASA (à citer comme source dans le README).
- Téléchargé dans `data/nasa_zip/` (gitignoré), extrait dans `data/nasa_raw/` (~401 Mo).

## Format réel
Pas de CSV. Zip contenant 6 zips imbriqués, eux-mêmes contenant des `.mat` MATLAB (un par cellule, `B00xx.mat`) et des README.

Structure : tableau `cycle`, chaque entrée = `type` (charge | discharge | impedance), `ambient_temperature`, `time` (date vector MATLAB), `data` (mesures, séries temporelles).
- discharge : Voltage_measured, Current_measured, Temperature_measured, Current_charge, Voltage_charge, Time, **Capacity** (Ah)
- charge : mêmes champs, sans Capacity
- impedance : Sense_current, Battery_current, Current_ratio, Battery_impedance, Rectified_impedance, Re, Rct

## Pièges pour l'ingestion
- **Doublons** : B0025 à B0028 sont présents dans `2. ..._25_26_27_28_P1/` ET `3. ..._25-44/` (B0025 vérifié identique octet par octet). Dédupliquer par id de cellule.
- **Conditions d'essai hétérogènes** (lues dans les README) : courant de décharge 2 A ou 4 A, tension de coupure de 2,0 à 2,7 V, température ambiante variable, fin de vie à 30 % de perte (B0005/6/7/18) ou 20 % (groupe 33-36). Ces paramètres doivent devenir des colonnes de `dim_battery`, sinon les SOH ne sont pas comparables entre cellules.
- La capacité nominale (2 Ah) est à confirmer cellule par cellule avant de calculer le SOH.
- `time` est un date vector MATLAB : conversion en timestamp à faire à l'ingestion.
- Volumétrie : le gros du volume est dans les séries temporelles intra-cycle, pas dans le nombre de cycles. À mesurer après conversion.

## Décision de modélisation à prendre
Charger les séries intra-cycle complètes dans `raw` (volumineux) ou seulement un résumé par cycle (capacité, durées, tension et température min/max) ? À trancher après mesure.

## Volumétrie mesurée (34 cellules uniques, 38 fichiers dont 4 doublons)
- Cycles : 2 815 charge, 2 794 décharge, 1 956 impédance.
- Lignes de séries temporelles : ~6,5 M (charge), ~0,77 M (décharge), ~0,09 M (impédance).
- Un résumé par cycle de décharge = ~2,8 k lignes seulement. Séries complètes = ~7,4 M lignes.

## Anomalies de données constatées (à traiter en staging)
- Capacité initiale très basse sur plusieurs cellules (B0033 0,068 Ah, B0039 0,119, B0041 0,056) : cycles de départ non représentatifs, pas un vrai SOH.
- Capacité finale à 0 (B0053, B0054) ou NaN (B0050, B0052 : champ Capacity vide sur 4 et 21 cycles de décharge).
- Capacité non monotone : B0031 reste à 1,667 Ah, B0036/B0039 remontent. Fin de vie non atteinte pour plusieurs cellules (B0025-28, B0029-32).
- Températures ambiantes multiples sur une même cellule (4, 22, 24, 43, 44 °C) : la température est une colonne du cycle, pas de la cellule.
- Le SOH doit donc se calculer sur des décharges valides uniquement (Capacity non vide, > 0, plausible), avec une capacité de référence choisie par cellule.

## Découvertes de l'étape 3 (ingestion)
- **Le README NASA est inexact sur les noms de champs.** En décharge, les champs sont Current_load / Voltage_load (le README dit Current_charge / Voltage_charge) ; en impédance, Rectified_Impedance prend un I majuscule. Le loader se fie aux fichiers, pas à la doc.
- **Re et Rct complexes** dans B0049 (8 cycles) et B0051 (1 cycle) : parties imaginaires non nulles (valeurs conjuguées). `raw.nasa_cycles.re_ohm/rct_ohm` = partie réelle, `re_imag_ohm/rct_imag_ohm` = partie imaginaire. Décision d'usage laissée au staging ; ces cycles sont a priori suspects.
- **Capacités à 0 plus répandues que vu en échantillonnant** : 1 à 3 décharges à 0 dans B0042 à B0054 (sauf B0052), en plus des valeurs vides de B0050 (4) et B0052 (21). Conservées telles quelles dans raw (NULL pour vide, 0 pour 0).
- **Chargement** : `make ingest` charge les 34 cellules en ~4 s. Les séries complètes de décharge ne sont chargées que pour B0005, B0006, B0007 et B0018 (185 721 lignes).
- **Idempotence** : un hash sha256 par fichier et une version du loader (`LOADER_VERSION`) décident du rechargement ; toute modification du contenu produit par le loader doit incrémenter cette version.
