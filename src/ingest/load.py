"""Chargement des .mat dans le schéma raw. Idempotent : relancer ne duplique rien."""

import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg

from .config import LOADER_VERSION, SQL_RAW_DIR
from .download import sha256_file
from .mat_reader import discharge_samples, read_cell, summarize_cycle

log = logging.getLogger(__name__)

CYCLE_COLS = (
    "cell_id", "cycle_idx", "cycle_type", "ambient_temp_c", "start_time", "n_samples",
    "duration_s", "capacity_ah", "v_min", "v_max", "i_min", "i_max", "i_median",
    "t_min", "t_max", "t_mean", "re_ohm", "rct_ohm", "re_imag_ohm", "rct_imag_ohm",
    "source_sha256", "run_id",
)
SAMPLE_COLS = (
    "cell_id", "cycle_idx", "sample_idx", "time_s", "voltage_measured", "current_measured",
    "temperature_measured", "current_load", "voltage_load", "run_id",
)


@dataclass(frozen=True)
class CellFile:
    cell_id: str
    path: Path
    group: str
    sha256: str
    rel: str


def discover(source: Path) -> tuple[list[CellFile], list[CellFile]]:
    """(fichiers retenus, doublons). B0025-28 existent dans deux dossiers du zip NASA.

    Un doublon doit être identique octet pour octet ; sinon on refuse de choisir.
    """
    by_cell: dict[str, list[CellFile]] = {}
    for p in sorted(source.rglob("B*.mat")):
        by_cell.setdefault(p.stem, []).append(
            CellFile(p.stem, p, p.parent.name, sha256_file(p), str(p.relative_to(source)))
        )
    if not by_cell:
        raise FileNotFoundError(f"aucun fichier B*.mat sous {source} (lancer make download ?)")
    kept, dups = [], []
    for cell_id, files in by_cell.items():
        kept.append(files[0])
        for other in files[1:]:
            if other.sha256 != files[0].sha256:
                raise ValueError(f"{cell_id}: doublons différents ({files[0].rel} vs {other.rel})")
            dups.append(other)
    return kept, dups


def apply_ddl(conn: psycopg.Connection) -> None:
    for f in sorted(SQL_RAW_DIR.glob("*.sql")):
        conn.execute(f.read_text(encoding="utf-8"))


def _log_run(conn, cf: CellFile, status: str, with_samples: bool = False, error: str | None = None) -> None:
    conn.execute(
        """INSERT INTO raw.ingestion_runs
           (cell_id, source_file, source_group, source_sha256, status, loader_version,
            with_samples, error, finished_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp())""",
        (cf.cell_id, cf.rel, cf.group, cf.sha256, status, LOADER_VERSION, with_samples, error),
    )


def _is_up_to_date(conn, cf: CellFile, want_samples: bool) -> bool:
    row = conn.execute(
        """SELECT 1 FROM raw.ingestion_runs r
           WHERE r.cell_id = %(c)s AND r.status = 'success' AND r.source_sha256 = %(h)s
             AND r.loader_version = %(v)s AND (r.with_samples OR NOT %(s)s)
             AND EXISTS (SELECT 1 FROM raw.nasa_cycles n WHERE n.cell_id = %(c)s AND n.run_id = r.run_id)
           ORDER BY r.run_id DESC LIMIT 1""",
        {"c": cf.cell_id, "h": cf.sha256, "v": LOADER_VERSION, "s": want_samples},
    ).fetchone()
    return row is not None


def _load_cell(conn, cf: CellFile, with_samples: bool) -> tuple[int, int]:
    """Remplace toutes les lignes de la cellule. À appeler dans une transaction."""
    cell_id, cycles = read_cell(cf.path)
    if cell_id != cf.cell_id:
        raise ValueError(f"{cf.rel}: contient {cell_id}")
    run_id = conn.execute(
        """INSERT INTO raw.ingestion_runs
           (cell_id, source_file, source_group, source_sha256, status, loader_version, with_samples)
           VALUES (%s, %s, %s, %s, 'success', %s, %s) RETURNING run_id""",
        (cf.cell_id, cf.rel, cf.group, cf.sha256, LOADER_VERSION, with_samples),
    ).fetchone()[0]
    conn.execute("DELETE FROM raw.nasa_discharge_samples WHERE cell_id = %s", (cell_id,))
    conn.execute("DELETE FROM raw.nasa_cycles WHERE cell_id = %s", (cell_id,))

    with conn.cursor() as cur:
        with cur.copy(f"COPY raw.nasa_cycles ({', '.join(CYCLE_COLS)}) FROM STDIN") as cp:
            for i, cycle in enumerate(cycles):
                r = summarize_cycle(i, cycle)
                cp.write_row([cell_id, *(r[c] for c in CYCLE_COLS[1:-2]), cf.sha256, run_id])

        n_samples = 0
        if with_samples:
            with cur.copy(f"COPY raw.nasa_discharge_samples ({', '.join(SAMPLE_COLS)}) FROM STDIN") as cp:
                for i, cycle in enumerate(cycles):
                    if cycle["type"] == "discharge":
                        for row in discharge_samples(i, cycle):
                            cp.write_row([cell_id, *row, run_id])
                            n_samples += 1

    conn.execute(
        "UPDATE raw.ingestion_runs SET n_cycles = %s, n_samples = %s, finished_at = clock_timestamp() "
        "WHERE run_id = %s",
        (len(cycles), n_samples, run_id),
    )
    return len(cycles), n_samples


def ingest(source: Path, conninfo: str, demo_cells: tuple[str, ...], force: bool = False) -> dict[str, int]:
    """Charge toutes les cellules trouvées sous `source`. Retourne un compteur par statut."""
    kept, dups = discover(source)
    counts = {"success": 0, "skipped_unchanged": 0, "skipped_duplicate": 0, "failed": 0}
    # autocommit : chaque `conn.transaction()` ouvre une vraie transaction, un échec sur une
    # cellule n'annule donc que cette cellule et le journal d'échec reste écrit.
    with psycopg.connect(conninfo, autocommit=True) as conn:
        apply_ddl(conn)
        for cf in dups:
            _log_run(conn, cf, "skipped_duplicate")
            counts["skipped_duplicate"] += 1
            log.info("%s: doublon ignoré (%s)", cf.cell_id, cf.rel)
        for cf in kept:
            want = cf.cell_id in demo_cells
            if not force and _is_up_to_date(conn, cf, want):
                _log_run(conn, cf, "skipped_unchanged")
                counts["skipped_unchanged"] += 1
                log.info("%s: déjà à jour", cf.cell_id)
                continue
            try:
                with conn.transaction():
                    n_cycles, n_samples = _load_cell(conn, cf, want)
            except Exception as exc:  # noqa: BLE001 - une cellule en échec est journalisée sans bloquer les autres
                _log_run(conn, cf, "failed", want, f"{type(exc).__name__}: {exc}")
                counts["failed"] += 1
                log.error("%s: échec (%s)", cf.cell_id, exc)
                continue
            counts["success"] += 1
            log.info("%s: %d cycles, %d échantillons chargés", cf.cell_id, n_cycles, n_samples)
    return counts
