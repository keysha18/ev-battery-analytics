{#- Une ligne par cellule : niveau, pente de perte après le pic, fin de vie observée.

    Pente : régression linéaire de la capacité mesurée sur l'indice d'âge, après le pic.
    fade_estimate_quality dit si on peut s'y fier (nombre de points et r2).

    Seuil de fin de vie :
    - NASA l'exprime en Ah absolus (1,4 ou 1,6 Ah sur 2,0). Cela n'a de sens que si la cellule démarre
      nettement au-dessus : à 4 C, plusieurs cellules sont sous 1,4 Ah dès la première décharge, à cause
      de la température et non du vieillissement.
    - Si le pic de capacité est au moins eol_absolute_margin x le seuil NASA, on garde le seuil absolu
      (eol_basis = nasa_absolute). Sinon on applique la même perte (20 ou 30 %) au pic de la cellule
      (eol_basis = relative_to_peak). La marge est une heuristique, voir docs/dataset.md. -#}

with traj as (

    select * from {{ ref('fact_degradation') }}

),

per_cell as (

    select
        cell_id,
        max(temp_c) as temp_c,
        max(peak_current_a) as peak_current_a,
        max(nominal_capacity_ah) as nominal_capacity_ah,
        max(peak_age_index) as peak_age_index,
        max(peak_smooth_ah) as peak_smooth_ah,
        count(*) as n_points,
        max(age_index) as last_age_index,
        count(*) filter (where is_post_peak) as n_post_peak,
        regr_slope(capacity_ah, age_index) filter (where is_post_peak) as slope_ah_per_discharge,
        regr_r2(capacity_ah, age_index) filter (where is_post_peak) as r2,
        max(elapsed_days) as observed_days
    from traj
    group by cell_id

),

last_point as (

    select distinct on (cell_id) cell_id, capacity_smooth_ah as last_smooth_ah
    from traj
    order by cell_id, age_index desc

),

thresholds as (

    select
        p.cell_id,
        case
            when d.eol_capacity_ah is null then null
            when p.peak_smooth_ah >= {{ var('eol_absolute_margin') }} * d.eol_capacity_ah then d.eol_capacity_ah
            else p.peak_smooth_ah * (1 - d.eol_fade_pct / 100.0)
        end as eol_threshold_ah,
        case
            when d.eol_capacity_ah is null then null
            when p.peak_smooth_ah >= {{ var('eol_absolute_margin') }} * d.eol_capacity_ah then 'nasa_absolute'
            else 'relative_to_peak'
        end as eol_basis
    from per_cell p
    inner join {{ ref('dim_battery') }} d using (cell_id)

),

eol as (

    select
        t.cell_id,
        min(t.age_index) as eol_age_index
    from traj t
    inner join thresholds th using (cell_id)
    where t.is_post_peak
        and t.capacity_smooth_ah <= th.eol_threshold_ah
    group by t.cell_id

)

select
    p.cell_id,
    d.discharge_profile,
    p.temp_c,
    p.peak_current_a,
    p.nominal_capacity_ah,
    d.eol_capacity_ah as nasa_eol_capacity_ah,
    th.eol_threshold_ah,
    th.eol_basis,
    p.n_points,
    p.peak_age_index,
    p.peak_smooth_ah,
    p.peak_smooth_ah / p.nominal_capacity_ah as soh_nominal_at_peak,
    l.last_smooth_ah,
    l.last_smooth_ah / p.nominal_capacity_ah as soh_nominal_at_end,
    l.last_smooth_ah / p.peak_smooth_ah as soh_peak_at_end,
    p.n_post_peak,
    p.slope_ah_per_discharge,
    -- perte en % de la capacité nominale pour 100 décharges (positif = la cellule perd de la capacité)
    -100 * 100 * p.slope_ah_per_discharge / p.nominal_capacity_ah as fade_pct_nominal_per_100_discharges,
    p.r2,
    case
        when p.n_post_peak < 10 then 'insufficient'
        when p.n_post_peak >= 20 and p.r2 >= 0.5 then 'reliable'
        else 'weak'
    end as fade_estimate_quality,
    p.slope_ah_per_discharge < 0 as is_degrading,
    th.eol_threshold_ah is not null as has_eol_threshold,
    e.eol_age_index is not null as reached_eol,
    e.eol_age_index,
    p.last_age_index,
    p.observed_days
from per_cell p
inner join last_point l using (cell_id)
inner join thresholds th using (cell_id)
inner join {{ ref('dim_battery') }} d using (cell_id)
left join eol e using (cell_id)
