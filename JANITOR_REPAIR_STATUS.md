# Reparación de la auditoría de Janitor 1.0.0

Fecha: 2026-10-15. Rama de trabajo: `codex/janitor-revival-1.0`.

Este documento complementa `JANITOR_RECOVERY_AUDIT.md`, que conserva la observación anterior a las reparaciones. Corregir un hallazgo de código no certifica por sí solo la aceptación completa del producto. **Janitor v1.0.0 no está publicado ni autorizado por estos resultados para distribución estable.**

## Matriz de reparación

| ID | Cambio y evidencia de regresión | Estado |
| --- | --- | --- |
| R01 | Resolución compartida del perfil en bootstrap, instalador, Honcho y migraciones; migración global explícita. Tests con raíz y perfil distintos. | Código reparado |
| R02 | Normalización de endpoints del proveedor Honcho fijado. Seis cambios local/cloud con el cliente real; preservación de proxy cloud explícito. | Código reparado |
| R03 | Backup de configuración, secretos de servicios, `docker/`, memoria y dump Honcho. Restauración verifica hashes antes de escribir en un destino nuevo. | Código reparado |
| R04 | Skill Honcho instalada resuelve el launcher PM y conserva el perfil seleccionado. | Código reparado |
| R05 | Firecrawl exige respuesta con contenido Markdown, tres intentos acotados y salida no cero ante error. | Código reparado; imagen fijada pendiente de aceptación |
| D01 | Build de release rechaza árbol sucio/merge y verifica instalador remoto por SHA y contenido; desarrollo separado. | Código reparado; AppImage de desarrollo validado, release pendiente |
| D02 | Handshake de versión y UI lista; detección de salida prematura y rollback de AppImage. | Código reparado |
| D03 | Launcher recorre candidatos completos y ejecutables; descarta versiones parciales. | Código reparado |
| G01 | Redacción antes de escribir en capturas MCP compartidas o por servidor, incluso fallback. | Código reparado |
| G02 | `/start` Telegram conserva admisión, autorización y tópicos en foto y fallback de texto. | Código reparado |
| C01 | Eliminado parseo duplicado de slices; regresión verifica particiones disjuntas y cobertura completa. | Código reparado |
| C02 | Workflow Janitor Linux construye overlay, verifica metadatos/checksum y ejecuta smoke empaquetado; candidato requiere aceptación. | Implementado; ejecución remota pendiente |
| C03 | Corregidos errores propios y heredados de lint sin desactivar reglas. | Lints dirigidos aprobados; hook final pendiente |
| C04 | `cron/jobs.py` reconciliado con estable y auditor ampliado a módulos extraídos, cron, ACP y Janitor. | Código reparado |
| C05 | Auditor fuerza prefijos y formato Git estables; regresión con `diff.mnemonicPrefix=true`. | Código reparado |
| C06 | Lock website reproducible, instalación y build bilingüe. Sin críticas/moderadas; excepción acotada y con caducidad para braces 3.0.3. | Mitigado y documentado; vulnerabilidad sin parche aún presente |
| C07 | Autoría/licencia y catálogo regenerados. | Reparado; tres tests de snapshot y aislamiento aprobados |
| O01 | README e instrucciones actuales instalan Janitor y exigen Docker, MiniMax y Honcho. | Reparado |
| O02 | Inventario versionado de diferencias, consumidor, estado y sustituto; trece residuos Desktop retirados tras análisis de imports. Prototipos archivados como texto. | Reparado; inventario se verifica antes del commit |

## Validación local

- Gate canónico Janitor: 20 archivos, 249 tests aprobados, cero fallos; todas las regresiones incluidas.
- Gateway/MCP: 33 tests aprobados tras reproducir diez fallos previos.
- TUI: build y typecheck correctos; 1.639 tests aprobados con Python PM completo.
- Web: build y typecheck correctos; 429 tests aprobados.
- Desktop: typecheck completo y overlay correctos; 38 tests dirigidos aprobados; lint sin errores. Suite Electron: 3.650 aprobados, 24 omitidos y cuatro fallos por entorno, después aprobados en la repetición de los tres archivos afectados con PM.
- Bootstrap aislado: todas las etapas, assets, launcher y chat por la entrada real del proveedor aprobados con API de prueba. Esta prueba desactiva memoria externa en su turno de chat; no certifica memoria semántica.
- Dependencias de aplicación: npm audit registra cero críticas, altas o moderadas y ocho bajas.
- Website: instalación npm reproducible y build en inglés/chino aprobados. La excepción de braces vence el 29 de octubre de 2026; CI rechaza otras altas/críticas, cambios de versión, errores de audit y excepciones caducadas.
- Preservación: cinco checksums de backup correctos; cinco archivos OpenDesign idénticos al checkout original; sus archivos no rastreados siguen íntegros.

Los logs y artefactos locales se conservan fuera del árbol Git, en `../validation-evidence/r19/`, para no contaminar los scanners, snapshots o builds. No contienen las credenciales usadas en las comprobaciones.

## Condiciones que siguen bloqueando publicación estable

1. Completar el commit de recuperación y verificar el hook sin omisiones; ejecutar la suite upstream sobre ese commit inmutable.
2. Reconstruir y probar AppImage desde ese mismo SHA accesible, incluidos primer arranque y actualización entre versiones.
3. Validar memoria semántica real: la clave OpenAI instalada responde HTTP 401 al endpoint de embeddings y no hay credencial Honcho cloud configurada. No se han sustituido ni expuesto secretos.
4. Completar aceptación funcional de capacidades opcionales conservadas, incluida la imagen Firecrawl fijada. El scrape real aprobado contra el servicio existente acredita su API, no la imagen final.
5. Ejecutar aceptación Linux completa y registrar sus resultados antes de promover un candidato a Janitor v1.0.0.
