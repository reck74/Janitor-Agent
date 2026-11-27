"""Procesos de los trabajos: identidad, si siguen vivos, cómo se lanzan desligados y cómo
se mata su árbol en los tres sistemas.

Un proceso se identifica por PID **y** hora de arranque: un PID solo puede haberse
reutilizado por otro proceso, y matar a ese otro sería mucho peor que no matar nada.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys

import psutil

# psutil calcula la hora de arranque a partir del arranque del equipo; dos lecturas del
# mismo proceso coinciden, pero se deja margen por redondeos entre llamadas.
_MARGEN_ARRANQUE = 1.0
_ESPERA_TERMINAR = 3.0
_ESPERA_MATAR = 5.0


def identidad(pid: int) -> dict | None:
    try:
        return {"pid": pid, "arranque": psutil.Process(pid).create_time()}
    except psutil.Error:
        return None


def identidad_propia() -> dict:
    return {"pid": os.getpid(), "arranque": psutil.Process().create_time()}


def _identidad_valida(ident) -> bool:
    return (
        isinstance(ident, dict)
        and type(ident.get("pid")) is int
        and ident["pid"] > 0
        and type(ident.get("arranque")) in (int, float)
    )


def _proceso(ident) -> psutil.Process | None:
    """El proceso de ``ident`` si sigue vivo y es el mismo (no un PID reutilizado)."""
    if not _identidad_valida(ident):
        return None
    try:
        proceso = psutil.Process(ident["pid"])
        if abs(proceso.create_time() - ident["arranque"]) > _MARGEN_ARRANQUE:
            return None
        # Un hijo que terminó y su padre aún no recogió sigue en la tabla como zombi.
        if proceso.status() == psutil.STATUS_ZOMBIE:
            return None
    except psutil.Error:
        return None
    return proceso


def vive(ident) -> bool:
    return _proceso(ident) is not None


def opciones_desligado() -> dict:
    """Opciones de ``Popen`` para que el hijo no muera con quien lo lanza ni abra consola."""
    if sys.platform == "win32":
        return {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        }
    return {"start_new_session": True}


def _grupos_encabezados(raices) -> list[int]:
    """Grupos que encabezan las raíces. Se anotan antes de matar: muerto el líder, su grupo
    sigue existiendo con los nietos que cambiaron de padre, y la señal al grupo los alcanza."""
    if sys.platform == "win32":
        return []
    grupos = []
    for raiz in raices:
        with contextlib.suppress(OSError):
            if os.getpgid(raiz.pid) == raiz.pid:
                grupos.append(raiz.pid)
    return grupos


def _senal_grupos(grupos: list[int], senal: int) -> None:
    for grupo in grupos:
        # El grupo puede haberse vaciado ya.
        with contextlib.suppress(OSError):
            os.killpg(grupo, senal)


def matar_arbol(*idents) -> bool:
    """Termina cada proceso de ``idents`` que siga vivo junto con todos sus descendientes.

    Devuelve si había algo vivo. Primero pide terminar y, pasado un momento, mata.
    """
    raices = [p for p in (_proceso(i) for i in idents) if p is not None]
    if not raices:
        return False
    grupos = _grupos_encabezados(raices)
    # La lista se toma antes de matar y se recorre de las hojas a la raíz: muerto un padre,
    # sus hijos cambian de padre y ya no cuelgan de él.
    todos: dict[int, psutil.Process] = {}
    for raiz in raices:
        with contextlib.suppress(psutil.Error):
            for hijo in reversed(raiz.children(recursive=True)):
                todos.setdefault(hijo.pid, hijo)
        todos.setdefault(raiz.pid, raiz)

    for proceso in todos.values():
        # Puede haber terminado entre la lista y la señal.
        with contextlib.suppress(psutil.NoSuchProcess):
            proceso.terminate()
    _senal_grupos(grupos, signal.SIGTERM)
    _, quedan = psutil.wait_procs(list(todos.values()), timeout=_ESPERA_TERMINAR)
    for proceso in quedan:
        with contextlib.suppress(psutil.NoSuchProcess):
            proceso.kill()
    if sys.platform != "win32":
        _senal_grupos(grupos, signal.SIGKILL)
    if quedan:
        psutil.wait_procs(quedan, timeout=_ESPERA_MATAR)
    return True
