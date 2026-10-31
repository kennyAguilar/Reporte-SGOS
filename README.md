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
│   ├── csrf.py                 # Protección CSRF (token en sesión + before_request)
│   ├── database.py             # get_connection() → Neon PostgreSQL
│   ├── formato.py              # Helpers de formato (pesos, fechas)
│   └── sgos_parse.py           # Limpieza y normalización de Excel
├── modules/
│   ├── auth.py                 # Blueprint: /login, /logout, /mi-contrasena
│   ├── home.py                 # Blueprint: / (panel de control: alertas, último mes por módulo, estado de carga)
│   ├── getnet.py               # Blueprint: /getnet (dashboard, histórico, record, rendimiento)
│   ├── premios.py              # Blueprint: /premios (dashboard, histórico, record, rendimiento)
│   ├── asistentes.py           # Blueprint: /asistentes (rendimiento combinado Getnet + Premios)
│   ├── upload.py               # Blueprint: /upload (carga de Excel Getnet y Premios)
│   └── config.py               # Blueprint: /configuracion (admin — asistentes y usuarios)
├── repositories/
│   ├── usuarios_repository.py
│   ├── getnet_repository.py
│   ├── premios_repository.py
│   ├── asistentes_repository.py
│   ├── home_repository.py
│   ├── comps_repository.py
│   ├── upload_repository.py
│   └── config_repository.py
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── home.html
│   ├── upload.html
│   ├── getnet/
│   │   ├── dashboard.html
│   │   ├── historico.html
│   │   ├── record.html
│   │   └── placeholder.html
│   ├── premios/
│   │   ├── dashboard.html
│   │   ├── historico.html
│   │   └── record.html
│   ├── upload_premios.html
│   ├── config/
│   │   └── index.html
│   ├── partials/
│   │   ├── _header.html
│   │   └── _filters.html
│   └── errors/
│       ├── 404.html
│       └── 500.html
├── static/
│   ├── css/
│   │   ├── carbon-theme.css
│   │   ├── base.css
│   │   ├── dashboard.css
│   │   ├── getnet.css
│   │   ├── config.css
│   │   └── login.css
│   └── js/
│       ├── charts.js           # Chart.js: gráficos del dashboard Getnet
│       ├── filters.js          # Sidebar de filtros (año/mes)
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
| Home / Resumen — panel de control (alertas de rezago, último mes por módulo con Δ, tendencia, estado de carga) | ✅ Implementado |
| Getnet — Carga de Excel | ✅ Implementado |
| Getnet — Dashboard (KPIs con Δ mensual + gráficos + mapa de calor + donut formas de pago) | ✅ Implementado |
| Getnet — Histórico (resumen mensual con Δ, operaciones por hora) | ✅ Implementado |
| Getnet — Record Asistentes (podio, resumen operativo, transacciones, total acumulado) | ✅ Implementado |
| Getnet — Rendimiento (evaluación por asistente: prom./jornada, índice vs equipo, tendencia) | ✅ Implementado |
| Configuración (slots, usuarios con roles/estado, jefaturas, categorías — solo admin) | ✅ Implementado |
| Mi contraseña (cualquier usuario) + protección CSRF en todos los formularios | ✅ Implementado |
| Premios — Carga de Excel | ✅ Implementado |
| Premios — Dashboard (KPIs con Δ mensual + 5 gráficos + filtro por tipo de pago HP) | ✅ Implementado |
| Premios — Histórico (resumen mensual con Δ y ticket, operaciones por hora, conteo anual) | ✅ Implementado |
| Premios — Record Asistentes (podio, resumen por tipo, transacciones, acumulado) | ✅ Implementado |
| Premios — Rendimiento (evaluación por asistente: prom./jornada, índice vs equipo, tendencia) | ✅ Implementado |
| Asistentes — Rendimiento combinado Getnet + Premios (solo cantidades, podio, Top 10 apilado) | ✅ Implementado |
| COMPS | 📋 Pendiente |
| CoinIn | 📋 Pendiente |

