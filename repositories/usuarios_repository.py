"""Consultas SQL de la tabla usuarios."""
from core.database import get_connection


def get_user_by_username(username):
    """Devuelve el usuario por su username (con `activo`), o None si no existe."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, password_hash, is_admin, activo
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_password_hash(user_id):
    """Devuelve el hash actual de la contraseña del usuario, o None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
            r = cur.fetchone()
            return r["password_hash"] if r else None
    finally:
        conn.close()


def update_password(user_id, password_hash):
    """Guarda un nuevo hash de contraseña. Devuelve True si el usuario existía."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (password_hash, user_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
        return ok
    finally:
        conn.close()


def update_last_login(user_id):
    """Actualiza la marca de último ingreso del usuario."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                (user_id,),
            )
        conn.commit()
    finally:
        conn.close()
