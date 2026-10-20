{#- Re/Rct sont complexes dans B0049 et B0051 pour certains cycles (cf. docs/dataset.md) :
    ces lignes sont signalées, pas corrigées. -#}

select
    cell_id,
    cycle_idx,
    row_number() over (partition by cell_id order by cycle_idx) as impedance_number,
    ambient_temp_c,
    start_time,
    n_samples,
    re_ohm,
    rct_ohm,
    (re_imag_ohm is not null or rct_imag_ohm is not null) as has_complex_re_rct,
    run_id
from {{ ref('stg_nasa_cycles') }}
where cycle_type = 'impedance'
