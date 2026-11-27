# Fase 2 — Diseño: agentes, plantillas y catálogo de skills

Complementa `janitor-desktop-app.md` (decisión 2.3, tablero de la fase 2).
Diseño producido el 2026-11-22 por un subagente de investigación; el orquestador
lo revisó pero **no repitió las pruebas**. Etiquetas: **[ejecutado]** = se comprobó
corriéndolo en un home temporal, **[leído]** = se comprobó leyendo el código,
**[inferido]** = sin verificar.

## 1. Cómo funciona hoy la activación de skills

- El índice de skills del prompt se arma desde tres sitios: `skills/` del home,
  `skills.external_dirs` y directorios de proyecto de confianza
  (`agent/prompt_builder.py:1262`). **[leído]**
- El mismo filtro aplica a todos: quita lo que esté en `skills.disabled` y
  `platform_disabled` (`agent/skill_utils.py:300-312`). `hermes-agent` no se puede
  desactivar. **[leído]**
- **No existe lista de permitidas**, solo de desactivadas. **[leído]**
- Con `.no-bundled-skills`, `sync_skills` copia solo `hermes-agent`; no hay
  opción por skill (`tools/skills_sync.py:368-376`). **[leído]**
- `hermes skills install` solo cubre `optional-skills/`, no el árbol `skills/`. **[leído]**
- **Una entrada de `skills.external_dirs` puede apuntar al directorio de UNA skill**
  (`<instalación>/skills/productivity/pdf`). La skill aparece en el índice bajo la
  categoría `general`, y respeta `skills.disabled`. **[ejecutado]**
- Una entrada con una variable de entorno sin definir se descarta en silencio. **[ejecutado]**
- Dos perfiles de la misma instalación ven subconjuntos distintos del mismo árbol,
  porque cada perfil tiene su propio `config.yaml`. **[ejecutado]**
- Las skills externas son de solo lectura para `skill_manage` y el curador. **[leído]**

## 2. Mecanismo elegido

Cada perfil lleva en su `config.yaml`:

- `janitor.skills: [ids del catálogo]` — la fuente de verdad de ese agente.
- `skills.external_dirs` — **generado**: una entrada absoluta por skill.

`janitor.catalog.apply(home)` regenera `external_dirs` a partir de
`janitor.skills`; es idempotente y lo ejecutan la siembra, el lanzador y la
actualización (las rutas absolutas cambian si la instalación se mueve).

No se usa `skills.disabled` sobre la raíz `janitor/skills` como mecanismo: no
cubre las skills de upstream y dejaría activa cualquier skill nueva.

## 3. Formatos

`janitor/catalog.yaml`:

```yaml
schema: 1
purposes:
  sistema: "Equipo y sistema"
  documentos: "Documentos y oficina"
  investigacion: "Investigación"
  proyectos: "Proyectos"
  opcional: "Opcionales"
skills:
  - id: pdf
    source: upstream-bundled     # janitor | upstream-bundled | upstream-optional | hub
    path: productivity/pdf       # relativo a skills/ o a janitor/skills/
    purpose: documentos
    templates: [main]
  - id: apple-notes
    source: upstream-bundled
    path: apple/apple-notes
    purpose: opcional
    platforms: [macos]
    templates: []                # el usuario la marca
```

`janitor/templates/<nombre>/template.yaml` más un `SOUL.md` con solo la sección
del rol:

```yaml
name: investigador
display_name: Investigador
description: Investigación con fuentes verificables.
inherit_soul: true               # SOUL principal + sección del rol (directiva 18)
config:
  display: {personality: janitor, skin: sentry-janitor, language: es}
  plugins: {enabled: [janitor]}
skills_from_catalog: true        # entradas del catálogo cuyo `templates` lo incluye
```

## 4. Aprovisionamiento

- **Perfil principal:** `ensure_home` escribe la lista `main` del catálogo en vez
  de toda la raíz `${JANITOR_SKILLS_ROOT}`.
- **Especialista (primero por CLI):** `janitor plantillas list|crear <plantilla> [--nombre]`:
  1. `create_profile(nombre, no_skills=True, …)`.
  2. Fusiona `template.config` en el config del perfil y corre `catalog.apply`.
  3. Escribe `SOUL.md` = SOUL principal + sección del rol.
  4. Copia el skin.
  5. Copia la clave del proveedor al `.env` del perfil (cada perfil resuelve sus
     credenciales por separado; `hermes_cli/env_loader.py:432-434`). **[leído]**
- **No se usa clonar:** `--clone` copia `memories/` y rompe «sin memoria
  compartida». Las distribuciones de perfil reemplazan `config.yaml` entero y no
  admiten rutas relativas a la instalación. **[leído]**
- Sin el paso 2, un perfil nuevo no tiene plugin, skin, idioma ni SOUL de Janitor. **[ejecutado]**

### La app de escritorio, más adelante
El diálogo de crear perfil solo envía `{name, clone_from}`, con `default` por
defecto (clona la memoria); elegir «ninguno» siembra el paquete completo de
skills. **[leído]** Para plantillas en la app hará falta un plugin de escritorio
con su página, o un parche anclado al diálogo en `apps/desktop-janitor/`.

### Delegación
`delegate_task` solo acepta `goal`, `context` y `tasks`; un subagente comparte el
home y el índice de skills del padre (`tools/delegate_tool.py`). **[leído]** No se
le puede dar un conjunto restringido: las skills de investigación van en el
perfil principal, o el trabajo va al perfil Investigador.

## 5. Lista de retiro (un solo cambio)

- **Código:** `janitor/agents.py`; `janitor/opencode/`; el registro de `agents`
  en `janitor/plugin/__init__.py`; `scripts/test_opencode_orchestrator.py` y su
  entrada en `janitor/overlay.yaml`.
- **Skills:** borrar `agents/janitor-code-review-agent/`; de
  `janitor-repo-research-agent/` quitar `agent.yaml` y `system-prompt.md` y mover
  el resto a `research/`; retirar `core/janitor-config-audit`, `core/janitor-core`,
  `integrations/{janitor-browser,janitor-desktop-launcher,janitor-skill-integration}`.
- **Pruebas:** partes de `test_janitor_services.py` y `test_janitor_plugin.py`;
  `test_janitor_config_audit_skill.py` completo.
- **Docs:** `docs/janitor/specialized-agents/`; menciones en `README.md`,
  `AGENTS.md` (directiva 3 y sección de arquitectura) y `janitor-onboarding/SKILL.md`.
- **A decidir por el dueño:** `.claude/agents/janitor-dev-boss-autonomous.md`
  importa `OpenCodeOrchestrator`. *(Retirado el 2026-11-27 en la auditoría de
  pulido, junto con `.opencode/`.)*
- Grupos de skills tras el retiro (directiva 3): `core`, `system` (nuevo),
  `projects` (nuevo), `research` (reemplaza `agents`), `services`, `integrations`.
- La migración v1 arma su lista desde el árbol vivo; al borrar skills deja de ver
  las copias viejas. La migración v2 debe usar una lista congelada de nombres.

## 6. Tareas (alcances disjuntos)

| ID | Tarea | Alcance | Verificación |
|---|---|---|---|
| F2-02 | Catálogo | `janitor/catalog.yaml`, `janitor/catalog.py`, `pyproject.toml` (package-data), `tests/janitor/test_janitor_catalog.py` | Cada entrada resuelve a un `SKILL.md` cuyo `name` es su `id`; el índice de un home temporal es igual a la lista de la plantilla |
| F2-04 | Retiro + reorganización del árbol + migración v2 | Lista de la sección 5, `janitor/skills/**`, `janitor/migrations/v2.py`, `janitor/home.py`, `scripts/migrate-janitor-v2.sh` | `scripts/run_tests.sh tests/janitor/`, `python -m janitor.overlay check` |
| F2-01 | Perfil principal | `janitor/seed.py`, `janitor/cli.py`, `assets/janitor/config.yaml`, `tests/janitor/test_janitor_seed.py` | El índice de un home nuevo es igual a la lista `main` |
| F2-03 | Plantillas + comando | `janitor/templates/**`, `janitor/profile_templates.py`, registro en el plugin, pruebas | Home temporal A→B→A con índices distintos; el SOUL del especialista contiene la persona principal; `memories/` vacío |
| F2-05 | Onboarding reescrito | `janitor/skills/core/janitor-onboarding/SKILL.md` | — |

Orden: F2-02 → F2-04 → F2-01 → F2-03 → F2-05.

## 7. Verificado sobre las skills de upstream

Todas las skills nombradas en la decisión 2.3 existen bajo `skills/` (ninguna en
`optional-skills/`) y declaran Linux. **[ejecutado]** Las de Apple son solo macOS.

## 8. Riesgos

- Las rutas suponen que la instalación contiene el árbol `skills/` de upstream.
- Las skills añadidas por su propio directorio salen bajo `general`, no bajo su categoría.
- Sin verificar: carga del plugin por perfil con el gateway en modo multiperfil.
- Cambiar la lista de skills de una conversación en curso aplica desde la siguiente sesión.
