from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from psycopg import Connection

from ..db import get_conn
from ..schemas import (
    BatteryDetail,
    BatteryPage,
    CyclePage,
    FadeQuality,
    ForecastStatus,
    Knee,
    Prediction,
    Profile,
    RulResponse,
    SohPoint,
    SohReference,
    SohSeries,
)

router = APIRouter(prefix="/batteries", tags=["batteries"])

CellId = Annotated[str, Path(pattern=r"^B\d{4}$", description="Identifiant NASA, ex. B0005", examples=["B0005"])]
Conn = Annotated[Connection, Depends(get_conn)]

# Colonnes communes à la liste et au détail. La pente n'est pas exposée quand il y a moins de
# 10 points après le pic : elle est numériquement absurde (cf. docs/degradation.md).
SUMMARY_SELECT = """
    s.cell_id, s.discharge_profile, s.temp_c, s.peak_current_a, d.cutoff_voltage_v,
    s.nominal_capacity_ah, d.n_discharges, d.n_valid_discharges,
    case when s.fade_estimate_quality = 'insufficient' then null
         else s.fade_pct_nominal_per_100_discharges end as fade_pct_per_100_discharges,
    s.fade_estimate_quality, l.forecast_status, l.observed_eol_age_index
"""
SUMMARY_FROM = """
    from marts.cell_degradation_summary s
    join marts.dim_battery d using (cell_id)
    join marts.cell_lifetime l using (cell_id)
"""

MESSAGES = {
    "extrapolated": "Fin de vie estimée par extrapolation linéaire de la perte observée. Lire les caveats.",
    "unreliable_forecast": "Aucune prévision publiée : ajustement peu fiable, ou fin de vie trop éloignée "
    "de la durée déjà observée.",
    "not_degrading": "La capacité ne décroît pas sur la période observée.",
    "insufficient_data": "Trop peu de points après le pic de capacité pour estimer une fin de vie.",
    "no_threshold": "Aucun critère de fin de vie pour cette cellule (NASA n'en précise pas).",
}


def _require_battery(conn: Connection, cell_id: str) -> None:
    if conn.execute("select 1 from marts.dim_battery where cell_id = %s", (cell_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Cellule {cell_id} inconnue")


@router.get("", response_model=BatteryPage, summary="Liste des cellules")
def list_batteries(
    conn: Conn,
    profile: Profile | None = None,
    temp_c: Annotated[int | None, Query(description="Température de la condition principale")] = None,
    fade_quality: FadeQuality | None = None,
    forecast_status: ForecastStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    params = {"profile": profile, "temp_c": temp_c, "q": fade_quality, "st": forecast_status,
              "limit": limit, "offset": offset}
    where = """
        where (%(profile)s::text is null or s.discharge_profile = %(profile)s::text)
          and (%(temp_c)s::int is null or s.temp_c = %(temp_c)s::int)
          and (%(q)s::text is null or s.fade_estimate_quality = %(q)s::text)
          and (%(st)s::text is null or l.forecast_status = %(st)s::text)
    """
    total = conn.execute(f"select count(*) as n {SUMMARY_FROM} {where}", params).fetchone()["n"]
    items = conn.execute(
        f"select {SUMMARY_SELECT} {SUMMARY_FROM} {where} order by s.cell_id limit %(limit)s offset %(offset)s",
        params,
    ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/{cell_id}", response_model=BatteryDetail, summary="Détail d'une cellule")
def get_battery(cell_id: CellId, conn: Conn):
    row = conn.execute(
        f"""select {SUMMARY_SELECT},
                d.readme_group, d.readme_note, s.eol_basis, s.eol_threshold_ah, s.peak_age_index,
                s.peak_smooth_ah, s.soh_nominal_at_peak, s.soh_nominal_at_end, s.n_post_peak, s.r2,
                s.last_age_index, d.n_impedance_measures, d.n_complex_re_rct, d.has_full_series
            {SUMMARY_FROM} where s.cell_id = %s""",
        (cell_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Cellule {cell_id} inconnue")
    return row


@router.get("/{cell_id}/soh", response_model=SohSeries, summary="Trajectoire de capacité et SOH")
def get_soh(
    cell_id: CellId,
    conn: Conn,
    post_peak_only: Annotated[bool, Query(description="Ne garder que la phase de dégradation")] = False,
):
    ref = conn.execute(
        "select nominal_capacity_ah, peak_smooth_ah, peak_age_index, temp_c, peak_current_a "
        "from marts.cell_degradation_summary where cell_id = %s",
        (cell_id,),
    ).fetchone()
    if ref is None:
        raise HTTPException(status_code=404, detail=f"Cellule {cell_id} inconnue")
    points = conn.execute(
        """select age_index, discharge_number, elapsed_days, capacity_ah, capacity_smooth_ah,
                  soh_nominal, soh_smooth_nominal, soh_peak, is_post_peak
           from marts.fact_degradation
           where cell_id = %s and (not %s or is_post_peak)
           order by age_index""",
        (cell_id, post_peak_only),
    ).fetchall()
    return SohSeries(cell_id=cell_id, reference=SohReference(**ref), points=[SohPoint(**p) for p in points])


@router.get("/{cell_id}/cycles", response_model=CyclePage, summary="Décharges d'une cellule")
def get_cycles(
    cell_id: CellId,
    conn: Conn,
    valid_only: Annotated[bool, Query(description="Exclure les capacités invalides")] = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _require_battery(conn, cell_id)
    total = conn.execute(
        "select count(*) as n from marts.fact_discharge where cell_id = %s and (not %s or is_valid_capacity)",
        (cell_id, valid_only),
    ).fetchone()["n"]
    items = conn.execute(
        """select cycle_idx, discharge_number, valid_discharge_number, elapsed_days, ambient_temp_c,
                  capacity_ah, is_valid_capacity, invalid_reason, discharge_peak_current_a, duration_s
           from marts.fact_discharge
           where cell_id = %s and (not %s or is_valid_capacity)
           order by cycle_idx limit %s offset %s""",
        (cell_id, valid_only, limit, offset),
    ).fetchall()
    return {"cell_id": cell_id, "total": total, "limit": limit, "offset": offset, "items": items}


def _backtest_caveat(conn: Connection) -> str | None:
    r = conn.execute(
        """select count(*) as n, count(distinct cell_id) as cells,
                  count(*) filter (where interval_covers_actual) as covered,
                  avg(abs_pct_error) as mape
           from marts.rul_backtest"""
    ).fetchone()
    if not r["n"]:
        return None
    return (
        f"Backtest ({r['n']} prévisions rejouées sur {r['cells']} cellules) : l'intervalle contient la vraie "
        f"fin de vie dans {r['covered']} cas sur {r['n']} (il est donc trop étroit) ; erreur relative "
        f"moyenne {r['mape']:.0f} %."
    )


@router.get("/{cell_id}/rul", response_model=RulResponse, summary="Fin de vie et durée de vie restante")
def get_rul(cell_id: CellId, conn: Conn):
    r = conn.execute(
        """select l.*, s.eol_basis as basis, s.eol_threshold_ah as thr
           from marts.cell_lifetime l join marts.cell_degradation_summary s using (cell_id)
           where l.cell_id = %s""",
        (cell_id,),
    ).fetchone()
    if r is None:
        raise HTTPException(status_code=404, detail=f"Cellule {cell_id} inconnue")

    status = r["forecast_status"]
    message = (
        f"Seuil de fin de vie franchi à la décharge {r['observed_eol_age_index']}."
        if status == "observed" else MESSAGES[status]
    )
    caveats = ["Résultat issu d'heuristiques non calibrées sur une vérité terrain (docs/degradation.md)."]
    if status == "extrapolated":
        caveats.append(
            "Extrapolation linéaire : elle prévoit une fin de vie trop tardive si la perte s'accélère et trop "
            "précoce si elle ralentit ; le backtest montre les deux cas."
        )
        caveats.append("L'intervalle ne reflète que l'incertitude sur la pente, pas l'erreur de modèle.")
        if (bt := _backtest_caveat(conn)):
            caveats.append(bt)
        if r["rul_discharges"] == 0:
            caveats.append("RUL à 0 : la tendance franchit le seuil avant la dernière mesure (fin de vie imminente).")
    if r["fade_estimate_quality"] != "reliable":
        caveats.append(f"Qualité de l'ajustement : {r['fade_estimate_quality']}.")

    prediction = None
    if status == "extrapolated":
        prediction = Prediction(
            eol_age_index=r["predicted_eol_age_index"], interval_low=r["predicted_eol_low"],
            interval_high=r["predicted_eol_high"], rul_discharges=r["rul_discharges"],
        )
    knee = None
    if r["knee_detected"]:
        knee = Knee(
            age_index=r["knee_age_index"], slope_before_ah_per_discharge=r["knee_slope_before"],
            slope_after_ah_per_discharge=r["knee_slope_after"],
        )
    return RulResponse(
        cell_id=cell_id, status=status, message=message, eol_basis=r["basis"], eol_threshold_ah=r["thr"],
        observed_eol_age_index=r["observed_eol_age_index"], last_age_index=r["last_age_index"],
        fade_estimate_quality=r["fade_estimate_quality"], prediction=prediction, knee=knee, caveats=caveats,
    )
