import sys

from src.ingest.config import conninfo

from .run import run


def main() -> int:
    counts = run(conninfo())
    print(" | ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
