{#- Une ligne par décharge. Les capacités douteuses ne sont pas supprimées mais marquées
    (is_valid_capacity / invalid_reason) : l'analyse ne retient que les valides, l'audit reste possible. -#}

with discharges as (

    select * from {{ ref('stg_nasa_cycles') }}
    where cycle_type = 'discharge'

),

with_nominal as (

    select
        d.*,
        c.nominal_capacity_ah,
        row_number() over (partition by d.cell_id order by d.cycle_idx) as discharge_number
    from discharges d
    left join {{ ref('nasa_cell_conditions') }} c using (cell_id)

),

checked as (

    select
        *,
        case
            when capacity_ah is null then 'missing'
            when capacity_ah <= 0 then 'non_positive'
            when capacity_ah < {{ var('min_capacity_ratio') }} * nominal_capacity_ah then 'implausibly_low'
            when capacity_ah > {{ var('max_capacity_ratio') }} * nominal_capacity_ah then 'implausibly_high'
        end as invalid_reason
    from with_nominal

)

select
    cell_id,
    cycle_idx,
    discharge_number,
    ambient_temp_c,
    start_time,
    n_samples,
    duration_s,
    capacity_ah,
    nominal_capacity_ah,
    invalid_reason is null as is_valid_capacity,
    invalid_reason,
    -- courant de décharge mesuré (valeur absolue) : varie par cycle pour les profils multi_level
    abs(i_median) as discharge_median_current_a,
    abs(i_min) as discharge_peak_current_a,
    v_min,
    v_max,
    t_min,
    t_max,
    t_mean,
    run_id
from checked
