"""Ejecutor desligado de un trabajo: ``python -m janitor.obreros.ejecutor <carpeta_del_trabajo>``.

Vive aparte del proceso de Janitor (que puede cerrarse o reiniciarse): lanza el
programa con la línea de comando guardada en ``trabajo.json``, le da ``entrada.txt``
por stdin, escribe su salida en archivos, respeta el tope de tiempo y deja
``resultado.json`` y, después, el estado final. Solo depende de la carpeta que recibe:
ni del home de Janitor ni de su configuración.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import time
from pathlib import Path

from janitor.obreros import claude, codex
from janitor.obreros.encargo import Resultado
from janitor.obreros.procesos import identidad, identidad_propia, matar_arbol, opciones_desligado
from janitor.obreros.registro import (
    ENTRADA,
    ERRORES,
    FINAL_POR_RESULTADO,
    MARCA_CANCELAR,
    RESULTADO,
    SALIDA,
    TRABAJO,
    actualizar_estado,
    ahora,
    es_id,
    escribir_json,
    leer_json,
)

ADAPTADORES = {"claude": claude, "codex": codex}


_INTENTOS = 2
_PAUSA_REINTENTO = 3.0


def _trabajo_valido(carpeta: Path) -> dict | None:
    datos = leer_json(carpeta / TRABAJO)
    if (
        datos is None
        or not es_id(carpeta.name)
        or datos.get("id") != carpeta.name
        or datos.get("programa") not in ADAPTADORES
        or not isinstance(datos.get("argv"), list)
        or not datos["argv"]
        or not all(isinstance(a, str) for a in datos["argv"])
        or not isinstance(datos.get("carpeta"), str)
        or type(datos.get("tope_segundos")) not in (int, float)
        or datos["tope_segundos"] <= 0
    ):
        return None
    return datos


def _lanzar(datos: dict, carpeta: Path, adaptador) -> tuple[int | None, bool]:
    """Ejecuta el programa; devuelve su código (None si no arrancó) y si caducó."""
    with (
        open(carpeta / ENTRADA, "rb") as entrada,
        open(carpeta / SALIDA, "wb") as salida,
        open(carpeta / ERRORES, "wb") as errores,
    ):
        # Una cancelación que llegó mientras se preparaba el lanzamiento.
        if (carpeta / MARCA_CANCELAR).exists():
            return None, False
        try:
            proceso = subprocess.Popen(
                datos["argv"],
                cwd=datos["carpeta"],
                stdin=entrada,
                stdout=salida,
                stderr=errores,
                env=adaptador.entorno(os.environ),
                # Grupo propio: al caducar se mata al programa y a sus hijos sin tocar al ejecutor.
                **opciones_desligado(),
            )
        except OSError as exc:
            errores.write(f"No se pudo ejecutar el programa: {type(exc).__name__}\n".encode())
            return None, False
        programa = identidad(proceso.pid)
        actualizar_estado(carpeta, proceso_programa=programa)
        # Una cancelación que llegó entre la comprobación inicial y el arranque.
        if (carpeta / MARCA_CANCELAR).exists():
            matar_arbol(programa)
        try:
            return proceso.wait(timeout=datos["tope_segundos"]), False
        except subprocess.TimeoutExpired:
            matar_arbol(programa)
            return proceso.wait(), True


def ejecutar(carpeta: Path) -> int:
    datos = _trabajo_valido(carpeta)
    if datos is None:
        print("Carpeta de trabajo no válida", file=sys.stderr)
        return 2
    if (carpeta / MARCA_CANCELAR).exists():
        actualizar_estado(carpeta, estado="cancelado", fin=ahora(), detalle="Cancelado antes de empezar")
        return 0
    actualizar_estado(carpeta, estado="en_curso", inicio=ahora(), proceso_ejecutor=identidad_propia())

    adaptador = ADAPTADORES[datos["programa"]]
    for intento in range(_INTENTOS):
        codigo, caducado = _lanzar(datos, carpeta, adaptador)
        if codigo is None:
            resultado = Resultado(
                "error", "", None, (), None, None, None,
                f"No se pudo ejecutar «{datos['programa']}»",
            )
            break
        stdout = (carpeta / SALIDA).read_text(encoding="utf-8", errors="replace")
        resultado = adaptador.analizar_salida(stdout, codigo)
        # El programa a veces sale sin escribir nada mientras termina de arrancar (visto con
        # Claude cargando los ajustes de la organización): no gastó nada y se repite una vez.
        arranque_fallido = resultado.estado == "salida_invalida" and not stdout.strip()
        if not arranque_fallido or caducado or (carpeta / MARCA_CANCELAR).exists():
            break
        if intento + 1 < _INTENTOS:
            time.sleep(_PAUSA_REINTENTO)

    minutos = datos["tope_segundos"] / 60
    if (carpeta / MARCA_CANCELAR).exists():
        final, detalle = "cancelado", "Cancelado por el usuario"
    elif caducado:
        final, detalle = "caducado", f"Superó el tope de {minutos:g} minutos y se detuvo"
    else:
        final, detalle = FINAL_POR_RESULTADO[resultado.estado], resultado.detalle

    # Primero el resultado y después el estado: si el ejecutor muere entre los dos, la
    # reconciliación cierra el trabajo con este resultado en vez de darlo por perdido.
    escribir_json(carpeta / RESULTADO, {
        **dataclasses.asdict(resultado),
        "codigo": codigo,
        "final": final,
        "terminado": ahora(),
    })
    actualizar_estado(carpeta, estado=final, fin=ahora(), detalle=detalle)
    return 0


def main(argv: list[str] | None = None) -> int:
    argumentos = sys.argv[1:] if argv is None else argv
    if len(argumentos) != 1:
        print("uso: python -m janitor.obreros.ejecutor <carpeta_del_trabajo>", file=sys.stderr)
        return 2
    carpeta = Path(argumentos[0])
    try:
        return ejecutar(carpeta)
    except Exception as exc:
        # Sin esto el trabajo quedaría «en_curso» hasta que la reconciliación lo diera
        # por perdido sin decir por qué.
        if _trabajo_valido(carpeta) is not None:
            actualizar_estado(
                carpeta, estado="fallido", fin=ahora(),
                detalle=f"Error interno del ejecutor ({type(exc).__name__})",
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
