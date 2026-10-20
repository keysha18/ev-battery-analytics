{#- Dans chaque cellule, l'ordre des cycles dans le .mat doit suivre l'ordre du temps. Sinon
    cycle_idx ne peut pas servir d'axe de vieillissement. Retourne les ruptures. -#}

select cell_id, cycle_idx, start_time, prev_start_time
from (
    select
        cell_id,
        cycle_idx,
        start_time,
        lag(start_time) over (partition by cell_id order by cycle_idx) as prev_start_time
    from {{ ref('stg_nasa_cycles') }}
) t
where start_time < prev_start_time
