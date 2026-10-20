{#- Trajectoire de capacité par cellule, prête pour l'analyse de dégradation.

    Choix méthodologiques (cf. docs/dataset.md) :
    1. Seules les décharges valides sont retenues.
    2. La capacité dépend de la température et du courant : on ne garde que la condition
       (température, courant de crête) la plus fréquente de chaque cellule, sinon un changement
       de régime ressemblerait à du vieillissement (ex. B0042-44 : 22 C/2 A puis 4 C/1 A).
    3. Plusieurs cellules montent d'abord en capacité (conditionnement, ex. B0033 de 1,16 à 1,61 Ah) :
       la référence n'est donc pas la première mesure mais le pic de la capacité lissée
       (médiane glissante sur 5 décharges). La dégradation se mesure après ce pic (is_post_peak). -#}

with base as (

    select
        cell_id,
        cycle_idx,
        discharge_number,
        start_time,
        capacity_ah,
        round(ambient_temp_c)::int as temp_c,
        round(discharge_peak_current_a)::int as peak_current_a
    from {{ ref('fact_discharge') }}
    where is_valid_capacity

),

conditions as (

    select
        cell_id,
        temp_c,
        peak_current_a,
        row_number() over (partition by cell_id order by count(*) desc, min(cycle_idx)) as rk
    from base
    group by cell_id, temp_c, peak_current_a

),

primary_discharges as (

    select
        b.*,
        row_number() over (partition by b.cell_id order by b.cycle_idx) as age_index,
        extract(epoch from b.start_time - min(b.start_time) over (partition by b.cell_id)) / 86400.0 as elapsed_days
    from base b
    inner join conditions c
        on c.cell_id = b.cell_id
        and c.temp_c = b.temp_c
        and c.peak_current_a = b.peak_current_a
        and c.rk = 1

),

smoothed as (

    select
        a.*,
        (
            select percentile_cont(0.5) within group (order by w.capacity_ah)
            from primary_discharges w
            where w.cell_id = a.cell_id
                and w.age_index between a.age_index - 2 and a.age_index + 2
        ) as capacity_smooth_ah
    from primary_discharges a

),

peak as (

    select distinct on (cell_id)
        cell_id,
        age_index as peak_age_index,
        capacity_smooth_ah as peak_smooth_ah
    from smoothed
    order by cell_id, capacity_smooth_ah desc, age_index

)

select
    s.cell_id,
    s.cycle_idx,
    s.discharge_number,
    s.age_index,
    s.start_time,
    s.elapsed_days,
    s.temp_c,
    s.peak_current_a,
    s.capacity_ah,
    s.capacity_smooth_ah,
    d.nominal_capacity_ah,
    s.capacity_ah / d.nominal_capacity_ah as soh_nominal,
    s.capacity_smooth_ah / d.nominal_capacity_ah as soh_smooth_nominal,
    s.capacity_ah / p.peak_smooth_ah as soh_peak,
    p.peak_age_index,
    p.peak_smooth_ah,
    s.age_index >= p.peak_age_index as is_post_peak
from smoothed s
inner join peak p using (cell_id)
inner join {{ ref('dim_battery') }} d using (cell_id)
