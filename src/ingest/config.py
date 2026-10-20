import os
from pathlib import Path

from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DEFAULT_SOURCE = DATA_DIR / "nasa_raw"
SQL_RAW_DIR = ROOT / "sql" / "10_raw"

SOURCE_URL = "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
SOURCE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"

# Cellules dont on charge les séries temporelles complètes (les 4 du lot FY08Q4)
DEMO_CELLS = ("B0005", "B0006", "B0007", "B0018")

# À incrémenter quand le contenu produit par le loader change : force le rechargement
LOADER_VERSION = 2  # v2 : ajout de re_imag_ohm / rct_imag_ohm


def conninfo(dbname: str | None = None) -> str:
    """Connexion admin construite depuis les variables du .env (exportées par make)."""
    return make_conninfo(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
        dbname=dbname or os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
