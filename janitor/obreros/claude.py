"""Adaptador del programa `claude` (comprobado contra Claude Code 2.1.332).

Construye la línea de comando y analiza la salida JSON de `claude -p`. No lanza nada:
quien lo use ejecuta `argv` con `cwd=carpeta` y el texto de `encargo.a_prompt` por
stdin. Claude no tiene opción para la carpeta de trabajo: es el directorio del proceso,
y `--restricted` confina las herramientas de archivo a él.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from .encargo import (
    MODOS,
    Resultado,
    comprobar_carpeta,
    comprobar_modelo,
    comprobar_modo,
    comprobar_sesion,
    entorno_comun,
)

__all__ = ["MODOS", "Resultado", "construir_argv", "entorno", "analizar_salida"]

_HERRAMIENTAS = {
    "consulta": (),
    "revision": ("Read", "Grep", "Glob"),
}

# Sin esto, `claude -p` cargaría los hooks, servidores MCP, plugins, skills y ajustes del
# usuario y del proyecto, y los ejecutaría sin preguntar.
_AISLAMIENTO = (
    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
    "--setting-sources", "",
    "--safe-mode",
    "--restricted",
    "--disable-slash-commands",
)

# `dontAsk` niega todo lo que no esté en `--allowedTools`, y `--permission-prompts none`
# garantiza que nadie aprueba por el usuario: lo que pediría permiso acaba en
# `permission_denials` y el trabajo vuelve al director como «bloqueado».
_PERMISOS = ("--permission-mode", "dontAsk", "--permission-prompts", "none")

# Sin `--bare` (desactiva la sesión de la suscripción) ni `--no-session-persistence`
# (impediría `--resume`).


def construir_argv(
    ejecutable: str,
    *,
    modo: str,
    carpeta: str,
    modelo: str | None = None,
    sesion: str | None = None,
) -> list[str]:
    comprobar_modo(modo)
    comprobar_carpeta(carpeta)
    herramientas = ",".join(_HERRAMIENTAS[modo])
    argv = [ejecutable, "-p", "--output-format", "json", "--tools", herramientas]
    argv += _AISLAMIENTO
    argv += _PERMISOS
    if herramientas:
        argv += ["--allowedTools", herramientas]
    if modelo is not None:
        argv.append(f"--model={comprobar_modelo(modelo)}")
    if sesion is not None:
        argv += ["--resume", comprobar_sesion(sesion)]
    return argv


def entorno(base: Mapping[str, str]) -> dict[str, str]:
    return entorno_comun(base, extras=("CLAUDE_CONFIG_DIR",))


def _entero(valor) -> int | None:
    return valor if type(valor) is int and valor >= 0 else None


def _tokens(uso) -> tuple[int | None, int | None]:
    if not isinstance(uso, dict):
        return None, None
    # La caché de prompt también es entrada procesada: sin sumarla, una conversación
    # reanudada parecería casi gratis.
    partes = [
        _entero(uso.get(k))
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    ]
    conocidas = [p for p in partes if p is not None]
    entrada = sum(conocidas) if conocidas else None
    return entrada, _entero(uso.get("output_tokens"))


def _modelos(uso_por_modelo) -> tuple[str, ...]:
    if not isinstance(uso_por_modelo, dict):
        return ()
    nombres = set()
    for nombre, datos in uso_por_modelo.items():
        canonico = datos.get("canonicalModel") if isinstance(datos, dict) else None
        elegido = canonico if isinstance(canonico, str) and canonico.strip() else nombre
        if isinstance(elegido, str) and elegido.strip():
            nombres.add(elegido)
    return tuple(sorted(nombres))


def _herramientas_negadas(negaciones) -> str:
    nombres = sorted({
        n.get("tool_name") for n in negaciones
        if isinstance(n, dict) and isinstance(n.get("tool_name"), str)
    })
    return ", ".join(nombres) if nombres else "sin nombre"


def analizar_salida(stdout: str, returncode: int) -> Resultado:
    try:
        datos = json.loads(stdout)
    except (ValueError, RecursionError):
        datos = None
    if not isinstance(datos, dict) or datos.get("type") != "result":
        return Resultado(
            "salida_invalida", "", None, (), None, None, None,
            f"La salida de claude no es el JSON de resultado esperado (código {returncode})",
        )

    respuesta = datos.get("result") if isinstance(datos.get("result"), str) else ""
    sesion = datos.get("session_id") if isinstance(datos.get("session_id"), str) else None
    entrada, salida = _tokens(datos.get("usage"))
    coste = datos.get("total_cost_usd")
    coste = float(coste) if type(coste) in (int, float) else None
    modelos = _modelos(datos.get("modelUsage"))

    negaciones = datos.get("permission_denials")
    if isinstance(negaciones, list) and negaciones:
        estado = "bloqueado"
        detalle = f"Claude pidió permisos que no tiene: {_herramientas_negadas(negaciones)}"
    elif datos.get("is_error") is not False or datos.get("subtype") != "success" or returncode != 0:
        estado = "error"
        detalle = f"Claude terminó con error ({datos.get('subtype')}, código {returncode})"
    elif not respuesta.strip():
        estado = "salida_invalida"
        detalle = "Claude terminó sin respuesta"
    else:
        estado = "ok"
        detalle = ""
    return Resultado(estado, respuesta, sesion, modelos, entrada, salida, coste, detalle)
