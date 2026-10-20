from typing import Annotated

from fastapi import APIRouter, Depends
from psycopg import Connection

from ..db import get_conn
from ..schemas import BacktestPoint, FleetSummary

router = APIRouter(prefix="/fleet", tags=["fleet"])


@router.get("/backtest", response_model=list[BacktestPoint], summary="Prévisions rejouées sur les fins de vie observées")
def fleet_backtest(conn: Annotated[Connection, Depends(get_conn)]):
    """Une ligne par (cellule, part de vie observée) : fin de vie prévue contre fin de vie réelle."""
    return conn.execute(
        """select cell_id, observed_fraction, predicted_eol_age_index, actual_eol_age_index, error_discharges,
                  interval_low, interval_high, interval_covers_actual
           from marts.rul_backtest order by observed_fraction, cell_id"""
    ).fetchall()


@router.get("/summary", response_model=FleetSummary, summary="Synthèse sur l'ensemble des cellules")
def fleet_summary(conn: Annotated[Connection, Depends(get_conn)]):
    totals = conn.execute(
        "select count(*) as n_batteries, sum(n_discharges)::int as n_discharges, "
        "sum(n_valid_discharges)::int as n_valid_discharges from marts.dim_battery"
    ).fetchone()
    by_status = conn.execute(
        "select forecast_status as key, count(*)::int as n from marts.cell_lifetime group by 1 order by 2 desc, 1"
    ).fetchall()
    by_quality = conn.execute(
        "select fade_estimate_quality as key, count(*)::int as n from marts.cell_degradation_summary "
        "group by 1 order by 2 desc, 1"
    ).fetchall()
    # Seules les cellules à ajustement fiable : les pentes 'weak' ne sont pas comparables
    by_temp = conn.execute(
        """select temp_c, count(*)::int as n_cells,
                  (percentile_cont(0.5) within group (order by fade_pct_nominal_per_100_discharges))::float
                      as median_fade_pct_per_100_discharges,
                  min(fade_pct_nominal_per_100_discharges)::float as min_fade_pct_per_100_discharges,
                  max(fade_pct_nominal_per_100_discharges)::float as max_fade_pct_per_100_discharges
           from marts.cell_degradation_summary
           where fade_estimate_quality = 'reliable' and is_degrading
           group by temp_c order by temp_c"""
    ).fetchall()
    backtest = conn.execute(
        """select observed_fraction, count(*)::int as n_cells,
                  avg(abs(error_discharges))::float as mean_abs_error_discharges,
                  avg(abs_pct_error)::float as mean_abs_pct_error,
                  (count(*) filter (where interval_covers_actual))::float / count(*) as interval_coverage
           from marts.rul_backtest group by 1 order by 1"""
    ).fetchall()
    return {
        **totals,
        "by_forecast_status": by_status,
        "by_fade_quality": by_quality,
        "fade_by_temperature_reliable_cells": by_temp,
        "backtest": backtest,
        "notes": [
            (
                "Les écarts entre températures ne sont pas attribuables à la température seule : les groupes "
                "de cellules diffèrent aussi par la tension de coupure et le courant de décharge."
            ),
            "Le backtest ne porte que sur les cellules ayant atteint leur fin de vie (effectif très réduit).",
            "Méthode, heuristiques et limites : docs/degradation.md.",
        ],
    }
