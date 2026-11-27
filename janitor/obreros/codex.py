"""Adaptador del programa `codex` (comprobado contra Codex CLI 0.172.0).

Construye la línea de comando de `codex exec --json` y analiza sus eventos JSONL. No
lanza nada: quien lo use ejecuta `argv` con `cwd=carpeta` y el texto de
`encargo.a_prompt` por stdin (el «-» final le dice a Codex que lo lea de ahí).

El aislamiento `read-only` de Codex deja **leer todo el disco**: solo impide escribir.
Por eso no se usa. En consulta se le quita la herramienta de comandos (no puede leer
nada); en revisión corre con un perfil de permisos propio que solo deja leer la carpeta
del proyecto, lo mínimo del sistema y la instalación del propio Codex, sin escritura ni
red. Comprobado en Linux con un archivo señuelo fuera de la carpeta.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

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

__all__ = ["MODOS", "Resultado", "construir_argv", "entorno", "analizar_salida", "preparar"]

# Las dos políticas se fijan también como `-c`, porque `exec resume` no acepta
# `--sandbox` y lo que quede en efecto no puede depender de la configuración del usuario.
_POLITICA = ("-c", 'approval_policy="never"')
_PERFIL = "janitor_obrero"
_TIEMPO_SONDEO = 20.0

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


def _instalacion(ejecutable: str) -> str | None:
    """Carpeta que el aislamiento debe poder leer para ejecutar el propio Codex."""
    real = Path(os.path.realpath(ejecutable))
    raiz = real.parent.parent if real.parent.name == "bin" else real.parent
    # Nunca algo tan ancho como la carpeta personal o la raíz de un disco.
    if len(raiz.parts) < 4 or raiz == Path.home():
        raiz = real.parent
    return str(raiz) if len(raiz.parts) >= 3 else None


def preparar(ejecutable: str) -> dict:
    """Averigua qué carpetas necesita leer Codex para lanzar sus comandos aislados.

    El ejecutable que se encuentra en el PATH puede ser un lanzador (npm, mise…) y el
    binario real vivir en otra parte. En Linux se le pregunta al propio aislamiento: ahí
    dentro, el proceso 1 es ese binario.
    """
    rutas = {_instalacion(ejecutable)}
    if sys.platform.startswith("linux"):
        try:
            sondeo = subprocess.run(
                [ejecutable, "sandbox", "-c", 'sandbox_mode="read-only"', "--",
                 "readlink", "/proc/1/exe"],
                capture_output=True, text=True, timeout=_TIEMPO_SONDEO, stdin=subprocess.DEVNULL,
                env=entorno(os.environ),
            )
            real = sondeo.stdout.strip()
            if sondeo.returncode == 0 and os.path.isabs(real):
                rutas.add(_instalacion(real))
        except (OSError, subprocess.SubprocessError):
            pass  # sin sondeo, el perfil se queda con la ruta del lanzador
    return {"legibles": tuple(sorted(r for r in rutas if r))}


def _toml(texto: str) -> str:
    return json.dumps(texto, ensure_ascii=False)


def _permisos(modo: str, legibles: tuple[str, ...]) -> list[str]:
    if modo == "consulta":
        return ["--disable", "shell_tool"]
    entradas = ['":minimal"="read"', '":workspace_roots"={"."="read"}']
    entradas += [f"{_toml(ruta)}=\"read\"" for ruta in legibles]
    return [
        "-c", f'default_permissions="{_PERFIL}"',
        "-c", f"permissions.{_PERFIL}.filesystem={{{', '.join(entradas)}}}",
    ]


def construir_argv(
    ejecutable: str,
    *,
    modo: str,
    carpeta: str,
    modelo: str | None = None,
    sesion: str | None = None,
    legibles: tuple[str, ...] = (),
) -> list[str]:
    comprobar_modo(modo)
    comprobar_carpeta(carpeta)
    # `-a` solo existe antes de `exec`; `-C` también, para que valga en `resume`, que no
    # lo acepta después.
    argv = [ejecutable, "-a", "never", "-C", carpeta, "exec"]
    if sesion is not None:
        argv += ["resume", comprobar_sesion(sesion)]
    argv += ["--json", *_POLITICA, *_permisos(modo, legibles), *_AISLAMIENTO]
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
