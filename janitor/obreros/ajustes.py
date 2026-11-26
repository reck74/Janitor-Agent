"""Ajustes de los obreros en ``config.yaml`` del home (clave ``janitor.obreros``).

Se leen en cada envío, no al importar: un mismo proceso puede servir a varios perfiles.
La escritura usa el mismo mecanismo que ``janitor.catalog`` (lectura que se niega a
pisar un archivo ilegible, cabecera de comentarios conservada, reemplazo atómico).
"""

from __future__ import annotations

import copy
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

CLAVE = "obreros"

POR_DEFECTO_A_LA_VEZ = 2
POR_DEFECTO_MINUTOS = 30


@dataclass(frozen=True)
class Ajustes:
    activo: bool
    trabajos_a_la_vez: int
    minutos_por_trabajo: float
    tope_tokens_dia: int | None


def _positivo_entero(valor) -> int | None:
    return valor if type(valor) is int and valor > 0 else None


def _positivo(valor) -> float | None:
    # Se admiten decimales en los minutos (p. ej. 0.5): el tope real se guarda en segundos.
    return valor if type(valor) in (int, float) and valor > 0 else None


def _seccion(config) -> dict:
    janitor_cfg = config.get("janitor") if isinstance(config, dict) else None
    seccion = janitor_cfg.get(CLAVE) if isinstance(janitor_cfg, dict) else None
    return seccion if isinstance(seccion, dict) else {}


def leer(home: Path) -> Ajustes:
    ruta = Path(home) / "config.yaml"
    config = {}
    if ruta.is_file():
        try:
            config = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"{ruta} tiene un error de formato; corrígelo antes de usar los obreros") from exc
    seccion = _seccion(config)
    return Ajustes(
        activo=seccion.get("activo") is True,
        trabajos_a_la_vez=_positivo_entero(seccion.get("trabajos_a_la_vez")) or POR_DEFECTO_A_LA_VEZ,
        minutos_por_trabajo=_positivo(seccion.get("minutos_por_trabajo")) or POR_DEFECTO_MINUTOS,
        tope_tokens_dia=_positivo_entero(seccion.get("tope_tokens_dia")),
    )


def _escribir_nuevo(ruta: Path, texto: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{ruta.name}.", dir=str(ruta.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
        os.chmod(tmp, 0o600)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def guardar(home: Path, **cambios) -> None:
    """Fija las claves de ``janitor.obreros`` dadas en ``cambios``; el resto del archivo queda igual."""
    from hermes_cli.config import require_readable_config_before_write

    from janitor.catalog import _atomic_write, _leading_comments, dump_config

    home = Path(home)
    ruta = home / "config.yaml"
    config = require_readable_config_before_write(ruta)
    nuevo = copy.deepcopy(config)
    janitor_cfg = nuevo.get("janitor")
    if not isinstance(janitor_cfg, dict):
        janitor_cfg = nuevo["janitor"] = {}
    seccion = janitor_cfg.get(CLAVE)
    if not isinstance(seccion, dict):
        seccion = janitor_cfg[CLAVE] = {}
    seccion.update(cambios)
    if nuevo == config and ruta.exists():
        return
    if ruta.exists():
        cabecera = _leading_comments(ruta.read_text(encoding="utf-8"))
        _atomic_write(ruta, dump_config(nuevo, cabecera))
    else:
        home.mkdir(parents=True, exist_ok=True)
        _escribir_nuevo(ruta, dump_config(nuevo))
