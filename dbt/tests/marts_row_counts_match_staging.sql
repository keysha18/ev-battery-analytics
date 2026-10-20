{#- Les faits ne perdent aucune ligne par rapport au staging, la dimension couvre toutes les cellules du seed. -#}

select 'fact_discharge' as model, s.n as expected_rows, m.n as actual_rows
from (select count(*) n from {{ ref('stg_nasa_discharges') }}) s,
     (select count(*) n from {{ ref('fact_discharge') }}) m
where s.n <> m.n

union all

select 'fact_impedance', s.n, m.n
from (select count(*) n from {{ ref('stg_nasa_impedance') }}) s,
     (select count(*) n from {{ ref('fact_impedance') }}) m
where s.n <> m.n

union all

select 'dim_battery', s.n, m.n
from (select count(*) n from {{ ref('nasa_cell_conditions') }}) s,
     (select count(*) n from {{ ref('dim_battery') }}) m
where s.n <> m.n
