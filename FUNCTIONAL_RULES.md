# SGOS — FUNCTIONAL_RULES.md

Reglas funcionales y de negocio del **Sistema de Gestión de Operaciones de Slots (SGOS)**.

**Alcance de este documento:** definir cómo deben tratarse los datos, archivos Excel, columnas, Jornada, filtros, validaciones, exportaciones y módulos operativos.  
**No contiene:** diseño visual detallado ni arquitectura técnica del proyecto.

---

## 1. Propósito del documento

Este archivo debe ser consultado antes de modificar cualquier lógica relacionada con:

- carga de Excel;
- cálculo de Jornada;
- transformación de datos;
- validación de columnas;
- generación de ID único;
- filtros;
- totales;
- exportaciones;
- módulos Getnet, Premios, COMPS y CoinIn.

La IA no debe cambiar reglas funcionales sin confirmación cuando existan dudas.

---

## 2. Separación entre documentos

| Documento | Uso |
|---|---|
| `DESIGN.md` | Cómo se ve la interfaz |
| `ARCHITECTURE.md` | Cómo se organiza el código y el backend |
| `FUNCTIONAL_RULES.md` | Cómo funcionan los datos y reglas de negocio |

---

## 3. Regla global de Jornada

La **Jornada** es una fecha operativa, no necesariamente la misma fecha calendario.

### 3.1 Horario oficial de Jornada

La Jornada comienza a las **10:00** y termina a las **08:00 del día siguiente**.

Formato horario: **24 horas**.

```text
Inicio de Jornada: 10:00
Fin de Jornada:    08:00 del día siguiente
```

### 3.2 Interpretación

| Hora real del registro | Jornada asignada |
|---|---|
| 10:00 a 23:59 | Fecha del mismo día |
| 00:00 a 07:59 | Fecha del día anterior |
| 08:00 a 09:59 | Pendiente de confirmar tratamiento operativo |

La franja **08:00 a 09:59** debe confirmarse antes de automatizar reglas definitivas, porque puede corresponder a cierre, limpieza de datos o periodo fuera de Jornada.

### 3.3 Formato de Jornada visible

Formato recomendado para usuario final:

```text
dd/mm/aaaa
```

Ejemplo:

```text
21/05/2026
```

---

## 4. Filtros globales del sistema

El sistema debe tener filtros reutilizables en todos los apartados.

### 4.1 Filtros principales

| Filtro | Uso |
|---|---|
| Año | Filtra datos por año de Jornada o fecha según módulo |
| Mes | Filtra datos por mes de Jornada o fecha según módulo |
| Nombre | Busca por asistente, cliente u otro nombre visible según módulo |
| Filas totales | Muestra u oculta totales en tablas y reportes |

### 4.2 Regla de panel retráctil

El panel de filtros debe ser **retráctil** y controlarse desde el botón **Filtros** del header.

Esta regla aplica a:

- Home / Resumen;
- Getnet;
- Premios;
- COMPS;
- Análisis general;
- Control;
- CoinIn Cero;
- Totales / Filas totales;
- cualquier vista futura que use filtros.

### 4.3 Alcance de los filtros

Por defecto, los filtros deben afectar la vista actual.  
Si la vista muestra datos consolidados, los filtros deben aplicarse sobre todos los módulos visibles dentro de esa vista.

---

## 5. Exportación a Excel

Regla base:

- si el usuario está viendo una vista filtrada, **Exportar a Excel** debe exportar los datos según los filtros activos;
- si se requiere exportar todo, debe existir una opción clara como `Exportar todo` o se debe confirmar antes.

### 5.1 Nombre de archivo sugerido

Formato recomendado:

```text
SGOS_<modulo>_<año>_<mes>_<fecha_exportacion>.xlsx
```

Ejemplos:

```text
SGOS_getnet_2026_05_2026-05-29.xlsx
SGOS_premios_2026_05_2026-05-29.xlsx
```

---

## 6. Regla de ID único

El ID único evita duplicar registros al cargar archivos varias veces.

### 6.1 Regla general sugerida

Cuando existan los campos necesarios, el ID único debe construirse con:

```text
fecha + últimos 12 dígitos del id_cliente + monto + voucher
```

### 6.2 Normalización antes de crear ID

Antes de generar el ID único:

- limpiar espacios;
- quitar puntos y separadores innecesarios en montos;
- normalizar fechas;
- convertir texto a formato consistente;
- extraer solo los últimos 12 dígitos cuando aplique;
- evitar diferencias por mayúsculas/minúsculas.

### 6.3 Si faltan campos

Si un archivo no trae todos los campos necesarios para el ID único:

1. no inventar datos;
2. registrar advertencia;
3. usar una regla alternativa solo si está definida en este documento;
4. si no existe regla alternativa, solicitar confirmación.

---

## 7. Carga de archivos Excel

### 7.1 Validaciones mínimas

Antes de procesar un archivo:

- validar extensión `.xlsx` o `.xls`;
- validar que el archivo no esté vacío;
- validar hoja requerida;
- validar fila de encabezado;
- validar columnas obligatorias;
- validar fechas;
- validar montos;
- validar duplicados por ID único;
- informar errores claros al usuario.

### 7.2 Resultado de carga

Después de cargar, el sistema debe mostrar:

| Dato | Descripción |
|---|---|
| Archivo cargado | Nombre del archivo |
| Fecha de carga | Fecha/hora de procesamiento |
| Registros leídos | Total bruto del Excel |
| Registros válidos | Filas aceptadas |
| Registros duplicados | Filas omitidas por ID único |
| Registros con error | Filas rechazadas |
| Jornada máxima | Última Jornada detectada |
| Total principal | Monto, micros u otra métrica del módulo |

---

## 8. Home / Resumen principal

El Home debe mostrar el estado de carga de los módulos principales.

### 8.1 Módulos visibles en Home

- Getnet
- Premios
- COMPS

### 8.2 Métricas por módulo

| Métrica | Descripción |
|---|---|
| Mes cargado | Mes disponible o último mes procesado |
| Hasta jornada | Última Jornada registrada dentro del módulo |
| Monto total / Micros total | Total principal del mes seleccionado |
| Última jornada | Total y cantidad de operaciones de la última Jornada |

### 8.3 Estado sin datos

Si un módulo no tiene carga registrada:

```text
No hay carga registrada para este módulo.
```

---

## 9. Módulo Getnet

### 9.1 Fuente de datos

Archivo Excel descargado para ser cargado en SGOS.

Hoja esperada:

```text
Sheet1
```

Encabezados esperados:

```text
Desde A2 hasta I2
```

### 9.2 Campos mínimos a extraer

| Campo | Uso |
|---|---|
| Fecha | Base para fecha real y cálculo de Jornada |
| Jornada | Fecha operativa calculada o normalizada |
| Monto | Total de operación |
| Slot Attendant | Asistente asociado |
| Forma de pago | Tipo de pago utilizado |
| Id Cliente | Requerido para ID único cuando exista |
| Voucher | Requerido para ID único cuando exista |

### 9.3 Reglas Getnet

- La Jornada debe calcularse según la regla global 10:00 a 08:00.
- El monto debe normalizarse como número.
- El asistente debe quedar con nombre limpio, sin espacios extras.
- El tipo de pago debe normalizarse para evitar duplicados por escritura.
- El ID único debe usar fecha + últimos 12 dígitos del cliente + monto + voucher cuando existan los campos.

### 9.4 KPIs Getnet

| KPI | Descripción |
|---|---|
| Mes cargado | Mes del archivo o de la Jornada filtrada |
| Hasta jornada | Última Jornada con registros |
| Monto total del mes | Suma de montos filtrados |
| Última jornada | Total y cantidad de operaciones de la Jornada más reciente |

---

## 10. Módulo Premios

### 10.1 Fuente de datos

Archivo Excel de Premios.

Encabezados esperados:

```text
Desde A2 hasta M2
```

### 10.2 Regla principal

Se debe crear una columna nueva llamada:

```text
Jornada
```

Esta columna debe generarse desde la fecha/hora del registro usando la regla global de Jornada.

### 10.3 Columnas requeridas para Neon.tech

El sistema debe enviar a la base de datos solo las columnas necesarias:

| Columna | Uso |
|---|---|
| Fecha | Fecha/hora original del registro |
| Jornada | Fecha operativa calculada |
| Cliente | Cliente asociado al premio |
| Transferencia Final | Monto final transferido |
| Slot Attendant | Asistente asociado |
| Tipo de pago | Tipo de pago registrado |

### 10.4 Reglas Premios

- No cargar columnas innecesarias si no serán utilizadas por la app.
- Normalizar `Transferencia Final` como monto numérico.
- Normalizar nombre de cliente y asistente.
- Validar que la Jornada no quede vacía.
- Si se requiere ID único, debe definirse con campos disponibles del archivo. No inventar campos faltantes.

### 10.5 KPIs Premios

| KPI | Descripción |
|---|---|
| Mes cargado | Mes de Jornada cargado |
| Hasta jornada | Última Jornada registrada |
| Monto total del mes | Suma de Transferencia Final |
| Última jornada | Total y cantidad de premios de la última Jornada |

---

## 11. Módulo COMPS

### 11.1 Regla principal

El módulo COMPS debe trabajar con **ID único** para evitar registros duplicados.

### 11.2 Datos esperados

Las columnas definitivas de COMPS deben confirmarse con el archivo final usado por SGOS.

Hasta que se confirme, la IA debe tratar COMPS con cuidado y no asumir columnas que no estén presentes.

### 11.3 Métricas esperadas

| KPI | Descripción |
|---|---|
| Mes cargado | Mes disponible en datos COMPS |
| Hasta jornada | Última Jornada registrada |
| Micros totales del mes | Total principal del módulo COMPS |
| Última jornada | Micros y cantidad de registros de la última Jornada |

### 11.4 Reglas COMPS pendientes de confirmar

- columnas exactas del Excel;
- fila de encabezado;
- fórmula definitiva de ID único;
- tratamiento de micros;
- reglas de diferencia o auditoría si aplican.

---

## 12. Módulo CoinIn / CoinIn Cero

### 12.1 Objetivo

El módulo CoinIn debe procesar información de Coin In y permitir detectar o visualizar casos de **CoinIn Cero** cuando corresponda.

### 12.2 Fuente esperada

Archivo tipo:

```text
SRW - Coin In & EP
```

### 12.3 Reglas pendientes

Las columnas definitivas para la base de datos deben confirmarse con el Excel final.

Mientras no estén confirmadas, la IA debe:

- no inventar columnas;
- revisar encabezados reales;
- documentar columnas detectadas;
- pedir confirmación antes de guardar estructura definitiva.

### 12.4 CoinIn Cero

Una vista **CoinIn Cero** debería mostrar registros donde el valor de Coin In sea cero o cumpla la condición definida por operación.

La regla exacta de CoinIn Cero debe confirmarse antes de automatizar alertas.

---

## 13. Módulo Análisis general

El módulo Análisis general debe consolidar información de varios módulos.

Posibles análisis:

- operaciones por mes;
- operaciones por Jornada;
- montos por asistente;
- montos por módulo;
- comparación entre Getnet, Premios y COMPS;
- tendencias por hora;
- ranking operativo.

Regla: cualquier métrica consolidada debe indicar claramente qué módulos incluye.

---

## 14. Módulo Control

El módulo Control debe definirse con precisión antes de programarlo.

Posibles usos:

- control operativo;
- control de diferencias;
- control de cargas;
- control de usuarios;
- validación entre módulos.

La IA no debe asumir el objetivo final del módulo Control sin confirmación.

---

## 15. Reglas de totales

### 15.1 Filas totales

El control **Filas totales** debe permitir mostrar u ocultar totales en tablas y reportes.

Debe aplicar en:

- Getnet;
- Premios;
- COMPS;
- CoinIn;
- Análisis general;
- Home si corresponde;
- vistas filtradas.

### 15.2 Totales filtrados

Los totales deben calcularse con los filtros activos, salvo que la vista indique explícitamente `Total general`.

---

## 16. Formatos de visualización

### 16.1 Montos CLP

Formato:

```text
$112.182.200
```

Reglas:

- usar punto como separador de miles;
- no usar decimales si no son necesarios;
- al exportar, los montos deben mantenerse como números cuando sea posible.

### 16.2 Fechas

Formato visible recomendado:

```text
dd/mm/aaaa
```

Formato técnico interno recomendado:

```text
aaaa-mm-dd
```

### 16.3 Horas

Formato:

```text
HH:MM
```

Ejemplo:

```text
22:51
```

---

## 17. Validación de duplicados

Antes de insertar registros en Neon.tech:

1. calcular ID único;
2. consultar si ya existe;
3. si existe, omitir o actualizar según regla del módulo;
4. registrar cantidad de duplicados;
5. informar al usuario.

Regla base: no insertar duplicados silenciosamente.

---

## 18. Reglas para errores de usuario

Mensajes sugeridos:

| Caso | Mensaje sugerido |
|---|---|
| Hoja no encontrada | `No se encontró la hoja requerida en el archivo.` |
| Encabezado incorrecto | `El archivo no tiene el formato esperado.` |
| Columna faltante | `Falta una columna obligatoria: <nombre_columna>.` |
| Archivo vacío | `El archivo no contiene registros para procesar.` |
| Duplicados | `Se omitieron registros duplicados ya cargados anteriormente.` |
| Error de BD | `No fue posible guardar la información. Intente nuevamente o contacte al administrador.` |

---

## 19. Reglas para la IA

Cuando la IA trabaje en reglas funcionales:

1. Debe revisar este archivo antes de modificar código.
2. No debe cambiar el cálculo de Jornada sin confirmación.
3. No debe inventar columnas de Excel.
4. No debe modificar ID único sin revisar el módulo afectado.
5. Debe mantener separadas las reglas de Getnet, Premios, COMPS y CoinIn.
6. Si una regla está marcada como pendiente, debe preguntar antes de implementarla.
7. Si el usuario entrega una captura o Excel nuevo, debe actualizar este documento con la regla confirmada.
8. Debe evitar que un cambio en un módulo afecte otros módulos sin necesidad.

---

## 20. Pendientes de confirmación

| Tema | Estado |
|---|---|
| Tratamiento exacto de registros entre 08:00 y 09:59 | Pendiente |
| Columnas definitivas de COMPS | Pendiente |
| Fórmula definitiva de ID único para COMPS | Pendiente |
| Columnas definitivas de CoinIn | Pendiente |
| Regla exacta de CoinIn Cero | Pendiente |
| Objetivo final del módulo Control | Pendiente |
| Roles y permisos definitivos | Pendiente |
| Si `Exportar a Excel` exporta siempre vista filtrada o tendrá doble opción | Base definida: exporta filtrado; confirmar si se agrega `Exportar todo` |

---

## 21. Regla final funcional

SGOS debe priorizar datos limpios, trazables y no duplicados.

Cada carga debe permitir saber:

- qué archivo se cargó;
- cuándo se cargó;
- qué usuario lo cargó;
- cuántos registros se leyeron;
- cuántos se guardaron;
- cuántos fueron duplicados;
- cuántos tuvieron error;
- hasta qué Jornada llegó la información.
