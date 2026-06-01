"""Consultas SQL del apartado de Configuración.

Cubre dos áreas:

1. Slots activos: estado activo/inactivo de cada slot attendant de Getnet.
   - La tabla `slot_attendants` guarda SOLO el estado (nombre + activo).
   - Los nombres salen de DISTINCT getnet.slot_attendant.
   - Un attendant que no está en la tabla se considera ACTIVO por defecto.
   - El módulo Getnet excluye de sus estadísticas SOLO los marcados como
     inactivos (ver getnet_repository._inactivos_sql()).

2. Gestión de usuarios: listar, crear y restablecer contraseñas.

3. Jefaturas: datos maestros (usuario_id, nombre, area) que el módulo COMPS
   usará para cruzar las operaciones con su jefatura. Se administra a mano.
"""
from werkzeug.security import generate_password_hash

from core.database import get_connection
from psycopg2.extras import execute_values


def ensure_schema():
    """Crea las tablas de configuración si no existen (idempotente)."""
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS jefaturas (
                    id         serial PRIMARY KEY,
                    usuario_id varchar(50)  NOT NULL UNIQUE,
                    nombre     varchar(200) NOT NULL,
                    area       varchar(100),
                    created_at timestamptz  NOT NULL DEFAULT now(),
                    updated_at timestamptz  NOT NULL DEFAULT now()
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


# ---------------------------------------------------------------------------
# Jefaturas (datos maestros para COMPS)
# ---------------------------------------------------------------------------
def list_jefaturas():
    """Lista todas las jefaturas ordenadas por área y nombre."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, usuario_id, nombre, area
                FROM jefaturas
                ORDER BY area NULLS LAST, nombre
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_areas():
    """Lista las áreas distintas ya registradas (para sugerencias)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT area
                FROM jefaturas
                WHERE area IS NOT NULL AND TRIM(area) <> ''
                ORDER BY area
                """
            )
            return [r["area"] for r in cur.fetchall()]
    finally:
        conn.close()


def create_jefatura(usuario_id, nombre, area=None):
    """Crea una jefatura. Devuelve True si se creó, False si el usuario_id ya existía."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jefaturas (usuario_id, nombre, area)
                VALUES (%s, %s, %s)
                ON CONFLICT (usuario_id) DO NOTHING
                RETURNING id
                """,
                (usuario_id, nombre, area or None),
            )
            creado = cur.fetchone() is not None
        conn.commit()
        return creado
    finally:
        conn.close()


def upsert_jefaturas_desde_comps(pares):
    """Inserta jefaturas faltantes a partir de la carga de COMPS.

    `pares` es una lista de tuplas (usuario_id, nombre). Insertamos solo las
    que NO existen todavía: ON CONFLICT (usuario_id) DO NOTHING. No se tocan
    las jefaturas ya registradas, para preservar el `area` cargada a mano.

    Devuelve la cantidad de jefaturas realmente insertadas.
    """
    # Filtramos pares válidos (usuario_id obligatorio) y eliminamos duplicados
    # dentro del mismo archivo conservando el primer nombre visto.
    vistos = {}
    for usuario_id, nombre in pares:
        usuario_id = (usuario_id or "").strip()
        nombre = (nombre or "").strip()
        if usuario_id and usuario_id not in vistos:
            vistos[usuario_id] = nombre

    if not vistos:
        return 0

    valores = [(uid, nombre) for uid, nombre in vistos.items()]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            insertadas = execute_values(
                cur,
                """
                INSERT INTO jefaturas (usuario_id, nombre)
                VALUES %s
                ON CONFLICT (usuario_id) DO NOTHING
                RETURNING id
                """,
                valores,
                fetch=True,
            )
            inserted = len(insertadas)
        conn.commit()
        return inserted
    finally:
        conn.close()


def update_jefatura(id, usuario_id, nombre, area=None):
    """Actualiza una jefatura existente. Devuelve True si existía."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jefaturas
                SET usuario_id = %s, nombre = %s, area = %s, updated_at = now()
                WHERE id = %s
                """,
                (usuario_id, nombre, area or None, id),
            )
            actualizado = cur.rowcount > 0
        conn.commit()
        return actualizado
    finally:
        conn.close()


def delete_jefatura(id):
    """Elimina una jefatura por id. Devuelve True si existía."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jefaturas WHERE id = %s", (id,))
            eliminado = cur.rowcount > 0
        conn.commit()
        return eliminado
    finally:
        conn.close()
