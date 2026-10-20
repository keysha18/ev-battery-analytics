-- Tables écrites par src/analytics (knee + fin de vie). Entièrement recalculées à chaque exécution :
-- on les recrée donc plutôt que de les migrer.
-- Créées par ev_admin dans marts : les droits par défaut donnent SELECT à api_ro.

DROP TABLE IF EXISTS marts.rul_backtest;
DROP TABLE IF EXISTS marts.cell_lifetime;

CREATE TABLE marts.cell_lifetime (
    cell_id                  text PRIMARY KEY,
    fade_estimate_quality    text NOT NULL,
    -- genou (accélération de la perte), détecté sur la capacité lissée après le pic
    knee_detected            boolean NOT NULL,
    knee_age_index           double precision,
    knee_slope_before        double precision,   -- Ah par décharge
    knee_slope_after         double precision,
    knee_sse_ratio           double precision,
    -- fin de vie
    eol_basis                text,
    eol_threshold_ah         double precision,
    forecast_status          text NOT NULL
        CHECK (forecast_status IN ('observed', 'extrapolated', 'unreliable_forecast', 'not_degrading',
                                   'insufficient_data', 'no_threshold')),
    observed_eol_age_index   int,                -- fin de vie réellement franchie
    -- Les 4 colonnes suivantes ne sont renseignées que si forecast_status = 'extrapolated'
    -- (ajustement fiable ET fin de vie prévue dans l'horizon déjà observé).
    predicted_eol_age_index  double precision,
    predicted_eol_low        double precision,   -- intervalle sur la pente seule : trop étroit (cf. rul_backtest)
    predicted_eol_high       double precision,
    rul_discharges           double precision,   -- décharges restantes, plafonné à 0 (0 = fin de vie imminente)
    last_age_index           int NOT NULL,
    computed_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE marts.rul_backtest (
    cell_id                 text NOT NULL,
    observed_fraction       double precision NOT NULL,   -- part de la vie observée avant la prévision
    cutoff_age_index        double precision NOT NULL,
    predicted_eol_age_index double precision NOT NULL,
    actual_eol_age_index    double precision NOT NULL,
    error_discharges        double precision NOT NULL,   -- prévu - réel (négatif = trop pessimiste)
    abs_pct_error           double precision NOT NULL,
    interval_low            double precision NOT NULL,
    interval_high           double precision,
    interval_covers_actual  boolean NOT NULL,
    PRIMARY KEY (cell_id, observed_fraction)
);
