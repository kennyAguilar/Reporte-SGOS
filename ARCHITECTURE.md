# SGOS — ARCHITECTURE.md

Arquitectura técnica del **Sistema de Gestión de Operaciones de Slots (SGOS)**.

**Alcance de este documento:** definir cómo está construido el proyecto, cómo debe organizarse el código y cómo deben separarse los módulos.  
**No contiene:** decisiones visuales detalladas ni reglas de negocio específicas de Excel.

---

## 1. Stack tecnológico oficial

SGOS se construye con el siguiente stack:

| Capa | Tecnología | Uso |
|---|---|---|
| Backend | Flask + Python | Servidor web, rutas, procesamiento de archivos y lógica de aplicación |
| Base de datos | Neon.tech / PostgreSQL | Persistencia principal de datos procesados |
| Frontend | HTML + Jinja2 + CSS | Vistas renderizadas desde Flask |
| Diseño UI | Carbon Design System v11 | Sistema visual base |
| Tema visual | Gray 100 / Dark Theme | Interfaz oscura para dashboards |
| Procesamiento de Excel | Python + Pandas / OpenPyXL | Lectura, normalización y validación de archivos Excel |
| Producción recomendada | Seenode | Plataforma principal de despliegue |
| Respaldo / pruebas | Render | Alternativa de despliegue o entorno de respaldo |

Importante: **Carbon Design System no es Material Design**. La referencia visual oficial del proyecto es Carbon Design System.

---

## 2. Separación entre documentos del proyecto

| Documento | Responsabilidad |
|---|---|
| `DESIGN.md` | Diseño visual, pantallas, colores, layout, componentes y comportamiento UI |
| `ARCHITECTURE.md` | Stack, estructura del código, módulos, Blueprints, conexión a BD y despliegue |
| `FUNCTIONAL_RULES.md` | Reglas de negocio: Excel, Jornada, ID único, filtros, módulos y validaciones |

La IA debe revisar el documento correcto según la tarea solicitada.

---

## 3. Principio principal de arquitectura

El archivo `app.py` **no debe concentrar toda la lógica del sistema**.

`app.py` debe funcionar como punto de entrada de Flask y debe encargarse principalmente de:

- crear la aplicación Flask;
- cargar configuración;
- registrar Blueprints;
- inicializar extensiones;
- definir manejadores globales de error si corresponde;
- arrancar la aplicación en desarrollo local.

La lógica de cada módulo debe vivir en archivos separados.

---

## 4. Estructura recomendada del proyecto

```text
sgos/
│
├── app.py                          # Punto de entrada principal
├── config.py                       # Configuración general y variables de entorno
├── requirements.txt                # Dependencias del proyecto
├── .env.example                    # Ejemplo de variables necesarias, sin claves reales
│
├── core/
│   ├── __init__.py
│   ├── database.py                 # Conexión a Neon.tech / PostgreSQL
│   ├── auth.py                     # Login, sesión y autorización
│   ├── errors.py                   # Manejo centralizado de errores
│   └── utils.py                    # Utilidades compartidas
│
├── modules/
│   ├── __init__.py
│   ├── home.py                     # Home / Resumen principal
│   ├── getnet.py                   # Rutas y lógica del módulo Getnet
│   ├── premios.py                  # Rutas y lógica del módulo Premios
│   ├── comps.py                    # Rutas y lógica del módulo COMPS
│   ├── coinin.py                   # Rutas y lógica del módulo CoinIn / CoinIn Cero
│   ├── analisis.py                 # Análisis general
│   ├── control.py                  # Control operativo / diferencias / validaciones
│   └── usuarios.py                 # Usuarios y roles, si aplica
│
├── services/
│   ├── __init__.py
│   ├── excel_service.py            # Lectura y validación común de Excel
│   ├── export_service.py           # Exportaciones a Excel
│   ├── getnet_service.py           # Tratamiento específico de Getnet
│   ├── premios_service.py          # Tratamiento específico de Premios
│   ├── comps_service.py            # Tratamiento específico de COMPS
│   └── coinin_service.py           # Tratamiento específico de CoinIn
│
├── repositories/
│   ├── __init__.py
│   ├── getnet_repository.py        # Consultas SQL de Getnet
│   ├── premios_repository.py       # Consultas SQL de Premios
│   ├── comps_repository.py         # Consultas SQL de COMPS
│   └── coinin_repository.py        # Consultas SQL de CoinIn
│
├── templates/
│   ├── base.html                   # Layout base con header y filtros
│   ├── login.html                  # Login
│   ├── home.html                   # Resumen principal
│   ├── getnet.html                 # Vista Getnet
│   ├── premios.html                # Vista Premios
│   ├── comps.html                  # Vista COMPS
│   ├── coinin.html                 # Vista CoinIn / CoinIn Cero
│   └── errors/
│       ├── 404.html
│       └── 500.html
│
├── static/
│   ├── css/
│   │   ├── base.css
│   │   ├── carbon-theme.css
│   │   ├── login.css
│   │   ├── dashboard.css
│   │   └── tables.css
│   ├── js/
│   │   ├── filters.js              # Abrir/cerrar filtros globales
│   │   ├── upload.js               # Flujo de carga Excel
│   │   └── dashboard.js
│   └── img/
│
└── tests/
    ├── test_getnet.py
    ├── test_premios.py
    ├── test_comps.py
    └── test_functional_rules.py
```

Esta estructura puede simplificarse al inicio, pero la regla obligatoria es mantener `app.py` liviano.

---

## 5. Rol de `app.py`

Ejemplo recomendado:

```python
from flask import Flask
from config import Config

from modules.home import home_bp
from modules.getnet import getnet_bp
from modules.premios import premios_bp
from modules.comps import comps_bp
from modules.coinin import coinin_bp
from modules.analisis import analisis_bp
from modules.control import control_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(home_bp)
    app.register_blueprint(getnet_bp)
    app.register_blueprint(premios_bp)
    app.register_blueprint(comps_bp)
    app.register_blueprint(coinin_bp)
    app.register_blueprint(analisis_bp)
    app.register_blueprint(control_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
```

Regla: si `app.py` crece demasiado, se debe mover código al módulo correspondiente.

---

## 6. Uso de Blueprints

Cada módulo funcional debe tener su propio Blueprint.

Ejemplo para Getnet:

```python
from flask import Blueprint, render_template, request

getnet_bp = Blueprint("getnet", __name__, url_prefix="/getnet")


@getnet_bp.route("/")
def index():
    return render_template("getnet.html")
```

Rutas sugeridas:

| Módulo | Blueprint | Prefix |
|---|---|---|
| Home | `home_bp` | `/` |
| Getnet | `getnet_bp` | `/getnet` |
| Premios | `premios_bp` | `/premios` |
| COMPS | `comps_bp` | `/comps` |
| CoinIn | `coinin_bp` | `/coinin` |
| Análisis general | `analisis_bp` | `/analisis-general` |
| Control | `control_bp` | `/control` |
| Usuarios | `usuarios_bp` | `/usuarios` |

---

## 7. Separación por capas

Para evitar archivos extensos, cada módulo debe separar responsabilidades.

### 7.1 Rutas / Blueprints

Responsables de:

- recibir requests;
- leer parámetros de filtros;
- llamar servicios;
- renderizar templates;
- devolver respuestas o redirecciones.

No deben contener procesamiento pesado de Excel ni SQL complejo.

### 7.2 Services

Responsables de:

- procesamiento de Excel;
- limpieza de datos;
- cálculo de Jornada;
- validación de columnas;
- generación de ID único;
- reglas de negocio;
- preparación de datos para guardar o mostrar.

### 7.3 Repositories

Responsables de:

- consultas SQL;
- inserts, updates y selects;
- búsqueda por filtros;
- consultas de KPIs;
- acceso a Neon.tech / PostgreSQL.

### 7.4 Templates

Responsables de:

- estructura HTML;
- mostrar datos recibidos;
- reutilizar `base.html`;
- no contener lógica pesada.

### 7.5 Static

Responsables de:

- CSS;
- JavaScript de interacción visual;
- comportamiento del panel de filtros;
- assets.

---

## 8. Conexión a Neon.tech / PostgreSQL

La conexión debe centralizarse en `core/database.py`.

Reglas:

- usar `DATABASE_URL` desde variable de entorno;
- no escribir contraseñas reales en el código;
- no subir `.env` al repositorio;
- usar `.env.example` solo como referencia;
- cerrar conexiones correctamente;
- manejar errores de conexión con mensajes claros.

Ejemplo conceptual:

```python
import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no está configurada")

    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
```

---

## 9. Variables de entorno

Variables recomendadas:

```text
FLASK_ENV=production
SECRET_KEY=change-me
DATABASE_URL=postgresql://...
APP_NAME=SGOS
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH_MB=50
```

Reglas:

- `SECRET_KEY` debe ser distinta en producción;
- `DATABASE_URL` nunca debe exponerse en el frontend;
- los archivos `.env` reales no se deben subir a GitHub;
- los ambientes Seenode y Render deben tener sus propias variables.

---

## 10. Despliegue

### 10.1 Seenode

Se considera el ambiente recomendado para producción.

Uso:

- versión oficial para operación;
- conexión principal a Neon.tech;
- procesamiento de archivos Excel;
- acceso de usuarios reales.

### 10.2 Render

Se puede mantener como respaldo, pruebas o alternativa.

Uso:

- validación de cambios;
- pruebas previas;
- ambiente secundario.

Regla importante: no mantener dos versiones productivas activas sin control, porque puede generar confusión de datos y usuarios.

### 10.3 Desarrollo local

Uso:

- pruebas con Flask;
- validación de módulos;
- revisión de cambios antes del despliegue.

---

## 11. Flujo general de carga de Excel

Flujo recomendado:

```text
Usuario inicia sesión
        ↓
Selecciona módulo o Cargar Excel
        ↓
Sube archivo Excel
        ↓
El sistema valida extensión y tamaño
        ↓
El service correspondiente lee el archivo
        ↓
Se validan hojas y encabezados
        ↓
Se normalizan columnas
        ↓
Se calcula Jornada e ID único si corresponde
        ↓
Se detectan duplicados
        ↓
Se inserta o actualiza en Neon.tech
        ↓
Se muestra resumen de carga
        ↓
Home / módulo actualiza KPIs
```

---

## 12. Autenticación y sesiones

Reglas base:

- login requerido para acceder al sistema;
- usuario visible en header;
- cerrar sesión desde botón `Salir`;
- proteger rutas internas con sesión;
- no mostrar datos si no hay sesión activa.

Roles sugeridos:

| Rol | Permisos |
|---|---|
| Administrador | Cargar Excel, exportar, gestionar usuarios, ver todo |
| Operador | Cargar y consultar módulos permitidos |
| Consulta | Ver dashboards y exportar si se permite |

Los roles definitivos deben confirmarse antes de implementarlos.

---

## 13. Exportación a Excel

La exportación debe centralizarse en `services/export_service.py`.

Reglas técnicas:

- no duplicar lógica de exportación en cada módulo;
- reutilizar filtros aplicados;
- usar nombres de archivo claros;
- generar archivos temporales seguros;
- evitar guardar archivos exportados permanentemente si no es necesario.

---

## 14. Manejo de errores

Errores esperados:

- archivo inválido;
- hoja no encontrada;
- encabezado incorrecto;
- columna faltante;
- duplicados;
- error de conexión a base de datos;
- sesión expirada;
- error de permisos.

Reglas:

- los errores técnicos se registran en logs;
- el usuario ve mensajes claros y breves;
- no mostrar trazas internas de Python en producción;
- cada módulo debe indicar qué archivo o columna generó el problema.

---

## 15. Convenciones para la IA

Cuando la IA modifique el proyecto:

1. No debe convertir `app.py` en un archivo gigante.
2. Debe modificar solo el módulo relacionado con la tarea.
3. Debe evitar tocar Getnet si el cambio solicitado es de Premios, salvo que sea una utilidad compartida.
4. Debe poner funciones comunes en `services/` o `core/`.
5. Debe consultar `FUNCTIONAL_RULES.md` antes de cambiar columnas, Jornada o ID único.
6. Debe consultar `DESIGN.md` antes de cambiar pantallas, colores, layout o filtros.
7. Debe mantener nombres claros y consistentes.
8. Debe evitar duplicar funciones de lectura de Excel.
9. Debe separar rutas, servicios y consultas de base de datos.
10. Debe dejar comentarios solo donde ayuden a entender reglas importantes.

---

## 16. Convenciones de nombres

| Elemento | Convención | Ejemplo |
|---|---|---|
| Archivos Python | snake_case | `getnet_service.py` |
| Blueprints | snake_case + `_bp` | `getnet_bp` |
| Templates | snake_case | `analisis_general.html` |
| CSS | kebab-case o módulo | `dashboard.css` |
| Funciones | snake_case | `calcular_jornada()` |
| Variables | snake_case | `fecha_jornada` |
| Tablas BD | snake_case | `getnet_operaciones` |

---

## 17. Regla final de arquitectura

SGOS debe crecer por módulos, no por acumulación dentro de `app.py`.

La arquitectura debe permitir que una persona o una IA trabaje en:

- Getnet sin romper Premios;
- Premios sin romper COMPS;
- COMPS sin romper CoinIn;
- diseño visual sin tocar reglas de negocio;
- reglas de negocio sin alterar el layout.
