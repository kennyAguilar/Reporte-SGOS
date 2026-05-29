"""Consultas SQL de la tabla usuarios."""
from core.database import get_connection


def get_user_by_username(username):
    """Devuelve el usuario por su username, o None si no existe."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, password_hash, is_admin
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            return cur.fetchone()
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
