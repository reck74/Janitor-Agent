# Auditoría de la recuperación de Janitor Agent 1.0.0

Fecha: 15 de octubre de 2026. Estado: implementación avanzada, pendiente de reparación y aceptación. **No publicar Janitor v1.0.0 ni distribuir el AppImage actual como candidato válido.**

La arquitectura del plan sigue siendo adecuada: Hermes estable como motor, extensiones Janitor aisladas, PM para el runtime y overlay de Desktop. Hay mejoras verificadas y el trabajo local original está preservado. Sin embargo, quedan regresiones reproducibles, controles de calidad incompletos y pruebas de aceptación pendientes. Conviene conservar lo construido y ejecutar la fase de reparación definida aquí.

Esta auditoría contrastó el plan aprobado con el diff frente a Hermes estable, los registros de pruebas y reproducciones independientes en directorios temporales. Tres revisores cubrieron runtime/instalación, Desktop/Gateway/MCP y CI/documentación. Durante esta revisión no se modificó código de producto, no se actualizaron servicios del usuario y no se publicó ninguna release.

## Estado de Git y protección del trabajo

- Checkout original: `/home/reck/Projects/Janitor-Agent`, HEAD `1796524ef…`; conserva sus tres archivos modificados y cuatro archivos sin rastrear.
- Worktree de recuperación: `/home/reck/.codex/worktrees/janitor-revival/Janitor-Agent`, rama `codex/janitor-revival-1.0`.
- Base de recuperación: `origin/main`, commit `282a00fc0875455c5f611062eb1a6d2729600d7f`.
- Motor objetivo: Hermes v0.22.2, commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8`. El objeto de merge resuelve al commit acordado.
- No quedan conflictos Git sin resolver. El merge continúa sin commit porque el hook de calidad rechazó los intentos de guardarlo.
- El diff de producto frente a estable abarca 271 rutas antes de añadir este informe. El volumen mucho mayor del merge incluye la actualización upstream; no debe confundirse con código nuevo de Janitor.
- Los cinco archivos de OpenDesign conservados en recovery coinciden byte a byte con el checkout original. Los cuatro archivos sin rastrear coinciden con el archivo de respaldo.
- Los cinco checksums del respaldo persistente verifican correctamente. Ubicación: `.git/janitor-revival-backups/pre-revival-20261015/` en el checkout original. El patch original sigue siendo equivalente; sólo cambia la longitud de los hashes abreviados que imprime Git.
- `website/package.json` contiene cambios adicionales sin añadir al índice; su lockfile todavía no refleja esos overrides.

## Lo que sí está demostrado

La actualización utiliza entrypoints delegadores y un núcleo compartido. Hay adaptación de SOUL al contrato upstream, separación entre versión Janitor y versión Hermes, configuración basada en defaults actuales más overlay, preservación de personalizaciones y backup SQLite mediante la API de SQLite. El proveedor Honcho fijado distingue los hosts de los perfiles nombrados; no se confirmó la sospecha inicial de una memoria global compartida por todos los perfiles.

Desktop tiene overlay de identidad y bootstrap separado, y conserva los componentes modernos upstream. La captura MCP individual distingue servidor y perfil. Los manifiestos Python centralizan los tests Janitor. Los documentos históricos v5 remiten a `legacy/`; sus stubs activos no reactivan esos planes.

| Comprobación | Evidencia y alcance |
| --- | --- |
| Gate canónico Janitor repetido durante esta auditoría | **213 aprobados, 20 archivos, 0 fallos**, 42,4 segundos, dos workers. |
| Revisión independiente runtime | **60 tests existentes aprobados** de CLI, instalación, actualización y migración; las regresiones descritas abajo no estaban cubiertas. |
| TUI, registro de implementación | Build y typecheck aprobados; **1.638 tests aprobados, 2 omitidos**. |
| Web, registro de implementación | Build y typecheck aprobados; **429 tests aprobados**. |
| Desktop, registros de implementación | Typecheck aprobado y suite Electron con **3.633 tests aprobados, 24 omitidos**; esto no equivale a aceptación de una instalación completa. |
| AppImage real | Arranca con identidad Janitor 1.0.0, muestra formulario MiniMax/Honcho, permite cancelar y ejecuta la PTY empaquetada. El smoke cancela antes de instalar. |
| MiniMax y almacenamiento Honcho | Chat CLI real completo; conversación guardada y datos conservados tras reiniciar Honcho. |
| Opcionales | n8n, NocoDB, WAHA y Firecrawl alcanzaron healthcheck y HTTP 200 en recursos temporales aislados. No certifica workflows, pairing/mensajes ni scraping. |
| Migración de volumen | Copia offline de datos verificada byte a byte, conservando el volumen anterior. |
| Dependencias de aplicación | El último audit guardado de la raíz registra 0 críticas/altas/moderadas y 8 bajas. No es una evaluación equivalente del website. |

La última segunda parte de la suite upstream registra **34.978 aprobados, 31 fallidos, 717 omitidos**, en 2.982 archivos, más un timeout de `test_doctor.py`. La primera parte había aprobado 2.603 archivos antes de interrumpirse. Estos registros no forman una certificación única sobre un commit inmutable. Hay fallos de entorno —dependencias del venv dentro del árbol inspeccionado— y fixtures que clonan el HEAD anterior, además de defectos propios. Cada fallo debe clasificarse y repetirse; no corresponde atribuir los 31 a regresiones Janitor ni declararlos resueltos.

## Hallazgos reproducibles

P1 identifica reparaciones que bloquean una entrega fiable. P2 identifica defectos funcionales o de mantenimiento que también deben cerrarse antes de la aceptación acordada.

| ID | Prioridad | Hallazgo, evidencia y efecto | Reparación requerida |
| --- | --- | --- | --- |
| R01 | P1 | `scripts/janitor-install.sh:5` sustituye un `HERMES_HOME` de perfil por `JANITOR_HOME` raíz. La reproducción con dos rutas distintas delegó al perfil incorrecto. `janitor_ext/honcho.py:144` y `migrate.py:145` usan la misma precedencia inconsistente. | Definir una resolución compartida de perfil; probar instalación, reparación y Honcho sin cambios en perfiles ajenos. Distinguir explícitamente migración de raíz completa y reparación de un perfil. |
| R02 | P1 | `janitor_ext/install.py:87` elimina `baseUrl` plano al cambiar a cloud, pero conserva `endpoint.baseUrl`. El cliente real del plugin fijado siguió eligiendo `http://localhost:1973` en una reproducción sin red. | Normalizar las variantes de configuración admitidas y comprobar la conexión efectiva del proveedor. Cubrir local→cloud y cloud→local, raíz y perfiles nombrados. |
| R03 | P1 | `janitor_ext/migrate.py:14` y `:21` omiten configuración y secretos bajo `docker/`. Un fixture con cinco archivos de credenciales de servicios devolvió un inventario vacío. El backup actual no permite recuperar íntegramente las credenciales asociadas a volúmenes existentes. | Inventariar los archivos duraderos de cada servicio y probar restauración. Incorporar también el dump posterior de Honcho a un manifiesto verificable. |
| R04 | P2 | `skills/janitor-honcho/scripts/deploy.sh:3` sólo funciona desde el checkout. Copiado a `<perfil>/skills/janitor-honcho`, busca `<perfil>/scripts/janitor`; incluso `--help` termina con 127. | Resolver el launcher PM instalado como hacen los otros opcionales y mantener el perfil elegido. |
| R05 | P2 | `skills/janitor-firecrawl/scripts/deploy.sh:230` devuelve éxito tras fallar `curl`; `:271` ignora también el fallo de verificación. Un curl sintético con exit 22 produjo verificación exit 0. | Propagar errores, validar respuesta funcional y aplicar reintentos acotados. No anunciar scraping operativo sólo por healthcheck. |
| D01 | P1 | `apps/desktop/janitor/build.mjs:96` estampa HEAD aunque el árbol esté modificado. El AppImage actual contiene UI nueva pero su comprobante apunta a `282a00fc…`; su bootstrap descarga el instalador antiguo, incompatible con el protocolo nuevo. | Añadir condiciones de build de release reproducible, separar artefacto de desarrollo, obtener un SHA limpio y accesible y reconstruir. Ejecutar la instalación completa desde ese AppImage. |
| D02 | P1 | `apps/desktop/janitor/update.mjs:204` considera suficiente el evento `spawn`. Una nueva AppImage sintética que sale inmediatamente con 42 produjo `ok:true` y permaneció instalada. | Confirmar arranque y versión mediante handshake, detectar salida prematura, restaurar el artefacto anterior y representar correctamente el resultado parcial del runtime. |
| D03 | P2 | `skills/janitor-desktop-launcher/scripts/launch.sh:43` elige el nombre de mayor versión antes de comprobar que sea utilizable. Una 1.0.1 parcial impidió lanzar una 1.0.0 válida. | Recorrer candidatos completos, validar ejecutable y metadatos y continuar ante candidatos incompletos. |
| G01 | P2 | `janitor_ext/mcp_logs.py:79` escribe stderr original al sink compartido antes de redactar la copia individual. Una credencial sintética permaneció en el log compartido. | Redactar antes de todos los destinos, incluidos errores y fallback. Comprobar ambas capturas sin mezclar servidores ni perfiles. |
| G02 | P2 | `plugins/platforms/telegram/adapter.py:6553` añade `/start` sin las comprobaciones de admisión/autorización del handler upstream y sin `message_thread_id`. La reproducción envió respuesta sin verificar autorización y fuera del tópico recibido. | Reutilizar las garantías del adapter vigente; probar usuarios rechazados, chats permitidos y tópicos. |
| C01 | P1 | `scripts/run_tests_parallel.py:1407` repite el parseo de slices después de consumir y borrar `HERMES_TEST_SLICE`. Con variable `3/6`, el resultado fue `slice_index=None, slice_count=1`. `tests.yml:144` usa esa variable; cada uno de los seis jobs ejecutaría la suite completa. | Eliminar el bloque duplicado. Probar tanto variable como argumento y comprobar que las seis particiones sean disjuntas y su unión cubra toda la suite. |
| C02 | P1 | Ningún workflow ejecuta el build/smoke del overlay Janitor. `desktop-bundled-release.yml:1266` mantiene Linux deshabilitado y el E2E existente construye upstream. | Añadir gate del Desktop Janitor source/bootstrap y publicación de candidato Linux con AppImage, checksum y metadatos; verificar los contratos de los workflows. |
| C03 | P1 | El hook impide el commit. Desktop registra 96 errores: 41 en el delta del fork y 55 en archivos idénticos a estable. TUI tiene cuatro propios y dos heredados; Python también falla. | Corregir los propios, tratar los heredados con evidencia y mantener el hook. No desactivar controles ni presentar todos los errores como introducidos por Janitor. |
| C04 | P2 | `cron/jobs.py` contiene tres `_job_output_dir` (123, 213, 538), dos `_jobs_lock_file` (139, 361) y dos `_jobs_lock` (145, 401). El auditor en `tests/test_janitor_no_duplicate_methods.py:16` omite `cron/`. Las definiciones actuales posteriores son las de estable, pero permanecen sombras accidentales. | Eliminar únicamente bloques sustituidos por upstream y ampliar la cobertura del auditor a todo el runtime afectado. |
| C05 | P2 | `janitor_ext/fork_audit.py` reconoce sólo `+++ b/`. `scripts/audit_janitor_merge.py` no fija prefijos Git. Con `diff.mnemonicPrefix=true`, la misma violación sintética es detectada con a/b pero pasa con c/w. | Forzar un formato de diff independiente de configuración o interpretar los encabezados robustamente; añadir regresión. |
| C06 | P2 | `website/package.json:39` contiene overrides sin lock correspondiente, incluido Tinypool 2.1.2 frente a 1.1.1. El último audit guardado del website aún registra 19 críticas, 24 altas, 18 moderadas y 4 bajas; es una evaluación de la cadena de dependencias, no prueba de explotación del sitio. | Completar lock reproducible, instalación, build y audit; documentar las excepciones justificadas y validar los cambios de versión mayor. |
| C07 | P2 | Las skills Desktop launcher y OpenCode incumplen campos de autoría/licencia exigidos por los tests. El catálogo y el snapshot de prompt también tienen validación pendiente. | Completar metadatos y regenerar artefactos mediante sus herramientas, conservando tests upstream. |
| O01 | P1 | `README.md:39` describe Docker/Honcho como opcionales; `:67` instala Hermes desde NousResearch. Conserva además instrucciones de takeover y rutas antiguas. | Reescribir la entrada pública para instalar Janitor con los requisitos y rutas reales; revisar instrucciones de reparación y actualización. |
| O02 | P2 | Falta la matriz versionada del fork por archivo/consumidor/sustituto. Quedan 13 archivos Desktop retirados upstream, aproximadamente 3.448 líneas, sin consumidores actuales confirmados. No se demostró que sombreen módulos activos. | Completar el inventario y retirar o archivar sólo tras verificar consumidores. Mantener explicación, sustituto y soporte de cada elemento legacy. |

## Estado del plan aprobado

| Entrega | Evaluación |
| --- | --- |
| 1. Base protegida e inventario | Protección y worktree correctos. Falta inventario persistente completo y baseline comprometido. |
| 2. Sincronización estable | Referencia correcta y conflictos resueltos. Persisten duplicados, residuos y controles de calidad rechazados. |
| 3. Runtime y actualizador | Diseño y pruebas principales mejorados. Falta cerrar resolución de perfiles y verificar la cadena completa de actualización sobre el commit final. |
| 4. Instalación, Honcho y migración | Bootstrap y chat real parcialmente probados. Endpoint cloud, backups y aceptación semántica pendientes. |
| 5. Desktop Linux | Overlay y AppImage construidos; smoke de arranque válido. El artefacto actual no instala la recuperación final y el rollback de arranque es insuficiente. |
| 6. Gateway, Web y MCP | Builds y tests frontend aprobados; MCP por servidor implementado. Falta redacción completa, autorización/contexto Telegram y matriz de streaming real entre superficies. |
| 7. Opcionales | Pins y healthchecks parciales. Falta aceptación funcional completa, propagación fiable de errores y resolver Honcho como skill instalada. |
| Limpieza, documentación y release | Legacy parcialmente organizado. README, inventario, lock del website, pipeline Linux y aceptación de release siguen abiertos. |

No hay evidencia de aceptación completa de cancelación/reconexión, herramientas, aprobaciones, persistencia compartida y caching/alternancia en la matriz CLI/TUI/Web/Desktop. Los tests heredados aportan cobertura útil, pero no sustituyen una prueba de los adaptadores Janitor funcionando juntos.

## Plan de reparación y criterios de salida

1. **Cerrar el merge y hacer fiables sus controles.** Resolver C01, C03, C04 y C05; completar metadatos y regeneraciones de C07. Clasificar cada fallo upstream frente a estable. Mantener el entorno de pruebas fuera del árbol que inspeccionan los scanners. Salida: lint y auditores verdes, reparto de tests demostrado y diff revisable sin sombras accidentales.
2. **Proteger perfiles, conexiones y recuperación de datos.** Resolver R01–R04 y G01–G02. Añadir regresiones que fallen con el código actual, más restauración de configuración/secretos/SQLite y reutilización de volúmenes. Salida: sólo cambia el perfil previsto y todos los datos duraderos tienen backup/restauración verificables.
3. **Completar documentación, inventario y dependencias.** Resolver O01–O02 y C06. Registrar cada diferencia activa, sustituida, experimental o legacy y su consumidor. Salida: bootstrap documentado correcto, locks coherentes, build/audit del website y limpieza respaldada por consumidores.
4. **Cerrar Desktop y su entrega Linux.** Resolver D01–D03 y C02. Incorporar pruebas de arranque fallido, crash del updater, interrupción del swap y resultado parcial. Salida: build y smoke del overlay en CI, publicación de candidato preparada y reemplazo con rollback probado. La aceptación final requiere un commit limpio y accesible que coincida con el artefacto.
5. **Validar servicios y experiencias completas.** Resolver R05 y ejecutar pruebas funcionales de Browser, Firecrawl, OpenDesign, LightRAG, n8n, NocoDB y WAHA según su contrato. Probar instalación limpia, reinstalación, perfiles, migración y streaming/cancelación/reconexión/herramientas/aprobaciones. Salida: cada capacidad documentada funciona desde su comando y permanece fuera del arranque base cuando es opcional.
6. **Candidato y aceptación Linux.** Guardar el commit revisado, ejecutar los gates sobre ese SHA, publicar un candidato y reconstruir/verificar AppImage y comprobantes contra ese SHA. Probar primer arranque completo y actualización real N→N+1 con conservación de sesiones/perfiles; completar memoria real. Sólo después crear Janitor v1.0.0 estable.

Las tareas 2 y 3 pueden avanzar en paralelo después de corregir los controles de la tarea 1. El pipeline Desktop puede desarrollarse en paralelo; su aceptación depende del runtime corregido y del SHA final. No hace falta rehacer la arquitectura ni volver a empezar desde cero.

## Bloqueos externos y evidencia conservada

La credencial OpenAI disponible para embeddings de Honcho local y la credencial Honcho cloud respondieron HTTP 401 en las pruebas previas. Está pendiente renovar una de esas rutas en el archivo local de secretos; no se deben pegar claves en el chat. La aceptación local todavía necesita derivación y recuperación semántica reales, además del almacenamiento ya demostrado.

WAHA no se emparejó con una cuenta real. Firecrawl sólo acreditó liveness. El registro de opcionales dejó LightRAG como aceptación pendiente; esta auditoría no encontró un resultado final que permita declararlo funcional. También faltan la integración completa de OpenDesign y una validación visual de escritorio; el smoke de formulario no sustituye esa revisión.

Los cuatro contenedores temporales Honcho `janitor-revival-e4_hq0h9-*` están detenidos. Sus volúmenes y algunos fixtures privados se conservaron para repetir la aceptación; el cierre debe retirar únicamente recursos de esta sesión y los secretos temporales, sin podas globales ni cambios en servicios del usuario.

Registros locales consultados:

- `/tmp/janitor-independent-canonical-audit.log` — gate repetido durante esta auditoría.
- `/tmp/janitor-independent-runtime-audit-tests.log` — 60 tests independientes.
- `/tmp/janitor-revival-checkpoint-commit.log` — rechazo del hook.
- `/tmp/janitor-revival-upstream-full.log` y `/tmp/janitor-revival-upstream-remaining.log` — ejecución ampliada y fallos pendientes de clasificación.
- `/tmp/janitor-revival-tui-final.log` y `/tmp/janitor-revival-web-final.log` — builds/tests de interfaz.
- `/tmp/janitor-desktop-appimage-smoke5.log` — smoke nativo limitado a arranque/formulario/cancelación/PTY.
- `/tmp/janitor-first-chat-result.json` y `/tmp/janitor-honcho-acceptance-result.json` — chat y persistencia, con límite explícito de embeddings.
- `/tmp/janitor-optional-acceptance-20261015.json` — healthchecks y migración de volumen.

Los registros de `/tmp` son temporales. Los resultados y límites esenciales quedan preservados en este informe; la entrega final debe guardar evidencia de CI vinculada al commit aceptado.

La revisión automática de permisos había rechazado una propuesta de archivar playbooks Kanban y referencias relacionadas por posibles consumidores activos. Esa limpieza no se ejecutó y queda pendiente de justificar con el inventario. Los fallos de lint son un bloqueo distinto, producido por los controles del repositorio.
