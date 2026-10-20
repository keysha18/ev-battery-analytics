from contextlib import asynccontextmanager
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from psycopg import Connection
from psycopg_pool import PoolTimeout

from .db import get_conn, make_pool
from .routers import batteries, fleet
from .schemas import Health

DESCRIPTION = """
Résultats de l'analyse de dégradation de 34 cellules Li-ion NASA (lecture seule).

**À lire avant d'utiliser les prévisions** : une fin de vie n'est publiée que si l'ajustement est fiable
et si elle reste dans l'horizon déjà observé. Le backtest (6 cellules) montre des erreurs de 10 à 36
décharges selon la part de vie observée, et des intervalles trop étroits. Chaque réponse de
`/batteries/{id}/rul` porte ses `caveats`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = make_pool()
    pool.open(wait=True, timeout=15)
    app.state.pool = pool
    yield
    pool.close()


app = FastAPI(title="EV Battery Analytics API", version="0.1.0", description=DESCRIPTION, lifespan=lifespan)
app.include_router(batteries.router)
app.include_router(fleet.router)


@app.exception_handler(psycopg.errors.UndefinedTable)
async def _missing_tables(request, exc):
    return JSONResponse(
        status_code=503,
        content={"detail": "Tables analytiques absentes : lancer `make dbt-build` puis `make analyze`."},
    )


@app.exception_handler(PoolTimeout)
@app.exception_handler(psycopg.OperationalError)
async def _db_down(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Base de données indisponible."})


@app.get("/health", response_model=Health, tags=["ops"], summary="État du service et de la base")
def health(conn: Annotated[Connection, Depends(get_conn)]):
    ok = conn.execute(
        "select to_regclass('marts.cell_lifetime') is not null and to_regclass('marts.dim_battery') is not null as ok"
    ).fetchone()["ok"]
    if not ok:
        raise HTTPException(status_code=503, detail="Tables analytiques absentes : make dbt-build puis make analyze.")
    return {"status": "ok", "database": "ok"}
