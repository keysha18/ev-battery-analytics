{#- Échoue (retourne des lignes) pour toute cellule sans aucune décharge valide :
    elle serait inutilisable pour l'analyse de dégradation. -#}

select c.cell_id
from {{ ref('nasa_cell_conditions') }} c
left join {{ ref('stg_nasa_discharges') }} d
    on d.cell_id = c.cell_id and d.is_valid_capacity
group by c.cell_id
having count(d.cell_id) = 0
