{#- Grain : une décharge d'une cellule. Toutes les décharges sont gardées (valides ou non) ;
    les analyses filtrent sur is_valid_capacity. valid_discharge_number numérote les seules décharges valides. -#}

select
    cell_id,
    cycle_idx,
    discharge_number,
    case
        when is_valid_capacity
            then count(*) filter (where is_valid_capacity)
                over (partition by cell_id order by cycle_idx rows between unbounded preceding and current row)
    end as valid_discharge_number,
    start_time,
    extract(epoch from start_time - min(start_time) over (partition by cell_id)) / 86400.0 as elapsed_days,
    ambient_temp_c,
    capacity_ah,
    is_valid_capacity,
    invalid_reason,
    discharge_median_current_a,
    discharge_peak_current_a,
    duration_s,
    n_samples,
    v_min,
    v_max,
    t_min,
    t_max,
    t_mean
from {{ ref('stg_nasa_discharges') }}
