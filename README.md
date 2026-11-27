# Janitor Agent

**Janitor** es el conserje que limpia el desastre tecnológico que vas dejando:
equipos, sistemas, redes, infraestructura, seguridad, proyectos y código. Te
habla en español, sin rodeos y sin filtro. Si le pides una estupidez, te lo va a
decir. Luego te la arregla bien, que para eso está.

Por debajo es un **fork delgado** de [Hermes Agent](https://github.com/NousResearch/hermes-agent)
(Nous Research): Hermes pone el motor (agente, memoria, skills, cron,
subagentes, gateway de mensajería, TUI y app de escritorio) y Janitor añade su
identidad, sus skills y sus aplicativos opcionales sin reescribir el core.

- **Todo lo tecnológico**, no solo código: revisa la salud del equipo, libera
  disco, ordena carpetas, investiga repositorios, monta proyectos.
- **App de escritorio y terminal** con el mismo home (`~/.janitor`) y las mismas
  sesiones. No pisa ningún `~/.hermes` que tengas.
- **Base ligera:** sin Docker, sin Honcho y sin un proveedor de IA obligatorio.
  MiniMax viene recomendado y preconfigurado; eliges otro si te da la gana.
- **Lo pesado es opcional:** Honcho, n8n, LightRAG, NocoDB, WAHA, Firecrawl y
  Open Design se añaden después, solo si los pides.

---

## Descargar e instalar

Janitor se instala con su **app de escritorio**. Nada de pegar `curl | bash` en
un terminal. Bájala de la última versión publicada:
<https://github.com/reck74/Janitor-Agent/releases/latest>

| Sistema | Archivo |
|---|---|
| Linux (x86_64, cualquier distribución) | `Janitor-linux-x86_64.AppImage` |
| Arch Linux | `janitor-desktop-bin-<versión>-1-x86_64.pkg.tar.zst` |
| Windows (x64) | `Janitor-win-x64.exe` |
| macOS (Apple Silicon) | `Janitor-mac-arm64.dmg` |
| macOS (Intel, experimental) | `Janitor-mac-x64.dmg`, solo si aparece en la versión |
| Todos | `SHA256SUMS`, para comprobar que bajaste lo que crees |

Las versiones `v1.0.0` y `v0.1.x` que aún aparecen en esa página son de antes
de la app: no las instales. Usa la marcada como última («Latest»).

Paso a paso por sistema (permisos del AppImage, `pacman -U`, el aviso de
SmartScreen en Windows, Gatekeeper en macOS, verificar la suma y desinstalar):
[`docs/janitor/instalar-app.md`](docs/janitor/instalar-app.md). El instalador
de Windows no está firmado y la app de macOS no está notarizada: sí, saldrán
avisos; la guía dice cómo pasarlos. Windows y macOS se compilan y arrancan en CI,
pero todavía no se han probado en un equipo real. Si eres el primero, avisa.

**Primer arranque:**

1. La app instala el motor en `~/.janitor` (en Windows,
   `%USERPROFILE%\.janitor`) con `scripts/install.sh` (`scripts/install.ps1` en
   Windows). Verás las etapas en pantalla. Ten paciencia.
2. Eliges el proveedor de IA. MiniMax es el recomendado; la clave la pones tú.
3. El navegador del agente (Chromium) no viene de serie: se descarga la primera
   vez que el agente navega. Esa primera vez tarda; las siguientes, no.

### ¿Tienes un Janitor antiguo instalado por terminal?

Si tienes `~/.janitor/janitor-core`, la app se niega a instalar encima y no toca
nada. No se adopta ni se migra: se desinstala y se empieza de cero.
Instrucciones: [`docs/janitor/desinstalar-instalacion-antigua.md`](docs/janitor/desinstalar-instalacion-antigua.md).

---

## Desde el terminal

La instalación deja también el comando `janitor` (`~/.local/bin/janitor`; en
Windows, `%USERPROFILE%\.janitor\bin`). Abre una terminal nueva para que
aparezca.

```bash
janitor                         # Janitor en el terminal (con el skin sentry-janitor)
janitor --tui                   # interfaz de pantalla completa
janitor --version
janitor gateway                 # gateway de mensajería (Telegram, Discord, ...)
janitor plantillas list         # plantillas de agente especialista
janitor plantillas crear investigador   # o creador-proyectos
janitor obreros estado          # dirigir tu Claude Code / Codex (desactivado hasta que lo actives)
```

Casi todos los subcomandos de `hermes` funcionan igual con `janitor`. Las
excepciones: `janitor update` sigue el canal de Janitor (abajo), y los flujos de
cuenta de Nous están ocultos. La documentación del motor está en inglés:
[hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/).

---

## Aplicativos opcionales

Nada de esto se instala con la base. Lo pides y Janitor te guía; solo entonces
hace falta Docker. En la app también los ves y los arrancas o paras desde la
pantalla **Servicios**.

```bash
janitor services list               # catálogo y estado
janitor services status [nombre]    # estado de los contenedores
janitor services deploy <nombre>    # instalar o reparar (contenedores janitor-*)
janitor services start <nombre>
janitor services stop <nombre>
janitor services uninstall <nombre> # quita los contenedores; los volúmenes se quedan
```

| Aplicativo | Para qué | Cómo |
|---|---|---|
| `honcho` | Memoria avanzada entre sesiones (nube o local) | Docker si es local |
| `n8n` | Automatizaciones con flujos visuales | Docker |
| `lightrag` | Base de conocimiento con grafo y RAG | Docker |
| `nocodb` | Bases de datos con interfaz web y API | Docker |
| `waha` | Auditoría **de solo lectura** de tu WhatsApp personal | Docker |
| `firecrawl` | Extracción y búsqueda web desde tu equipo | Docker |
| Open Design | Generar diseños | Sin Docker: pídeselo a Janitor (skill `janitor-opendesign`); no pasa por `janitor services` |

WAHA no manda mensajes salvo orden directa tuya, y tus conversaciones viajan al
proveedor de IA que elegiste. Piénsalo antes.

En Windows, los aplicativos con Docker no se pueden instalar ni administrar
desde Janitor: necesitan Linux o macOS.

---

## Actualizar

Janitor solo entrega **versiones etiquetadas**. Una fusión a `main` no le llega a
nadie: el canal es la rama `stable`, que solo avanza cuando se publica una
etiqueta `v…`. La app y `janitor update` siguen ese canal, nunca la rama de
desarrollo.

```bash
janitor update --check   # solo mira si hay algo nuevo
janitor update           # actualiza el motor
```

Si todavía no hay ninguna versión publicada, lo dice y no toca nada. Si el motor
queda más nuevo que la app, la app te avisa y te lleva a la página de versiones
para bajar la nueva (instrucciones en
[`instalar-app.md`](docs/janitor/instalar-app.md#8-actualizar)). Si alguna
versión futura reorganiza `~/.janitor`, el siguiente arranque lo migra solo, con
copia previa en `~/.janitor/.backup/`.

## Desinstalar

Ver [`instalar-app.md`, sección 10](docs/janitor/instalar-app.md#10-desinstalar).
Quitar la app no borra el motor ni tus datos; eso lo decides tú.

---

## Para desarrolladores

| Ruta | Contenido |
|---|---|
| `janitor/` | Lanzador, actualización, canal `stable`, migraciones, plugin de Hermes, plugin de la app, servicios, catálogo de skills, plantillas, obreros, inventario del fork |
| `janitor/skills/{core,system,projects,research,services,integrations}/` | Skills Janitor, leídas en su sitio; `janitor/catalog.yaml` decide cuáles ve cada agente |
| `assets/janitor/` | Config, `SOUL.md` y skin `sentry-janitor` de partida |
| `apps/desktop-janitor/` | Overlay de build de la app (marca, idioma, empaquetado) |
| `tests/janitor/` | Suite de tests de Janitor |

El resto del árbol es Hermes. Cada edición sobre un archivo de upstream está
declarada en [`janitor/overlay.yaml`](janitor/overlay.yaml), y
`python -m janitor.overlay check` falla ante cualquier divergencia no declarada.
Así cada release de Hermes entra con `git merge <tag>` sin perder nada.

```bash
uv venv .venv --python 3.11 && source .venv/bin/activate
uv pip install -e ".[all,dev]"
scripts/run_tests.sh tests/janitor/     # suite Janitor
scripts/janitor-sync-verify.sh          # gate completo (overlay + tests + TUI + desktop)
```

- [AGENTS.md](AGENTS.md): directivas del fork y guía de desarrollo de Hermes.
- [MERGE_GUIDE.md](MERGE_GUIDE.md): cómo integrar una release nueva de Hermes.
- [docs/janitor/plans/janitor-desktop-app.md](docs/janitor/plans/janitor-desktop-app.md): decisiones, estado y tareas pendientes.
- [CHANGELOG.md](CHANGELOG.md): cambios del fork por versión.

---

## Licencia

MIT. Ver [LICENSE](LICENSE).

**Construido por Reck!** ([@reck74](https://github.com/reck74)). Basado en
[Hermes Agent](https://github.com/NousResearch/hermes-agent) de
[Nous Research](https://nousresearch.com).
