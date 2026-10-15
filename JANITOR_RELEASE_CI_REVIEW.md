# Revisión de controles de publicación heredados

Estado: pendiente; no se ha modificado ningún gate para aceptar estos resultados.

## Patrones de ejecución codificada

El scanner supply-chain detecta cinco líneas en cuatro archivos. Los cuatro archivos son idénticos por objeto Git al motor Hermes v0.22.2 fijado:

| Archivo | Objeto Git verificado |
| --- | --- |
| `hermes_cli/_launchers.py` | `61ca4d8ef779675d012d9436fe1d10a6ed837cb0` |
| `tools/file_operations.py` | `1a93283f8c99617803753183f8b64ba040cf4cf6` |
| `tests-js/scripts/desktop-smoke.test.ts` | `490dadc9345f615efe6774fa532958be6459772d` |
| `tests/gateway/test_gateway_inline_bootstrap_identity.py` | `c51d58080488f240b470179d6aaa15278235af28` |

La revisión del flujo encuentra estos usos:

- `_launchers.py:300`: codifica el script generado por `_launcher_script` para transportarlo a través del quoting de `cmd.exe`; no descarga un payload. Es el fallback cuando no puede usar el launcher ejecutable de distlib.
- `file_operations.py:730`: transporta los programas Python construidos internamente para lectura UTF-16 y borrado de archivos. Las rutas se introducen con `json.dumps`; el intérprete pasa por el escape del backend. Mantiene las verificaciones de acceso antes de borrar.
- `desktop-smoke.test.ts:506,529`: escribe launchers sintéticos en directorios temporales para verificar que el settle usa el intérprete correcto; el texto `eA==` es dato de prueba.
- `test_gateway_inline_bootstrap_identity.py:33`: construye representaciones de argv para los lectores de identidad del gateway; comprueba clasificación de comandos.

Esta evidencia explica los positivos del patrón; la coincidencia de SHA por sí sola no acredita seguridad. No se ha partido ninguna línea para eludir el scanner, ni añadido excepciones, ni cambiado sus patrones. El gate sigue fallando y requiere una decisión de revisión antes de publicar.

## Atribución

Se consultó la asociación `author.login` del API de commits de GitHub y se añadieron 17 archivos de mapping con enlace al commit público que respalda cada identidad. No se usó la mera existencia de un nombre de usuario como prueba.

Continúan pendientes los emails sin asociación, los genéricos (`you@example.com` se asocia a `invalid-email-address`, lo que no demuestra autoría) y `Halldrix@users.noreply.github.com`, que colisiona con el archivo existente en minúsculas. No se creó un segundo archivo incompatible con macOS/Windows ni se inventaron identidades. La evidencia completa está en `validation-evidence/r19/attribution-github-evidence.json` fuera del árbol.

La propuesta separada sobre salud y tamaño de blobs está en `JANITOR_CI_BASELINE_PROPOSAL.md`. No cubre ni autoriza cambios en estos dos controles.
