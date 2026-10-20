{#- Le staging ne doit ni perdre ni inventer de cycles : charges + décharges + impédances = raw. -#}

with raw_n as (
    select count(*) as n from {{ source('raw', 'nasa_cycles') }}
),
staged as (
    select
        (select count(*) from {{ ref('stg_nasa_discharges') }})
      + (select count(*) from {{ ref('stg_nasa_impedance') }})
      + (select count(*) from {{ ref('stg_nasa_cycles') }} where cycle_type = 'charge') as n
)
select raw_n.n as raw_rows, staged.n as staged_rows
from raw_n, staged
where raw_n.n <> staged.n
