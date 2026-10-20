import argparse
import logging
import sys
from pathlib import Path

from .config import DEFAULT_SOURCE, DEMO_CELLS, conninfo
from .load import ingest


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m src.ingest", description="Charge les .mat NASA dans PostgreSQL (schéma raw).")
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="dossier contenant les B*.mat extraits")
    p.add_argument("--demo-cells", default=",".join(DEMO_CELLS),
                   help="cellules dont on charge les séries complètes (liste séparée par des virgules, vide = aucune)")
    p.add_argument("--force", action="store_true", help="recharger même si la source n'a pas changé")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    demo = tuple(c for c in args.demo_cells.split(",") if c)
    counts = ingest(args.source, conninfo(), demo, force=args.force)
    print(" | ".join(f"{k}={v}" for k, v in counts.items()))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
