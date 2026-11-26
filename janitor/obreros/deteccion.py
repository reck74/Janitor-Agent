"""Detección de los obreros: ¿está instalado ``claude`` / ``codex`` y tiene sesión?

Solo se ejecuta el binario del usuario (``--version`` y su orden de estado de
sesión). Nunca se abren ni se consultan los archivos de credenciales: el estado lo
dice el propio programa, y del resultado se conservan solo booleanos y una
etiqueta corta del método de acceso, nunca correo, organización ni claves.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

from janitor.obreros.encargo import entorno_comun

PROGRAMAS = ("claude", "codex")

TIEMPO_LIMITE = 10.0

Buscar = Callable[[str], "str | None"]
Ejecutar = Callable[[list[str], float], "tuple[int, str, str]"]

_ORDEN_SESION = {
    "claude": ("auth", "status"),
    "codex": ("login", "status"),
}
_ORDEN_LOGIN = {
    "claude": "claude auth login",
    "codex": "codex login",
}

_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)*(?:-[0-9A-Za-z.]+)?")
# authMethod de Claude se copia solo si tiene forma de etiqueta; cualquier otra
# cosa podría ser un identificador y se descarta.
_ETIQUETA = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,23}")
from janitor.obreros.encargo import entorno_comun


@dataclass(frozen=True)
class Programa:
    nombre: str
    ruta: str | None
    version: str | None
    sesion: bool | None
    metodo: str | None
    detalle: str

    @property
    def disponible(self) -> bool:
        return self.ruta is not None and self.sesion is True


def entorno_hijo(base: "os._Environ[str] | dict[str, str] | None" = None) -> dict[str, str]:
    """El mismo entorno con el que después se lanza al obrero.

    Si la detección mirase otro entorno (otro ``CODEX_HOME``, sin el proxy), diría
    «con sesión» de un programa que al trabajar no la encuentra.
    """
    origen = os.environ if base is None else base
    return entorno_comun(origen, extras=("CLAUDE_CONFIG_DIR", "CODEX_HOME"))


def buscar_programa(nombre: str) -> str | None:
    """Ruta del ejecutable: PATH y después donde lo dejan sus instaladores.

    Se usa el localizador de ``hermes_platform`` (no ``shutil.which``) porque el
    instalador nativo de Claude deja el binario en ``~/.local/bin`` y npm en su
    carpeta global, que a menudo no están en el PATH del proceso de la app.
    """
    from hermes_platform.resolver import locate_command
    from hermes_platform.resolver.known_dirs import (
        homebrew_dirs,
        node_tool_dirs,
        user_local_bin,
        windows_user_program_dirs,
    )

    resolucion = locate_command(
        nombre,
        known_dirs=(
            *user_local_bin(),
            *node_tool_dirs(),
            *homebrew_dirs(),
            *windows_user_program_dirs(),
        ),
    )
    return resolucion.command[0] if resolucion.command else None


def ejecutar_programa(argv: list[str], timeout: float) -> tuple[int, str, str]:
    """Ejecuta sin shell ni entrada, con entorno filtrado; propaga timeout/OSError."""
    resultado = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=entorno_hijo(),
        # Sin esto, en Windows cada comprobación abre una consola visible.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return resultado.returncode, resultado.stdout or "", resultado.stderr or ""


def _correr(ejecutar: Ejecutar, argv: list[str]) -> tuple[int, str, str] | str:
    """Devuelve la salida o, si no hubo respuesta, la causa en español."""
    try:
        return ejecutar(argv, TIEMPO_LIMITE)
    except subprocess.TimeoutExpired:
        return "no respondió a tiempo"
    except OSError:
        return "no se pudo ejecutar"


def _leer_version(salida: str) -> str | None:
    coincidencia = _VERSION.search(salida)
    return coincidencia.group(0) if coincidencia else None


def _sesion_claude(codigo: int, stdout: str) -> tuple[bool | None, str | None]:
    texto = stdout.strip()
    try:
        datos = json.loads(texto)
    except ValueError:
        # Algún aviso previo al JSON no debe impedir leerlo.
        inicio, fin = texto.find("{"), texto.rfind("}")
        try:
            datos = json.loads(texto[inicio:fin + 1]) if 0 <= inicio < fin else None
        except ValueError:
            datos = None
    if not isinstance(datos, dict) or not isinstance(datos.get("loggedIn"), bool):
        return None, None
    if not datos["loggedIn"]:
        return False, None
    if codigo != 0:
        return None, None
    metodo = datos.get("authMethod")
    if isinstance(metodo, str) and _ETIQUETA.fullmatch(metodo) and "@" not in metodo:
        return True, metodo
    return True, None


def _sesion_codex(codigo: int, stdout: str, stderr: str) -> tuple[bool | None, str | None]:
    # Codex escribe el estado en stderr; se mira también stdout por si cambia.
    linea = next(
        (l.strip() for l in (stdout + "\n" + stderr).splitlines() if l.strip()),
        "",
    )
    if codigo != 0 or not linea.startswith("Logged in"):
        return False, None
    # Con clave de API la línea incluye la clave enmascarada: solo se guarda el tipo.
    if "ChatGPT" in linea:
        return True, "ChatGPT"
    if "API key" in linea:
        return True, "api"
    return True, None


def detectar(
    nombre: str,
    *,
    buscar: Buscar = buscar_programa,
    ejecutar: Ejecutar = ejecutar_programa,
) -> Programa:
    if nombre not in PROGRAMAS:
        raise ValueError(f"programa desconocido: {nombre!r}; se esperaba uno de {PROGRAMAS}")

    ruta = buscar(nombre)
    if ruta is None:
        return Programa(
            nombre, None, None, None, None,
            f"No está instalado: no se encontró «{nombre}».",
        )

    version = None
    salida_version = _correr(ejecutar, [ruta, "--version"])
    if not isinstance(salida_version, str) and salida_version[0] == 0:
        version = _leer_version(salida_version[1] or salida_version[2])

    salida_sesion = _correr(ejecutar, [ruta, *_ORDEN_SESION[nombre]])
    if isinstance(salida_sesion, str):
        return Programa(
            nombre, ruta, version, None, None,
            f"Instalado, pero no se pudo comprobar la sesión: {salida_sesion}.",
        )

    codigo, stdout, stderr = salida_sesion
    if nombre == "claude":
        sesion, metodo = _sesion_claude(codigo, stdout)
    else:
        sesion, metodo = _sesion_codex(codigo, stdout, stderr)

    if sesion is True:
        detalle = "Instalado y con sesión iniciada" + (f" ({metodo})." if metodo else ".")
    elif sesion is False:
        detalle = f"Instalado, pero sin sesión: ejecuta «{_ORDEN_LOGIN[nombre]}»."
    else:
        detalle = "Instalado, pero su estado de sesión no se pudo interpretar."
    return Programa(nombre, ruta, version, sesion, metodo, detalle)


def detectar_todos(**kw) -> dict[str, Programa]:
    return {nombre: detectar(nombre, **kw) for nombre in PROGRAMAS}


def alguno_disponible(**kw) -> bool:
    return any(p.disponible for p in detectar_todos(**kw).values())
