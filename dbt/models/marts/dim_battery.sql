{#- Une ligne par cellule : conditions d'essai (seed) + volumétrie issue du staging. -#}

with discharges as (

    select
        cell_id,
        count(*) as n_discharges,
        count(*) filter (where is_valid_capacity) as n_valid_discharges,
        count(*) filter (where not is_valid_capacity) as n_invalid_discharges,
        min(start_time) as first_discharge_at,
        max(start_time) as last_discharge_at
    from {{ ref('stg_nasa_discharges') }}
    group by cell_id

),

impedance as (

    select
        cell_id,
        count(*) as n_impedance_measures,
        count(*) filter (where has_complex_re_rct) as n_complex_re_rct
    from {{ ref('stg_nasa_impedance') }}
    group by cell_id

),

with_series as (

    select distinct cell_id from {{ ref('stg_nasa_discharge_samples') }}

)

select
    c.cell_id,
    c.readme_group,
    c.ambient_temp_nominal_c,
    c.discharge_profile,
    c.discharge_current_a,
    c.discharge_current_levels_a,
    c.cutoff_voltage_v,
    c.nominal_capacity_ah,
    c.eol_capacity_ah,
    case
        when c.eol_capacity_ah is not null
            then round(100 * (c.nominal_capacity_ah - c.eol_capacity_ah) / c.nominal_capacity_ah, 1)
    end as eol_fade_pct,
    c.readme_note,
    coalesce(d.n_discharges, 0) as n_discharges,
    coalesce(d.n_valid_discharges, 0) as n_valid_discharges,
    coalesce(d.n_invalid_discharges, 0) as n_invalid_discharges,
    d.first_discharge_at,
    d.last_discharge_at,
    coalesce(i.n_impedance_measures, 0) as n_impedance_measures,
    coalesce(i.n_complex_re_rct, 0) as n_complex_re_rct,
    s.cell_id is not null as has_full_series
from {{ ref('nasa_cell_conditions') }} c
left join discharges d using (cell_id)
left join impedance i using (cell_id)
left join with_series s using (cell_id)
