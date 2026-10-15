# Reparación de la auditoría de Janitor 1.0.0

Fecha: 2026-10-15. PR borrador: [#80](https://github.com/reck74/Janitor-Agent/pull/80), rama `codex/janitor-revival-1.0`. El merge `ba9de6a32c421d0d846a1a7ed8546088652a4c9d` conserva como padres la base del fork y Hermes estable. Las correcciones posteriores de aceptación se preparan en un segundo worktree para no alterar la suite en ejecución.

Este documento complementa `JANITOR_RECOVERY_AUDIT.md`, que conserva la observación anterior a las reparaciones. Corregir un hallazgo de código no certifica por sí solo la aceptación completa del producto. **Janitor v1.0.0 no está publicado ni autorizado por estos resultados para distribución estable.**

## Matriz de reparación

| ID | Cambio y evidencia de regresión | Estado |
| --- | --- | --- |
| R01 | Resolución compartida del perfil, migración global explícita y ámbito de secretos upstream. Tests con raíz/perfil distintos y credenciales de proceso antiguas. | Código reparado |
| R02 | Normalización coherente JSON/YAML/env del proveedor fijado; seis cambios local/cloud con SDK real. Servidor local compartido sólo con propietario y credenciales verificados dentro de la instalación. | Código reparado |
| R03 | Backup de configuración, secretos de servicios, `docker/`, memoria y dump Honcho. Restauración verifica hashes antes de escribir en un destino nuevo; el manifiesto usa rutas portátiles POSIX también al generarse en Windows. | Código reparado |
| R04 | Skill Honcho instalada resuelve el launcher PM y conserva el perfil seleccionado. | Código reparado |
| R05 | Firecrawl exige respuesta con contenido Markdown, tres intentos acotados y salida no cero ante error. | Reparado y aceptado con los cinco digests fijados |
| D01 | Build de release rechaza árbol sucio/merge y verifica instalador remoto por SHA y contenido; desarrollo separado. | Reparado; builds y smokes release aprobados en ba9de6a32c, bcdc9ea03 y ef081f9c15; reconstrucción del checkpoint final pendiente |
| D02 | Handshake de versión y UI lista; detección de salida prematura y rollback de AppImage. | Reparado; dos transiciones reales entre checkpoints aprobadas |
| D03 | Launcher recorre candidatos completos y ejecutables; descarta versiones parciales. | Código reparado |
| G01 | Redacción antes de escribir en capturas MCP compartidas o por servidor, incluso fallback. | Código reparado |
| G02 | `/start` Telegram conserva autorización, pairing y tópicos: sólo autorización explícita permite bienvenida; los demás casos pasan al comando upstream. | Código reparado |
| C01 | Eliminado parseo duplicado de slices; regresión verifica particiones disjuntas y cobertura completa. | Código reparado |
| C02 | Workflow Janitor Linux construye overlay, verifica metadatos/checksum y ejecuta smoke empaquetado; candidato requiere aceptación. | Implementado; build/smoke del overlay aprobados también en CI |
| C03 | Corregidos errores propios y heredados de lint, portabilidad y complejidad sin desactivar reglas. | Diez guards de árbol verdes; comparación CI de salud/blobs pendiente de aprobación |
| C04 | `cron/jobs.py` reconciliado con estable y auditor ampliado a módulos extraídos, cron, ACP y Janitor. | Código reparado |
| C05 | Auditor fuerza prefijos y formato Git estables; regresión con `diff.mnemonicPrefix=true`. | Código reparado |
| C06 | Lock website reproducible, instalación y build bilingüe. Sin críticas/moderadas; excepción acotada y con caducidad para braces 3.0.3. | Mitigado y documentado; vulnerabilidad sin parche aún presente |
| C07 | Autoría/licencia y catálogo regenerados. | Catálogo validado; atribución histórica pendiente de completar |
| O01 | README e instrucciones actuales instalan Janitor y exigen Docker, MiniMax y Honcho. | Reparado |
| O02 | Inventario versionado de diferencias, consumidor, estado y sustituto; trece residuos Desktop retirados tras análisis de imports. Prototipos archivados como texto. | Reparado; inventario regenerado después de cada checkpoint de aceptación |

## Validación local

- Gate canónico Janitor: 21 archivos, 327 tests aprobados, cero fallos (55,9 segundos), incluidas las últimas regresiones de portabilidad, manifiestos y salida Python CRLF de WAHA; incluye OpenDesign y las regresiones posteriores.
- Gateway/MCP: suite inicial de 33 tests aprobada; aceptación posterior cubre 57 tests Telegram y las rutas MCP únicas, con redacción en errores.
- TUI: build, typecheck y lint correctos; 1.639 tests aprobados con Python PM completo y dependencias instaladas desde cero.
- Web: build, typecheck y lint correctos; 431 tests aprobados en aceptación (incluye dos regresiones de expansión).
- Desktop: typecheck completo y overlay correctos; 38 tests dirigidos aprobados; lint sin errores. Suite Electron: 3.650 aprobados, 24 omitidos y cuatro fallos por entorno, después aprobados en la repetición de los tres archivos afectados con PM.
- Bootstrap aislado: todas las etapas, assets, launcher y chat por la entrada real del proveedor aprobados con API de prueba. Esta prueba desactiva memoria externa en su turno de chat; no certifica memoria semántica.
- Catálogo, metadata y prompts: 1.632 tests aprobados; enlaces de documentación correctos.
- Dependencias de aplicación: npm audit registra cero críticas, altas o moderadas y ocho bajas.
- Website: instalación npm reproducible y build en inglés/chino aprobados. La excepción de braces vence el 29 de octubre de 2026; CI rechaza otras altas/críticas, cambios de versión, errores de audit y excepciones caducadas.
- Preservación: cinco checksums de backup correctos. Los cinco archivos OpenDesign se copiaron intactos al checkpoint inicial; las reparaciones posteriores sólo modifican las copias del worktree. El checkout original y sus archivos no rastreados siguen íntegros.

Los logs y artefactos locales se conservan fuera del árbol Git, en `/home/reck/.codex/worktrees/janitor-revival/validation-evidence/r19/`, para no contaminar los scanners, snapshots o builds. No contienen las credenciales usadas en las comprobaciones.

## Condiciones que siguen bloqueando publicación estable

1. Completar la aceptación remota estricta del runtime reparado. La suite local sobre el merge inmutable `ba9de6a32c` terminó con cobertura exacta de 5.585 archivos: 61.045 tests aprobados, 17 fallos, 852 omitidos y dos xfails esperados. Los 17 fallos se conservan como resultado original; cada familia tiene reparación y comprobación causal separada. La ejecución original terminó con código 137 tras 3.165 archivos y se reanudaron sólo los 2.420 pendientes, sin solapamiento. No se atribuye esa interrupción a OOM sin evidencia. Esta suma no equivale a una ejecución completa verde del commit reparado. La aceptación remota se lanzó sobre `ef081f9c15` con `release=false` y `strict_acceptance=1`, incluidas seis particiones Python y Desktop core/update E2E.
2. Reconstruir AppImage con el SHA final y cerrar su aceptación. Los builds release y smokes nativos sobre `ba9de6a32c`, `bcdc9ea03` y `ef081f9c15` pasaron. Las transiciones reales ba9de→bcdc y bcdc→ef081 ejecutaron el actualizador Janitor, PM, builds npm y reemplazo de AppImage con handshake, preservando secretos, sesiones, configuración y WIP en raíz/perfil. En la segunda transición, `--check` no modificó ninguno de 84.307 archivos. Se usó una rama explícita, un espejo Git privado de commits públicos y transporte HTTP local: no certifica el feed estable de GitHub aún no publicado ni una transición de versión pública N→N+1, pues ambos commits declaran 1.0.0. El recibo `ef081-acceptance-receipt.json` conserva hashes y límites; tampoco certifica memoria ni una llamada real al modelo en esa transición.
3. Validar memoria semántica real: la clave OpenAI instalada responde HTTP 401 al endpoint de embeddings y no hay credencial Honcho cloud configurada. No se han sustituido ni expuesto secretos.
4. Completar capacidades opcionales pendientes. Firecrawl fijado ya pasó dos deploys/scrapes reales, n8n ejecutó un workflow Webhook→Set, NocoDB pasó CRUD/persistencia y WAHA verificó autenticación y endpoints sin pairing. Todos conservaron credenciales al reinstalar y limpiaron sus recursos temporales. LightRAG pasó ingesta, consulta con referencia, reinstalación y persistencia tras reinicio; fijación del manifiesto Ollama comprobada. Browser pasó navegación/lectura/click con ambos backends en Chromium real y HOME aislado. OpenDesign pasó registro idempotente sobre 0.25.0, instalación, build de producción con heap de 4 GiB, salud HTTP y MCP stdio con 22 herramientas; WAHA con pairing/mensajes reales requiere una cuenta de prueba y autorización del destinatario.
5. Completar los gates remotos: macOS ya pasa; Windows detectó fixtures de Bash/paths/permisos que se corrigen sin omitir sus pruebas funcionales. Siguen pendientes salud/blobs con su decisión de referencia pendiente, revisión de cinco patrones supply-chain heredados y atribución histórica. Diecisiete autores ya tienen mapping añadido con asociación del commit verificada por GitHub; los ambiguos y la colisión de mayúsculas siguen pendientes. El scanner y el gate de autoría conservan sus reglas.
6. Ejecutar aceptación Linux completa, incluidos Desktop core/update E2E (omitidos en PR por diseño upstream), y registrar sus resultados antes de promover un candidato a Janitor v1.0.0.


## Correcciones encontradas durante la aceptación

- CI TUI: construir primero `packages/hermes-ink`, además del build principal, antes de typecheck/tests; añadir lint explícito y restaurar la separación de imports de `externalLink.ts`. Las 78 suites fallidas en CI provenían del paquete Ink sin generar, oculto por artefactos locales anteriores.
- CI general: ampliar `detect` de uno a cinco minutos. El checkout y la clasificación del merge grande consumieron más de un minuto; las anotaciones de GitHub confirman timeout, no un fallo del clasificador.
- LightRAG: retirar también `LIGHTRAG_WEBUI_USER` y `LIGHTRAG_WEBUI_PASSWORD` antes de actualizar `.env`; una reproducción de dos instalaciones duplicaba esas variables.
- Honcho: inicialmente 46 tests de instalación/E2E aprobados tras corregir fallback YAML, alcance de secretos y reutilización del servidor por perfiles. Seis construcciones reales del cliente/SDK confirman los modos local/cloud; esto no certifica memoria semántica.
- Honcho legado: la revisión independiente detectó el proyecto Compose histórico `docker`. Se admite sólo desde el propietario validado y con credenciales verificadas; 44 tests de instalación aprobados, incluidos cinco casos de migración/rechazo.
- Telegram: 57 tests de branding, autorización, redacción y DM aprobados tras reproducir la pérdida del flujo de pairing.
- LightRAG: fijar y verificar el digest del manifiesto de embeddings que produce la imagen Ollama fijada; impedir arranque ante deriva. Configuración nativa `reasoning_split` separa el razonamiento de MiniMax de las respuestas. 34 tests dirigidos aprobados.
- Instrucciones: compactar `AGENTS.md` de 23.266 a 11.846 caracteres conservando sus quince contratos y el contexto en `JANITOR_FORK_DIRECTIVES.md`; todas las cadenas de instrucciones pasan el guard upstream sin elevar límites.
- NocoDB: corregir el login documentado a `/api/v1/db/auth/user/signin`, comprobado contra la imagen fijada. La ruta v2 antigua devuelve 404.

- SQLite/Btrfs: el diagnóstico de bloqueos verifica el descriptor por dispositivo/inode y su lock fdinfo; 38 pruebas y un escritor SQLite real pasan. No atribuye archivos de otro subvolumen ni abre la base para diagnosticar.
- macOS: bootstrap compatible con Bash 3.2, gate Node sin PCRE de GNU y temporales WAHA explícitos; 25 pruebas pasan con Bash 3.2 real y otras 25 con Bash actual. LightRAG migra su `.env` mediante escritura privada atómica.
- WAHA: repetir pairing conserva sesiones WORKING, reutiliza STARTING/SCAN_QR_CODE y consulta `?all=true` para detectar STOPPED; transición a WORKING y errores desconocidos cubiertos. Recuperación comprobada con la imagen fijada sin red ni cuenta; 37 tests opcionales pasan.
- Fixtures PM/Fedora: se usan las entradas JavaScript npm/npx emparejadas con Node y perfiles de shell sintéticos, sin depender de wrappers mise o del `/etc/profile` del host; 31 tests PM y cuatro de shell pasan (un caso Windows omitido en Linux).
- Windows: el runner canónico resuelve Bash mediante PM y evita el stub WSL; dos regresiones reproducen el fallo y 16 contratos CI pasan.
- Pruebas de recuperación: un venv stdlib limpio evita que el importador editable resuelva el bootstrap deliberadamente ausente desde otro checkout; las 14 pruebas pasan sin modificar producción.
- Pruebas de proveedores: aislar también el probe nativo Ollama evita que un servicio local reemplace el catálogo sintético; 93 tests de la familia pasan.
- Modelos: corregir exclusión mutua por perfil/credencial y escritura concurrente de la caché; controles negativos reproducen doble fetch y pérdida de filas. Aislar HOME en el test de Copilot y comprobar causalmente que el picker no espera a la API de usage.
- MCP: retirar las rutas antiguas duplicadas de discovery/logs; un test comprueba que sólo existe el propietario autenticado de `janitor_ext`.
- Limpieza: retirada la infografía de PR obsoleta sin consumidores, ya eliminada por estable y rechazada por su guard; bytes recuperables por referencia Git documentada en `legacy/README.md`.
- Portabilidad: seis codificaciones explícitas, dos shebangs portables y temporales privados con cleanup en WAHA/cookies/documentación.

La comparación de salud contra el fork de agosto informa 6.447 bloqueos heredados; contra el motor estable fijado inicialmente identificó 40 bloqueos del fork, ya corregidos: cero bloqueos y un advisory en el diagnóstico final contra ese motor. Diez guards de árbol pasan sin cambiar sus reglas. La propuesta de comparar la sincronización con el motor verificado y reconocer blobs idénticos heredados fue rechazada por revisión automática pendiente de aprobación explícita. Los gates originales permanecen sin cambios. La propuesta y su riesgo de aceptar temporalmente límites del motor están en `JANITOR_CI_BASELINE_PROPOSAL.md`.

La entrega de producto sigue siendo Linux x86_64. Las comprobaciones nativas Windows de los módulos y fixtures portátiles no anuncian soporte del instalador Bash en Windows nativo; Honcho declara Linux/macOS y OpenDesign incluye WSL2.

- Workflows: corregidas dos expresiones anidadas inválidas de selección Windows. Actionlint detectaba ambos errores y ahora no detecta errores nuevos frente al motor fijado; los doce diagnósticos `cache-mode`, un `if: false` y una matriz duplicada ya existen en upstream.
- Windows: selección PM de Bash, HOME/USERPROFILE aislados y fixtures UTF-8/LF con rutas portátiles. Las aserciones POSIX de modo 0600 sólo se aplican donde esos bits representan permisos; las verificaciones de contenido, backups y cleanup siguen ejecutándose.
- WAHA/Windows: cuatro capturas de salida Python omiten el salto de línea para que Bash no conserve CR; seis casos fallaban antes de la reparación y las catorce combinaciones de sesión/LF/CRLF pasan después.
- Migración: manifiestos y registros de dumps externos usan `/` en todos los sistemas; una prueba de registro repetido y restauración verifica checksum, ausencia de duplicados y separación de dumps externos.

Estos cambios cuentan con reproducciones o evidencia CI y se validan por separado sin modificar el commit bajo la suite larga.
