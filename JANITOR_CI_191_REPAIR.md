# Revisión del checkpoint 191ca84b1f

Observación: 16 de octubre de 2026. Este documento distingue el resultado remoto del checkpoint de las reparaciones posteriores; no certifica Janitor 1.0.0 ni autoriza su publicación.

## CI remoto observado

- PR #80: https://github.com/reck74/Janitor-Agent/pull/80 (borrador).
- Suite estricta: https://github.com/reck74/Janitor-Agent/actions/runs/38805876916 (`strict_acceptance=1`, sin release).
- CI de PR: https://github.com/reck74/Janitor-Agent/actions/runs/38805819253.
- Linux E2E: 857 aprobados, 39 fallos y 16 omitidos. El checkpoint anterior registraba 811/74/16.
- Pasaron JS/TS, Windows E2E de procesos reales, los cuatro grupos Desktop update, upgrade PM/core/handoff/network/hosts, shards Python 2/5/6 y el gate canónico Janitor en Linux.
- Fallaron Desktop core, cuatro síntomas en shards Python 1/3/4, upgrade Git, tests Windows unitarios/instalación, y el gate canónico Windows. Supply-chain y atribución siguen pendientes; no quedan cubiertos por la autorización del baseline.
- Salud y tamaño de blobs pasaron en el CI del PR. La comparación aprobada conserva los límites y sólo reconoce contenido heredado idéntico al motor fijado.

## Reparaciones posteriores

Los recibos externos bajo `validation-evidence/r19/ci191-*` conservan logs rojos, resultados verdes y hashes. Los conteos de familias se solapan y no deben sumarse como una suite completa.

- Dashboard: mantiene íntegros los mensajes dentro del límite HTTP y rechaza exceso de partes; instalar MCP desde HTTP usa modo no interactivo aunque el servidor tenga TTY. 73 pruebas dirigidas aprobadas.
- Desktop core: comprueba los sockets que entregaron mensajes, sin exigir que permanezcan abiertos tras terminar. Conserva el control que detecta conexiones duplicadas. Prueba real Electron aprobada con renderizado software; no certifica GPU ni el AppImage final.
- Windows: importaciones Linux del fixture son diferidas, WAHA prepara PATH dentro de Bash y Git alternativo se verifica antes de usarlo. El instalador E2E limita a dos instalaciones simultáneas, registra capacidad de disco y sólo limpia directorios creados exclusivamente por la fixture, con evidencia exportada y sin procesos vivos. Requiere CI Windows nativo.
- El test Windows de commit de actualización usa confirmación de lock y señal de liberación, en lugar de asumir que PowerShell arrancará dentro de 25 segundos. Registra duración y diagnósticos antes del timeout; no amplía los límites.
- Python: referencias PM, streams MCP envueltos y el presupuesto serializado de páginas se comprueban por comportamiento. Se elimina una entrada de resolución ya inexistente.
- Adjuntar sesiones exige prueba HMAC de desafío fresco ligada a sesión, perfil y URL. El lease no viaja por HTTP. No existe todavía un productor distribuido que anuncie este contrato: los owners sin soporte conservan su lease y devuelven una acción concreta al usuario.
- Reinicios: identifica el mensaje original de Slack/Discord por transporte, conversación y usuario. Telegram conserva su guard de update_id.
- TUI: la selección explícita de sesión prevalece sobre el arranque automático y sobre respuestas tardías de creación. Suite completa 1.642 aprobados; PTY real 12 aprobados; build y typecheck correctos.
- Kanban: presupuesto durable para descomposición automática, límite de fanout, heartbeat por intento, logs separados por intento, handoff de revisión, pins ausentes y rechazo explícito de artefactos externos. E2E 15 aprobados; suite de 120 archivos: 902 aprobados y 4 omitidos.
- Proveedores: se validan por separado los adaptadores, el tratamiento de errores terminales, la recuperación de replay, aliases de discovery y el aislamiento de grants. Los resultados de simuladores HTTP/procesos locales no equivalen a certificación de cada servicio cloud.

- Vertex: conserva JSON Schema mediante el override nativo documentado de Google, después de construir la identidad de caché. 47 pruebas dirigidas aprobadas, incluida serialización HTTP del SDK; pendiente la certificación contra el servicio cloud real.

Gates locales del checkpoint: 370 pruebas canónicas aprobadas y 2 omitidas por plataforma; 327 regresiones de proveedores aprobadas en 17 archivos; diez guards correctos; salud sin bloqueos y un advisory existente; blobs dentro del contrato aprobado. El inventario y el auditor de directivas pasan. La conservación del checkout original se verificó contra el backup: HEAD, estado, patch y cuatro archivos no rastreados coinciden.

## Bloqueos que no deben ocultarse

La fixture Git fija el instalador histórico `v2026.8.16` en `df4b65147d7ddd74dd449f9067aabbca5aef0ec7`, verificando el commit y su ascendencia. Resuelve la ausencia de tags en CI, pero revela un fallo anterior al swap: ese instalador descarga aproximadamente 774 MB de Git frente a un presupuesto de 133 MB. La actualización funciona; la aceptación de ancho de banda sigue roja. No se modifica el límite ni se elimina el caso.

También requieren cierre: entrega tras crash/ack perdido; validación Windows nativa; una intermitencia del fixture Codex que perdió su diagnóstico inicial (se añadió diagnóstico para distinguirla); nueva aceptación del SHA final; memoria Honcho real; revisión de supply-chain/atribución; AppImage final y transición pública N→N+1. Los detalles actualizados están en `JANITOR_REPAIR_STATUS.md` y los recibos externos.

Los cambios del checkout original se conservan. Los checkpoints sólo pueden subirse a `codex/janitor-revival-1.0` para CI; este trabajo no fusiona `main`, no crea tags ni publica Janitor 1.0.0.
