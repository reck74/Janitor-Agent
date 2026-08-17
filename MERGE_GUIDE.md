# Guía de Merge Upstream para Janitor

> Este documento describe el flujo de trabajo para sincronizar Janitor con los cambios del repositorio upstream `NousResearch/hermes-agent`, preservando la identidad y las extensiones propias de Janitor.

---

## 1. Principios del Fork (Janitor vs. Upstream)

### 1.1 Regla de oro: Zero-Renaming

**NUNCA** hagas buscar-y-reemplazo global de la palabra `hermes` en el core. El motor subyacente se mantiene intacto para garantizar que `git pull upstream main` funcione sin conflictos destructivos.

- ✅ **Sí**: Extender, envolver, inyectar comportamiento vía patrones wrapper.
- ❌ **No**: Renombrar clases, funciones o archivos core de Hermes.

### 1.2 Líneas divisorias

| Capa | Upstream (Hermes) | Janitor (Fork) |
|------|-------------------|----------------|
| **Core** | `cli.py`, `run_agent.py`, `gateway/run.py`, `model_tools.py` | **Inmutable** — solo se mergea, no se edita |
| **CLI wrapper** | `cli.py` (base) | `janitor_cli.py` (extensiones heredadas de `HermesCLI`) |
| **Skills** | `skills/*` (oficiales) | `skills/janitor-*/` (skills propios) |
| **TUI branding** | Componentes base Ink | `branding.tsx`, skins (`sentry-janitor.yaml`) |
| **Instalador** | `scripts/bootstrap.sh` | `scripts/janitor-install.sh`, `setup-honcho.sh` |
| **Configuración** | `config.yaml` (estructura) | Valores por defecto (`assets/janitor/config.yaml`) |

---

## 2. Flujo de Merge

### 2.1 Preparación

```bash
# Asegúrate de tener el remoto upstream configurado
git remote add upstream ssh://git@github.com/NousResearch/hermes-agent.git 2>/dev/null || true

# Fetch del tag exacto v2026.8.13 (no upstream/main; los commits entre el tag
# y main pueden romper los gates Janitor sin que tengamos visibilidad).
git fetch origin main
git fetch upstream tag v2026.8.13

# Verifica cuántos commits faltan desde el tag
git log --oneline HEAD..v2026.8.13
```

> **Estrategia:** resolver cada path en conflicto individualmente según su
> categoría (§3). Prohibido usar `-X theirs` o `-X ours` globalmente —
> borra silenciosamente personalizaciones Janitor dentro de archivos upstream
> sin levantar conflicto de 3 vías (precedente: wholesale adoption
> `607078d2c` borró toda la zona Telegram). El merge se ejecuta siempre con
> `git merge v2026.8.13 --no-edit` (default 3-way).

### 2.2 Checklist previo al merge

- [ ] `git status` limpio (sin cambios sin commitear)
- [ ] Stash de cambios locales temporales si es necesario
- [ ] Eliminar archivos de continuación de Sisyphus: `rm -f .sisyphus/run-continuation/*.json`

### 2.3 Ejecución del merge

```bash
# Merge directo contra el tag exacto (crea un commit de merge)
git merge v2026.8.13 --no-edit

# Si hay conflictos, resuelve manualmente antes de continuar
```

---

## 3. Resolución de Conflictos por Categoría

### 3.1 Workflows de GitHub (`.github/workflows/`)

**Situación**: Upstream modifica workflows que Janitor eliminó o reemplazó.

**Solución**:
```bash
# Elimina todos los workflows en conflicto (modificados por upstream, eliminados por Janitor)
git rm -f .github/workflows/*.yml 2>/dev/null || true

# Restaura los workflows nativos de Janitor si existían en HEAD
git checkout HEAD -- .github/workflows/
```

**Regla**: Janitor mantiene sus propios workflows (`janitor-ci.yml`, `upstream-sync.yml`). Nunca adoptar workflows de upstream sin revisar.

### 3.2 Branding / Identidad Visual

**Archivos típicamente en conflicto**:
- `ui-tui/src/components/branding.tsx`
- `hermes_cli/main.py` (funciones de versión)
- `README.md`

> **Telegram:** el path activo es `plugins/platforms/telegram/adapter.py`.
> La ubicación histórica `gateway/platforms/telegram.py` ya no es el
> target desde el refactor upstream a plugins/platforms — los símbolos
> Janitor (`_set_janitor_avatar`, `_handle_start`) viven ahora en el
> adapter. Ver §11 para el inventario histórico.

**Reglas de resolución**:

1. **TUI (`branding.tsx`)**:
   - Adopta la lógica responsiva de upstream (`wide ? ... : ...`)
   - Reemplaza texto hardcoded de upstream (`Nous Research`, `Messenger of the Digital Gods`) con variables del tema Janitor (`t.brand.name`, `t.brand.icon`, `t.brand.version`)
   - No uses constantes string hardcoded; usa helpers dinámicos:
     ```typescript
     const brandTagFull = (t: Theme) => `${t.brand.name} · DevSecOps Orchestrator`
     ```

2. **CLI (`main.py`)**:
   - Adopta funciones helper de upstream (ej. `_print_version_info()`)
   - Cambia strings de versión a `THE JANITOR`:
     ```python
     print(f"THE JANITOR v{__version__} ({__release_date__})")
     ```

3. **README**:
   - Preserva la estructura de upstream si mejora la documentación
   - Mantén el contrato del instalador mínimo + skills opcionales
   - Docker, Honcho, Firecrawl son **skills opcionales**, no requisitos base

### 3.3 Scripts de Instalación (`scripts/setup-stack.sh`)

**Reglas**:
- Elimina cualquier referencia a GHCR (`ghcr.io`, `check_ghcr_auth`) — Janitor compila Honcho desde fuente
- Corrige problemas de `set -e` que bypass error handling:
  ```bash
  # ❌ Mal (set -e sale antes del if)
  DOCKER_OUTPUT=$(docker info 2>&1)
  if [ $? -ne 0 ]; then ...

  # ✅ Bien
  if ! DOCKER_OUTPUT=$(docker info 2>&1); then ...
  ```

---

## 4. Validación Post-Merge (Gates Obligatorios)

### 4.1 Checklist de validación

- [ ] **Shell syntax**: `bash -n scripts/setup-stack.sh`
- [ ] **Python syntax**: `python3 -m py_compile hermes_cli/main.py gateway/run.py`
- [ ] **Conflict markers**: escanear archivos resueltos por `<<<<<<<`, `=======`, `>>>>>>>`
- [ ] **Branding sanitization**: verificar que no queden strings de upstream (`Nous Research`, `Messenger of the Digital Gods`, `Hermes Agent v`)
- [ ] **GHCR purge**: verificar que no queden `check_ghcr_auth` ni `ghcr.io` en scripts
- [ ] **Git status**: `git status --short` debe estar limpio (sin untracked de `.sisyphus/run-continuation/`)
- [ ] **Janitor dependency pins intactos**: verificar que ningún merge revirtió pins requeridos por features Janitor — ver §4.4 para la lista canónica y comandos de validación
- [ ] **Monkey-patch signatures (directiva #14)**: `janitor_cli.py` monkey-patchea funciones upstream. Si upstream cambió la firma de alguna, el wrapper se rompe en runtime. Validación automática: `python -m pytest tests/test_janitor_monkeypatch_signatures.py -v`. Si falla, actualizar la firma del wrapper en `janitor_cli.py` para calzar con la firma upstream actual — NO debilitar el test. Ver §4.5 para el procedimiento de auditoría manual.
- [ ] **Duplicate method audit (directiva #15)**: un merge `-X theirs` puede dejar dos definiciones del mismo método en un archivo core (una del fork, otra de upstream) en zonas no conflictivas del archivo. Python "last definition wins" silenciosamente pisa la primera con la segunda — puede cambiar un método de `async` a `sync` mientras los callers siguen usando `await`, produciendo `TypeError: object NoneType can't be used in 'await' expression` en runtime. Validación automática: `python -m pytest tests/test_janitor_no_duplicate_methods.py -v`. Si falla, identificar cuál definición es la correcta (usualmente la del fork Janitor, con la lógica más completa) y borrar la otra — NO debilitar el test. Ver §4.6 para el procedimiento de auditoría manual.
- [ ] **Web dashboard gate**: si el sync toca `web/`, `hermes_cli/main.py`, `hermes_cli/web_server.py`, `package.json`, `package-lock.json` o workflows JS, ejecutar el gate completo de §4.7 y verificar que `janitor-ci.yml` sobrevive la poda de `upstream-sync.yml`.

### 4.2 Gates del TUI (obligatorios si se toca `ui-tui/`)

```bash
cd ui-tui
npm run type-check
npm run build --prefix packages/hermes-ink
npm run build
npm test
```

**Criterios de aprobación**:
- `npm run type-check`: 0 errores de TypeScript
- `npm run build`: exit code 0, genera `dist/entry.js`
- `npm test`: 0 tests fallidos (skips aceptables)

### 4.3 Compilación rápida de Python

```bash
python3 -m py_compile cli.py run_agent.py gateway/run.py
```

### 4.4 Pins de dependencias requeridos por features Janitor

Ciertos pins en `pyproject.toml` no son negociables porque el código Janitor
asume APIs que solo existen en versiones mínimas específicas. Un sync upstream
con `-X theirs` puede revertirlos silenciosamente, dejando la lógica Python
intacta pero el comportamiento roto en runtime (los mocks de tests no detectan
el problema). Esta sección es la lista canónica.

| Pin | Razón | Símbolo / archivo Janitor que lo requiere |
|---|---|---|
| `python-telegram-bot[webhooks]>=22.7,<23` (en extras `messaging` y `termux`) | `set_my_profile_photo` / `remove_my_profile_photo` solo disponibles desde PTB 22.7 | `gateway/platforms/telegram.py:_set_janitor_avatar()` |

**Comando de validación** (incluir en todo `chore(sync):` post-merge):

```bash
# Debe retornar exactamente 2 matches (messaging + termux)
grep -E 'python-telegram-bot\[webhooks\]>=22\.7' pyproject.toml | wc -l

# Validación completa de runtime: la versión resuelta en uv.lock debe ser >= 22.7
grep -A1 'name = "python-telegram-bot"$' uv.lock | grep version
# Salida esperada (o cualquier 22.x >= 22.7):
#   version = "22.8"
```

**One-liner fail-fast** (retorna exit 0 si está bien, 1 si falta el pin):

```bash
(
  [ "$(grep -cE 'python-telegram-bot\[webhooks\]>=22\.7' pyproject.toml)" = "2" ] && \
  uv lock --check && \
  python3 -c "import tomllib, re; d=tomllib.loads(open('pyproject.toml').read())['project']['optional-dependencies']; assert any('>=22.7' in x for x in d.get('messaging', [])), 'messaging pin missing'; assert any('>=22.7' in x for x in d.get('termux', [])), 'termux pin missing'; print('Janitor pins: OK')" \
) || echo "Janitor pins: FAIL — restore with: git show <fix-commit> -- pyproject.toml uv.lock | git apply"
```

**Origen del riesgo** (jun 2026): el cherry-pick `ab83b15f7` revirtió el pin
`>=22.7,<23` → `==22.6` durante un wholesale adoption. El fix de T5b.3
(`91a891618`) restauró el código Python pero pasó por alto el pin, dejando
el bug dormido hasta el siguiente arranque del bot en runtime. Este guardrail
existe para que el próximo `chore(sync):` no repita la regresión.

**Si falla**: NO cambiar el código Python para que coincida con la versión
antigua — eso es deuda técnica. Restaurar el pin correcto:

```bash
# Pin de referencia
git show fa2b7d8a5 -- pyproject.toml | grep "python-telegram-bot" | head -2
# Regenerar lock
uv lock
# Validar
scripts/run_tests.sh tests/gateway/test_telegram_janitor_branding.py
```

### 4.5 Auditoría de firmas de monkey-patches (directiva #14)

`janitor_cli.py` monkey-patchea funciones upstream en tiempo de importación. Si
un sync upstream cambia la firma de una función parchada (añade/remueve
parámetros), `-X theirs` adopta el caller nuevo y el callee nuevo, pero nunca
tocan `janitor_cli.py` (archivo del fork), así que el wrapper conserva la firma
vieja y crashea en runtime con `TypeError`.

**Esto ya pasó** (sync v2026.7.7.2, PR #44): upstream añadió `context_length` a
`prompt_builder.load_soul_md` y cambió `system_prompt.py:186` para pasarlo. El
wrapper `_janitor_load_soul_md` seguía con cero argumentos.

**Validación automática** (incluida en todo `chore(sync):` post-merge):

```bash
python -m pytest tests/test_janitor_monkeypatch_signatures.py -v
```

**Auditoría manual** (para descubrir nuevos parches que el test aún no cubre):

```bash
# Listar todas las asignaciones de monkey-patch en janitor_cli.py
grep -nE '^\w+\.\w+ = _janitor_|ArgumentParser\.__init__ = ' janitor_cli.py

# Para cada parche encontrado, comparar la firma del wrapper vs el original:
python3 -c "
import inspect, janitor_cli
from agent import prompt_builder
orig = inspect.signature(janitor_cli._original_load_soul_md)
wrap = inspect.signature(prompt_builder.load_soul_md)
print('Original:', orig)
print('Wrapper:', wrap)
assert set(orig.parameters) <= set(wrap.parameters), 'Wrapper missing params!'
print('OK')
"
```

**Si el test falla**: actualizar la firma del wrapper en `janitor_cli.py` para
calzar con la firma upstream actual. NO debilitar el test — es la única barrera
automatizada contra este bug. Ver directiva #14 en `AGENTS.md`.

### 4.6 Auditoría de métodos duplicados (directiva #15)

Un merge `-X theirs` resuelve conflictos textuales a favor de upstream, pero
cuando tanto el fork Janitor como upstream añaden un método con el mismo
nombre a la misma clase en distintas zonas del archivo (zonas no
conflictivas), **ambas definiciones sobreviven**. Python aplica "last
definition wins": la segunda definición pisa silenciosamente a la primera.
Si una es `async` y la otra `sync`, los callers que usan `await` crashean
con `TypeError: object NoneType can't be used in 'await' expression`.

**Esto ya pasó** (sync v2026.7.7.2, merge `83d4f8d62`): el fork tenía
`async def _refresh_agent_cache_message_count` en `gateway/run.py:16134`
(commits `3bc4a2ff7`, `aa4731598`, `b4cacba6a`) y upstream añadió una
versión `def` (sync) en `gateway/run.py:16209`. La versión sync pisó a la
async, y cada mensaje de Telegram crasheó **después** de generar la
respuesta correcta — el gateway descartaba la respuesta y enviaba el
mensaje de error genérico.

**Validación automática** (incluida en todo `chore(sync):` post-merge):

```bash
python -m pytest tests/test_janitor_no_duplicate_methods.py -v
```

**Auditoría manual** (para descubrir duplicados que el test aún no cubre
o para archivos fuera de la lista `_SCANNED_FILES`):

```bash
# Detectar métodos duplicados en un archivo core específico vía AST.
# Excluye pares @property/@.setter (intencionales). Retorna líneas
# donde hay >1 definición del mismo método en la misma clase.
python3 -c "
import ast, sys
path = sys.argv[1]
tree = ast.parse(open(path).read())
def deco_name(d):
    if isinstance(d, ast.Name): return d.id
    if isinstance(d, ast.Attribute):
        parts=[]; c=d
        while isinstance(c, ast.Attribute): parts.append(c.attr); c=c.value
        if isinstance(c, ast.Name): parts.append(c.id)
        return '.'.join(reversed(parts))
    return ''
def is_prop(n):
    ds={deco_name(x) for x in n.decorator_list}
    return 'property' in ds or 'cached_property' in ds or any(x.endswith(('.setter','.deleter','.getter')) for x in ds)
seen={}
for node in ast.walk(tree):
    if not isinstance(node, ast.ClassDef): continue
    for c in node.body:
        if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef)) and not is_prop(c):
            seen.setdefault((node.name,c.name),[]).append((c.lineno,'async' if isinstance(c,ast.AsyncFunctionDef) else 'sync'))
for (cls,mth),locs in seen.items():
    if len(locs)>1:
        print(f'{cls}.{mth}: {locs}')
" gateway/run.py
```

**Si el test falla**: identificar cuál definición es la correcta
——usualmente la del fork Janitor, que tiene la lógica más completa (por
ejemplo, manejo de 4-tuple cache entries en `_refresh_agent_cache_message_count`)
——y borrar la otra. Si se conserva la versión sync, eliminar también el
`await` de los callers. Si se conserva la async, asegurar que las llamadas
a métodos ahora-sync (como `SessionDB.get_session`) usen `asyncio.to_thread`.
NO debilitar el test. Ver directiva #15 en `AGENTS.md`.

### 4.7 Gate del dashboard web

Este gate es obligatorio cuando un sync toca `web/`, el arranque/servido del
dashboard, metadata npm raíz o workflows relacionados. `npm run typecheck`
debe atravesar las project references; un exit 0 vacío no es evidencia.

```bash
npm run typecheck --workspace web
npm run check --workspace web
npm run build --workspace web
test -f hermes_cli/web_dist/index.html
```

Después de compilar, validar el camino real on-demand en loopback:

```bash
janitor dashboard --host 127.0.0.1 --port 9119 --no-open
janitor dashboard --status
janitor dashboard --stop
```

Antes de aprobar el sync, el job `Janitor CI / web-tests` debe estar verde y
`.github/workflows/upstream-sync.yml` debe preservar explícitamente
`janitor-ci.yml`, `tests.yml` y `upstream-sync.yml`. `hermes_cli/web_dist/` es
salida ignorada de build; no se añade al commit.

---

## 5. Commit del Merge

### 5.1 Mensaje del commit de merge

```
chore(merge): resolve upstream conflicts and purge obsolete GHCR check
```

### 5.2 Si hay fixes post-review

Si los agentes de review encuentran bloqueos, crear commits atómicos separados:

```
fix(branding): remove upstream identity leaks
fix(installer): align legacy stack guidance
fix(tui): resolve merge compilation blockers
```

**Nunca** mezclar fixes de branding con fixes de installer en el mismo commit.

---

## 6. Verificación Final con Agentes

Tras completar el merge y sus fixes, lanzar los 5 agentes de review en paralelo:

1. **Goal & Constraint Verification** (oracle): ¿Se cumplió el objetivo del merge?
2. **QA Execution** (unspecified-high): ¿Pasan las validaciones manuales?
3. **Code Quality Review** (oracle): ¿Es mantenible y consistente?
4. **Security Audit** (oracle): ¿Hay riesgos de seguridad?
5. **Context Mining** (unspecified-high): ¿Faltó contexto relevante?

**Todos deben dar PASS** antes de considerar el merge finalizado.

---

## 7. Troubleshooting

### 7.1 El TUI no compila después del merge

**Síntoma**: `npm run type-check` falla con errores de tipo en archivos que no tocaste.

**Causa probable**: Upstream cambió la firma de funciones en `@hermes/ink` y el paquete no está recompilado.

**Solución**:
```bash
npm run build --prefix packages/hermes-ink  # Recompila las exportaciones
npm run type-check                           # Ahora debería pasar
```

### 7.2 Tests del TUI fallan con `wrapAnsi is not a function`

**Causa**: El build de `packages/hermes-ink` generó un export inválido o el test usa un mock incompleto.

**Solución**: Revisar `ui-tui/packages/hermes-ink/src/ink/wrapAnsi.ts` y asegurar que exporta correctamente; recompilar.

### 7.3 Conflictos recurrentes en `branding.tsx`

**Prevención**: Si upstream actualiza frecuentemente el banner, considera crear un patch file o un script de post-merge que verifique automáticamente que `TAG_FULL` no re-aparezca.

---

## 8. Anexo: Referencia Rápida de Comandos

```bash
# Fetch y ver diferencias
git fetch upstream main
git log --oneline HEAD..upstream/main

# Merge
git merge upstream/main --no-edit

# Validación rápida
bash -n scripts/setup-stack.sh
python3 -m py_compile hermes_cli/main.py
grep -rn 'Nous Research\|Messenger of the Digital Gods\|Hermes Agent v' ui-tui/src/components/branding.tsx hermes_cli/main.py
grep -rn 'check_ghcr_auth\|ghcr.io' scripts/setup-stack.sh

# TUI gates
cd ui-tui && npm run type-check && npm run build --prefix packages/hermes-ink && npm run build && npm test

# Estado final
git status --short

---

### 3.X Re-apply test-assertion branding after any upstream sync

Per AGENTS.md fork directive #12 (TEST ASSERTION BRANDING), any test file that newly contains the upstream-original string `Hermes Agent` (or `Hermes Agent v`) in a banner / `--version` assertion must be updated to `THE JANITOR` (or `THE JANITOR v`) in the same commit that re-applies the branding. Run this grep after the merge to find any drift; the result must be `0 matches`:

```bash
git grep -nE '"Hermes Agent"|"Hermes Agent v"' -- tests/ -- ':!*.pyc' ':!docs/superpowers/'
```

If any matches are found, update the assertion in the same commit and add the inline comment block pointing back to AGENTS.md rule #12 (the comment template lives in `docs/superpowers/specs/2026-06-10-migrate-specialized-agents-to-kanban-profiles-design.md`, "Baseline assertion drift" section).

---

*Última actualización: Mayo 2026*

---

## v2026.6.5 Sync (Hermes v0.16.0)

**Rango:** `1a710e8df` → `2a14e8957` (1,607 commits, 996 files, +80,859 / -26,205 líneas)
**Fecha:** 2026-06-15
**Estrategia:** Full merge con `git merge -X theirs upstream/main --no-commit` + restauración manual de archivos Janitor-only desde `HEAD` + re-aplicación de branding

### Cambios adoptados

**7 parches de seguridad críticos:**
- `da28d5d11` — SSH/credential gate en `cp`/`mv`/`install`
- `972a9885e` — Bloqueo de exfil en MCP stdio configs
- `fc4635458` — Gateway fail-closed en own-policy adapters
- `3380563d9` — `/api/status` host-leak fix
- `a218a0f15` + `af5b52647` — SSL CA bundle fail-fast guard
- `bd66e7e3f` — Codex OAuth refresh_token self-heal
- `7a1eed826` — Anthropic replay redaction

**Módulos nuevos adoptados:**
- `agent/coding_context.py` (738 líneas)
- `agent/ssl_guard.py` + `agent/anthropic_adapter.py`
- `agent/transports/{anthropic,chat_completions,codex,types}.py`
- `cron/blueprint_catalog.py` (713 líneas)
- `gateway/platforms/whatsapp_cloud.py` (1956 líneas)
- `hermes_cli/mcp_security.py` (nuevo módulo seguridad)
- `hermes_cli/blueprint_cmd.py`, `model_cost_guard.py`, `setup_whatsapp_cloud.py`, `suggestions_cmd.py`, `write_approval_commands.py`
- `tools/blueprints.py`, `read_extract.py`, `read_terminal_tool.py`, `write_approval.py`

**Plataformas nuevas:** `photon`, `simplex`, `teams`, `whatsapp_cloud`

**Providers nuevos:** `zai` (GLM-5.2), `langfuse` observability

**Skills nuevos adoptados (11):** 5 github + 4 productivity + 2 media + 1 research + 1 note-taking (ver `skills/` post-merge)

**Config v11→v12 + breaking change:**
- `memory.write_mode` / `skills.write_mode` (tri-state) → `write_approval` (boolean, default false)
- `_config_version`: 28 → 29
- Slash commands: `/memory mode <on|off|approve>` → `/memory approval <on|off>` (mode queda como alias)

**God-file refactor:** cli.py y gateway/run.py (Phase 2/3) — módulos extraídos a `hermes_cli/subcommands/`, `gateway/*_mixin.py`

### Cambios descartados

- **1,495 archivos de tests upstream** en `tests/` (per directiva #11)
  - El job `upstream-sync-verify` corre la suite completa contra el código post-merge en `workflow_dispatch` y en pushes a `main` con commits `chore(sync):` / `fix(sync):`
  - **Preservados**: 5 tests Janitor-specific + 3 archivos comunes (`__init__.py`, `conftest.py`) + 114 tests Electron del subtree `apps/desktop/electron/*.test.cjs`

- **32 commits de `chore(release): map <author>`** (bookkeeping upstream irrelevante)
- **`apps/desktop/` subtree Electron** traído pero NO publicado (per directivas #4 + #8). El instalador base sigue sin incluirlo.

### Fixes aplicados durante el merge

1. `scripts/run_tests_parallel.py`: removida definición duplicada de `--slice` (regresión upstream en su propio merge de god-file phase)
2. `pyproject.toml`: restaurados `janitor_cli`, `janitor_update_bootstrap`, `janitor_update_core` en `py-modules` (necesario para directiva #13)
3. Branding re-aplicado: `hermes_cli/main.py:231` y `hermes_cli/banner.py:478` ahora dicen `THE JANITOR v{VERSION} ({RELEASE_DATE})`

### Post-merge para usuarios existentes

```bash
# Si tenías una config v0.15.x con write_mode, migrar:
bash scripts/migrate-janitor-v0.16.0.sh

# Verificar que la versión es correcta:
janitor --version
# Expected: THE JANITOR v0.16.0 (...)
```

### Branding
- `THE JANITOR` preservado en `hermes_cli/main.py:231` y `hermes_cli/banner.py:478`
- Re-aplicado automáticamente durante el merge

### CI
- `tests.yml` sigue podado a 5 tests Janitor-specific
- `upstream-sync.yml` presente (job `upstream-sync-verify`)
- `janitor-ci.yml` presente
- `supply-chain-audit.yml` y `typecheck.yml` aceptados
- 19 workflows en total (vs 18 upstream-only)

---

## 9. Customizaciones Desktop — Asset Replacement (`apps/desktop/public/`)

> Las personalizaciones visuales de la app desktop siguen un enfoque **puramente
> binario**: reemplazar assets upstream con sus contrapartes Janitor. Cero
> código React/CSS/TS tocado. Trade-off: cualquier cambio upstream a esos
> archivos requiere re-aplicar el reemplazo (conflicto trivial esperado).

### 9.1 Archivos reemplazados (3 upstream binary swaps)

| Path upstream | Tamaño antes → después | Asset Janitor | Uso upstream |
|---|---|---|---|
| `apps/desktop/public/ds-assets/filler-bg0.jpg` | 3.8 MB → 766 KB | `j4nitor-agent-logo-transparent.png` (wireframe) | `<img>` en `src/components/Backdrop.tsx:103` — fondo del empty view |
| `apps/desktop/public/nous-girl.jpg` | 20 KB → 1.3 MB | `j4nitor-monogram.png` (wireframe) | `<img>` en `src/components/brand-mark.tsx:16` — Settings/About + Updates overlay |
| `apps/desktop/public/apple-touch-icon.png` | 541 KB → 1.3 MB | `j4nitor-monogram.png` (wireframe) | favicon (`index.html:7-9`) + Dock/Taskbar icon (`electron/main.cjs:339-343` via `APP_ICON_PATHS`) |

### 9.2 Archivos NO modificados (intencional)

| Path | Razón |
|---|---|
| `apps/desktop/public/hermes.png` | Sin referencia en `src/` (graph confirma 0 usos). Mantenido como reliquia upstream. |
| `apps/desktop/public/hermes-sprite.png` | Sin referencia en `src/`. Mantenido. |
| `apps/desktop/public/hermes-frames/hermes-frame-{0..7}.png` | Sin referencia en `src/`. Mantenidos. |
| `apps/desktop/src/components/chat/intro.tsx` (wordmark + tagline) | Renderiza texto React con `<p>{WORDMARK}</p>`. **No es un asset binario**. Reemplazar este archivo requiere upstream modification o componente React override (próxima iteración). |
| `apps/desktop/index.html:11` (`<title>Hermes</title>`) | Texto en HTML, no binario. Próxima iteración. |
| `apps/desktop/assets/icon.{icns,ico,png}` | Build-time Electron icons. Reemplazo va via electron-builder config externo (`apps/desktop/electron-builder.janitor.json`) — próxima iteración. |

### 9.3 Riesgo conocido — MIME mismatch

Los assets wireframe source son **PNG**, pero el path upstream exige extensión
`.jpg` para 2 de los 3 archivos. El reemplazo conserva el filename upstream:

| Archivo | Contenido real | Extensión | MIME servido |
|---|---|---|---|
| `filler-bg0.jpg` | PNG (1942×809 RGBA) | `.jpg` | `image/jpeg` por Vite |
| `nous-girl.jpg` | PNG (1254×1254 RGB) | `.jpg` | `image/jpeg` por Vite |
| `apple-touch-icon.png` | PNG (1254×1254 RGB) | `.png` | `image/png` (sin riesgo) |

**Mitigación Chromium (Electron renderer)**: content-sniffing debería detectar
el contenido real y renderizar OK. Si el render local muestra cuadros rotos,
el fix es renombrar upstream a `.png` + actualizar el path en `Backdrop.tsx:103`
(de upstream modification menor).

### 9.4 Conflictos esperados al `git pull upstream main`

| Archivo | Riesgo | Mitigación |
|---|---|---|
| `apps/desktop/public/ds-assets/filler-bg0.jpg` | **Alto** — upstream puede actualizar el fondo (animaciones, nuevos productos) | Aceptar upstream, re-aplicar el reemplazo Janitor |
| `apps/desktop/public/nous-girl.jpg` | **Medio** — asset visualmente estable, upstream raramente lo cambia | Mismo |
| `apps/desktop/public/apple-touch-icon.png` | **Medio** — idem | Mismo |
| `apps/desktop/src/components/Backdrop.tsx` | CERO | No tocado |
| `apps/desktop/src/components/brand-mark.tsx` | CERO | No tocado |
| `apps/desktop/index.html` | CERO | No tocado |
| Código React/TS/CSS upstream | CERO | Este commit no toca código fuente |

### 9.5 Verificación post-merge

```bash
cd apps/desktop
npm run typecheck      # sin errores esperados (no tocamos código)
npm run test:desktop:platforms  # 18 tests electron, no afectados
# Visual: npm run dev → verificar BrandMark, fondo, favicon
```

### 9.6 Próximas iteraciones (no incluidas)

- **Wordmark + tagline**: requieren componente React o upstream modification en `intro.tsx:145,21-42,117-138`.
- **Window title** (`index.html:11`): cambio trivial upstream, 1 línea.
- **Sidebar top-left brand**: no existe upstream, requiere nuevo componente React.
- **Build-time icons** (`apps/desktop/assets/icon.{icns,ico,png}`): requieren electron-builder config externo + regenerar `.icns`/`.ico` desde PNG fuente.

### 9.7 Pre-flight checklist antes de PR de branding

Antes de cualquier PR que toque `apps/desktop/public/`:

- [ ] `npm run dev` local muestra el render esperado (BrandMark, fondo, favicon)
- [ ] `vite build` OK sin warnings de MIME/asset resolution
- [ ] `git diff --stat` solo toca `apps/desktop/public/*` + (opcional) `.gitignore`
- [ ] Screenshot de Settings → About + Updates overlay + ventana maximizada con fondo visible

---

## 10. Stale CI Config — Actualización post-sync de `janitor-ci.yml`

> **Lección aprendida:** El sync upstream (`607078d2c`, v0.16.0) eliminó/renombró
> archivos referenciados por `janitor-ci.yml`, pero el workflow no se actualizó
> en el mismo commit. Resultado: ambos jobs (`python-tests` y `react-tests`)
> fallaban en CI sin que el código tuviera bugs reales.

### 10.1 Síntomas

- `python-tests` job falla con `ERROR: file or directory not found: tests/hermes_cli/test_skin_engine.py`
- `react-tests` job falla con `npm error Missing script: "type-check"`
- Los tests pasan localmente cuando se ejecutan manualmente con los nombres correctos

### 10.2 Causa raíz

El commit de sync upstream puede **eliminar, mover o renombrar** archivos que
`janitor-ci.yml` referencia directamente. El sync es un merge masivo (~1600
commits, ~1000 archivos) y `janitor-ci.yml` es un archivo Janitor-only que el
sync no toca — pero sus **referencias** apuntan a archivos que sí cambiaron.

| Referencia en `janitor-ci.yml` | Qué pasó en el sync | Fix aplicado |
|---|---|---|
| `tests/hermes_cli/test_skin_engine.py` | Eliminado por upstream (reestructuración de tests) | Reemplazado con `tests/test_janitor_update_core.py` |
| `npm run type-check` | Script renombrado a `typecheck` (sin guion) en `ui-tui/package.json` | Actualizado a `npm run typecheck` |

### 10.3 Checklist post-sync obligatorio para `janitor-ci.yml`

Después de **cualquier** `git merge upstream/main` (o `chore(sync):` commit),
verificar estas 3 referencias antes de pushear:

```bash
# 1. Los archivos de test referenciados existen
grep -E 'python -m pytest' .github/workflows/janitor-ci.yml | \
  grep -oE 'tests/\S+\.py' | \
  while read f; do test -f "$f" && echo "OK: $f" || echo "MISSING: $f"; done

# 2. Los scripts de npm referenciados existen en package.json
grep -E 'npm run ' .github/workflows/janitor-ci.yml | \
  grep -oE 'npm run \S+' | \
  while read script; do
    name=$(echo "$script" | sed 's/npm run //')
    node -e "const p=require('./ui-tui/package.json'); \
      p.scripts['$name'] ? console.log('OK: $name') : console.log('MISSING: $name')"
  done

# 3. La versión de actions/checkout es consistente con el resto de workflows
grep 'actions/checkout@' .github/workflows/janitor-ci.yml
```

Si cualquier línea dice `MISSING:`, corregir `janitor-ci.yml` en el mismo
commit del sync (o en un commit `fix(ci):` inmediatamente después) antes
de abrir el PR.

### 10.4 Prevención — añadir al checklist de validación post-merge (§4.1)

Añadir estos ítems al checklist de la sección 4.1 después de cada sync:

- [ ] **CI refs válidos**: `janitor-ci.yml` no referencia archivos eliminados ni scripts renombrados (ver §10.3)
- [ ] **CI jobs verificados**: ejecutar localmente los 2 jobs de `janitor-ci.yml` antes de pushear

### 10.5 Archivos Janitor-only que el sync NO protege

`janitor-ci.yml` es un archivo Janitor-only — el sync upstream no lo toca ni
lo valida. Cualquier referencia que apunte a código upstream (tests, scripts
de npm, paths de build) es **frágil** y debe verificarse después de cada sync.

Archivos Janitor-only que dependen de estructura upstream:

| Archivo Janitor | Dependencia upstream | Riesgo |
|---|---|---|
| `.github/workflows/janitor-ci.yml` | Tests files, npm scripts | **Alto** — se rompe en cada sync que reestructura tests o renombra scripts |
| `.github/workflows/tests.yml` | Tests files (5 Janitor-specific) | **Medio** — los tests Janitor-specific son estables, pero nombres de archivos pueden cambiar |
| `janitor_cli.py` | `HermesCLI` class en `cli.py` | **Bajo** — la interfaz pública es estable |

### 10.6 Fix aplicado en este commit

```
fix(ci): update janitor-ci.yml references after upstream sync

- Replace deleted tests/hermes_cli/test_skin_engine.py with
  tests/test_janitor_update_core.py (skin_engine test was removed
  by upstream sync commit 607078d2c)
- Fix npm run type-check → npm run typecheck (script renamed in
  upstream sync)
- Document stale CI config issue in MERGE_GUIDE.md §10

Both CI jobs now pass locally:
- python-tests: 29 passed
- react-tests: 1026 passed, 2 skipped
```

---

## 11. Telegram Core Customization (`gateway/platforms/telegram.py`)

> **Lección aprendida:** El sync upstream vía wholesale adoption (T2.1,
> commit `607078d2c`) eliminó **todas** las personalizaciones Janitor de
> Telegram al sobreescribir `gateway/platforms/telegram.py` con la versión
> upstream. El fix de re-aplicación (`91a891618`) tuvo que restaurar 6
> piezas de código + 5 constantes + 1 import + 1 handler + 1 call site.
> Las personalizaciones **no sobreviven** a un merge masivo si no se
> documentan como zona de conflicto explícita.

### 11.1 Inventario de personalizaciones Janitor en `telegram.py`

Todas las adiciones son **puramente aditivas** (cumple directiva #1
ZERO-RENAMING y directiva #4 TUI ISOLATION — no se renombra nada de
upstream, solo se inyecta comportamiento):

| Símbolo | Tipo | Ubicación | Qué hace |
|---|---|---|---|
| `_JANITOR_ASSETS_DIR` | Constante módulo | línea 116 | `Path(__file__).resolve().parents[2] / "assets" / "janitor"` |
| `_JANITOR_AVATAR_PATH` | Constante módulo | línea 117 | Apunta a `assets/janitor/janitor_avatar.png` (uso general) |
| `_JANITOR_TELEGRAM_AVATAR_PATH` | Constante módulo | línea 118 | Apunta a `assets/janitor/janitor_avatar_telegram.jpg` (uso Telegram) |
| `_JANITOR_WELCOME_PATH` | Constante módulo | línea 119 | Apunta a `assets/janitor/telegram_welcome.jpg` |
| `_JANITOR_WELCOME_TEXT` | Constante módulo | línea 120 | Texto de bienvenida en español (menciona `/topic`) |
| `InputProfilePhotoStatic` (try/except) | Import | líneas 31, 33, 53 | Necesario para PTB ≥ 22.7; los mocks de test lo parchean en ambas ramas |
| `_set_janitor_avatar()` | Método async | líneas 1872-1926 | Quita el profile photo actual del bot y sube el JPG Janitor vía `set_my_profile_photo` (PTB ≥ 22.7) con fallback `do_api_request("removeMyProfilePhoto")` |
| `await self._set_janitor_avatar()` | Call site | línea 2077 dentro de `connect()` | **Punto de inyección único** — se ejecuta después de `_app.initialize()` |
| `self._app.add_handler(CommandHandler("start", self._handle_start))` | Handler registration | línea 2052 | Registra el comando `/start` que envía la imagen de bienvenida |
| `_handle_start()` | Método async | líneas 5874-5906 | Envía `telegram_welcome.jpg` con caption `_JANITOR_WELCOME_TEXT`; fallback a texto si falta el asset |

### 11.2 Assets aislados (NO se modifican en merges)

Estos archivos viven en `assets/janitor/` y **no son parte de upstream**.
Un merge no debe tocarlos (no aparecen en el árbol de upstream):

| Archivo | Tamaño | Uso | Test |
|---|---|---|---|
| `assets/janitor/janitor_avatar_telegram.jpg` | ~36 KB | Profile photo del bot (set on every connect) | `test_telegram_avatar_asset_is_jpeg` verifica magic bytes JPEG |
| `assets/janitor/telegram_welcome.jpg` | ~948 KB | Imagen enviada en `/start` | Implícitamente cubierto por `test_handle_start_*` |
| `assets/janitor/janitor_avatar.png` | ~169 KB | Avatar general (no Telegram-específico) | Sin test directo |

**Verificación rápida post-merge**:
```bash
test -f assets/janitor/janitor_avatar_telegram.jpg && \
  test -f assets/janitor/telegram_welcome.jpg && \
  echo "OK: telegram assets present" || \
  echo "MISSING: telegram assets"
```

### 11.3 Test de regresión — `tests/gateway/test_telegram_janitor_branding.py`

Este es el archivo de **regression guard** para toda la zona de conflicto
Telegram. Cualquier sync upstream que toque `gateway/platforms/telegram.py`
debe ir acompañado de una corrida verde de este test.

**12 funciones de test** que cubren:
1. Avatar upload en cada `connect()` (sin flag file de "ya subido")
2. Idempotencia del avatar setter (sube en cada llamada)
3. Skip graceful cuando PTB < 22.7 (warning + no-op)
4. Fallback a `do_api_request("removeMyProfilePhoto")` cuando falla la API moderna
5. Uso correcto de `photo=` kwarg (no `profile_photo=` ni `media=`) — testea el contrato de la API de PTB
6. Skip silencioso cuando falta el asset (no bloquea startup)
7. `/start` envía `telegram_welcome.jpg` con caption Janitor (no `send_message`)
8. `/start` fallback a texto cuando falta el asset
9. Integridad JPEG del avatar (`file(1)` confirma `JPEG image data`)

**Wiring CI** (ver §4.1):
```yaml
# Mirror of AGENTS.md directive #11 — kept in lockstep across the three
# workflows that invoke this list:
#   * .github/workflows/tests.yml          :: test          (PR gate on ubuntu-latest)
#   * .github/workflows/janitor-ci.yml     :: python-tests  (mirror on ubuntu-latest)
#   * .github/workflows/janitor-ci.yml     :: os-compat     (macOS + Windows portability smoke)
# Line numbers in the source files drift with every change to those workflows;
# search for the literal test list above and the job names `Run Janitor-specific
# tests` / `Run Python tests` / `Run Janitor tests` to locate the invocations.
# Adding a new tests/**/test_*janitor*.py requires updating all four places
# (the three invocations + directive #11 in AGENTS.md) in the same PR.
- name: Run Janitor-specific tests
  run: |
    source .venv/bin/activate
    python -m pytest \
      tests/test_janitor_cli.py \
      tests/test_janitor_update_bootstrap.py \
      tests/test_janitor_update_core.py \
      tests/test_janitor_bootstrap_node_version.py \
      tests/gateway/test_telegram_janitor_branding.py \
      tests/skills/test_janitor_config_audit_skill.py \
      tests/skills/test_janitor_firecrawl_skill.py \
      tests/skills/test_janitor_lightrag_skill.py \
      tests/test_janitor_monkeypatch_signatures.py \
      tests/test_janitor_no_duplicate_methods.py \
      tests/test_janitor_migrate_v0201.py \
      tests/hermes_cli/test_mcp_router_discover.py \
      tests/hermes_cli/test_mcp_router_logs.py \
      --tb=short -v
```

### 11.4 Síntomas de regresión Telegram

Si un merge upstream rompe las personalizaciones Janitor de Telegram,
los síntomas son:

- `tests/gateway/test_telegram_janitor_branding.py` reporta **11 de 12 tests rojos** (solo pasa `test_telegram_avatar_asset_is_jpeg`, que no depende del código)
- En runtime: el bot de Telegram arranca con el avatar de upstream (o sin avatar) en lugar de `janitor_avatar_telegram.jpg`
- En runtime: el comando `/start` responde con texto genérico de Hermes en lugar de `telegram_welcome.jpg` + caption Janitor
- Mensaje en logs: `TelegramAdapter` no llama a `_set_janitor_avatar()` durante el connect

### 11.5 Causa raíz

`gateway/platforms/telegram.py` es un **hot path** de upstream — recibe
commits en casi cada sync (v0.16.0 incorporó ~25 commits Telegram: rich
messages, Bot API 10.1, streaming fixes, etc.). Los métodos de Janitor
(`_set_janitor_avatar`, `_handle_start`) son **inyectados en el cuerpo
de la clase `TelegramAdapter`**, lo que los hace invisibles al `git
diff` de superficie: un merge con `-X theirs` los borra sin levantar
conflictos de tres vías.

### 11.6 Resolución de conflictos

**Si git marca conflicto en `gateway/platforms/telegram.py`**:

1. **NO adoptes upstream completo** — las personalizaciones Janitor están en medio de métodos de upstream (`connect()`, `_handle_start` se inyecta cerca de otros handlers).
2. **Resuelve preservando ambos lados**:
   - Adopta la lógica nueva de upstream (rich messages, streaming fixes, etc.)
   - Conserva los símbolos `_JANITOR_*`, los métodos `_set_janitor_avatar` y `_handle_start`, y los call sites en `connect()` y `add_handler`
   - Verifica que el import de `InputProfilePhotoStatic` siga en **ambas** ramas del try/except (líneas 31 y 33)
3. **Después de resolver, corre el test de regresión**:
   ```bash
   python -m pytest tests/gateway/test_telegram_janitor_branding.py -v
   ```
   Debe pasar 12/12 en menos de 2s.

**Si git NO marca conflicto pero el test falla** (caso del wholesale
adoption `607078d2c`): upstream sobreescribió el archivo sin conservar
nada. Restaurar desde el commit de re-aplicación de referencia
`91a891618`:
```bash
# Ver qué se perdió
git diff 91a891618^ -- gateway/platforms/telegram.py | head -200

# Re-aplicar el delta Janitor desde el commit de referencia
git show 91a891618 -- gateway/platforms/telegram.py | git apply
```

### 11.7 Checklist post-merge obligatorio para Telegram

Añadir al checklist de validación (§4.1) después de cualquier merge
que toque `gateway/platforms/telegram.py`:

- [ ] **Constantes presentes**: `grep -q "_JANITOR_ASSETS_DIR" gateway/platforms/telegram.py`
- [ ] **Método avatar presente**: `grep -q "_set_janitor_avatar" gateway/platforms/telegram.py`
- [ ] **Call site en connect**: `grep -q "await self._set_janitor_avatar" gateway/platforms/telegram.py`
- [ ] **Handler /start**: `grep -q "_handle_start" gateway/platforms/telegram.py`
- [ ] **Import PTB**: `grep -q "InputProfilePhotoStatic" gateway/platforms/telegram.py` (debe aparecer en línea 31 — try block — Y en línea 33 — except block; en total ≥ 2 referencias)
- [ ] **Test verde**: `python -m pytest tests/gateway/test_telegram_janitor_branding.py -v` → 12/12 pass
- [ ] **Assets presentes**: `test -f assets/janitor/janitor_avatar_telegram.jpg && test -f assets/janitor/telegram_welcome.jpg`
- [ ] **Pin PTB intacto**: `grep -E 'python-telegram-bot\[webhooks\]>=22\.7' pyproject.toml | wc -l` debe retornar `2` (messaging + termux). Si retorna 0, el pin fue revertido por el sync aunque los símbolos del código sigan presentes — los mocks de tests bypasean el check `hasattr(self._bot, "set_my_profile_photo")` pero el bot real falla en runtime. Ver §4.4 para el guardrail completo y comando de restauración.

```bash
# One-liner para validar todo de una vez
(
  grep -q "_JANITOR_ASSETS_DIR" gateway/platforms/telegram.py && \
  grep -q "_set_janitor_avatar" gateway/platforms/telegram.py && \
  grep -q "await self._set_janitor_avatar" gateway/platforms/telegram.py && \
  grep -q "_handle_start" gateway/platforms/telegram.py && \
  grep -q "InputProfilePhotoStatic" gateway/platforms/telegram.py && \
  test -f assets/janitor/janitor_avatar_telegram.jpg && \
  test -f assets/janitor/telegram_welcome.jpg
) && echo "Telegram Janitor branding: SYMBOLS OK" || echo "Telegram Janitor branding: SYMBOLS MISSING"

# Test verde (separado porque pytest puede tardar):
python -m pytest tests/gateway/test_telegram_janitor_branding.py -q
```

### 11.8 Archivos Janitor-only relacionados con Telegram

| Archivo | Tipo | Riesgo en sync |
|---|---|---|
| `tests/gateway/test_telegram_janitor_branding.py` | Test Janitor-only | **Medio** — corre en PR gate pero el sync puede romper `gateway/platforms/telegram.py` y el test detecta regresiones |
| `assets/janitor/janitor_avatar_telegram.jpg` | Asset binario | **Bajo** — no está en árbol upstream, no se toca |
| `assets/janitor/telegram_welcome.jpg` | Asset binario | **Bajo** — idem |
| `.sisyphus/evidence/post-merge-gate-9-telegram.txt` | Evidencia | **Bajo** — archivo `.sisyphus/` ignorado por git |
| `docs/plans/2026-06-09-003-fix-telegram-stream-overflow-continuations-plan.md` | Plan activo | **Bajo** — fork-only, fuera del árbol upstream |

### 11.9 Fix de referencia — commit `91a891618`

El commit de referencia para restaurar las personalizaciones Janitor de
Telegram tras un wholesale adoption es:

```
91a891618 fix(sync): re-apply Janitor fork identity lost by upstream adoption (T5b.3)

- _JANITOR_ASSETS_DIR, _JANITOR_AVATAR_PATH,
  _JANITOR_TELEGRAM_AVATAR_PATH, _JANITOR_WELCOME_PATH,
  _JANITOR_WELCOME_TEXT constants
- _set_janitor_avatar() method (with PTB >= 22.7 fallback)
- _handle_start() method
- await self._set_janitor_avatar() call in connect()
- CommandHandler('start', self._handle_start) registration
- Added 'InputProfilePhotoStatic' to both try/except import blocks
```

Si un sync futuro vuelve a borrar la zona (por ejemplo, otro wholesale
adoption o una resolución `-X theirs` mal calibrada), este commit es
la **fuente canónica** del delta Janitor en `telegram.py`. Aplicar con:
```bash
git show 91a891618 -- gateway/platforms/telegram.py | git apply
```


---

## v2026.8.13 Sync

**Base:** `467ffd02` · **Target:** tag `v2026.8.13` (`f80f453`) · **Version:** `0.20.1+janitor.1`.

**Original 10-path conflict set (resolved by intent):** `gateway/platforms/api_server.py`, `hermes_cli/kanban_db.py`, `tools/cronjob_tools.py`, `tools/image_generation_tool.py`, `scripts/release.py`, `.github/workflows/{tests,docker,skills-index,uv-lockfile-check}.yml`, `uv.lock`. Each resolved file-by-file per §3 (no `-X theirs`/`-X ours` global, ver §2.1).

**PTB pin:** `python-telegram-bot[webhooks]>=22.7,<23` en `pyproject.toml` (messaging + termux); `uv.lock` regenerado con `22.8` locked.

**Deferred to post-merge:** Janitor update-flow files, the final 13-file CI test list (directiva #11), and installer OS-gate jobs — see Tasks 10–11.
