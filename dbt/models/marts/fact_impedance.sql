{#- Grain : une mesure d'impédance d'une cellule. discharges_before relie la mesure à l'état de
    vieillissement (nombre de décharges déjà effectuées), pour croiser Rct/Re avec la capacité. -#}

with discharges as (

    select cell_id, cycle_idx from {{ ref('stg_nasa_discharges') }}

)

select
    i.cell_id,
    i.cycle_idx,
    i.impedance_number,
    i.start_time,
    extract(epoch from i.start_time - min(i.start_time) over (partition by i.cell_id)) / 86400.0 as elapsed_days,
    i.ambient_temp_c,
    (
        select count(*)
        from discharges d
        where d.cell_id = i.cell_id and d.cycle_idx < i.cycle_idx
    ) as discharges_before,
    i.re_ohm,
    i.rct_ohm,
    i.has_complex_re_rct,
    i.n_samples
from {{ ref('stg_nasa_impedance') }} i
