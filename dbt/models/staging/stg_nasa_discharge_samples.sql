select
    cell_id,
    cycle_idx,
    sample_idx,
    time_s,
    voltage_measured,
    current_measured,
    temperature_measured,
    current_load,
    voltage_load,
    run_id
from {{ source('raw', 'nasa_discharge_samples') }}
