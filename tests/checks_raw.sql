-- Contrôles de cohérence du schéma raw après ingestion (valeurs attendues = mesures faites sur les .mat).
\pset footer off
\echo '--- cellules / cycles par type (attendu: 34 cellules; charge 2815, discharge 2794, impedance 1956) ---'
SELECT count(DISTINCT cell_id) AS cells, count(*) FILTER (WHERE cycle_type='charge') AS charge,
       count(*) FILTER (WHERE cycle_type='discharge') AS discharge,
       count(*) FILTER (WHERE cycle_type='impedance') AS impedance FROM raw.nasa_cycles;

\echo '--- échantillons de démo (attendu: 185721 = 3 x 50285 + 34866) ---'
SELECT count(*) AS samples, count(DISTINCT cell_id) AS cells FROM raw.nasa_discharge_samples;

\echo '--- lignes orphelines: ne doit pas dépasser 0 (lignes dont le run_id n''est pas le dernier succès de la cellule) ---'
WITH last_ok AS (
    SELECT DISTINCT ON (cell_id) cell_id, run_id FROM raw.ingestion_runs
    WHERE status = 'success' ORDER BY cell_id, run_id DESC)
SELECT (SELECT count(*) FROM raw.nasa_cycles c LEFT JOIN last_ok l USING (cell_id, run_id) WHERE l.run_id IS NULL) AS stale_cycles,
       (SELECT count(*) FROM raw.nasa_discharge_samples c LEFT JOIN last_ok l USING (cell_id, run_id) WHERE l.run_id IS NULL) AS stale_samples;

\echo '--- anomalies conservées telles quelles dans raw ---'
SELECT cell_id,
       count(*) FILTER (WHERE cycle_type='discharge' AND capacity_ah IS NULL) AS cap_null,
       count(*) FILTER (WHERE cycle_type='discharge' AND capacity_ah = 0)     AS cap_zero,
       count(*) FILTER (WHERE re_imag_ohm IS NOT NULL OR rct_imag_ohm IS NOT NULL) AS re_rct_complex
FROM raw.nasa_cycles GROUP BY cell_id
HAVING count(*) FILTER (WHERE cycle_type='discharge' AND (capacity_ah IS NULL OR capacity_ah = 0)) > 0
    OR count(*) FILTER (WHERE re_imag_ohm IS NOT NULL OR rct_imag_ohm IS NOT NULL) > 0
ORDER BY cell_id;

\echo '--- journal par statut ---'
SELECT status, loader_version AS v, count(*) FROM raw.ingestion_runs GROUP BY 1, 2 ORDER BY 2, 1;
