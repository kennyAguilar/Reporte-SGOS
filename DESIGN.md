# SGOS — DESIGN.md

Guía de Diseño de Interfaz para **Sistema de Gestión de Operaciones de Slots (SGOS)**.

**Sistema visual oficial:** Carbon Design System v11  
**Tema base:** Gray 100 / Dark Theme  
**Acento visual SGOS:** Oro operativo  
**Alcance de este documento:** definir cómo debe verse y comportarse la interfaz. No contiene arquitectura técnica ni reglas de negocio.

---

## 1. Propósito del documento

Este archivo debe ser utilizado por la IA o por cualquier desarrollador para mantener consistencia visual en SGOS.

Aquí se documentan:

- identidad visual;
- paleta de colores;
- tipografía;
- espaciado;
- layout general;
- pantalla de login;
- home / resumen principal;
- header superior;
- panel de filtros retráctil;
- cards, tablas, botones y estados visuales.

Las decisiones sobre Flask, Python, Neon.tech, Seenode, Render, estructura de carpetas, módulos y base de datos deben consultarse en `ARCHITECTURE.md`.

Las reglas sobre Jornada, columnas de Excel, ID único, Getnet, Premios, COMPS y CoinIn deben consultarse en `FUNCTIONAL_RULES.md`.

---

## 2. Identidad visual y paleta de colores

SGOS utiliza un esquema oscuro inspirado en **Carbon Design System v11**, especialmente el tema **Gray 100**, optimizado para dashboards, reportes, tablas y sistemas de alta densidad de información.

### 2.1 Superficies principales

| Token Carbon | Hex | Uso en SGOS |
|---|---:|---|
| `$background` | `#161616` | Fondo general de la aplicación |
| `$layer-01` | `#262626` | Cards, contenedores principales, tablas y paneles |
| `$layer-02` | `#393939` | Inputs, cards elevadas, menús, elementos anidados |
| `$layer-03` | `#525252` | Hovers, menús desplegables y elementos de tercer nivel |

### 2.2 Texto

| Token Carbon | Hex | Uso |
|---|---:|---|
| `$text-primary` | `#f4f4f4` | Títulos, valores principales, KPIs, texto activo |
| `$text-secondary` | `#c6c6c6` | Subtítulos, labels, metadatos, información secundaria |
| `$text-helper` | `#8d8d8d` | Ayudas, hints, texto auxiliar, estados deshabilitados |
| `$text-error` | `#ffb3b8` | Mensajes de error y validación crítica |

### 2.3 Acentos y estados

| Token / Color | Hex | Uso en SGOS |
|---|---:|---|
| `$interactive` / Oro SGOS | `#d4af37` | CTA principal, navegación activa, valores destacados |
| Oro hover | `#e0bd48` | Hover de botones principales |
| Oro active | `#b8922d` | Estado presionado del botón principal |
| `$support-success` | `#24a148` | Cargas correctas, validaciones exitosas |
| `$support-error` | `#da1e28` | Errores de validación o carga |
| `$support-warning` | `#f1c21b` | Advertencias o datos pendientes |
| `$support-info` | `#0043ce` | Información general del sistema |

### 2.4 Reglas de uso del color oro

El color oro debe usarse con moderación para mantener una interfaz seria y profesional.

Usos permitidos:

- botón principal;
- navegación activa;
- borde de card financiera destacada;
- valores monetarios importantes;
- logo compacto del sistema;
- chips o indicadores activos.

Usos no recomendados:

- fondos grandes;
- tablas completas;
- textos largos;
- estados de error o advertencia.

---

## 3. Tipografía

Carbon utiliza **IBM Plex Sans**. SGOS debe utilizar esta fuente como referencia principal.

**Familia principal:** `IBM Plex Sans`  
**Fallback:** `system-ui, sans-serif`

| Token Carbon | Weight | Size | Uso en SGOS |
|---|---:|---:|---|
| `$body-short-01` | 400 | 14px | Texto general, celdas de tabla, listas |
| `$label-01` | 500 | 12px | Labels de formulario, headers de columnas |
| `$heading-01` | 600 | 14px | Títulos de cards y secciones secundarias |
| `$heading-03` | 400 | 20px | Títulos de página |
| `$code-01` | 400 | 12px | IDs, logs, códigos, transacciones |

Reglas:

- usar textos cortos en dashboards;
- evitar párrafos largos dentro de cards;
- usar mayúsculas pequeñas en etiquetas de KPI;
- mantener contraste alto sobre fondo oscuro;
- aplicar `-webkit-font-smoothing: antialiased;`.

---

## 4. Espaciado

SGOS debe seguir una escala similar a Carbon para evitar desorden visual.

| Token Carbon | Valor | Uso típico |
|---|---:|---|
| `$spacing-01` | 2px | Microajustes |
| `$spacing-03` | 8px | Separación icono-texto, separación corta |
| `$spacing-05` | 16px | Padding estándar de inputs, botones y cards compactas |
| `$spacing-06` | 24px | Padding de cards principales |
| `$spacing-07` | 32px | Separación entre secciones |
| `$spacing-09` | 48px | Bloques grandes, login, hero |

Regla general: no improvisar márgenes. Usar siempre múltiplos de 8px cuando sea posible.

---

## 5. Layout base de la aplicación

La aplicación debe usar una estructura tipo **UI Shell**, con:

- header superior fijo;
- navegación principal horizontal;
- botón global de filtros;
- área de contenido central;
- panel lateral de filtros retráctil;
- layout responsivo.

```html
<header class="app-header">
  <!-- Marca, navegación, usuario y acciones globales -->
</header>

<div class="dashboard-layout">
  <aside id="filters-panel" class="filters-panel">
    <!-- Filtros globales de la vista actual -->
  </aside>

  <main class="app-content">
    {% block content %}{% endblock %}
  </main>
</div>
```

---

## 6. Pantalla de Login

La pantalla de login debe mantener el estilo **Carbon Gray 100**, con una apariencia seria, limpia y enfocada en personal autorizado.

### 6.1 Objetivo

- Identificar el sistema como **SGOS — Reportes de Operaciones**.
- Comunicar que el sistema procesa, analiza y visualiza reportes de operaciones desde archivos Excel.
- Mantener el acceso restringido.
- Evitar elementos decorativos innecesarios.

### 6.2 Layout recomendado

| Zona | Ancho desktop | Fondo | Uso |
|---|---:|---|---|
| Hero institucional | 72% | `$background` `#161616` | Marca, descripción y módulos principales |
| Panel de acceso | 28% / máx. 560px | `$layer-01` `#262626` | Formulario de login |

En pantallas pequeñas, el diseño pasa a una sola columna.

```css
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 560px;
  background: #161616;
  color: #f4f4f4;
}

.login-hero {
  padding: 48px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.login-panel {
  background: #262626;
  border-left: 1px solid #393939;
  padding: 0 80px;
  display: flex;
  align-items: center;
}

@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
  }

  .login-panel {
    border-left: none;
    border-top: 1px solid #393939;
    padding: 32px 24px;
  }
}
```

### 6.3 Texto sugerido del hero

```text
SGOS
Reportes de Operaciones

Sistema de Gestión
de Operaciones

Procesa, analiza y visualiza reportes de operaciones desde
archivos Excel con dashboards en tiempo real.
```

### 6.4 Módulos destacados del login

| Módulo | Descripción | Ícono sugerido |
|---|---|---|
| Cargas | Importa reportes Excel de operaciones | Upload |
| Reportes | Dashboards y KPIs por turno y mesa | ChartColumn |
| Usuarios | Control de accesos y roles del sistema | UserMultiple |

### 6.5 Panel de acceso

Contenido sugerido:

```text
Iniciar sesión
Accede con tu cuenta autorizada

¿Cómo acceder?
Haz clic en Ingresar e introduce tu usuario y contraseña.
Si no tienes cuenta, contacta al administrador.
```

Campos requeridos:

| Campo | Tipo | Placeholder | Validación |
|---|---|---|---|
| Usuario | Texto | `nombre.usuario` | Requerido |
| Contraseña | Password | `••••••••` | Requerido |

### 6.6 Botón de ingreso

| Estado | Fondo | Texto |
|---|---:|---:|
| Default | `#d4af37` | `#161616` |
| Hover | `#e0bd48` | `#161616` |
| Active | `#b8922d` | `#161616` |
| Disabled | `#525252` | `#8d8d8d` |

```css
.login-submit {
  width: 100%;
  height: 48px;
  border: none;
  background: #d4af37;
  color: #161616;
  font-weight: 600;
  cursor: pointer;
}
```

### 6.7 Estados de validación del login

| Estado | Comportamiento visual |
|---|---|
| Campo vacío | Borde inferior rojo y texto de ayuda |
| Credenciales inválidas | Mensaje visible en rojo claro `#ffb3b8` |
| Cargando | Botón deshabilitado con texto `Ingresando...` o spinner |
| Acceso correcto | Redirección al Home sin confirmación innecesaria |

---

## 7. Header superior de SGOS

El header debe aparecer después del login y mantenerse visible en las vistas internas.

### 7.1 Elementos del header

| Elemento | Descripción | Regla visual |
|---|---|---|
| Logo `S` | Identificador compacto | Fondo oro, texto oscuro |
| Marca | `MESA OPERATIVA` + `SGOS Reportes` | Texto claro, compacto |
| Navegación | Resumen, Getnet, Premios, Comps, Análisis general, Control, CoinIn Cero | Tab activo con borde inferior oro |
| Usuario | Nombre de usuario autenticado | Card compacta `$layer-02` |
| Filtros | Abre/cierra el panel lateral | Botón secundario oscuro |
| Cargar Excel | Acción de importación | Botón secundario |
| Exportar a Excel | Acción principal de salida | Botón oro |
| Salir | Cierre de sesión | Botón secundario con icono |

### 7.2 Navegación principal

Orden recomendado:

1. Resumen
2. Getnet
3. Premios
4. Comps
5. Análisis general
6. Control
7. CoinIn Cero

El tab activo debe ser claro y visible con línea inferior oro.

---

## 8. Panel de filtros retráctil

El panel de filtros **no debe ser fijo permanente**. Debe ser **retráctil** y abrirse/cerrarse desde el botón **Filtros** del header.

Esta regla aplica a:

- Resumen / Home;
- Getnet;
- Premios;
- Comps;
- Análisis general;
- Control;
- CoinIn Cero;
- vistas de Totales / Filas totales;
- cualquier tabla, reporte o dashboard que use filtros.

### 8.1 Reglas visuales del panel

| Estado | Comportamiento visual |
|---|---|
| Abierto | El panel ocupa entre 260px y 300px. El contenido se adapta dejando espacio. |
| Cerrado | El panel no deja columna vacía. El contenido usa todo el ancho disponible. |
| Móvil | El panel funciona como drawer lateral superpuesto. |
| Filtro activo | Mostrar chips o resumen visible de filtros aplicados. |

### 8.2 Controles del panel

| Control | Tipo | Uso |
|---|---|---|
| Año | Select | Filtrar por año |
| Mes | Select | Filtrar por mes |
| Nombre | Input text | Buscar por asistente o cliente |
| Aplicar | Botón primario compacto | Ejecuta filtros |
| Todos | Botón secundario/outline | Selecciona todos los registros |
| Ninguno | Botón secundario | Limpia selección activa |
| Filas totales | Toggle | Muestra u oculta totales en tablas/reportes |
| Último archivo | Card informativa | Muestra archivo y fecha de última carga |

### 8.3 Accesibilidad del botón Filtros

El botón debe incluir:

```html
<button aria-controls="filters-panel" aria-expanded="true">
  Filtros
</button>
```

Cuando el panel se cierre, `aria-expanded` debe cambiar a `false`.

### 8.4 CSS sugerido

```css
.dashboard-layout {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  grid-template-rows: 48px 1fr;
  background: #161616;
  color: #f4f4f4;
}

.dashboard-layout.filters-collapsed {
  grid-template-columns: 0 minmax(0, 1fr);
}

.filters-panel {
  background: #262626;
  border-right: 1px solid #393939;
  padding: 24px 16px;
  overflow: hidden;
  transition: width 180ms ease, padding 180ms ease;
}

.dashboard-layout.filters-collapsed .filters-panel {
  width: 0;
  padding-left: 0;
  padding-right: 0;
  border-right: none;
}
```

---

## 9. Home / Resumen principal

La pantalla **Home** es la primera vista después del login. Debe entregar una lectura rápida del estado de carga de los módulos principales.

### 9.1 Objetivo

- Mostrar el estado general de carga de **Getnet**, **Premios** y **COMPS**.
- Permitir navegación rápida hacia los módulos.
- Mostrar métricas clave por módulo.
- Usar el panel de filtros retráctil global.

### 9.2 Estructura visual

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Header: SGOS Reportes | Resumen | Getnet | Premios | Comps | ... | Acciones │
├───────────────┬──────────────────────────────────────────────────────────────┤
│ Filtros       │ Dashboard Home / Resumen                                     │
│ Año           │ GETNET                                                       │
│ Mes           │ [Mes cargado] [Hasta jornada] [Monto total] [Última jornada] │
│ Nombre        │                                                              │
│ Vista         │ PREMIOS                                                      │
│ Último archivo│ [Mes cargado] [Hasta jornada] [Monto total] [Última jornada] │
│               │                                                              │
│               │ COMPS                                                        │
│               │ [Mes cargado] [Hasta jornada] [Micros totales] [Última jor.] │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

### 9.3 Bloques por módulo

| Módulo | Métricas visibles |
|---|---|
| Getnet | Mes cargado, hasta jornada, monto total del mes, última jornada |
| Premios | Mes cargado, hasta jornada, monto total del mes, última jornada |
| COMPS | Mes cargado, hasta jornada, micros totales del mes, última jornada |

### 9.4 KPI Cards

| Elemento | Estilo recomendado |
|---|---|
| Fondo | `$layer-01` `#262626` |
| Borde | `1px solid #393939` |
| Padding | `20px` a `24px` |
| Label superior | Mayúsculas, 11px, tracking amplio, `$text-helper` |
| Valor principal | 24px a 28px, peso 600, `$text-primary` |
| Valor financiero destacado | Oro `#d4af37` |
| Nota inferior | 12px, `$text-secondary` |
| Acento | Borde izquierdo oro en cards financieras principales |

```css
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(220px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.kpi-card {
  min-height: 104px;
  padding: 20px 24px;
  background: #262626;
  border: 1px solid #393939;
}

.kpi-card--accent {
  border-left: 3px solid #d4af37;
}

.kpi-card--accent strong {
  color: #d4af37;
}
```

### 9.5 Estados visuales del Home

| Estado | Comportamiento visual |
|---|---|
| Sin archivo cargado | Card vacía con mensaje `No hay carga registrada para este módulo.` |
| Cargando | Skeleton cards en `$layer-02` |
| Error de datos | Inline notification en rojo sobre el módulo afectado |
| Filtro activo | Chips o resumen de filtros visibles |
| Exportación en proceso | Botón deshabilitado y texto `Exportando...` |

---

## 10. Tablas y reportes

Las tablas deben mantener lectura rápida, alto contraste y densidad controlada.

Reglas:

- headers en `$layer-02`;
- filas en `$layer-01`;
- hover con `$layer-03`;
- texto de celdas en 14px;
- números alineados a la derecha;
- fechas y nombres alineados a la izquierda;
- totales visibles con peso 600;
- valores monetarios importantes pueden usar color oro si son totales principales.

---

## 11. Botones

| Tipo | Uso | Estilo |
|---|---|---|
| Primario | Exportar, ingresar, acción principal | Fondo oro, texto oscuro |
| Secundario | Filtros, cargar Excel, salir | Fondo oscuro, borde sutil |
| Outline | Todos, limpiar, acciones neutras | Fondo transparente, borde visible |
| Peligro | Eliminar, descartar | Rojo solo cuando corresponda |

---

## 12. Responsive

| Tamaño | Comportamiento |
|---|---|
| Desktop | Header completo, filtros laterales, cards en 4 columnas |
| Tablet | Cards en 2 columnas, navegación puede comprimirse |
| Móvil | Cards en 1 columna, filtros como drawer lateral, botones agrupados |

---

## 13. Accesibilidad

- Todo input debe tener label visible.
- Los errores deben usar `role="alert"` cuando corresponda.
- El botón Filtros debe actualizar `aria-expanded`.
- No depender solo del color para indicar error.
- Mantener contraste alto en textos.
- El sistema debe poder navegarse con teclado.

---

## 14. Pantallas pendientes por documentar

| Orden | Pantalla / Módulo | Estado |
|---:|---|---|
| 1 | Login | Documentado |
| 2 | Home / Resumen | Documentado |
| 3 | Cargar Excel | Pendiente de captura / flujo final |
| 4 | Getnet | Pendiente de captura final |
| 5 | Premios | Pendiente de captura final |
| 6 | COMPS | Pendiente de captura final |
| 7 | Análisis general | Pendiente de definición visual |
| 8 | Control | Pendiente de definición visual |
| 9 | CoinIn Cero | Pendiente de definición visual |
| 10 | Usuarios / Roles | Pendiente de definición visual |

---

## 15. Regla final para la IA

Cuando la IA trabaje en interfaz, debe consultar este archivo.  
Cuando la IA trabaje en backend, estructura del código, Flask, Neon.tech o despliegue, debe consultar `ARCHITECTURE.md`.  
Cuando la IA trabaje en columnas, Excel, Jornada, ID único o reglas de datos, debe consultar `FUNCTIONAL_RULES.md`.
