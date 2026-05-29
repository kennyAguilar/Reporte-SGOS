"""Conexión a Neon.tech / PostgreSQL."""
import os

import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    """Devuelve una conexión a PostgreSQL usando DATABASE_URL."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no está configurada")

    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
