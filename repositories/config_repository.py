"""Consultas SQL del apartado de Configuración.

Cubre cuatro áreas:

1. Slots activos: estado activo/inactivo de cada slot attendant.
   - La tabla `slot_attendants` guarda SOLO el estado (nombre + activo).
   - Los nombres salen de DISTINCT slot_attendant de `getnet` ∪ `premios`.
   - Un attendant que no está en la tabla se considera ACTIVO por defecto.
   - Getnet, Premios y Asistentes excluyen de sus estadísticas SOLO los
     marcados como inactivos (constante `_FILTRO_ACTIVOS` en cada repositorio).

2. Gestión de usuarios: listar, crear, activar/desactivar, cambiar rol,
   eliminar y restablecer contraseñas. `users.activo = false` bloquea el login.

3. Jefaturas: datos maestros (usuario_id, nombre, area) que el módulo COMPS
   usa para cruzar las operaciones con su jefatura. Se administra a mano.

4. Categorías: % de margen teórico por categoría de jugador (DREAMS, GOLD,
   BLACK, PLATINUM, AUTOEXCLUIDO, Primario). Se usan para calcular el monto
   de cortesías disponible/autorizado (Coin In Cero y Análisis).
"""
from werkzeug.security import generate_password_hash

from core.database import get_connection
from core.formato import fecha_corta
from psycopg2.extras import execute_values

# La categoría "Primario" es el factor base de todos los montos autorizados:
# si se elimina, Coin In Cero y Análisis pasan a mostrar $0. No se puede borrar.
CATEGORIA_PROTEGIDA = "PRIMARIO"


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
            # Usuarios desactivados no pueden iniciar sesión (ver modules/auth.py).
            cur.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS activo boolean NOT NULL DEFAULT true"
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS categorias_margen (
                    id         serial PRIMARY KEY,
                    categoria  varchar(100)  NOT NULL UNIQUE,
                    porcentaje numeric(5, 2) NOT NULL DEFAULT 0,
                    created_at timestamptz   NOT NULL DEFAULT now(),
                    updated_at timestamptz   NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                INSERT INTO categorias_margen (categoria, porcentaje) VALUES
                    ('DREAMS', 0.0),
                    ('DREAMS GOLD', 2.0),
                    ('DREAMS BLACK', 3.0),
                    ('DREAMS PLATINUM', 4.0),
                    ('AUTOEXCLUIDO', 0.0),
                    ('Primario', 6.5)
                ON CONFLICT (categoria) DO NOTHING
                """
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Slots activos
# ---------------------------------------------------------------------------
def _tabla_existe(cur, tabla):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS existe", (f"public.{tabla}",))
    return bool((cur.fetchone() or {}).get("existe"))


def list_slot_attendants():
    """Lista todos los slot attendants (Getnet ∪ Premios) con estado y actividad.

    Devuelve una lista de dicts ordenada por nombre:
        {nombre, activo, getnet, premios, operaciones, ultima (date|None),
         ultima_fmt ("dd/mm/aaaa" o "—")}
    `operaciones` suma ambas tablas y `ultima` es la jornada más reciente en
    cualquiera de las dos. Un attendant sin registro en slot_attendants se
    reporta como activo. Si `premios` aún no existe, se usa solo Getnet.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fuentes = ["SELECT slot_attendant, jornada, 'getnet' AS origen FROM getnet"]
            if _tabla_existe(cur, "premios"):
                fuentes.append("SELECT slot_attendant, jornada, 'premios' AS origen FROM premios")
            union = " UNION ALL ".join(fuentes)
            cur.execute(
                f"""
                SELECT u.slot_attendant                                     AS nombre,
                       COALESCE(sa.activo, true)                            AS activo,
                       SUM(CASE WHEN u.origen = 'getnet'  THEN 1 ELSE 0 END) AS getnet,
                       SUM(CASE WHEN u.origen = 'premios' THEN 1 ELSE 0 END) AS premios,
                       COUNT(*)                                              AS operaciones,
                       MAX(u.jornada)                                        AS ultima
                FROM ({union}) u
                LEFT JOIN slot_attendants sa
                       ON sa.nombre = u.slot_attendant
                WHERE u.slot_attendant IS NOT NULL
                  AND u.slot_attendant <> ''
                GROUP BY u.slot_attendant, sa.activo
                ORDER BY u.slot_attendant
                """
            )
            filas = []
            for r in cur.fetchall():
                d = dict(r)
                d["getnet"] = int(d["getnet"] or 0)
                d["premios"] = int(d["premios"] or 0)
                d["operaciones"] = int(d["operaciones"] or 0)
                d["ultima_fmt"] = fecha_corta(d["ultima"]) if d["ultima"] else "—"
                filas.append(d)
            return filas
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
                SELECT id, username, is_admin, activo, created_at, last_login_at
                FROM users
                ORDER BY username
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_user(user_id):
    """Devuelve {id, username, is_admin, activo} o None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, is_admin, activo FROM users WHERE id = %s",
                (user_id,),
            )
            r = cur.fetchone()
            return dict(r) if r else None
    finally:
        conn.close()


def count_admins_activos(excluir_id=None):
    """Cantidad de administradores activos, opcionalmente sin contar a uno."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM users
                WHERE is_admin = true AND activo = true
                  AND (%s IS NULL OR id <> %s)
                """,
                (excluir_id, excluir_id),
            )
            return int((cur.fetchone() or {}).get("n") or 0)
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


def set_user_activo(user_id, activo):
    """Activa o desactiva un usuario. Devuelve True si existía."""
    return _update_user(user_id, "activo = %s", (bool(activo),))


def set_user_admin(user_id, is_admin):
    """Cambia el rol de un usuario. Devuelve True si existía."""
    return _update_user(user_id, "is_admin = %s", (bool(is_admin),))


def _update_user(user_id, set_sql, valores):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {set_sql} WHERE id = %s", (*valores, user_id))
            actualizado = cur.rowcount > 0
        conn.commit()
        return actualizado
    finally:
        conn.close()


def delete_user(user_id):
    """Elimina un usuario. Devuelve True si existía."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            eliminado = cur.rowcount > 0
        conn.commit()
        return eliminado
    finally:
        conn.close()


def reset_password(username, password):
    """Cambia la contraseña de un usuario por username. Devuelve True si existía."""
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


def reset_password_by_id(user_id, password):
    """Cambia la contraseña de un usuario por id. Devuelve True si existía."""
    return _update_user(user_id, "password_hash = %s", (generate_password_hash(password),))


# ---------------------------------------------------------------------------
# Jefaturas (datos maestros para COMPS)
# ---------------------------------------------------------------------------
def list_jefaturas():
    """Lista todas las jefaturas ordenadas por área y nombre.

    Incluye `cortesias`: cantidad de registros de COMPS asociados por
    usuario_id (0 si la tabla `comps` aún no existe). Sirve para saber si una
    jefatura está en uso antes de eliminarla.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if _tabla_existe(cur, "comps"):
                cur.execute(
                    """
                    SELECT j.id, j.usuario_id, j.nombre, j.area,
                           COUNT(c.id) AS cortesias
                    FROM jefaturas j
                    LEFT JOIN comps c ON c.usuario_id = j.usuario_id
                    GROUP BY j.id, j.usuario_id, j.nombre, j.area
                    ORDER BY j.area NULLS LAST, j.nombre
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, usuario_id, nombre, area, 0 AS cortesias
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


# ---------------------------------------------------------------------------
# Categorías (% de margen teórico por categoría de jugador)
# ---------------------------------------------------------------------------
# Variantes de categoría que llegan sin el prefijo "DREAMS" desde los Excel.
_ALIAS_CATEGORIA = {
    "BLACK": "DREAMS BLACK",
    "GOLD": "DREAMS GOLD",
    "PLATINUM": "DREAMS PLATINUM",
}


def normalizar_categoria(categoria):
    """Homologa variantes de categoría a las claves de categorias_margen."""
    cat = (categoria or "").strip().upper()
    return _ALIAS_CATEGORIA.get(cat, cat)


def get_porcentajes_margen():
    """Devuelve (pct_primario, {CATEGORIA_EN_MAYUSCULAS: pct})."""
    pct = {
        c["categoria"].strip().upper(): float(c["porcentaje"])
        for c in list_categorias_margen()
    }
    return pct.get("PRIMARIO", 0.0), pct


def calcular_monto_autorizado(coin_in, categoria, pct_primario, pct_por_categoria):
    """Coin In × % Primario × % de la categoría del jugador.

    Categoría sin match en Configuración -> 0 (no se puede calcular).
    """
    pct_categoria = pct_por_categoria.get(normalizar_categoria(categoria))
    if pct_categoria is None:
        return 0
    return coin_in * pct_primario / 100 * pct_categoria / 100


def list_categorias_margen():
    """Lista todas las categorías con su % de margen, ordenadas por id.

    Cada fila trae `porcentaje` (Decimal), `porcentaje_fmt` ("6,5") y
    `protegida` (True para Primario, que no se puede eliminar).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, categoria, porcentaje
                FROM categorias_margen
                ORDER BY id
                """
            )
            filas = []
            for r in cur.fetchall():
                d = dict(r)
                pct = float(d["porcentaje"] or 0)
                d["porcentaje_fmt"] = (f"{pct:.2f}".rstrip("0").rstrip(".") or "0").replace(".", ",")
                d["protegida"] = d["categoria"].strip().upper() == CATEGORIA_PROTEGIDA
                filas.append(d)
            return filas
    finally:
        conn.close()


def create_categoria_margen(categoria, porcentaje):
    """Crea una categoría. Devuelve True si se creó, False si ya existía."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO categorias_margen (categoria, porcentaje)
                VALUES (%s, %s)
                ON CONFLICT (categoria) DO NOTHING
                RETURNING id
                """,
                (categoria, porcentaje),
            )
            creado = cur.fetchone() is not None
        conn.commit()
        return creado
    finally:
        conn.close()


def update_categoria_margen(id, categoria, porcentaje):
    """Actualiza una categoría existente. Devuelve True si existía."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE categorias_margen
                SET categoria = %s, porcentaje = %s, updated_at = now()
                WHERE id = %s
                """,
                (categoria, porcentaje, id),
            )
            actualizado = cur.rowcount > 0
        conn.commit()
        return actualizado
    finally:
        conn.close()


def delete_categoria_margen(id):
    """Elimina una categoría por id. Devuelve True si existía.

    La categoría Primario está protegida: lanza ValueError en vez de borrarla.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT categoria FROM categorias_margen WHERE id = %s", (id,))
            fila = cur.fetchone()
            if fila and fila["categoria"].strip().upper() == CATEGORIA_PROTEGIDA:
                raise ValueError("La categoría Primario no se puede eliminar.")
            cur.execute("DELETE FROM categorias_margen WHERE id = %s", (id,))
            eliminado = cur.rowcount > 0
        conn.commit()
        return eliminado
    finally:
        conn.close()
