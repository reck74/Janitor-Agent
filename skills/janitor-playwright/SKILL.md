---
name: janitor-playwright
description: "Automatización de navegador web mediante Playwright."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]

metadata:
  hermes:
    tags: [playwright, browser, automation, scraping, testing, web]
    category: automation
---

# janitor-playwright

Automatización de navegadores web mediante Playwright. Permite navegar,
extraer contenido, capturar pantallas y evaluar JavaScript en páginas reales.

## Cuando Usar

- Extraer contenido de páginas web dinámicas (SPA, JS-rendered)
- Capturar pantallas de sitios complejos o protegidos contra scraping
- Automatizar flujos web que requieren JavaScript real
- Verificar que una página carga correctamente y no tiene errores
- Extraer datos de tablas, listados o contenido generado por JS

## Prerrequisitos

- Node.js >= 18
- Módulo Playwright instalado en Janitor-Agent:
  ```
  ~/Janitor-Agent/node_modules/playwright
  ```
- Navegador Chromium cacheado:
  ```
  ~/.cache/ms-playwright/chromium-1217
  ```
- Directorio de capturas existente:
  ```
  ~/.janitor/screenshots/
  ```
- Credenciales en `~/.janitor/.env` si el sitio requiere autenticación

## Como Ejecutar

### Scripts disponibles

Los scripts individuales estan en `~/Janitor-Agent/skills/janitor-playwright/scripts/`:

| Script | Descripcion |
|--------|-------------|
| `screenshot.js` | Captura pantalla completa de la pagina |
| `extract-text.js` | Extrae texto visible del body |
| `form-test.js` | Prueba flujos de formulario |
| `local-verify.js` | Verifica que un servidor responde |

### Modo headless vs visual

**Headless (default):** Sin interfaz grafica, mas rapido.

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/screenshot.js \
  "https://example.com" \
  "~/.janitor/screenshots/mi-captura.png"
```

**Visual:** Abre el navegador visible. Útil para depuración.

```bash
# Editar el script y cambiar headless: true a headless: false
```

## Referencia Rapida

### Captura de pantalla

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/playwright_runner.js \
  --url "https://example.com" \
  --action screenshot \
  --output ~/.janitor/screenshots/salida.png
```

### Extraccion de texto

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/playwright_runner.js \
  --url "https://news.ycombinator.com" \
  --action text
```

### Scrapeo con selector CSS

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/playwright_runner.js \
  --url "https://example.com" \
  --action scrape \
  --selector "article.post h2" \
  --output ~/.janitor/screenshots/datos.json
```

### Evaluacion JavaScript

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/playwright_runner.js \
  --url "https://example.com" \
  --action evaluate \
  --script "() => document.title"
```

## API JavaScript

```javascript
const { chromium } = require('~/Janitor-Agent/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto('https://example.com', { waitUntil: 'networkidle' });
    const title = await page.title();
    console.log('Titulo:', title);
  } finally {
    await browser.close(); // SIEMPRE cerrar en finally o catch
  }
})();
```

**Regla absoluta:** Toda llamada a `chromium.launch()` debe incluir `browser.close()` en un bloque `finally` o `catch`. Si no se cierra el navegador, los procesos de Chromium quedan huérfanos y consumen recursos.

## Capturas de pantalla

Las capturas se guardan en `~/.janitor/screenshots/`. La ruta es configurable via variable de entorno:

```bash
export JANITOR_SCREENSHOTS_DIR=/ruta/personalizada
```

## Errores comunes

| Error | Causa | Solucion |
|-------|-------|----------|
| `browserType.launch: Executable doesn't exist` | Chromium no esta cacheado | `npx playwright install chromium` |
| `net::ERR_NAME_NOT_RESOLVED` | Sin conexion a internet | Verificar red o usar VPN |
| `page.goto: Timeout` | Pagina lenta o inaccesible | Aumentar `--timeout` o verificar URL |
| Procesos Chromium huerfanos | `browser.close()` no llamado | Siempre cerrar en `finally` o `catch` |

## Verificacion

Verificar que Playwright y Chromium estan instalados correctamente:

```bash
node -e "const { chromium } = require('~/Janitor-Agent/node_modules/playwright'); console.log('Playwright OK:', typeof chromium);"
```

Verificar que el navegador Chromium esta disponible:

```bash
ls ~/.cache/ms-playwright/chromium-1217/chrome-linux/chrome
```

Captura de prueba:

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/playwright_runner.js \
  --url "https://example.com" \
  --action screenshot \
  --output ~/.janitor/screenshots/test-verificacion.png
```

Si la imagen se genera sin errores, el skill esta funcionando.
