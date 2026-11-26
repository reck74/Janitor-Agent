"""Adaptador del programa `codex` (comprobado contra Codex CLI 0.172.0).

Construye la línea de comando de `codex exec --json` y analiza sus eventos JSONL. No
lanza nada: quien lo use ejecuta `argv` con `cwd=carpeta` y el texto de
`encargo.a_prompt` por stdin (el «-» final le dice a Codex que lo lea de ahí).

Codex no tiene un interruptor de «sin herramientas»: en modo consulta el aislamiento de
solo lectura es el límite real y el texto del encargo le pide no leer ni ejecutar nada.
Eso es una instrucción al modelo, no una garantía.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from .encargo import (
    MODOS,
    VARIABLE_PROFUNDIDAD,
    Resultado,
    comprobar_carpeta,
    comprobar_modelo,
    comprobar_modo,
    comprobar_sesion,
    entorno_comun,
)

__all__ = ["MODOS", "Resultado", "construir_argv", "entorno", "analizar_salida"]

# Las dos políticas se fijan también como `-c`, porque `exec resume` no acepta
# `--sandbox` y lo que quede en efecto no puede depender de la configuración del usuario.
_POLITICA = (
    "-c", 'sandbox_mode="read-only"',
    "-c", 'approval_policy="never"',
)

# Lo que el usuario tenga configurado (hooks, plugins, MCP, reglas, búsqueda web,
# subagentes) no entra en el obrero.
_AISLAMIENTO = (
    "--skip-git-repo-check",
    "--ignore-user-config",
    "--ignore-rules",
    "--disable", "hooks",
    "--disable", "plugins",
    "--disable", "apps",
    "--disable", "multi_agent",
    "--disable", "multi_agent_v2",
    "--disable", "browser_use",
    "--disable", "browser_use_external",
    "--disable", "computer_use",
    "--disable", "memories",
    "-c", 'web_search="disabled"',
    "-c", "mcp_servers={}",
    "-c", f'shell_environment_policy.set.{VARIABLE_PROFUNDIDAD}="1"',
    "-c", 'shell_environment_policy.exclude=["OPENAI_API_KEY","ANTHROPIC_API_KEY"]',
)

# Sin `--ephemeral`: la conversación debe quedar guardada para `exec resume`.


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
    # `-a` solo existe antes de `exec`; `-C` también, para que valga en `resume`, que no
    # lo acepta después.
    argv = [ejecutable, "-a", "never", "-C", carpeta, "exec"]
    if sesion is not None:
        argv += ["resume", comprobar_sesion(sesion)]
    else:
        argv += ["--sandbox", "read-only"]
    argv += ["--json", *_POLITICA, *_AISLAMIENTO]
    if modelo is not None:
        argv.append(f"--model={comprobar_modelo(modelo)}")
    argv.append("-")
    return argv


def entorno(base: Mapping[str, str]) -> dict[str, str]:
    return entorno_comun(base, extras=("CODEX_HOME",))


def _entero(valor) -> int | None:
    return valor if type(valor) is int and valor >= 0 else None


def _mensaje(evento: dict) -> str:
    error = evento.get("error")
    texto = error.get("message") if isinstance(error, dict) else evento.get("message")
    return texto if isinstance(texto, str) else ""


def _hilo(estado: dict, evento: dict) -> None:
    if isinstance(evento.get("thread_id"), str):
        estado["sesion"] = evento["thread_id"]


def _elemento(estado: dict, evento: dict) -> None:
    elemento = evento.get("item")
    if isinstance(elemento, dict) and elemento.get("type") == "agent_message":
        if isinstance(elemento.get("text"), str):
            estado["respuesta"] = elemento["text"]


def _turno_completado(estado: dict, evento: dict) -> None:
    estado["completado"] = True
    uso = evento.get("usage")
    if isinstance(uso, dict):
        for clave, destino in (("input_tokens", "entrada"), ("output_tokens", "salida")):
            valor = _entero(uso.get(clave))
            if valor is not None:
                estado[destino] = (estado[destino] or 0) + valor


def _fallo(estado: dict, evento: dict) -> None:
    estado["fallos"].append(_mensaje(evento) or evento["type"])


_EVENTOS = {
    "thread.started": _hilo,
    "item.completed": _elemento,
    "turn.completed": _turno_completado,
    "turn.failed": _fallo,
    "error": _fallo,
}


def analizar_salida(stdout: str, returncode: int) -> Resultado:
    estado = {
        "sesion": None, "respuesta": "", "completado": False,
        "entrada": None, "salida": None, "fallos": [],
    }
    for linea in stdout.splitlines():
        if not linea.strip():
            continue
        try:
            evento = json.loads(linea)
        except (ValueError, RecursionError):
            evento = None
        if not isinstance(evento, dict) or not isinstance(evento.get("type"), str):
            return Resultado(
                "salida_invalida", "", estado["sesion"], (), None, None, None,
                f"Una línea de la salida de codex no es un evento JSON (código {returncode})",
            )
        manejador = _EVENTOS.get(evento["type"])
        if manejador is not None:
            manejador(estado, evento)

    def resultado(estado_final: str, detalle: str) -> Resultado:
        return Resultado(
            estado_final, estado["respuesta"], estado["sesion"], (),
            estado["entrada"], estado["salida"], None, detalle,
        )

    if estado["fallos"]:
        return resultado("error", "Codex informó un fallo: " + "; ".join(estado["fallos"]))
    if returncode != 0:
        return resultado("error", f"Codex terminó con código {returncode}")
    if not estado["completado"]:
        return resultado("salida_invalida", "Codex no cerró el turno")
    if not estado["respuesta"].strip():
        return resultado("salida_invalida", "Codex terminó sin respuesta")
    return resultado("ok", "")
