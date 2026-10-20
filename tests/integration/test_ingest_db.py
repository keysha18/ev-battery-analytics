"""Ingestion de bout en bout sur une base jetable (créée puis supprimée par le test)."""

import os
import shutil
import uuid

import psycopg
import pytest

from src.ingest.config import conninfo
from src.ingest.load import ingest
from tests import synthetic

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    """Base temporaire ev_test_xxx ; skip si Postgres ou les variables .env sont absents."""
    if "POSTGRES_USER" not in os.environ:
        pytest.skip("variables POSTGRES_* absentes (lancer via make test)")
    name = f"ev_test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(conninfo("postgres"), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres injoignable (make up ?)")
    admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield conninfo(name)
    finally:
        admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.close()


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "src"
    synthetic.write_mat(src / "grp1" / "B9001.mat", "B9001", synthetic.make_cycles(1.8))
    synthetic.write_mat(src / "grp1" / "B9002.mat", "B9002", synthetic.make_cycles(1.5))
    return src


def count(ci, table, where=""):
    with psycopg.connect(ci) as c:
        return c.execute(f"SELECT count(*) FROM raw.{table} {where}").fetchone()[0]


def test_first_load_then_rerun_is_idempotent(db, source):
    first = ingest(source, db, demo_cells=("B9001",))
    assert first == {"success": 2, "skipped_unchanged": 0, "skipped_duplicate": 0, "failed": 0}
    assert count(db, "nasa_cycles") == 8  # 2 cellules x 4 cycles
    assert count(db, "nasa_discharge_samples") == 8  # 2 décharges x 4 points, B9001 seule

    second = ingest(source, db, demo_cells=("B9001",))
    assert second["skipped_unchanged"] == 2 and second["success"] == 0
    assert count(db, "nasa_cycles") == 8
    assert count(db, "nasa_discharge_samples") == 8


def test_empty_capacity_is_null_in_db(db, source):
    ingest(source, db, demo_cells=())
    assert count(db, "nasa_cycles", "WHERE cell_id='B9001' AND cycle_type='discharge' AND capacity_ah IS NULL") == 1
    assert count(db, "nasa_cycles", "WHERE capacity_ah = 0") == 0  # aucune valeur inventée


def test_changed_source_replaces_rows_without_duplicates(db, source):
    ingest(source, db, demo_cells=())
    synthetic.write_mat(source / "grp1" / "B9001.mat", "B9001", synthetic.make_cycles(1.2)[:3])
    res = ingest(source, db, demo_cells=())
    assert res["success"] == 1 and res["skipped_unchanged"] == 1
    assert count(db, "nasa_cycles", "WHERE cell_id='B9001'") == 3
    assert count(db, "nasa_cycles", "WHERE cell_id='B9002'") == 4


def test_adding_demo_cell_reloads_samples_only_for_it(db, source):
    ingest(source, db, demo_cells=())
    assert count(db, "nasa_discharge_samples") == 0
    res = ingest(source, db, demo_cells=("B9002",))
    assert res["success"] == 1 and res["skipped_unchanged"] == 1
    assert count(db, "nasa_discharge_samples", "WHERE cell_id='B9002'") == 8


def test_identical_duplicate_is_skipped(db, source):
    (source / "grp2").mkdir()
    shutil.copy(source / "grp1" / "B9001.mat", source / "grp2" / "B9001.mat")
    res = ingest(source, db, demo_cells=())
    assert res["skipped_duplicate"] == 1 and res["success"] == 2
    assert count(db, "nasa_cycles", "WHERE cell_id='B9001'") == 4


def test_conflicting_duplicates_are_refused(db, source):
    synthetic.write_mat(source / "grp2" / "B9001.mat", "B9001", synthetic.make_cycles(1.1))
    with pytest.raises(ValueError, match="doublons différents"):
        ingest(source, db, demo_cells=())


def test_corrupt_file_is_logged_and_does_not_block_others(db, source):
    (source / "grp1" / "B9003.mat").write_bytes(b"pas un fichier matlab")
    res = ingest(source, db, demo_cells=())
    assert res["failed"] == 1 and res["success"] == 2
    assert count(db, "nasa_cycles", "WHERE cell_id='B9003'") == 0
    assert count(db, "ingestion_runs", "WHERE cell_id='B9003' AND status='failed' AND error IS NOT NULL") == 1
