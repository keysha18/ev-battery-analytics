-- Schéma raw : sortie du loader NASA. Idempotent (appliqué à chaque ingestion).
-- "Raw" = aucune correction de valeur (capacités à 0, NULL, etc. conservées telles quelles).
-- Les .mat sont réduits à un résumé par cycle ; les séries complètes ne sont chargées
-- que pour quelques cellules de démonstration (nasa_discharge_samples).

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.ingestion_runs (
    run_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cell_id         text        NOT NULL,
    source_file     text        NOT NULL,
    source_group    text        NOT NULL,
    source_sha256   text        NOT NULL,
    status          text        NOT NULL
                    CHECK (status IN ('success', 'failed', 'skipped_unchanged', 'skipped_duplicate')),
    loader_version  int         NOT NULL,
    with_samples    boolean     NOT NULL DEFAULT false,
    n_cycles        int,
    n_samples       int,
    error           text,
    started_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at     timestamptz
);
CREATE INDEX IF NOT EXISTS ingestion_runs_cell_idx
    ON raw.ingestion_runs (cell_id, status, run_id DESC);

-- Un enregistrement par cycle (charge, discharge ou impedance) et par cellule.
CREATE TABLE IF NOT EXISTS raw.nasa_cycles (
    cell_id         text             NOT NULL,
    cycle_idx       int              NOT NULL,  -- position dans le tableau "cycle" du .mat
    cycle_type      text             NOT NULL CHECK (cycle_type IN ('charge', 'discharge', 'impedance')),
    ambient_temp_c  double precision,
    start_time      timestamp,                  -- date vector MATLAB converti, heure locale du labo (sans fuseau)
    n_samples       int,
    duration_s      double precision,
    capacity_ah     double precision,           -- décharge uniquement, NULL si le champ est vide dans le .mat
    v_min           double precision,
    v_max           double precision,
    i_min           double precision,
    i_max           double precision,
    i_median        double precision,
    t_min           double precision,           -- température mesurée
    t_max           double precision,
    t_mean          double precision,
    re_ohm          double precision,           -- impédance uniquement
    rct_ohm         double precision,
    source_sha256   text             NOT NULL,
    run_id          bigint           NOT NULL REFERENCES raw.ingestion_runs (run_id),
    PRIMARY KEY (cell_id, cycle_idx)
);

-- Séries temporelles complètes des décharges, cellules de démonstration uniquement.
CREATE TABLE IF NOT EXISTS raw.nasa_discharge_samples (
    cell_id              text             NOT NULL,
    cycle_idx            int              NOT NULL,
    sample_idx           int              NOT NULL,
    time_s               double precision,
    voltage_measured     double precision,
    current_measured     double precision,
    temperature_measured double precision,
    current_load         double precision,
    voltage_load         double precision,
    run_id               bigint           NOT NULL REFERENCES raw.ingestion_runs (run_id),
    PRIMARY KEY (cell_id, cycle_idx, sample_idx)
);
