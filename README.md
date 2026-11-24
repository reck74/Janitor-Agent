<p align="center">
  <img src="janitor-tui.png" alt="Janitor Agent" width="100%">
</p>

# Janitor Agent

Janitor es un **orquestador DevSecOps** con personalidad cínica, construido como
**fork delgado** de [Hermes Agent](https://github.com/NousResearch/hermes-agent)
(Nous Research). Hermes aporta el motor completo — CLI, TUI, gateway de
mensajería (Telegram, Discord, Slack…), memoria, skills, cron, subagentes y la
app de escritorio — y Janitor añade encima su identidad, sus skills y sus
servicios self-hosted, sin reescribir el core.

- Audita código buscando OWASP Top 10, CWE Top 25 y deuda técnica.
- Vive aislado en `~/.janitor` (`HERMES_HOME`), independiente de cualquier `~/.hermes`.
- Instalación mínima; Firecrawl, n8n, LightRAG, NocoDB, WAHA y Browser son opcionales.
- Se mantiene al día con cada release de Hermes mediante un sync semanal verificado.

---

## Instalación

Janitor se instala desde su **app de escritorio** (Linux AppImage primero; ver
[Janitor Desktop](#janitor-desktop)). En el primer arranque la app ejecuta
`scripts/install.sh` de este fork por etapas: el motor queda en
`~/.janitor/hermes-agent`, el comando `janitor` en `~/.local/bin` y el
proveedor de IA se elige en pantalla (MiniMax es el recomendado). No hace
falta Docker ni ninguna clave para la instalación base.

¿Tienes un Janitor antiguo instalado por terminal (`~/.janitor/janitor-core`)?
No se adopta ni se migra: desinstálalo siguiendo
[`docs/janitor/desinstalar-instalacion-antigua.md`](docs/janitor/desinstalar-instalacion-antigua.md)
y empieza de cero con la app.

Con la app instalada, el terminal también sirve:

```bash
janitor              # CLI interactiva
janitor --tui        # TUI (skin sentry-janitor)
janitor gateway      # gateway de mensajería
janitor update       # actualizar desde este fork
```

Todos los subcomandos de `hermes` funcionan igual con `janitor`; la
documentación del core está en [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs/).

## Servicios opcionales

```bash
janitor services list                 # catálogo y estado de cada servicio
janitor services deploy firecrawl     # desplegar (contenedores janitor-*)
janitor services stop firecrawl       # detener (los volúmenes se conservan)
```

| Servicio | Para qué |
|----------|----------|
| `honcho` | Memoria persistente local |
| `firecrawl` | Web scraping |
| `n8n` | Automatización de workflows |
| `lightrag` | RAG sobre grafos de conocimiento |
| `nocodb` | Base de datos con UI |
| `waha` | WhatsApp HTTP API |

Dentro de Janitor, la skill `janitor-onboarding` guía el resto (Open Design,
escritorio).

## Janitor Desktop

Las releases del fork publican un AppImage `Janitor-<versión>-linux-x86_64.AppImage`
(app de escritorio de Hermes con la identidad Janitor, apuntando a
`~/.janitor`). Descárgalo de la página de releases del fork, dale permiso de
ejecución y ábrelo.

## Actualizar

```bash
janitor update
```

Si una versión futura reestructura `~/.janitor`, el siguiente arranque de
`janitor` lo migra solo, con backup previo en `~/.janitor/.backup/`.

---

## Arquitectura

| Ruta | Contenido |
|------|-----------|
| `janitor/` | Lanzador, flujo de update, migraciones, plugin Hermes, servicios, inventario del fork |
| `janitor/skills/{core,system,projects,research,services,integrations}/` | Skills Janitor (cargadas vía `skills.external_dirs`) |
| `assets/janitor/` | Config, `SOUL.md` y skin `sentry-janitor` de partida |
| `apps/desktop-janitor/` | Overlay de build del escritorio |
| `tests/janitor/` | Suite de tests de Janitor |

El resto del árbol es Hermes. Cada edición en un archivo upstream está
declarada en [`janitor/overlay.yaml`](janitor/overlay.yaml), y
`python -m janitor.overlay check` falla ante cualquier divergencia no declarada.
Así cada release de Hermes se integra con `git merge <tag>` sin perder nada.

## Desarrollo

```bash
uv venv .venv --python 3.11 && source .venv/bin/activate
uv pip install -e ".[all,dev]"
scripts/run_tests.sh tests/janitor/     # suite Janitor
scripts/janitor-sync-verify.sh          # gate completo (overlay + tests + TUI + desktop)
```

- [AGENTS.md](AGENTS.md): directivas del fork y guía de desarrollo de Hermes.
- [MERGE_GUIDE.md](MERGE_GUIDE.md): cómo integrar una release nueva de Hermes.

---

## Licencia

MIT — ver [LICENSE](LICENSE).

**Construido por Reck!** — [@reck74](https://github.com/reck74). Basado en
[Hermes Agent](https://github.com/NousResearch/hermes-agent) de
[Nous Research](https://nousresearch.com).
