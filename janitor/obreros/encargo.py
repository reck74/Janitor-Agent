"""Encargo para un obrero, su texto de entrada y el resultado común de los adaptadores.

Funciones puras: aquí no se lanza ningún proceso. Los adaptadores (`claude.py`,
`codex.py`) construyen la línea de comando y analizan la salida con estas piezas.
"""

from __future__ import annotations

import json
import ntpath
import posixpath
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Primera entrega (decisión 7.5 del plan de obreros): sin modo de escritura.
MODOS = ("consulta", "revision")

LIMITE_ENCARGO_BYTES = 64 * 1024
_CAMPOS = ("objetivo", "contexto", "entregables", "restricciones")

# Marcador anti-recursión: un obrero que vea esta variable no debe llamar a Janitor
# ni a otro obrero.
VARIABLE_PROFUNDIDAD = "JANITOR_OBRERO_PROFUNDIDAD"

# Lo mínimo para que el programa arranque y encuentre su propia sesión en los tres
# sistemas. Las claves de API quedan fuera a propósito: el obrero usa la sesión que
# el usuario inició en el programa, nunca credenciales que Janitor le pase.
_ENTORNO_COMUN = frozenset({
    # POSIX
    "HOME", "LANG", "LANGUAGE", "LOGNAME", "PATH", "SHELL", "TERM", "TMPDIR", "TZ",
    "USER", "DBUS_SESSION_BUS_ADDRESS", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
    "XDG_DATA_HOME", "XDG_RUNTIME_DIR", "XDG_STATE_HOME",
    # Windows
    "APPDATA", "COMSPEC", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATHEXT",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "SYSTEMDRIVE", "SYSTEMROOT",
    "TEMP", "TMP", "USERNAME", "USERPROFILE", "WINDIR",
    # Redes con proxy o certificados propios
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_DIR", "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
})

_ID_SESION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_NOMBRE_MODELO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,127}")


@dataclass(frozen=True)
class Encargo:
    objetivo: str
    contexto: str
    entregables: tuple[str, ...]
    restricciones: tuple[str, ...]


@dataclass(frozen=True)
class Resultado:
    estado: str  # "ok" | "error" | "bloqueado" | "salida_invalida"
    respuesta: str
    sesion: str | None
    modelos: tuple[str, ...]
    tokens_entrada: int | None
    tokens_salida: int | None
    coste_usd: float | None
    detalle: str


def _lista_de_textos(valor, campo: str) -> tuple[str, ...]:
    if not isinstance(valor, (list, tuple)) or any(
        not isinstance(v, str) or not v.strip() for v in valor
    ):
        raise ValueError(f"«{campo}» debe ser una lista de textos con contenido")
    return tuple(valor)


def validar(datos: dict) -> Encargo:
    if not isinstance(datos, dict):
        raise ValueError("El encargo debe ser un objeto con objetivo, contexto, entregables y restricciones")
    if set(datos) != set(_CAMPOS):
        faltan = sorted(set(_CAMPOS) - set(datos))
        sobran = sorted(set(datos) - set(_CAMPOS))
        partes = []
        if faltan:
            partes.append("faltan: " + ", ".join(faltan))
        if sobran:
            partes.append("sobran: " + ", ".join(map(str, sobran)))
        raise ValueError("El encargo lleva exactamente objetivo, contexto, entregables y restricciones (" + "; ".join(partes) + ")")
    if not isinstance(datos["objetivo"], str) or not datos["objetivo"].strip():
        raise ValueError("«objetivo» debe ser un texto con contenido")
    if not isinstance(datos["contexto"], str):
        raise ValueError("«contexto» debe ser texto (puede ir vacío)")
    entregables = _lista_de_textos(datos["entregables"], "entregables")
    if not entregables:
        raise ValueError("«entregables» necesita al menos un elemento")
    restricciones = _lista_de_textos(datos["restricciones"], "restricciones")
    tamano = len(json.dumps(datos, ensure_ascii=False).encode("utf-8"))
    if tamano > LIMITE_ENCARGO_BYTES:
        raise ValueError(f"El encargo ocupa {tamano} bytes y el límite es 64 KiB")
    return Encargo(datos["objetivo"], datos["contexto"], entregables, restricciones)


def comprobar_modo(modo: str) -> str:
    if modo == "construccion":
        raise ValueError(
            "El modo «construccion» (escribir en el proyecto) todavía no existe: "
            "esta entrega solo admite «consulta» y «revision»"
        )
    if modo not in MODOS:
        raise ValueError(f"Modo desconocido «{modo}»: usa «consulta» o «revision»")
    return modo


def comprobar_sesion(sesion: str) -> str:
    # El id viaja como argumento: uno que empiece por «-» se leería como opción.
    if not isinstance(sesion, str) or not _ID_SESION.fullmatch(sesion):
        raise ValueError("Identificador de sesión no válido")
    return sesion


def comprobar_modelo(modelo: str) -> str:
    if not isinstance(modelo, str) or not _NOMBRE_MODELO.fullmatch(modelo):
        raise ValueError("Nombre de modelo no válido")
    return modelo


def comprobar_carpeta(carpeta: str) -> str:
    # Relativa dependería del directorio del proceso que lanza, no del que eligió el usuario.
    if not isinstance(carpeta, str) or not carpeta or not _es_absoluta(carpeta):
        raise ValueError("La carpeta del proyecto debe ser una ruta absoluta")
    return carpeta


def _es_absoluta(ruta: str) -> bool:
    # Pura y sin depender del sistema en que corra: la ruta puede venir de cualquiera.
    return posixpath.isabs(ruta) or (ntpath.isabs(ruta) and bool(ntpath.splitdrive(ruta)[0]))


def entorno_comun(base: Mapping[str, str], extras: Iterable[str] = ()) -> dict[str, str]:
    permitidas = _ENTORNO_COMUN | {e.upper() for e in extras}
    # Windows no distingue mayúsculas en los nombres de variable.
    entorno = {
        clave: valor
        for clave, valor in base.items()
        if clave.upper() in permitidas or clave.upper().startswith("LC_")
    }
    entorno[VARIABLE_PROFUNDIDAD] = "1"
    return entorno


_ALCANCE = {
    "consulta": (
        "Modo consulta: no tienes herramientas. No leas archivos ni ejecutes comandos; "
        "responde solo con lo que dice este encargo."
    ),
    "revision": (
        "Modo revisión: solo lectura. Puedes leer y buscar en los archivos del proyecto, "
        "pero no modifiques, crees ni borres nada, ni ejecutes comandos que cambien el "
        "equipo. Cita rutas y evidencia en cada hallazgo."
    ),
}


def _viñetas(elementos: tuple[str, ...]) -> str:
    return "\n".join(f"- {e}" for e in elementos) if elementos else "- (ninguna)"


def a_prompt(encargo: Encargo, modo: str) -> str:
    comprobar_modo(modo)
    return (
        "Eres un obrero que recibe un encargo de Janitor.\n"
        f"{_ALCANCE[modo]}\n"
        "No llames a Janitor, a Claude, a Codex ni a ningún otro agente o subagente, "
        "y no delegues el trabajo. No leas credenciales ni archivos de configuración "
        "personales. Responde una sola vez, en español, con los entregables pedidos; si "
        "algo te lo impide, dilo y explica qué falta.\n\n"
        f"## Objetivo\n{encargo.objetivo}\n\n"
        f"## Contexto\n{encargo.contexto or '(sin contexto adicional)'}\n\n"
        f"## Entregables\n{_viñetas(encargo.entregables)}\n\n"
        f"## Restricciones\n{_viñetas(encargo.restricciones)}\n"
    )
