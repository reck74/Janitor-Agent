# Ejemplos de Uso - janitor-playwright

Referencia rapida para ejecutar los scripts de automatizacion web.

---

## Informacion del Entorno

| Componente | Ruta / Version |
|------------|----------------|
| Playwright | 1.59.1 |
| Chromium | 1217 |
| Cache navegador | `~/.cache/ms-playwright/chromium-1217` |
| Modulo Node | `~/Janitor-Agent/node_modules/playwright` |
| Directorio capturas | `~/.janitor/screenshots/` |

---

## 1. screenshot.js

Captura una pantalla completa de cualquier pagina web.

### Uso basico

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/screenshot.js \
  "https://example.com"
```

### Con ruta de salida personalizada

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/screenshot.js \
  "https://example.com" \
  "~/.janitor/screenshots/mi-captura.png"
```

### Parametros

| Posicion | Descripcion | Default |
|----------|-------------|---------|
| 1 | URL de la pagina | `https://example.com` |
| 2 | Ruta donde guardar la imagen | `~/.janitor/screenshots/capture.png` |

### Detalles tecnicos

- Viewport: 1280x720
- Espera `networkidle` antes de capturar
- Genera captura completa de la pagina (`fullPage: true`)

---

## 2. extract-text.js

Extrae el contenido de texto visible de una pagina web.

### Uso basico

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/extract-text.js \
  "https://news.ycombinator.com"
```

### Extrayendo texto de una API o dashboard

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/extract-text.js \
  "https://httpbin.org/html"
```

### Parametros

| Posicion | Descripcion | Requerido |
|----------|-------------|-----------|
| 1 | URL de la pagina | Si |

### Limitacion

El script trunca la salida a 2000 caracteres para evitar saturar la terminal.

### Detalles tecnicos

- Usa `page.textContent('body')` para extraer texto
- Espera `networkidle` antes de extraer
- Solo devuelve texto visible, sin HTML

---

## 3. form-test.js

Prueba un formulario web llenando campos y verificando el submit.

### Uso basico

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/form-test.js \
  "https://httpbin.org/forms/post"
```

### Verificando un login

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/form-test.js \
  "https://httpbin.org/forms/post"
```

### Parametros

| Posicion | Descripcion | Requerido |
|----------|-------------|-----------|
| 1 | URL de la pagina con formulario | Si |

### Lo que hace el script

1. Navega a la URL proporcionada
2. Llena `input[name="email"]` con `test@janitor.local`
3. Llena `input[name="password"]` con `TestPassword123!`
4. Hace click en `button[type="submit"]`
5. Espera la navegacion posterior
6. Guarda screenshot en `/tmp/form-test-result.png`
7. Imprime URL final y titulo de la pagina

### Detalles tecnicos

- Captura screenshot del resultado en `/tmp/form-test-result.png`
- Cierra el navegador al finalizar
- Exit code 0 si tiene exito, 1 si falla

---

## 4. local-verify.js

Verifica que una pagina web carga correctamente y detecta errores de consola.

### Uso basico

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/local-verify.js \
  "https://example.com"
```

### Verificando un servicio interno

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/local-verify.js \
  "http://localhost:3000"
```

### Parametros

| Posicion | Descripcion | Requerido |
|----------|-------------|-----------|
| 1 | URL a verificar | Si |

### Lo que verifica el script

1. Carga la pagina con `domcontentloaded`
2. Espera 2 segundos para capturar errores tardios
3. Registra errores de consola (`console.error`)
4. Devuelve el codigo de status HTTP

### Criterios de exito

| Condicion | Exit code |
|-----------|-----------|
| Status HTTP 200 | 0 (exito) |
| Status HTTP != 200 | 1 (fallo) |
| Error de conexion | 1 (fallo) |

### Ejemplo de salida exitosa

```
Status: 200
Title: Example Domain
Console errors: 0
```

---

## Patrones Comunes

### Verificar que un sitio esta vivo

```bash
node ~/Janitor-Agent/skills/janitor-playwright/scripts/local-verify.js \
  "https://example.com"
```

### Capturar pantalla y verificar

```bash
# Verificar que carga
node ~/Janitor-Agent/skills/janitor-playwright/scripts/local-verify.js \
  "https://example.com"

# Si funciona, capturar pantalla
node ~/Janitor-Agent/skills/janitor-playwright/scripts/screenshot.js \
  "https://example.com"
```

### Extraer contenido y analizar

```bash
# Extraer texto
node ~/Janitor-Agent/skills/janitor-playwright/scripts/extract-text.js \
  "https://news.ycombinator.com"
```

---

## Solucion de Problemas

### " playwright not found"

Verifica que el modulo esta instalado:

```bash
ls ~/Janitor-Agent/node_modules/playwright
```

### " Chromium not installed"

Instala el navegador:

```bash
cd ~/Janitor-Agent/node_modules/playwright
node install chromium
```

### Permiso denegado al guardar screenshot

Asegurate de que el directorio existe:

```bash
mkdir -p ~/.janitor/screenshots
```

### Timeout esperando networkidle

Algunas paginas usan WebSockets o streams perpetuos. Para esas,
considera usar `local-verify.js` que solo espera `domcontentloaded`.
