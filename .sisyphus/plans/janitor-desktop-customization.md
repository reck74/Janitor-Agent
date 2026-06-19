# PLAN DE PERSONALIZACIÓN: Janitor Desktop — TEMA VISUAL
> **Plan documentado - NO EJECUTAR EN ESTA SESIÓN**
> Sesión actual es solo análisis y exploración.
>
> **v3.0 — ENFOQUE SIMPLIFICADO**
>
> ## Principios rectores
>
> 1. **Personalización PURAMENTE GRÁFICA** — sin modificar funcionalidades
> 2. **Aprovechar el sistema de temas existente** (`installUserTheme()` API + CSS vars)
> 3. **CERO código nuevo en React** — solo data (presets) + assets + CSS overrides mínimos
> 4. **Reemplazar app icon + nombre de display** (vía electron-builder config externo)
> 5. **Mantener comportamiento upstream** intacto — solo piel visual
> 6. **Equilibrio wireframe/realidad** — capturar la esencia visual (paleta, tipografía, hairlines, monoespaciado) sin replicar componentes no existentes

---

## Metadata
- **Origen**: Análisis exploratorio + wireframe visual concreto
- **Versión upstream**: 0.15.1 (NousResearch/hermes-agent)
- **Estrategia**: User themes via `installUserTheme()` + assets binarios + electron-builder config externo
- **Complejidad**: **BAJA** — solo ~5 archivos, la mayoría data
- **Principio rector**: Solo se modifica **piel visual**, no comportamiento

---

## 1. QUÉ HACEMOS (alcance gráfico)

### 1.1 Lo único que toca este plan

| # | Acción | Tipo | Conflicto upstream |
|---|--------|------|---------------------|
| 1 | Crear **1 user theme** Janitor (dark + light) | Data | CERO |
| 2 | Copiar **3 assets binarios** (icon, logo, avatar) | Archivos | CERO |
| 3 | Agregar **1 línea import** en `main.tsx` para auto-instalar theme | Código | Trivial |
| 4 | Crear **1 CSS overrides file** (BrandMark, monospace global, sidebar tweaks) | Estilos | CERO |
| 5 | Crear **1 electron-builder config externo** (appId, productName) | Build config | CERO |
| 6 | Reemplazar **1 archivo** `package.json` script section (agrega 4 líneas) | Scripts | CERO |

### 1.2 Lo que NO hacemos (eliminaciones del plan v2.0)

| Eliminado | Razón |
|-----------|-------|
| ❌ Patch en `update-remote.cjs` para self-update | El user puede seguir usando `janitor update` desde CLI. El desktop usa el update upstream por defecto. |
| ❌ Patch en `main.cjs` para `HERMES_HOME=~/.janitor` | No es tema visual. El CLI ya maneja esto. El desktop upstream usa `~/.hermes` por defecto, lo cual está bien. |
| ❌ Componente `CommandBay` (home view nueva) | Funcionalidad nueva. El desktop ya tiene su home view (vacía por defecto). Replicar el wireframe significaría reescribir `desktop-controller.tsx`. |
| ❌ Componente `IndustrialToggle` hexagonal | Funcionalidad nueva. El desktop ya tiene `Switch` en `components/ui/switch.tsx`. |
| ❌ Componente `DeniedMessage` | Funcionalidad nueva. El desktop ya tiene `clarify-tool.tsx` y `tool-approval.tsx`. |
| ❌ Componente `AuditCard` + nueva vista `/audit` | Funcionalidad nueva. NO existe en Hermes y replicarlo requiere reescribir rutas. |
| ❌ Componente `StatusCell` + `DeckCard` + `LiveDiagnostics` | Funcionalidad nueva. |
| ❌ i18n overrides runtime | El sistema de temas NO depende de i18n. Los nombres "Hermes" en strings i18n son cosmético, fuera de alcance de "tema". |
| ❌ Fase de QA extensiva | Las personalizaciones son data/assets, no lógica nueva. Riesgo de regresión es mínimo. |
| ❌ Build script custom `build-janitor.cjs` | Podemos usar `electron-builder --config electron-builder.janitor.json` directamente sin script custom. |
| ❌ Custom Command Input styling | El composer del Hermes ya existe y funciona. Solo cambiamos colores vía theme. |

### 1.3 Equilibrio wireframe/realidad

| Elemento del wireframe | ¿Se implementa? | ¿Cómo? |
|------------------------|------------------|---------|
| Paleta verde lima + cyan + naranja + rojo | ✅ Sí | Via user theme + CSS vars |
| Tipografía monoespaciada global | ✅ Sí | Via theme typography |
| Hairlines fríos (#24383E, #34495A) | ✅ Sí | Via theme colors (border, input) |
| Brand mark con monograma Janitor | ✅ Sí | Reemplazar `nous-girl.jpg` (asset) |
| Logo hero "J4NITOR-AGENT" en splash | ⚠️ Parcial | Solo si el splash usa `<img>` del brand mark. Si no, omitir. |
| Sidebar 304px, background gradient, sessions dots | ⚠️ Solo color | El layout ya existe en Hermes; el theme da los colores correctos. |
| Command Bay home view (status strip + deck cards) | ❌ NO | Replicar es reescribir el desktop-controller. Out of scope. |
| Industrial toggle hexagonal | ❌ NO | El Switch de Hermes es funcional; no lo cambiamos. |
| DENIED message style | ❌ NO | El desktop ya tiene `tool-approval.tsx` con estilo propio. |
| Audit cards (VETO/PATCH) + vista `/audit` | ❌ NO | Funcionalidad nueva. |
| Ambient avatar watermark | ❌ NO | Requiere inyectar componente en cada vista. |
| Status dot glow verde lima | ⚠️ Solo si lo usa el theme | Los status dots usan `--dt-*` tokens, así que se pintan automáticamente. |
| Tagline ">_ Sistema en linea. Habla." | ❌ NO | Reemplazaría el empty state. |
| Live diagnostics panel | ❌ NO | Funcionalidad nueva. |

**Resumen**: Capturamos la **esencia visual** (paleta, monospace, hairlines, brand) sin replicar el wireframe pixel-perfect.

---

## 2. IMPLEMENTACIÓN (5 fases, ~3-4 horas)

### FASE 1: Crear theme presets Janitor
> **Conflicto upstream**: CERO
> **Esfuerzo**: 30 min

**Crear** `apps/desktop/janitor/theme-presets.ts`:

```typescript
import type { DesktopTheme } from '@/themes/types'

// === Paleta Janitor (extraída del wireframe) ===
const JANITOR_DARK_COLORS = {
  background: '#020A0C',          // Negro azulado profundo
  foreground: '#D7D7C9',          // Verde hueso
  card: '#0C1D21',                // Panel elevado
  cardForeground: '#D7D7C9',
  muted: '#061316',               // Panel base
  mutedForeground: '#9EA7A4',     // Muted
  popover: '#0C1D21',
  popoverForeground: '#D7D7C9',
  primary: '#B6FF5C',             // Verde lima BRAND
  primaryForeground: '#020A0C',
  secondary: '#34495A',
  secondaryForeground: '#D7D7C9',
  accent: '#00D7E8',              // Cyan diagnóstico
  accentForeground: '#020A0C',
  border: '#24383E',              // Hairlines frías
  input: '#34495A',
  ring: '#B6FF5C',
  midground: '#B6FF5C',
  composerRing: '#B6FF5C',
  destructive: '#FF3B1F',         // Rojo veto
  destructiveForeground: '#FFFFFF',
  sidebarBackground: '#061316',
  sidebarBorder: '#24383E',
  userBubble: '#0C1D21',
  userBubbleBorder: '#34495A'
}

const JANITOR_LIGHT_COLORS = {
  background: '#F4F6F7',          // Light bg (conservador)
  foreground: '#020A0C',
  card: '#FFFFFF',
  cardForeground: '#020A0C',
  muted: '#E6EAEC',
  mutedForeground: '#657178',
  popover: '#FFFFFF',
  popoverForeground: '#020A0C',
  primary: '#8AE51E',             // Verde lima más oscuro para contraste
  primaryForeground: '#020A0C',
  secondary: '#D7D7C9',
  secondaryForeground: '#020A0C',
  accent: '#00A8B8',              // Cyan oscuro para light mode
  accentForeground: '#FFFFFF',
  border: '#9EA7A4',
  input: '#D7D7C9',
  ring: '#8AE51E',
  midground: '#8AE51E',
  composerRing: '#8AE51E',
  destructive: '#C72E1A',
  destructiveForeground: '#FFFFFF',
  sidebarBackground: '#E6EAEC',
  sidebarBorder: '#9EA7A4',
  userBubble: '#E6EAEC',
  userBubbleBorder: '#9EA7A4'
}

// Tipografía monoespaciada global
const JANITOR_TYPOGRAPHY = {
  fontSans: '"Cascadia Code", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace',
  fontMono: '"Cascadia Code", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace'
}

export const janitorDark: DesktopTheme = {
  name: 'janitor-dark',
  label: 'Janitor Dark',
  description: 'Industrial green-lime theme — DevSecOps by default',
  colors: JANITOR_DARK_COLORS,
  darkColors: JANITOR_DARK_COLORS,  // dark-only
  typography: JANITOR_TYPOGRAPHY
}

export const janitorLight: DesktopTheme = {
  name: 'janitor-light',
  label: 'Janitor Light',
  description: 'Light variant of Janitor theme',
  colors: JANITOR_LIGHT_COLORS,
  darkColors: JANITOR_LIGHT_COLORS,
  typography: JANITOR_TYPOGRAPHY
}

export const JANITOR_THEMES: DesktopTheme[] = [janitorDark, janitorLight]
```

**Verificación**:
- TypeScript compila
- `janitorDark` y `janitorLight` son tipos `DesktopTheme` válidos

---

### FASE 2: Auto-instalar theme al primer launch
> **Conflicto upstream**: CERO
> **Esfuerzo**: 20 min

**Crear** `apps/desktop/janitor/install-themes.ts`:

```typescript
import { installUserTheme } from '@/themes/user-themes'
import { JANITOR_THEMES } from './theme-presets'

const INSTALLED_KEY = 'janitor-desktop-themes-installed-v1'

/**
 * Instala los temas Janitor como user themes en localStorage.
 * Idempotente: se ejecuta una sola vez gracias a INSTALLED_KEY.
 * Si el user ya eligió un theme, no lo sobreescribe.
 */
export function installJanitorThemes(): void {
  if (typeof window === 'undefined') return
  if (window.localStorage.getItem(INSTALLED_KEY)) return

  let installed = 0
  for (const theme of JANITOR_THEMES) {
    try {
      installUserTheme(theme)
      installed++
    } catch (err) {
      console.warn(`[janitor] failed to install theme ${theme.name}:`, err)
    }
  }

  if (installed > 0) {
    window.localStorage.setItem(INSTALLED_KEY, 'true')

    // Aplicar janitor-dark como default SOLO si el user no ha elegido theme
    const currentTheme = window.localStorage.getItem('hermes-desktop-theme-v2')
    if (!currentTheme) {
      window.localStorage.setItem('hermes-desktop-theme-v2', 'janitor-dark')
      window.localStorage.setItem('hermes-desktop-mode-v1', 'dark')
    }
  }
}
```

**Crear** `apps/desktop/janitor/overlay.tsx`:

```typescript
import { useEffect } from 'react'
import { installJanitorThemes } from './install-themes'
import './overrides.css'

/**
 * Componente invisible: instala themes Janitor y carga CSS overrides.
 * Renderizar UNA vez en el árbol root, fuera de cualquier feature condicional.
 */
export function JanitorOverlay() {
  useEffect(() => {
    installJanitorThemes()
  }, [])
  return null
}
```

**Modificar** `apps/desktop/src/main.tsx` (1 línea):

```diff
  import App from './app'
  import { ErrorBoundary } from './components/error-boundary'
  import { HapticsProvider } from './components/haptics-provider'
  import { I18nProvider } from './i18n'
  import { installClipboardShim } from './lib/clipboard'
  import { queryClient } from './lib/query-client'
  import { ThemeProvider } from './themes/context'
+ import { JanitorOverlay } from './janitor/overlay'

  installClipboardShim()

  // ...

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary label="root">
        <QueryClientProvider client={queryClient}>
          <I18nProvider>
            <ThemeProvider>
              <HapticsProvider>
                <HashRouter>
+                 <JanitorOverlay />
                  <App />
                </HashRouter>
              </HapticsProvider>
            </ThemeProvider>
          </I18nProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </StrictMode>
  )
```

**Verificación**:
- `npm run typecheck` pasa
- App arranca, `localStorage.janitor-desktop-themes-installed-v1` = 'true'
- `/skin` picker muestra "Janitor Dark" y "Janitor Light"
- Settings → Appearance grid incluye ambos
- Primer launch: theme = `janitor-dark`, mode = `dark`

---

### FASE 3: CSS overrides (BrandMark + tweaks)
> **Conflicto upstream**: CERO (CSS specificity)
> **Esfuerzo**: 30 min

**Crear** `apps/desktop/janitor/overrides.css`:

```css
/* apps/desktop/janitor/overrides.css
   CSS overrides Janitor — cargados en runtime via JanitorOverlay.
   Solo modifica presentación; no toca comportamiento React. */

/* === BrandMark: usar monograma Janitor en lugar de nous-girl.jpg === */
img[src*="nous-girl.jpg"] {
  content: url('/janitor-monogram.png');
}

/* === Tipografía monoespaciada global (sobrescribe theme) === */
body, button, input, textarea, select,
.font-sans, [class*="font-sans"] {
  font-family: "Cascadia Code", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace !important;
}

/* === Sidebar background gradient sutil (efecto wireframe) === */
[data-sidebar], [class*="sidebar"] {
  background-image: repeating-linear-gradient(
    90deg, 
    transparent 0 14px, 
    rgba(182, 255, 92, 0.016) 14px 15px
  );
}

/* === Status dot con glow verde lima === */
[class*="status-dot"], [data-status-dot] {
  background-color: #B6FF5C !important;
  box-shadow: 0 0 10px rgba(182, 255, 92, 0.8) !important;
}

/* === Active session indicator: border-left verde lima === */
[class*="session"][class*="active"], [data-active="true"] {
  border-left: 3px solid #B6FF5C !important;
  background: linear-gradient(90deg, rgba(182, 255, 92, 0.13), rgba(182, 255, 92, 0.035)) !important;
}
```

**Verificación**:
- BrandMark en splash/onboarding muestra monograma Janitor
- Tipografía monoespaciada global
- Sidebar tiene efecto gradient sutil
- Sessions activas tienen border-left verde lima

---

### FASE 4: Reemplazar assets binarios
> **Conflicto upstream**: CERO (binarios, git LFS)
> **Esfuerzo**: 10 min

**Copiar desde wireframe**:
```bash
# Asset principal: monograma (app icon + brand mark)
cp .plans/janitor_theme_wireframe/assets/j4nitor-monogram.png apps/desktop/public/janitor-monogram.png

# Asset secundario: logo hero (splash)
cp .plans/janitor_theme_wireframe/assets/j4nitor-agent-logo-transparent.png apps/desktop/public/janitor-logo-hero.png

# Asset opcional: avatar (futuro uso)
cp .plans/janitor_theme_wireframe/assets/janitor-avatar-official.png apps/desktop/public/janitor-avatar.png
```

**NO reemplazamos** (mantener upstream para evitar conflictos):
- `apps/desktop/assets/icon.{icns,ico,png}` (build-time app icon)
- `apps/desktop/public/apple-touch-icon.png` (renderer favicon)
- `apps/desktop/public/nous-girl.jpg` (BrandMark actual)

Estos se cambian via electron-builder config en Fase 5.

**Verificación**:
- 3 archivos PNG presentes en `apps/desktop/public/`
- Tamaños coinciden con source

---

### FASE 5: electron-builder config externo (app name + bundle ID)
> **Conflicto upstream**: CERO
> **Esfuerzo**: 15 min

**Crear** `apps/desktop/electron-builder.janitor.json`:

```json
{
  "appId": "io.janitor.agent",
  "productName": "J4nitor-Agent",
  "executableName": "janitor",
  "artifactName": "J4nitor-Agent-${version}-${os}-${arch}.${ext}",
  "icon": "apps/desktop/assets/janitor-icon",
  "mac": {
    "extendInfo": {
      "CFBundleDisplayName": "J4nitor-Agent",
      "CFBundleName": "J4nitor-Agent",
      "CFBundleExecutable": "J4nitor-Agent",
      "NSAudioCaptureUsageDescription": "J4nitor-Agent uses the microphone for voice input.",
      "NSMicrophoneUsageDescription": "J4nitor-Agent uses the microphone for voice input and voice conversations."
    },
    "target": ["dmg", "zip"]
  },
  "win": {
    "legalTrademarks": "J4nitor-Agent",
    "target": ["nsis", "msi"]
  },
  "linux": {
    "maintainer": "Reck <support@janitor.local>",
    "synopsis": "Native desktop shell for J4nitor-Agent — DevSecOps Orchestrator.",
    "target": ["AppImage", "deb", "rpm"]
  },
  "nsis": {
    "shortcutName": "J4nitor-Agent",
    "uninstallDisplayName": "J4nitor-Agent"
  }
}
```

**Crear script de iconos Janitor** (1 vez):
```bash
# Convertir j4nitor-monogram.png a todos los formatos
mkdir -p apps/desktop/assets/janitor-icon-tmp
cp .plans/janitor_theme_wireframe/assets/j4nitor-monogram.png apps/desktop/assets/janitor-icon-tmp/source.png

# macOS
sips -z 1024 1024 apps/desktop/assets/janitor-icon-tmp/source.png --out apps/desktop/assets/janitor-icon-tmp/icon-1024.png
# ... (usar iconutil para generar .icns, ImageMagick para .ico)

# Linux/Windows  
cp apps/desktop/assets/janitor-icon-tmp/icon-1024.png apps/desktop/assets/janitor-icon.png
```

**Documentar en** `apps/desktop/janitor/README.md` cómo regenerar iconos.

**Build command**:
```bash
cd apps/desktop
npx electron-builder --config electron-builder.janitor.json --linux AppImage
```

**Verificación**:
- AppImage generado se llama `J4nitor-Agent-0.15.1-linux-x86_64.AppImage`
- macOS DMG: `J4nitor-Agent-0.15.1.dmg` con appId `io.janitor.agent`
- Win NSIS: `J4nitor-Agent Setup 0.15.1.exe`
- Icono Janitor en file manager / Finder / Dock

---

## 3. ESTRUCTURA FINAL

```
apps/desktop/janitor/
├── overlay.tsx                  # Componente React invisible (install themes + load CSS)
├── theme-presets.ts             # janitorDark + janitorLight themes (DATA)
├── install-themes.ts            # installUserTheme() wrapper (DATA + effect)
├── overrides.css                # CSS overrides Janitor (Brand mark, monospace, sidebar)
├── README.md                    # Instrucciones merge con upstream
└── electron-builder.janitor.json  # Build config externo (appId, productName)

apps/desktop/public/             # Asset additions
├── janitor-monogram.png         # Brand mark icon (1024x1024)
├── janitor-logo-hero.png        # Splash hero logo
└── janitor-avatar.png           # Avatar (futuro uso)

apps/desktop/assets/             # App icon overrides (build-time)
├── janitor-icon.png             # Linux PNG
├── janitor-icon.icns            # macOS bundle
└── janitor-icon.ico             # Windows ico
```

**Total**: 6 archivos creados en `janitor/`, 6 assets binarios, 1 línea agregada a `main.tsx`.

---

## 4. CÓMO SE VE EN LA APP

### 4.1 Primer launch
- App abre, splash usa `janitor-monogram.png` (vía CSS override en `nous-girl.jpg` placeholder)
- Theme `janitor-dark` se aplica automáticamente
- Tipografía monoespaciada global
- Sidebar con gradient sutil + sessions activas con border-left verde lima

### 4.2 Cambio de theme
- Settings → Appearance → grid muestra "Janitor Dark" y "Janitor Light" como opciones
- Click en "Janitor Dark" aplica el theme
- Click en otro theme (nous, midnight, etc.) revierte al upstream
- Persistencia en localStorage funciona normal

### 4.3 Build production
- `npx electron-builder --config electron-builder.janitor.json --linux AppImage`
- AppImage con nombre "J4nitor-Agent", icono Janitor, appId `io.janitor.agent`
- Instalación: icono Janitor en file manager, ejecutable `janitor`

### 4.4 Upstream sync
- `git pull upstream main`:
  - CERO conflictos en `apps/desktop/janitor/` (directorio nuestro)
  - CERO conflictos en `apps/desktop/public/janitor-*.png` (assets nuestros)
  - CERO conflictos en `apps/desktop/assets/janitor-icon.*` (assets nuestros)
  - POSIBLE conflicto en `apps/desktop/src/main.tsx` (1 línea import) → trivial
  - POSIBLE conflicto en `apps/desktop/package.json` si upstream reorganiza scripts → trivial

---

## 5. COMPARACIÓN CON PLAN v2.0

| Aspecto | v2.0 (complejo) | v3.0 (simplificado) |
|--------|------------------|----------------------|
| Archivos creados | ~15 | **6** |
| Líneas de código TS | ~500 | **~80** |
| Componentes custom nuevos | 10 (CommandBay, IndustrialToggle, DeniedMessage, AuditCard, etc) | **0** (solo data themes) |
| Conflictos upstream esperados | 4-5 (low) | **2 (trivial)** |
| Esfuerzo estimado | 13-16h | **3-4h** |
| Comportamiento funcional modificado | Sí (varios) | **NO** |
| Replicar wireframe pixel-perfect | Sí | **NO — solo esencia visual** |

---

## 6. WORKFLOW DE BUILD

```bash
# Dev (sin cambios)
cd apps/desktop
npm run dev

# Build upstream
npm run dist:linux  # AppImage "Hermes-0.15.1..."

# Build Janitor-branded
npx electron-builder --config electron-builder.janitor.json --linux AppImage
# Output: release/J4nitor-Agent-0.15.1-linux-x86_64.AppImage
```

---

## 7. RIESGOS Y MITIGACIONES

| Riesgo | Mitigación |
|--------|------------|
| `main.tsx` 1 línea conflict en upstream merge | Edit manual trivial, documentado en MERGE_GUIDE.md |
| Assets reemplazados en `apps/desktop/assets/` | Si upstream cambia iconos, re-aplicar replace |
| Theme typography sobreescribe `--dt-font-sans` globalmente | Si user quiere sans para algo específico, override en CSS posterior |
| CSS selectors `img[src*="nous-girl.jpg"]` puede romperse si upstream cambia filename | Usar selector más robusto: `span[class*="bg-white"] img[alt=""]` |
| localStorage keys `hermes-desktop-*` si upstream cambia schema | Migración simple: leer valor, fallback a janitor-dark |

---

## 8. PRÓXIMOS PASOS (futuras sesiones)

### Sesión 1: Implementación (3-4h)
- Ejecutar FASE 1-5
- Verificar build production
- Commit con mensaje: `feat(desktop): add Janitor visual theme via user-themes API`

### Sesión 2: Documentación + distribución
- Crear `apps/desktop/janitor/README.md` con instrucciones merge
- Actualizar `MERGE_GUIDE.md` con sección desktop
- Subir AppImage a GitHub Releases del fork

### Sesión 3 (opcional): Mejoras incrementales
- Custom toggle hexagonal (reemplaza `Switch` en skills/settings)
- Custom denied message style (override `clarify-tool.tsx`)
- Custom status bar layout (override `statusbar-controls.tsx`)
- Custom deck cards en empty state (override `chat/index.tsx` empty view)

---

## 9. ARCHIVOS DE REFERENCIA

### Source (NO modificar)
- `apps/desktop/electron/main.cjs` (intacto)
- `apps/desktop/electron/preload.cjs` (intacto)
- `apps/desktop/electron/update-remote.cjs` (intacto)
- `apps/desktop/src/themes/presets.ts` (intacto)
- `apps/desktop/src/themes/context.tsx` (intacto)
- `apps/desktop/src/app/desktop-controller.tsx` (intacto)
- `apps/desktop/src/components/brand-mark.tsx` (intacto)
- `apps/desktop/src/i18n/*.ts` (intacto)
- `apps/desktop/package.json:build.*` (intacto)

### Nuevos (nuestro control)
- `apps/desktop/janitor/overlay.tsx` (nuevo)
- `apps/desktop/janitor/theme-presets.ts` (nuevo)
- `apps/desktop/janitor/install-themes.ts` (nuevo)
- `apps/desktop/janitor/overrides.css` (nuevo)
- `apps/desktop/janitor/electron-builder.janitor.json` (nuevo)
- `apps/desktop/janitor/README.md` (nuevo)
- `apps/desktop/public/janitor-{monogram,logo-hero,avatar}.png` (nuevo)
- `apps/desktop/assets/janitor-icon.{png,icns,ico}` (nuevo)

### Modificados (1 línea)
- `apps/desktop/src/main.tsx` (+2 líneas: import + JSX)

### Plan asociado
- `.sisyphus/plans/janitor-desktop-customization.md` (este archivo)
- `.sisyphus/notepads/desktop-app-analysis/wireframe-vision.md` (paleta + componentes wireframe)
- `.sisyphus/notepads/desktop-app-analysis/ANALYSIS.md` (análisis técnico upstream)
