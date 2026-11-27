"""Formato en disco de un trabajo de obrero: nombres de archivo, estados, ids y JSON atómico.

Lo comparten la biblioteca (``trabajos``) y el ejecutor desligado (``ejecutor``), que
solo recibe la carpeta del trabajo y no sabe nada del home ni de la configuración.

Cada trabajo (= un intento) vive en ``<home>/obreros/<id>/``.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TRABAJO = "trabajo.json"
ENTRADA = "entrada.txt"
ESTADO = "estado.json"
SALIDA = "salida.log"
ERRORES = "errores.log"
RESULTADO = "resultado.json"
# Lo escribe quien lanza al ejecutor, para conocerlo antes de que el ejecutor arranque.
EJECUTOR = "ejecutor.json"
REGISTRO_EJECUTOR = "ejecutor.log"
MARCA_CANCELAR = "cancelar.marca"
MARCA_AVISADO = "avisado.marca"
# En modo consulta el obrero trabaja en esta carpeta vacía, sin ver ningún proyecto.
CARPETA_CONSULTA = "carpeta"

ACTIVOS = ("en_cola", "en_curso")
FINALES = ("terminado", "fallido", "bloqueado", "cancelado", "caducado", "perdido")
ESTADOS = ACTIVOS + FINALES

# Estado del trabajo según el que devuelve el adaptador al analizar la salida.
FINAL_POR_RESULTADO = {
    "ok": "terminado",
    "bloqueado": "bloqueado",
    "error": "fallido",
    "salida_invalida": "fallido",
}

_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{8}")


def nuevo_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4)


def es_id(valor) -> bool:
    return isinstance(valor, str) and _ID.fullmatch(valor) is not None


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def instante(texto) -> datetime | None:
    if not isinstance(texto, str):
        return None
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def escribir_json(ruta: Path, datos: dict) -> None:
    """Reemplazo atómico: un lector ve el archivo anterior o el nuevo, nunca uno a medias."""
    fd, tmp = tempfile.mkstemp(prefix=f".{ruta.name}.", dir=str(ruta.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def leer_json(ruta: Path) -> dict | None:
    """El objeto JSON de ``ruta``, o None si falta, está corrupto o no es un objeto."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return datos if isinstance(datos, dict) else None


def actualizar_estado(carpeta: Path, **campos) -> dict:
    """Mezcla ``campos`` con ``estado.json`` (un archivo ilegible se trata como vacío)."""
    ruta = Path(carpeta) / ESTADO
    estado = leer_json(ruta) or {}
    estado.update(campos)
    estado["actualizado"] = ahora()
    escribir_json(ruta, estado)
    return estado
