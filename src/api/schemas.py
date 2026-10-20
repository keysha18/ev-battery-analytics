from typing import Literal

from pydantic import BaseModel, Field

Profile = Literal["constant", "square_wave", "multi_level"]
FadeQuality = Literal["reliable", "weak", "insufficient"]
ForecastStatus = Literal[
    "observed", "extrapolated", "unreliable_forecast", "not_degrading", "insufficient_data", "no_threshold"
]


class BatterySummary(BaseModel):
    cell_id: str = Field(examples=["B0005"])
    discharge_profile: Profile
    temp_c: int = Field(description="Température de la condition principale de la cellule (°C).")
    peak_current_a: int = Field(description="Courant de crête de la condition principale (A).")
    cutoff_voltage_v: float
    nominal_capacity_ah: float
    n_discharges: int
    n_valid_discharges: int
    fade_pct_per_100_discharges: float | None = Field(
        description="Perte en % de la capacité nominale pour 100 décharges. Null si moins de 10 points "
        "après le pic ; à ignorer si fade_estimate_quality vaut 'weak'."
    )
    fade_estimate_quality: FadeQuality
    forecast_status: ForecastStatus
    observed_eol_age_index: int | None = Field(description="Rang de la décharge où le seuil de fin de vie est franchi.")


class BatteryPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[BatterySummary]


class BatteryDetail(BatterySummary):
    readme_group: str
    readme_note: str | None
    eol_basis: Literal["nasa_absolute", "relative_to_peak"] | None
    eol_threshold_ah: float | None
    peak_age_index: int
    peak_smooth_ah: float
    soh_nominal_at_peak: float
    soh_nominal_at_end: float
    n_post_peak: int
    r2: float | None
    last_age_index: int
    n_impedance_measures: int
    n_complex_re_rct: int
    has_full_series: bool


class SohReference(BaseModel):
    nominal_capacity_ah: float
    peak_smooth_ah: float
    peak_age_index: int
    temp_c: int
    peak_current_a: int


class SohPoint(BaseModel):
    age_index: int
    discharge_number: int
    elapsed_days: float
    capacity_ah: float
    capacity_smooth_ah: float
    soh_nominal: float
    soh_smooth_nominal: float
    soh_peak: float
    is_post_peak: bool


class SohSeries(BaseModel):
    cell_id: str
    reference: SohReference
    points: list[SohPoint]


class Cycle(BaseModel):
    cycle_idx: int
    discharge_number: int
    valid_discharge_number: int | None
    elapsed_days: float
    ambient_temp_c: float | None
    capacity_ah: float | None
    is_valid_capacity: bool
    invalid_reason: str | None
    discharge_peak_current_a: float | None
    duration_s: float | None


class CyclePage(BaseModel):
    cell_id: str
    total: int
    limit: int
    offset: int
    items: list[Cycle]


class Prediction(BaseModel):
    eol_age_index: float
    interval_low: float
    interval_high: float | None
    rul_discharges: float = Field(description="Décharges restantes ; 0 signifie fin de vie imminente.")


class Knee(BaseModel):
    age_index: float
    slope_before_ah_per_discharge: float
    slope_after_ah_per_discharge: float


class RulResponse(BaseModel):
    cell_id: str
    status: ForecastStatus
    message: str
    eol_basis: str | None
    eol_threshold_ah: float | None
    observed_eol_age_index: int | None
    last_age_index: int
    fade_estimate_quality: FadeQuality
    prediction: Prediction | None = Field(
        description="Renseigné uniquement si status vaut 'extrapolated'. Voir caveats avant toute utilisation."
    )
    knee: Knee | None
    caveats: list[str]


class StatusCount(BaseModel):
    key: str
    n: int


class FadeByTemp(BaseModel):
    temp_c: int
    n_cells: int
    median_fade_pct_per_100_discharges: float
    min_fade_pct_per_100_discharges: float
    max_fade_pct_per_100_discharges: float


class BacktestByFraction(BaseModel):
    observed_fraction: float
    n_cells: int
    mean_abs_error_discharges: float
    mean_abs_pct_error: float
    interval_coverage: float = Field(description="Part des cas où l'intervalle contient la vraie fin de vie.")


class FleetSummary(BaseModel):
    n_batteries: int
    n_discharges: int
    n_valid_discharges: int
    by_forecast_status: list[StatusCount]
    by_fade_quality: list[StatusCount]
    fade_by_temperature_reliable_cells: list[FadeByTemp]
    backtest: list[BacktestByFraction]
    notes: list[str]


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
