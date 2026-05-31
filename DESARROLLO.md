# Bitácora de desarrollo — SGOS

> Este documento explica el proyecto **en lenguaje sencillo**, paso a paso, para
> ir entendiendo *qué se construyó, cómo funciona y por qué se tomó cada decisión*.
> Está pensado como un diario de aprendizaje: se va ampliando a medida que avanza
> el proyecto.

Para detalles más técnicos ver también:
[README.md](README.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DESIGN.md](DESIGN.md) · [FUNCTIONAL_RULES.md](FUNCTIONAL_RULES.md)

---

## 1. ¿Qué es este proyecto?

**SGOS** es una aplicación web interna para procesar reportes de operaciones de
slots (máquinas de juego) que llegan en archivos **Excel**, guardarlos en una base
de datos y mostrar resúmenes (KPIs) en un panel.

El flujo general es:

```
Archivo Excel  →  Leer y limpiar  →  Guardar en PostgreSQL  →  Mostrar KPIs en el Home
```

Habrá tres módulos de datos: **Getnet** (terminado), **Premios** y **COMPS**
(pendientes). Todos siguen el mismo patrón.

---

## 2. Cómo está organizado el código

El proyecto separa responsabilidades en carpetas. Cada una hace *una sola cosa*:

| Carpeta | Para qué sirve | Ejemplo |
|---|---|---|
| `core/` | Utilidades compartidas | conexión a BD, formato, parseo de datos |
| `modules/` | Rutas web (lo que ve el navegador) | `/login`, `/`, `/upload` |
| `repositories/` | Consultas SQL de cada tabla | insertar y leer de `getnet` |
| `templates/` | HTML (las páginas) | `home.html`, `upload.html` |
| `static/` | CSS y JavaScript | estilos, filtros |

**Idea clave:** las rutas web (`modules/`) *no* escriben SQL directamente. Le piden
los datos a `repositories/`. Así, si cambia la base de datos, solo se toca un lugar.

```
Navegador  →  modules/ (ruta)  →  repositories/ (SQL)  →  PostgreSQL
                    ↓
              templates/ (HTML)
```

---

## 3. Cómo arrancar el proyecto

> Importante: el `python` del sistema NO sirve aquí (es de otro programa). Hay que
> usar **siempre** el del entorno virtual `.venv`.

```powershell
.\.venv\Scripts\python.exe app.py
```

Luego abrir <http://127.0.0.1:5000>, iniciar sesión y usar la app.

---

## 4. Módulo Getnet — Carga de Excel ✅ (terminado)

Es el primer módulo completo. Permite subir el Excel mensual de Getnet, limpiar los
datos y guardarlos sin duplicar.

### 4.1 ¿Qué hace, paso a paso?

1. El usuario entra a **`/upload`** y selecciona el archivo Excel.
2. La app **lee** la hoja `Sheet1` (el encabezado real está en la fila 2).
3. **Valida** que estén las columnas necesarias.
4. **Limpia y transforma** cada fila (ver punto 4.3).
5. **Inserta** en la tabla `getnet`, evitando duplicados.
6. **Registra** la carga en la tabla `upload_log`.
7. Muestra un **resumen**: cuántas filas se procesaron, insertaron y omitieron.

### 4.2 La tabla `getnet`

| Columna | Tipo | Qué guarda |
|---|---|---|
| `id` | serial | identificador interno (automático) |
| `id_unico` | text (UNIQUE) | clave para evitar duplicados (ver 4.4) |
| `jornada` | date | día de operación (viene listo del Excel) |
| `fecha` | timestamp | fecha **y hora** de la operación |
| `monto` | integer | monto de la transacción |
| `slot_attendant` | text | persona que atendió |
| `forma_pago` | text | Débito / Crédito |
| `created_at` | timestamp | cuándo se cargó (automático) |

> Guardamos la **hora** dentro de `fecha` porque más adelante se necesita calcular
> *operaciones por hora en promedio*.

### 4.3 Limpieza de los datos (`core/sgos_parse.py`)

El Excel viene "sucio" y hay que normalizarlo. Algunos ejemplos reales:

- **Id Cliente** viene con una comilla al inicio (`'301720...`) → se la quitamos.
- **Fecha** viene como `01-01-2026 18:19` (día-mes-año) → la convertimos a fecha real
  indicando que el día va primero (`dayfirst=True`).
- **Jornada** ya viene lista como `2026-01-01` → solo la pasamos a tipo fecha.
- **Monto** y **Voucher** se normalizan a número/texto limpio.

Cada función está comentada en el archivo para que se entienda qué hace.

### 4.4 El problema de los duplicados (la decisión más importante)

**El problema:** con más de 10 terminales Getnet, el número de **voucher se repite
entre máquinas**. O sea, dos operaciones distintas pueden tener el mismo voucher.
Por eso el voucher *solo* no sirve como clave única.

**La solución:** creamos una clave compuesta llamada `id_unico` que junta varios
datos. La versión final incluye **la hora**:

```
id_unico = jornada + fecha(con hora) + id_cliente + monto + voucher
```

Ejemplo real:

```
2026-01-01_2026-01-01T18:19:00_301720020100077042767_20000_973
```

**¿Por qué incluir la hora?** Sin la hora, el archivo de enero perdía **3
operaciones reales** que compartían `jornada + id_cliente + monto + voucher` y solo
se diferenciaban por el horario (por ejemplo, 22:21 vs 22:30). Al agregar la hora:

- Operaciones reales distintas → distinta hora → **se conservan ambas**. ✅
- Subir el **mismo** archivo otra vez → misma hora → **misma clave** → se detecta
  como duplicado y no se repite. ✅

### 4.5 Cómo se evitan los duplicados en la base de datos

Al insertar usamos esta instrucción de PostgreSQL:

```sql
INSERT INTO getnet (...) VALUES (...)
ON CONFLICT (id_unico) DO NOTHING
```

`ON CONFLICT (id_unico) DO NOTHING` significa: *"si ya existe una fila con ese
`id_unico`, no hagas nada (ignórala)"*. Así, si subes el mismo mes dos veces, los
registros repetidos simplemente se saltan.

Además, para que sea **rápido**, no insertamos fila por fila (eso eran miles de
viajes a la base de datos). Usamos `execute_values`, que manda **todo en un solo
viaje**. Resultado: ~4 segundos para 2676 filas.

### 4.6 ¿Qué pasa si subo el mismo mes otra vez?

No se duplica nada: todas las filas se detectan como repetidas y el resumen dirá
algo como *"2676 procesados, 0 insertados, 2676 duplicados"*. Si el archivo trae
operaciones **nuevas**, solo esas se agregan.

### 4.7 Cómo probarlo

1. Arrancar la app (ver punto 3).
2. Iniciar sesión → en el Home, botón **Cargar Excel**.
3. Subir el Excel → aparece el resumen de la carga.
4. El Home muestra los KPIs de Getnet (la jornada se ve en formato `dd/mm/aaaa`).

---

## 5. Decisiones importantes del módulo de carga

| Decisión | Por qué |
|---|---|
| Usar la columna `Jornada` del Excel tal cual | Ya viene lista; evita cálculos y es más rápido. |
| Guardar `fecha` con hora | Se necesitará para "operaciones por hora promedio". |
| Incluir la hora en `id_unico` | El voucher se repite entre máquinas; sin la hora se perdían operaciones reales. |
| `ON CONFLICT DO NOTHING` | Evita duplicados al re-subir un archivo. |
| Inserción por lotes (`execute_values`) | Mucho más rápido que fila por fila. |

---

## 6. Glosario

| Término | Significado |
|---|---|
| **Jornada** | Día de operación del casino (puede no coincidir con la fecha calendario; ej.: una operación de las 03:00 puede pertenecer a la jornada del día anterior). |
| **Voucher** | Número de comprobante de la terminal Getnet. Se repite entre máquinas. |
| **Slot Attendant** | Persona que atiende la operación. |
| **Dedup** | "Deduplicar": evitar registros repetidos. |
| **id_unico** | Clave compuesta que identifica de forma única cada operación. |
| **ON CONFLICT** | Instrucción SQL para decidir qué hacer cuando un registro ya existe. |
| **KPI** | Indicador clave (ej.: total de operaciones, monto total). |

---

## 7. Dashboard de Getnet ✅ (terminado)

Una vez que los datos están en la base de datos, el módulo **Getnet** ofrece tres
vistas accesibles desde un sub-menú:

| Vista | Ruta | Qué muestra |
|---|---|---|
| Dashboard | `/getnet` | KPIs + gráficos + mapa de calor |
| Histórico | `/getnet/historico` | Tabla con todas las operaciones |
| Record Asistentes | `/getnet/record` | Ranking de slot attendants |

### 7.1 KPIs del Dashboard

Cuatro tarjetas en la parte superior, calculadas por `get_kpis_dashboard()` y
respetuosas de los filtros activos:

| Tarjeta | Qué muestra |
|---|---|
| **Operaciones** | Total de operaciones · días contados · promedio por día |
| **Monto total** | Suma acumulada · ticket promedio por operación |
| **Hora pico** | Franja horaria con más operaciones · promedio de ops en esa hora |
| **Débito / Crédito** | Donut (arandela) con % por `forma_pago`; leyenda debajo; tooltip muestra ops y monto |

### 7.2 Gráficos (Chart.js)

Cuatro gráficos construidos con **Chart.js**:

| Gráfico | Tipo | Qué muestra |
|---|---|---|
| Operaciones por Mes | Barras (oro) | Conteo de operaciones por mes |
| Montos por Mes | Área (verde) | Suma de montos por mes |
| Operaciones por Hora (promedio) | Barras (azul) | Promedio de operaciones por franja horaria |
| Montos por Hora (promedio) | Área (naranja) | Promedio de montos por franja horaria |
| Débito / Crédito | Donut / arandela | % de operaciones por forma de pago; tooltip con monto |

Los gráficos se dibujan con `responsive: true` y `maintainAspectRatio: false` para
que llenen el ancho del contenedor. Los datos llegan embebidos en el HTML como JSON
dentro de un `<script id="getnet-data" type="application/json">`.

#### Bug corregido: crecimiento vertical infinito de los gráficos

**Síntoma:** la barra de scroll de la página se iba alargando con cada carga,
porque los gráficos crecían verticalmente sin límite.

**Causa:** `responsive: true` + `maintainAspectRatio: false` requieren que el
`<canvas>` esté dentro de un contenedor con altura fija. Sin ese contenedor, en
cada redibujo el canvas aumentaba un poco, empujaba al padre, que a su vez hacía
crecer al canvas → bucle infinito.

**Solución aplicada:**

1. Cada `<canvas>` se envuelve en `<div class="chart-box">`.
2. `.chart-box` tiene `position: relative; height: 260px;` — altura fija que rompe
   el bucle.
3. El canvas dentro del box usa `position: absolute; inset: 0;` para ocupar todo
   el contenedor.
4. Antes de crear cada gráfico se destruye la instancia anterior con
   `Chart.getChart(el)?.destroy()`, por si el script se ejecuta más de una vez
   sobre el mismo canvas (defensa extra).

### 7.3 Mapa de calor

Tabla Día de la semana × Hora (jornada 10:00 → 08:00). Cada celda muestra el
promedio de operaciones para esa franja. El color de fondo varía en intensidad
(oro translúcido) proporcional al valor máximo de la tabla: las franjas más activas
se ven más oscuras.

### 7.4 Filtros

El dashboard tiene un panel lateral con filtros de **Año** y **Mes**. Al aplicar,
todos los gráficos, KPIs y el mapa de calor se recalculan con el rango seleccionado.

---

## 8. Decisiones importantes (resumen actualizado)

| Decisión | Por qué |
|---|---|
| Usar la columna `Jornada` del Excel tal cual | Ya viene lista; evita cálculos y es más rápido. |
| Guardar `fecha` con hora | Se necesita para "operaciones por hora promedio". |
| Incluir la hora en `id_unico` | El voucher se repite entre máquinas; sin la hora se perdían operaciones reales. |
| `ON CONFLICT DO NOTHING` | Evita duplicados al re-subir un archivo. |
| Inserción por lotes (`execute_values`) | Mucho más rápido que fila por fila. |
| Contenedor de altura fija para Chart.js | Evita el bug de crecimiento vertical infinito en modo responsive. |
| Datos de gráficos embebidos en JSON | Evita peticiones AJAX adicionales; el template ya tiene los datos. |
| KPIs calculados en `get_kpis_dashboard()` | Una sola función de repositorio para las 4 tarjetas; reutiliza `_where()` y los filtros. |
| Donut de formas de pago con leyenda abajo | La leyenda lateral tapaba el tooltip de Chart.js; colocarla debajo la libera. |
| Columnas fijas de 5 años en "Total acumulado" | Muestra siempre el rango 2022–2026 aunque no haya datos, para comparar evolución. |
| `_FILTRO_ACTIVOS` en todas las queries Getnet | Los asistentes desactivados desde Configuración no contaminan ningún gráfico ni ranking. |

---

---

## 9. Record Asistentes ✅ (terminado)

Sección accesible desde el sub-menú de Getnet (`/getnet/record-asistentes`). Muestra
el rendimiento histórico de cada slot attendant. Respeta todos los filtros del header.

| Bloque | Qué muestra |
|---|---|
| **Podio Top 3** | Asistentes con el mayor número de operaciones en una sola jornada (🥇🥈🥉 + tabla del resto) |
| **Resumen por asistente** | Total de ops, ticket promedio, franja horaria más activa, mejor jornada |
| **Transacciones por mes/año** | Una tabla por año con los 12 meses como columnas; asistentes como filas |
| **Total acumulado por año** | Tabla asistente × año; siempre muestra las últimas 5 columnas (años sin datos = 0) |

Each block includes an `.info-note` legend explaining the calculation.

---

## 10. Configuración ✅ (solo admin)

Sección accesible desde el engranaje ⚙️ del header (solo visible para admins).
Ruta: `/configuracion`.

| Pestaña | Qué permite |
|---|---|
| Asistentes | Activar o desactivar un slot attendant (los inactivos no aparecen en ningún gráfico) |
| Usuarios | Ver la lista de usuarios y crear nuevos |
| Contraseña | Cambiar la propia contraseña |

Los asistentes inactivos se excluyen en todas las consultas gracias al filtro
`_FILTRO_ACTIVOS` en `getnet_repository.py`.

---

## 11. Módulo Premios ✅ (terminado)

Módulo paralelo a Getnet para procesar y analizar los premios otorgados en las
máquinas (jackpots). Sigue exactamente el mismo patrón: carga de Excel → tabla
PostgreSQL → dashboard + histórico + record.

### 11.1 La tabla `premios`

| Columna | Tipo | Qué guarda |
|---|---|---|
| `id` | serial PK | identificador interno (automático) |
| `id_unico` | text UNIQUE | clave para evitar duplicados |
| `fecha` | **timestamp** | fecha **y hora** de la operación (necesario para analizar por hora) |
| `jornada` | date | día de operación |
| `maquina` | text | número/nombre de la máquina |
| `cliente` | text | identificador del cliente |
| `transferencia_final` | integer | monto del premio |
| `slot_attendant` | text | asistente que atendió el premio |
| `tipo_de_pago` | text | tipo de premio (Jackpot HP, Progressive Jackpot HP, etc.) |
| `created_at` | timestamp | cuándo se cargó (automático) |

> La columna `fecha` es `TIMESTAMP` (no `DATE`) para poder calcular *operaciones
> por hora*. La tabla se llenó desde cero con el Excel para que la hora quedara
> correctamente registrada.

### 11.2 Regla de filtrado por tipo de pago

A diferencia de Getnet, no todos los tipos de pago son "premios reales" en sentido
monetario. Los tipos **Jackpot HP** y **Progressive Jackpot HP** son los que tienen
`transferencia_final > 0`. La regla aplicada es:

| Columna / bloque | ¿Qué tipos cuenta? |
|---|---|
| Conteo de operaciones | **Todos** los tipos |
| Montos (`transferencia_final`) | **Solo** Jackpot HP + Progressive Jackpot HP |
| Heatmap / distribución | **Todos** los tipos |

Esta regla se aplica de forma **independiente por columna o gráfico**, no como un
filtro global.

### 11.3 Dashboard de Premios (`/premios`)

Cinco gráficos + KPIs. Mismo layout que el Dashboard de Getnet.

| Gráfico | Tipo | Filtrado |
|---|---|---|
| Operaciones por Mes | Barras (oro) | Todos los tipos |
| Montos por Mes | Área (verde) | Solo HP — badge visible |
| Operaciones por Hora | Barras (azul) | Todos los tipos |
| Montos por Hora | Área (naranja) | Solo HP — badge visible |
| Heatmap Día × Hora | Tabla de calor | Todos los tipos |

Los gráficos de monto tienen un badge **"Solo premios HP"** para dejar claro el
filtro aplicado. El donut de distribución por tipo cierra la sección.

### 11.4 Histórico de Premios (`/premios/historico`)

Tres bloques de análisis, cada uno con su `.info-note` explicando cómo se calcula:

| Bloque | Qué muestra | Filtrado |
|---|---|---|
| **Resumen mensual** | Mes · Operaciones · Monto | Solo HP |
| **Operaciones por hora** | Hora · Ops · Ops promedio · Montos · Montos promedio · hora pico | Ops=todos / Montos=HP |
| **Conteo anual Mes × Máquina** | Fila por (Mes, Máquina) con columnas dinámicas por tipo + Monto premios | Conteo=todos / Monto=HP |

Los promedios dividen el total entre la cantidad de **jornadas únicas** del
periodo. La fila de la hora pico se resalta con `.pico-row` y un badge.

### 11.5 Record Asistentes de Premios (`/premios/record-asistentes`)

Cinco bloques paralelos al Record de Getnet, pero adaptados a las particularidades
de los premios:

| Bloque | Qué muestra |
|---|---|
| **Podio Top 3** | Los 3 asistentes con más premios en una sola jornada (🥇🥈🥉) |
| **Resumen por asistente por tipo** | Columnas dinámicas: una por cada tipo de pago + mejor jornada con fecha |
| **Transacciones por mes/año** | Tabla año × 12 meses por asistente |
| **Total acumulado por año** | Asistente × año (últimas 5 columnas) |
| **Distribución por tipo** | Donut de operaciones por tipo de pago |

Solo aparecen filas donde `slot_attendant IS NOT NULL AND TRIM(slot_attendant) <> ''`.

---

## 12. Pendiente

- [ ] Módulo **COMPS** (mismo patrón que Getnet / Premios).
- [ ] Módulo **CoinIn**.
- [ ] (Opcional) Aviso visual cuando una carga no agrega registros nuevos.
