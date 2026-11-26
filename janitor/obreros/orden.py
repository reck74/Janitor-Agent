"""Comando ``janitor obreros``: lo usan el usuario en el terminal, el agente y la app.

Cada orden reconcilia primero los trabajos que quedaron a medias. Las que devuelven
datos aceptan ``--json``. Un rechazo sale con código 1; un uso incorrecto, con 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from janitor.obreros import trabajos
from janitor.obreros.encargo import MODOS
from janitor.obreros.trabajos import Rechazo

PROGRAMAS = ("claude", "codex")

AVISO_ACTIVAR = """\
Antes de activar los obreros, lee esto:

- Janitor encargará trabajo a Claude Code y a Codex, los programas que ya tienes
  instalados y con tu sesión. El contenido de cada encargo y los archivos que el
  obrero lea salen de tu equipo hacia Anthropic o hacia OpenAI.
- Cada trabajo consume tu plan o tu saldo con ese proveedor.
- El uso automático e intenso de una suscripción puede chocar con las condiciones
  del proveedor. Si te preocupa, usa en esos programas una clave de API.
- Janitor nunca lee ni copia tus credenciales: solo ejecuta los programas.
"""


def setup_parser(parser) -> None:
    sub = parser.add_subparsers(dest="obreros_orden")

    def con_json(p):
        p.add_argument("--json", action="store_true", help="Salida en JSON")
        return p

    con_json(sub.add_parser("estado", help="Programas detectados, activación, topes y trabajos en curso"))

    activar = sub.add_parser("activar", help="Activa los obreros en este perfil (pide confirmación)")
    activar.add_argument("--si", action="store_true", help="Confirma sin preguntar")
    activar.add_argument("--tope-tokens-dia", type=int, metavar="N",
                         help="Tokens (entrada + salida) permitidos en 24 horas")
    sub.add_parser("desactivar", help="Desactiva los obreros en este perfil")

    enviar = con_json(sub.add_parser("enviar", help="Encarga un trabajo a un obrero, en segundo plano"))
    enviar.add_argument("--programa", required=True, choices=PROGRAMAS)
    enviar.add_argument("--modo", required=True, choices=MODOS)
    enviar.add_argument("--carpeta", help="Carpeta del proyecto (solo en modo revisión), ruta absoluta")
    enviar.add_argument("--encargo", required=True, metavar="ARCHIVO.json|-",
                        help="Encargo en JSON (objetivo, contexto, entregables, restricciones); «-» lo lee de la entrada")
    enviar.add_argument("--modelo")
    enviar.add_argument("--origen", help="Quién lo pidió (conversación o perfil), para el aviso de fin")
    enviar.add_argument("--esperar", action="store_true", help="Espera a que termine")

    con_json(sub.add_parser("lista", help="Lista los trabajos"))
    con_json(sub.add_parser("ver", help="Muestra un trabajo y su resultado")).add_argument("id")
    seguir = con_json(sub.add_parser("seguir", help="Espera a que un trabajo termine"))
    seguir.add_argument("id")

    reanudar = con_json(sub.add_parser("reanudar", help="Otro turno de la conversación de un trabajo terminado"))
    reanudar.add_argument("id")
    reanudar.add_argument("--encargo", required=True, metavar="ARCHIVO.json|-")
    reanudar.add_argument("--modelo")
    reanudar.add_argument("--origen")
    reanudar.add_argument("--esperar", action="store_true")

    con_json(sub.add_parser("cancelar", help="Detiene un trabajo y todos sus procesos")).add_argument("id")


class _Contexto:
    def __init__(self, args, out, home, detectar, entrada, preguntar):
        self.args = args
        self.out = out
        self.home = home
        self.detectar = detectar
        self.entrada = entrada
        self.preguntar = preguntar

    @property
    def json(self) -> bool:
        return bool(getattr(self.args, "json", False))

    def emitir(self, datos) -> None:
        self.out(json.dumps(datos, ensure_ascii=False, indent=2))


def _leer_encargo(origen: str, entrada) -> dict:
    try:
        texto = entrada.read() if origen == "-" else Path(origen).read_text(encoding="utf-8")
    except OSError as exc:
        raise Rechazo(f"No se pudo leer el encargo «{origen}»: {exc.strerror or exc}") from exc
    try:
        return json.loads(texto)
    except ValueError as exc:
        raise Rechazo("El encargo no es JSON válido") from exc


def _linea(t: trabajos.Trabajo) -> str:
    d = t.a_dict()
    return f"{d['id']}  {d['programa']:<6} {d['modo']:<9} {d['estado']:<10} {d['origen'] or ''}"


def _mostrar(ctx: _Contexto, t: trabajos.Trabajo) -> None:
    if ctx.json:
        ctx.emitir(t.a_dict())
        return
    d = t.a_dict()
    ctx.out(f"Trabajo {d['id']}: {d['estado']}")
    for etiqueta, clave in (
        ("Programa", "programa"), ("Modo", "modo"), ("Carpeta", "carpeta"), ("Modelo", "modelo"),
        ("Origen", "origen"), ("Reanuda", "anterior"), ("Creado", "creado"), ("Fin", "fin"),
        ("Sesión", "sesion"), ("Tokens de entrada", "tokens_entrada"),
        ("Tokens de salida", "tokens_salida"), ("Coste estimado (USD)", "coste_usd"),
    ):
        if d[clave] is not None:
            ctx.out(f"  {etiqueta}: {d[clave]}")
    if d["detalle"]:
        ctx.out(f"  Detalle: {d['detalle']}")
    if d["respuesta"]:
        ctx.out("")
        ctx.out(d["respuesta"])


def _codigo_fin(t: trabajos.Trabajo) -> int:
    return 0 if t.estado in ("terminado", "en_cola", "en_curso") else 1


def _estado(ctx: _Contexto) -> int:
    from janitor.obreros import ajustes, deteccion

    home = trabajos._home(ctx.home)
    detectar = ctx.detectar or deteccion.detectar
    programas = {n: detectar(n) for n in PROGRAMAS}
    conf = ajustes.leer(home)
    en_curso = trabajos.activos(home)
    datos = {
        "activo": conf.activo,
        "topes": {
            "trabajos_a_la_vez": conf.trabajos_a_la_vez,
            "minutos_por_trabajo": conf.minutos_por_trabajo,
            "tope_tokens_dia": conf.tope_tokens_dia,
            "tokens_ultimas_24h": trabajos.tokens_ultimas_24h(home),
        },
        "programas": {
            n: {"instalado": p.ruta is not None, "version": p.version, "sesion": p.sesion,
                "disponible": p.disponible, "detalle": p.detalle}
            for n, p in programas.items()
        },
        "en_curso": [t.a_dict() for t in en_curso],
    }
    if ctx.json:
        ctx.emitir(datos)
        return 0
    ctx.out("Obreros: " + ("activados" if conf.activo else "desactivados (janitor obreros activar)"))
    for nombre, p in programas.items():
        ctx.out(f"  {nombre:<6} {p.detalle}")
    topes = datos["topes"]
    ctx.out(
        f"Topes: {topes['trabajos_a_la_vez']} a la vez, {topes['minutos_por_trabajo']:g} minutos por trabajo, "
        f"{topes['tope_tokens_dia'] or 'sin fijar'} tokens al día ({topes['tokens_ultimas_24h']} usados en 24 h)"
    )
    ctx.out(f"En curso: {len(en_curso)}")
    for t in en_curso:
        ctx.out("  " + _linea(t))
    return 0


def _activar(ctx: _Contexto) -> int:
    from janitor.obreros import ajustes

    home = trabajos._home(ctx.home)
    ctx.out(AVISO_ACTIVAR)
    tope = ctx.args.tope_tokens_dia
    if not ctx.args.si:
        if ctx.preguntar is None:
            raise Rechazo("Sin terminal para confirmar: repite con --si y --tope-tokens-dia N")
        respuesta = ctx.preguntar("¿Activar los obreros? Escribe «si» para confirmar: ").strip().lower()
        if respuesta not in ("si", "sí"):
            ctx.out("No se activó nada.")
            return 1
        if tope is None and ajustes.leer(home).tope_tokens_dia is None:
            texto = ctx.preguntar("Tope de tokens (entrada + salida) en 24 horas: ").strip()
            if not texto.isdigit():
                raise Rechazo("El tope de tokens debe ser un número entero")
            tope = int(texto)
    conf = trabajos.activar(tope, home)
    ctx.out(f"Obreros activados. Tope: {conf.tope_tokens_dia} tokens al día.")
    return 0


def _desactivar(ctx: _Contexto) -> int:
    trabajos.desactivar(ctx.home)
    ctx.out("Obreros desactivados. Los trabajos en curso siguen hasta terminar o cancelarse.")
    return 0


def _tras_envio(ctx: _Contexto, t: trabajos.Trabajo) -> int:
    if ctx.args.esperar:
        t = trabajos.esperar(t.id, ctx.home)
        _mostrar(ctx, t)
        return _codigo_fin(t)
    if ctx.json:
        ctx.emitir(t.a_dict())
    else:
        ctx.out(f"Trabajo {t.id} enviado a {t.datos['programa']}. Síguelo con «janitor obreros seguir {t.id}».")
    return 0


def _enviar(ctx: _Contexto) -> int:
    a = ctx.args
    t = trabajos.enviar(
        programa=a.programa, modo=a.modo, encargo=_leer_encargo(a.encargo, ctx.entrada),
        carpeta=a.carpeta, modelo=a.modelo, origen=a.origen, home=ctx.home, detectar=ctx.detectar,
    )
    return _tras_envio(ctx, t)


def _reanudar(ctx: _Contexto) -> int:
    a = ctx.args
    t = trabajos.reanudar(
        a.id, encargo=_leer_encargo(a.encargo, ctx.entrada), modelo=a.modelo, origen=a.origen,
        home=ctx.home, detectar=ctx.detectar,
    )
    return _tras_envio(ctx, t)


def _lista(ctx: _Contexto) -> int:
    lista = trabajos.listar(ctx.home)
    if ctx.json:
        ctx.emitir([t.a_dict() for t in lista])
    elif not lista:
        ctx.out("No hay trabajos.")
    else:
        for t in lista:
            ctx.out(_linea(t))
    return 0


def _ver(ctx: _Contexto) -> int:
    _mostrar(ctx, trabajos.leer(ctx.args.id, ctx.home))
    return 0


def _seguir(ctx: _Contexto) -> int:
    t = trabajos.esperar(ctx.args.id, ctx.home)
    _mostrar(ctx, t)
    return _codigo_fin(t)


def _cancelar(ctx: _Contexto) -> int:
    t = trabajos.cancelar(ctx.args.id, ctx.home)
    if ctx.json:
        ctx.emitir(t.a_dict())
    else:
        ctx.out(f"Trabajo {t.id}: {t.estado}.")
    return 0


_ORDENES = {
    "estado": _estado,
    "activar": _activar,
    "desactivar": _desactivar,
    "enviar": _enviar,
    "reanudar": _reanudar,
    "lista": _lista,
    "ver": _ver,
    "seguir": _seguir,
    "cancelar": _cancelar,
}


def _preguntar_por_defecto():
    return input if sys.stdin is not None and sys.stdin.isatty() else None


def handle(args, *, out=print, home=None, detectar=None, entrada=None, preguntar="terminal") -> int:
    orden = getattr(args, "obreros_orden", None) or "estado"
    manejador = _ORDENES.get(orden)
    if manejador is None:
        out(f"error: orden desconocida «{orden}»")
        return 2
    ctx = _Contexto(
        args, out, home, detectar,
        entrada if entrada is not None else sys.stdin,
        _preguntar_por_defecto() if preguntar == "terminal" else preguntar,
    )
    try:
        trabajos.reconciliar(home)
        return manejador(ctx)
    except (Rechazo, ValueError) as exc:
        if ctx.json:
            ctx.emitir({"error": str(exc)})
        else:
            out(f"error: {exc}")
        return 1


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="janitor obreros")
    setup_parser(parser)
    return handle(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
