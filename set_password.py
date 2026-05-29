"""Utilidad de administración: fija/restablece la contraseña de un usuario.

Uso:
    .\\.venv\\Scripts\\python.exe set_password.py

Pide el username y la contraseña (oculta) directamente en la terminal,
genera el hash compatible con Werkzeug y lo guarda en la tabla `users`.
"""
import getpass
import sys

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

from core.database import get_connection


def main():
    username = input("Usuario: ").strip()
    if not username:
        print("Usuario vacío. Cancelado.")
        return 1

    pwd = getpass.getpass("Nueva contraseña: ")
    pwd2 = getpass.getpass("Repite la contraseña: ")
    if not pwd:
        print("Contraseña vacía. Cancelado.")
        return 1
    if pwd != pwd2:
        print("Las contraseñas no coinciden. Cancelado.")
        return 1

    password_hash = generate_password_hash(pwd)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (password_hash, username),
            )
            if cur.rowcount == 0:
                print(f"No existe el usuario '{username}'. Nada cambió.")
                conn.rollback()
                return 1
        conn.commit()
        print(f"Contraseña actualizada para '{username}'.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
