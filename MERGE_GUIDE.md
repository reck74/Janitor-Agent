# Sincronizar Janitor con Hermes

La base de esta revisión es Hermes **v0.22.2** (`d923a5eb487a17c0a68801bba9ef0f56c81040a8`). La versión del producto Janitor se mantiene por separado en `janitor_ext/release.json`.

## Preparación y resolución

1. Crear un worktree limpio y registrar el estado de origen. Fetch del tag estable elegido y verificar su commit antes del merge.
2. Ejecutar un merge de tres vías del tag exacto. Resolver cada conflicto según sus consumidores y conservar las extensiones del fork. No usar `-X theirs`, `-X ours` ni restauraciones masivas.
3. Conservar el core Hermes, sus nombres, tests y documentación. Mover sólo material histórico del fork a `legacy/`, con una explicación y revisión de referencias.
4. Usar el package manager Python `hermes pm` y su lock. Los workspaces JavaScript usan **npm** y `package-lock.json`; `pm/` no es una migración a pnpm.
5. No borrar workflows upstream en bloque. Revisar sus interfaces `workflow_call`, las actions locales, permisos y runners. El runner Linux puede configurarse con `JANITOR_LINUX_RUNNER`; por defecto se usa `ubuntu-latest`.

## Contratos del fork

- `janitor_cli.py` extiende HermesCLI. El flujo update permanece en `janitor_update_core.py`. Al cambiar una firma upstream, actualizar el wrapper y conservar la prueba de compatibilidad (directiva 14).
- TUI conserva JSON-RPC y usa skins o inyección de temas. Build y Vitest son obligatorios (directivas 4 y 7).
- Telegram vive en `plugins/platforms/telegram/adapter.py`. Revisar tanto rutas de respuesta como streaming y branding.
- Docker, MiniMax y Honcho son requisitos base. Browser y Firecrawl son opt-in. Nunca recuperar Infisical o AgentMemory como dependencias base desde documentación antigua.
- Los cambios de estructura incluyen migración con backup de configuración. La migración no borra volúmenes Docker ni secretos existentes.
- Las extensiones MCP viven en `janitor_ext/`; los probes usan la interfaz upstream. El endpoint de logs sólo devuelve capturas del servidor y perfil solicitados; un log global intercalado no demuestra atribución.

## Gate Python en dos niveles (directiva 11)

`.github/janitor-tests.txt` es la única lista de tests del fork. Los jobs `tests.yml::test`, `janitor-ci.yml::python-tests`, el gate nativo de PR en `tests-os.yml::os-tests` y el gate de compatibilidad manual ejecutan `scripts/run_janitor_tests.py`, que valida el manifiesto y llama a `scripts/run_tests.sh`.

Todo nuevo `tests/**/test_*janitor*.py` se añade al manifiesto en el mismo cambio. Los dos tests MCP del fork con nombres heredados también permanecen en él. No duplicar listas en workflows o documentación, ni sustituir el PR gate por toda la suite upstream.

Con el entorno `hermes pm` preparado:

```bash
python3 scripts/run_janitor_tests.py -j 2 --file-retries 0 --tb=short
```

`upstream-sync-verify` ejecuta la suite upstream completa para dispatch manual, release o push a main con `chore(sync):`, `fix(sync):` o merge `upstream-sync-*`. Un fallo se reproduce y resuelve por causa; no borrar tests upstream ni debilitar invariantes para volver verde.

El auditor de duplicados (directiva 15) incluye facades, cron, Janitor, ACP y módulos extraídos de gateway, agent, CLI, TUI gateway y MCP. `_refresh_agent_cache_message_count` debe tener exactamente una implementación async y todos sus callers deben hacer await.

## Gates antes de publicar

- Python: manifiesto Janitor verde, firmas compatibles, sin duplicados ni marcadores de merge. Ejecutar el gate upstream de sync y registrar cualquier fallo pendiente con su causa.
- TUI: `npm run build:ink` primero; después `npm run build --workspace ui-tui`, `npm run typecheck --workspace ui-tui`, `npm run test --workspace ui-tui -- --maxWorkers=2`.
- Web: `npm run check --workspace web` y `npm run build --workspace web`; verificar assets de `hermes_cli/web_dist`.
- Desktop Linux: tests del overlay, typecheck, bundle, AppImage y smoke real en perfil aislado. Un bundle correcto no certifica instalación, autenticación ni actualización real.
- Instalador: bootstrap completo con Docker disponible, HOME aislado y proveedor local de pruebas (`scripts/janitor-ci-smoke.sh`). `--profile-only` prueba generación de configuración; no sustituye ese smoke.
- Diff: ejecutar `python3 scripts/audit_janitor_merge.py --base <base>` y revisar manualmente la compatibilidad de cada extensión. El auditor detecta renombrados literales y ciertas violaciones; no sustituye la revisión.

## Seguridad de dependencias de esta revisión

Electron 41.10.6 y simple-git 4.0.2 corrigen advisories que afectaban dependencias de ejecución; concurrently 10.0.6 corrige tooling. Se fijan parches transitivos auditados y shell-quote 1.11.0 (ya corregido y compatible con la cuarentena npm de 14 días). No ejecutar `npm audit fix --force` ni desactivar globalmente la cuarentena.

El salto Electron 40→41 requiere los gates desktop anteriores antes de publicación. Revisar el resultado actualizado de `npm audit` y documentar riesgo residual; KaTeX en la cadena renderer usa una rama 0.16 y su actualización mayor exige una revisión específica de los renderers matemáticos.

Los snapshots anteriores de esta guía y los planes retirados están en `legacy/docs/pre-1.0/`.


## Instrucciones de agentes

El hub `AGENTS.md` mantiene las quince directivas del fork y la tabla de áreas dentro del límite upstream de 12.000 caracteres; cada cadena de instrucciones debe quedar bajo 30.000. El contexto histórico vive en `JANITOR_FORK_DIRECTIVES.md`. Ejecutar `python scripts/ci/check_agents_md_size.py` tras editar instrucciones; no aumentar límites ni eliminar contratos para superar el gate.

## Inventario y dependencias del website

`legacy/fork-inventory.json` registra por ruta las diferencias históricas y actuales frente al motor fijado, su clasificación, consumidores y sustitutos. Tras resolver un sync, ejecutar `python scripts/build_janitor_fork_inventory.py` y revisar el diff. El generador falla si una familia nueva no tiene clasificación; no valida por sí solo que una función sea innecesaria. Los residuos Desktop tienen además un análisis de imports en `apps/desktop/janitor/retired-files.json`.

La guía `website/SECURITY-DEPENDENCIES.md` registra la validación separada de dependencias del sitio. El gate del website conserva un audit completo y sólo permite la excepción acotada de braces 3.0.3 hasta el 29 de octubre de 2026; cualquier advisory alto/crítico nuevo o fecha vencida bloquea CI. El build del sitio no autoriza publicar una release Desktop.


## Comparación de CI durante esta sincronización

La autorización del usuario del 15 de octubre de 2026 está registrada en `JANITOR_CI_BASELINE_PROPOSAL.md`. `janitor_ext/ci_baseline.py` sólo permite comparar salud con el commit exacto del motor cuando éste es ancestro del candidato y la base del PR aún no lo contiene. Lee `ENFORCEMENT` de la base del PR; una vez incorporado el motor vuelve al ratchet ordinario del PR. Exige historia completa y rechaza revisiones no relacionadas. El control de blobs conserva el límite de 500 KiB y reconoce únicamente objetos Git idénticos al motor fijado. Esta autorización no cubre supply-chain ni atribución.

```bash
python -m janitor_ext.ci_baseline health --base <base-del-PR>
python -m janitor_ext.ci_baseline blob-size --base <base-del-PR>
```

## Reparaciones de aceptación que debe conservar el siguiente sync

- Streams: `agent/chat_completion_stream_tools.py` posee el ensamblador extraído; las llamadas terminadas con JSON inválido deben producir un resultado de herramienta visible, mientras un corte real conserva su recuperación. Comprobar prefijo de conversación, ids y alternancia.
- Credenciales: `hermes_cli/auth_api_keys.py` conserva la API pública de `auth.py`; un endpoint explícito evita los probes nativos. Polling OAuth respeta intervalo, `slow_down` de cinco segundos y deadline. Una rotación Nous conserva el destino del perfil sin reescribir el origen persistido.
- MCP: `tools/mcp_tool_wire.py` sólo retira `_meta` vacío del request y clasifica el HTTP 401 de la llamada bajo su lock. Conservar ids, metadata útil y argumentos; no atribuir rechazos antiguos a otra llamada. Plugins con el mismo manifiesto usan una selección común en runtime/listado, con aviso de colisión.
- Gateway: la redacción incremental actúa sobre la salida, antes de transportes y overflow; no cambia contexto ni historial. Verificar además el filtro de razonamiento al reiniciar segmentos. Sus límites por segmento y las excepciones URL de la política de redacción deben seguir documentados.
- PM: `repo_root()` sigue siendo el código ejecutado. `install_root()` puede resolver su propietario sólo mediante el registro existente y el identificador verificado de la generación. Probar versiones desde una generación real; para el E2E install/update el fixture clona `HEAD`, así que requiere un checkpoint comprometido.
- Desktop E2E: la fixture del motor usa una distribución privada de prueba; no se retira el guard de SHA público de Janitor. El recorder de sockets debe invalidar handles al cambiar de documento y seguir detectando conexiones duplicadas reales.

Los fallos conocidos sólo se retiran de `KNOWN` después de reproducirlos y pasar su ruta funcional. La ejecución Python con `strict_acceptance=1` no cambia por sí sola el tratamiento de casos esperados de Desktop. Registrar resultados originales y reparados por SHA; no sumar suites solapadas como una suite completa.
