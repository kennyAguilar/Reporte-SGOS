# SGOS — Sistema de Gestión de Operaciones de Slots

Aplicación web interna para procesar, analizar y visualizar reportes de operaciones de slots desde archivos Excel, con dashboards en tiempo real.

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12 + Flask 3.0 |
| Base de datos | PostgreSQL en [Neon.tech](https://neon.tech) |
| Driver BD | psycopg2-binary |
| Autenticación | Sesiones Flask + Werkzeug (pbkdf2:sha256) |
| Frontend | Carbon Design System v11 — tema Gray 100 |

## Estructura del proyecto

```
.
├── app.py                      # Punto de entrada, factory create_app()
├── config.py                   # Configuración (SECRET_KEY, DATABASE_URL, etc.)
├── core/
│   ├── auth.py                 # login_required, current_user()
│   └── database.py             # get_connection() → Neon PostgreSQL
├── modules/
│   ├── auth.py                 # Blueprint: /login, /logout
│   └── home.py                 # Blueprint: / (protegido)
├── repositories/
│   └── usuarios_repository.py  # Consultas SQL de la tabla users
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── home.html
│   └── errors/
│       ├── 404.html
│       └── 500.html
├── static/
│   ├── css/
│   │   ├── carbon-theme.css
│   │   ├── login.css
│   │   └── base.css
│   └── js/
│       └── login.js
├── set_password.py             # Utilidad: restablecer contraseña de usuario
├── requirements.txt
├── .env.example
└── .gitignore
```

## Instalación y arranque

### 1. Clonar el repositorio

```bash
git clone https://github.com/kennyAguilar/Reporte-SGOS.git
cd Reporte-SGOS
```

### 2. Crear entorno virtual

> **Windows** — usar `py -3.12` (no el `python` del PATH si usas Inkscape u otras herramientas que incluyen Python en el PATH).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Copia `.env.example` a `.env` y completa los valores:

```powershell
Copy-Item .env.example .env
```

```env
DATABASE_URL=postgresql://usuario:password@host/dbname?sslmode=require
SECRET_KEY=tu-clave-secreta-aleatoria
APP_NAME=SGOS
FLASK_ENV=development
```

### 4. Arrancar el servidor

```powershell
.\.venv\Scripts\python.exe app.py
```

El servidor quedará disponible en:
- Local: `http://127.0.0.1:5000`
- Red LAN: `http://<tu-ip-local>:5000`

## Base de datos

La aplicación usa Neon.tech (PostgreSQL serverless). La tabla principal de usuarios es `public.users`:

| Columna | Tipo | Descripción |
|---|---|---|
| id | serial PK | Identificador |
| username | text | Nombre de usuario |
| password_hash | text | Hash Werkzeug (pbkdf2:sha256) |
| is_admin | boolean | Rol administrador |
| created_at | timestamptz | Fecha de creación |
| last_login_at | timestamptz | Último ingreso |

### Restablecer contraseña de un usuario

```powershell
.\.venv\Scripts\python.exe set_password.py
```

## Módulos planificados

| Módulo | Estado |
|---|---|
| Login / Sesión | ✅ Implementado |
| Home / Resumen KPIs | 🔄 En desarrollo |
| Getnet (transacciones) | 📋 Pendiente |
| Premios | 📋 Pendiente |
| COMPS | 📋 Pendiente |
| CoinIn | 📋 Pendiente |
| Gestión de usuarios | 📋 Pendiente |

## Seguridad

- Las contraseñas se almacenan como hash `pbkdf2:sha256:600000` (Werkzeug).
- El archivo `.env` **nunca** se sube al repositorio (está en `.gitignore`).
- Las sesiones usan `SECRET_KEY` configurada en `.env`.
- Todas las rutas excepto `/login` requieren sesión activa.
