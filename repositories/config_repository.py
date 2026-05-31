"""Consultas SQL del apartado de Configuración.

Cubre dos áreas:

1. Slots activos: estado activo/inactivo de cada slot attendant de Getnet.
   - La tabla `slot_attendants` guarda SOLO el estado (nombre + activo).
   - Los nombres salen de DISTINCT getnet.slot_attendant.
   - Un attendant que no está en la tabla se considera ACTIVO por defecto.
   - El módulo Getnet excluye de sus estadísticas SOLO los marcados como
     inactivos (ver getnet_repository._inactivos_sql()).

2. Gestión de usuarios: listar, crear y restablecer contraseñas.
"""
from werkzeug.security import generate_password_hash

from core.database import get_connection


def ensure_schema():
    """Crea la tabla slot_attendants si no existe (idempotente)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS slot_attendants (
                    nombre     text PRIMARY KEY,
                    activo     boolean     NOT NULL DEFAULT true,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Slots activos
# ---------------------------------------------------------------------------
def list_slot_attendants():
    """Lista todos los slot attendants de getnet con su estado y nº de operaciones.

    Devuelve una lista de dicts: {nombre, activo, operaciones}, ordenada por
    nombre. Un attendant sin registro en slot_attendants se reporta como activo.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT g.slot_attendant                     AS nombre,
                       COALESCE(sa.activo, true)            AS activo,
                       COUNT(*)                              AS operaciones
                FROM getnet g
                LEFT JOIN slot_attendants sa
                       ON sa.nombre = g.slot_attendant
                WHERE g.slot_attendant IS NOT NULL
                  AND g.slot_attendant <> ''
                GROUP BY g.slot_attendant, sa.activo
                ORDER BY g.slot_attendant
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def set_slot_activo(nombre, activo):
    """Fija el estado activo/inactivo de un slot attendant (upsert)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO slot_attendants (nombre, activo, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (nombre)
                DO UPDATE SET activo = EXCLUDED.activo, updated_at = now()
                """,
                (nombre, bool(activo)),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gestión de usuarios
# ---------------------------------------------------------------------------
def list_users():
    """Lista los usuarios del sistema (sin exponer el hash)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, is_admin, created_at, last_login_at
                FROM users
                ORDER BY username
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def create_user(username, password, is_admin=False):
    """Crea un usuario. Devuelve True si se creó, False si ya existía."""
    password_hash = generate_password_hash(password)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (username, password_hash, is_admin, created_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (username) DO NOTHING
                RETURNING id
                """,
                (username, password_hash, bool(is_admin)),
            )
            creado = cur.fetchone() is not None
        conn.commit()
        return creado
    finally:
        conn.close()


def reset_password(username, password):
    """Cambia la contraseña de un usuario. Devuelve True si existía."""
    password_hash = generate_password_hash(password)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (password_hash, username),
            )
            actualizado = cur.rowcount > 0
        conn.commit()
        return actualizado
    finally:
        conn.close()
