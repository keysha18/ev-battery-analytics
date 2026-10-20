import os

from psycopg.conninfo import make_conninfo


def conninfo() -> str:
    """Connexion avec le rôle api_ro : lecture seule sur le schéma marts, rien d'autre."""
    return make_conninfo(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["API_RO_USER"],
        password=os.environ["API_RO_PASSWORD"],
        # Deuxième verrou en plus des droits du rôle : toute écriture serait refusée
        options="-c default_transaction_read_only=on",
        connect_timeout=5,
    )
