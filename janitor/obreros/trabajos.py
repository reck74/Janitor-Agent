"""Registro y ciclo de vida de los trabajos de obrero (F7-03, F7-13).

Cada trabajo es un intento: se crea en ``<home>/obreros/<id>/`` y lo ejecuta un proceso
desligado (``janitor.obreros.ejecutor``) que no depende de que Janitor siga abierto.
Aquí está todo lo demás: autorización y topes en cada envío, reanudar con una sesión
explícita, cancelar, reconciliar lo que quedó a medias y el aviso de fin, una sola vez.

El home se resuelve en cada llamada (``get_hermes_home()``) y toda función acepta uno
explícito: un mismo proceso puede servir a varios perfiles.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from janitor.obreros import ajustes as ajustes_mod
from janitor.obreros import procesos
from janitor.obreros.encargo import (
    VARIABLE_PROFUNDIDAD,
    Encargo,
    a_prompt,
    comprobar_carpeta,
    comprobar_modelo,
    comprobar_modo,
    comprobar_sesion,
    validar,
)
from janitor.obreros.ejecutor import ADAPTADORES
from janitor.obreros.registro import (
    ACTIVOS,
    CARPETA_CONSULTA,
    EJECUTOR,
    ENTRADA,
    ESTADO,
    ESTADOS,
    FINALES,
    MARCA_AVISADO,
    MARCA_CANCELAR,
    REGISTRO_EJECUTOR,
    RESULTADO,
    TRABAJO,
    actualizar_estado,
    ahora,
    es_id,
    escribir_json,
    instante,
    leer_json,
    nuevo_id,
)

CARPETA_RAIZ = "obreros"

# Un trabajo en cola sin ejecutor conocido pasado este tiempo es que su lanzamiento falló.
GRACIA_ARRANQUE = 60.0
_ESPERA_CERROJO = 10.0
_ESPERA_ARRANQUE = 5.0
_CERROJO_VIEJO = 60.0
_CERROJO = ".envio.cerrojo"
_LIMITE_ORIGEN = 200

# Carpetas con credenciales o configuración personal que un obrero nunca debe ver.
_PERSONALES_PROTEGIDAS = (
    ".claude", ".codex", ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker",
    ".password-store", ".config/gcloud", ".local/share/keyrings",
)

Detectar = Callable[[str], object]


class Rechazo(Exception):
    """Un envío u orden que no se puede hacer; el mensaje va en español para el usuario."""


@dataclass(frozen=True)
class Trabajo:
    id: str
    ruta: Path
    datos: dict
    estado_datos: dict
    resultado: dict | None
    avisado: bool

    @property
    def estado(self) -> str:
        nombre = self.estado_datos.get("estado")
        return nombre if nombre in ESTADOS else "en_cola"

    @property
    def activo(self) -> bool:
        return self.estado in ACTIVOS

    @property
    def tokens(self) -> int:
        if not self.resultado:
            return 0
        return sum(
            v for v in (self.resultado.get("tokens_entrada"), self.resultado.get("tokens_salida"))
            if type(v) is int and v >= 0
        )

    def a_dict(self) -> dict:
        resultado = self.resultado or {}
        return {
            "id": self.id,
            "programa": self.datos.get("programa"),
            "modo": self.datos.get("modo"),
            "carpeta": self.datos.get("carpeta"),
            "modelo": self.datos.get("modelo"),
            "origen": self.datos.get("origen"),
            "anterior": self.datos.get("anterior"),
            "creado": self.datos.get("creado"),
            "inicio": self.estado_datos.get("inicio"),
            "fin": self.estado_datos.get("fin"),
            "estado": self.estado,
            "detalle": self.estado_datos.get("detalle", ""),
            "respuesta": resultado.get("respuesta"),
            "sesion": resultado.get("sesion"),
            "modelos": resultado.get("modelos"),
            "tokens_entrada": resultado.get("tokens_entrada"),
            "tokens_salida": resultado.get("tokens_salida"),
            "coste_usd": resultado.get("coste_usd"),
            "avisado": self.avisado,
        }


# ── Rutas ──────────────────────────────────────────────────────────────────


def _home(home) -> Path:
    if home is not None:
        return Path(home)
    from hermes_constants import get_hermes_home

    return get_hermes_home()


def raiz(home=None) -> Path:
    return _home(home) / CARPETA_RAIZ


def _ruta(id_trabajo: str, home) -> Path:
    # El id acaba en una ruta: nada que no tenga la forma exacta llega a construirla.
    if not es_id(id_trabajo):
        raise Rechazo(f"Identificador de trabajo no válido: «{id_trabajo}»")
    return raiz(home) / id_trabajo


# ── Lectura ────────────────────────────────────────────────────────────────


def _cargar(ruta: Path) -> Trabajo | None:
    datos = leer_json(ruta / TRABAJO)
    if datos is None or datos.get("id") != ruta.name:
        return None
    return Trabajo(
        id=ruta.name,
        ruta=ruta,
        datos=datos,
        estado_datos=leer_json(ruta / ESTADO) or {},
        resultado=leer_json(ruta / RESULTADO),
        avisado=(ruta / MARCA_AVISADO).exists(),
    )


def leer(id_trabajo: str, home=None) -> Trabajo:
    trabajo = _cargar(_ruta(id_trabajo, home))
    if trabajo is None:
        raise Rechazo(f"No existe el trabajo «{id_trabajo}» o su registro está dañado")
    return trabajo


def listar(home=None) -> list[Trabajo]:
    """Todos los trabajos legibles, del más antiguo al más reciente; los dañados se omiten."""
    base = raiz(home)
    if not base.is_dir():
        return []
    trabajos = (_cargar(r) for r in sorted(base.iterdir()) if es_id(r.name) and r.is_dir())
    return [t for t in trabajos if t is not None]


def activos(home=None) -> list[Trabajo]:
    return [t for t in listar(home) if t.activo]


def tokens_ultimas_24h(home=None) -> int:
    desde = datetime.now(timezone.utc) - timedelta(hours=24)
    total = 0
    for trabajo in listar(home):
        creado = instante(trabajo.datos.get("creado"))
        if creado is not None and creado >= desde:
            total += trabajo.tokens
    return total


# ── Reconciliación ─────────────────────────────────────────────────────────


def _ejecutor_de(trabajo: Trabajo) -> dict | None:
    return trabajo.estado_datos.get("proceso_ejecutor") or leer_json(trabajo.ruta / EJECUTOR)


def _reconciliar_uno(trabajo: Trabajo) -> str | None:
    """Cierra un trabajo activo cuyo ejecutor ya no vive; devuelve el estado nuevo o None."""
    if not trabajo.activo:
        return None
    ejecutor = _ejecutor_de(trabajo)
    if procesos.vive(ejecutor):
        return None
    if ejecutor is None:
        creado = instante(trabajo.datos.get("creado"))
        edad = (datetime.now(timezone.utc) - creado).total_seconds() if creado else GRACIA_ARRANQUE
        if edad < GRACIA_ARRANQUE:
            return None
    # Entre la lectura y la comprobación el ejecutor pudo publicar su resultado y salir:
    # con él ya muerto nadie más escribe, así que lo que se lea ahora es definitivo.
    trabajo = _cargar(trabajo.ruta) or trabajo
    if not trabajo.activo:
        return None
    # El programa pudo quedar huérfano si mataron al ejecutor desde fuera.
    procesos.matar_arbol(trabajo.estado_datos.get("proceso_programa"))

    resultado = trabajo.resultado
    if (trabajo.ruta / MARCA_CANCELAR).exists():
        final, detalle = "cancelado", "Cancelado por el usuario"
    elif resultado is not None and resultado.get("final") in FINALES:
        final = resultado["final"]
        detalle = resultado.get("detalle") if isinstance(resultado.get("detalle"), str) else ""
    else:
        final, detalle = "perdido", "El ejecutor terminó sin dejar resultado"
    actualizar_estado(trabajo.ruta, estado=final, fin=trabajo.estado_datos.get("fin") or ahora(), detalle=detalle)
    return final


def reconciliar(home=None) -> dict[str, str]:
    """Cierra los trabajos activos cuyo ejecutor ya no vive: con su resultado si lo dejó
    guardado, o como ``perdido``. Nunca relanza nada; repetirla no cambia nada más."""
    cerrados = {}
    for trabajo in listar(home):
        final = _reconciliar_uno(trabajo)
        if final is not None:
            cerrados[trabajo.id] = final
    return cerrados


# ── Autorización ───────────────────────────────────────────────────────────


def _misma(a: Path, b: Path) -> bool:
    # Por identidad en disco: en un volumen que no distingue mayúsculas, «.SSH» y «.ssh»
    # son la misma carpeta con dos grafías.
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _dentro(ruta: Path, base: Path) -> bool:
    if ruta == base or ruta.is_relative_to(base):
        return True
    return any(_misma(tramo, base) for tramo in (ruta, *ruta.parents))


def _protegidas(home: Path) -> list[Path]:
    personal = Path.home()
    rutas = [personal / p for p in _PERSONALES_PROTEGIDAS]
    rutas.append(home)
    # Un perfil vive en <raíz>/profiles/<nombre>; la raíz guarda el .env de todos.
    if home.parent.name == "profiles":
        rutas.append(home.parent.parent)
    for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
        if os.environ.get(variable):
            rutas.append(Path(os.environ[variable]))
    return [r.resolve() for r in rutas]


def comprobar_carpeta_revision(carpeta: str | None, home=None) -> Path:
    if not carpeta:
        raise Rechazo("En modo revisión hace falta --carpeta con la carpeta del proyecto")
    try:
        comprobar_carpeta(carpeta)
    except ValueError as exc:
        raise Rechazo(str(exc)) from exc
    ruta = Path(carpeta)
    if not ruta.is_dir():
        raise Rechazo(f"La carpeta «{carpeta}» no existe o no es una carpeta")
    real = ruta.resolve()
    if real == Path(real.anchor) or _dentro(Path.home().resolve(), real):
        raise Rechazo(
            "No se le da al obrero la raíz, tu carpeta personal entera ni una que la "
            "contenga: elige la carpeta del proyecto"
        )
    for protegida in _protegidas(_home(home).resolve()):
        if _dentro(real, protegida) or _dentro(protegida, real):
            raise Rechazo(
                f"La carpeta «{carpeta}» es o contiene configuración personal o de Janitor "
                "(credenciales incluidas): el obrero no puede verla"
            )
    return real


def _comprobar_origen(origen) -> str | None:
    if origen is None:
        return None
    if (
        not isinstance(origen, str)
        or not origen.strip()
        or len(origen) > _LIMITE_ORIGEN
        or any(not c.isprintable() for c in origen)
    ):
        raise Rechazo("El origen debe ser un texto corto de una línea")
    return origen


def _comprobar_activado(ajustes: ajustes_mod.Ajustes) -> None:
    if not ajustes.activo:
        raise Rechazo("Los obreros están desactivados en este perfil. Actívalos con «janitor obreros activar».")
    if ajustes.tope_tokens_dia is None:
        raise Rechazo(
            "Falta el tope de tokens por día. Fíjalo con «janitor obreros activar --tope-tokens-dia N»."
        )


def _comprobar_topes(ajustes: ajustes_mod.Ajustes, home: Path) -> None:
    en_marcha = len(activos(home))
    if en_marcha >= ajustes.trabajos_a_la_vez:
        raise Rechazo(
            f"Ya hay {en_marcha} trabajos en marcha y el tope es {ajustes.trabajos_a_la_vez} a la vez: "
            "espera a que termine alguno o cancélalo"
        )
    gastados = tokens_ultimas_24h(home)
    if gastados >= ajustes.tope_tokens_dia:
        raise Rechazo(
            f"Se alcanzó el tope de tokens del día ({gastados} de {ajustes.tope_tokens_dia} en las "
            "últimas 24 horas). Súbelo con «janitor obreros activar --tope-tokens-dia N» o espera."
        )


def _detectar_por_defecto(nombre: str):
    from janitor.obreros.deteccion import detectar

    return detectar(nombre)


@contextlib.contextmanager
def _cerrojo_envio(base: Path):
    """Exclusión entre envíos simultáneos, para que el tope de trabajos a la vez se cumpla."""
    base.mkdir(parents=True, exist_ok=True)
    ruta = base / _CERROJO
    limite = time.monotonic() + _ESPERA_CERROJO
    while True:
        try:
            os.close(os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            break
        except FileExistsError:
            try:
                edad = time.time() - ruta.stat().st_mtime
            except FileNotFoundError:
                continue
            # Un cerrojo tan viejo es de un envío que murió a medias.
            if edad > _CERROJO_VIEJO:
                ruta.unlink(missing_ok=True)
                continue
            if time.monotonic() > limite:
                raise Rechazo("Otro envío de obreros está en marcha; inténtalo de nuevo") from None
            time.sleep(0.1)
    try:
        yield
    finally:
        ruta.unlink(missing_ok=True)


# ── Envío ──────────────────────────────────────────────────────────────────


def _entorno_ejecutor(adaptador) -> dict[str, str]:
    import janitor

    entorno = adaptador.entorno(os.environ)
    # El ejecutor importa janitor aunque el paquete no esté instalado en el entorno.
    raiz_paquete = str(Path(janitor.__file__).resolve().parent.parent)
    entorno["PYTHONPATH"] = raiz_paquete
    return entorno


def _lanzar_ejecutor(ruta: Path, adaptador) -> None:
    with open(ruta / REGISTRO_EJECUTOR, "wb") as registro:
        # Salida a un archivo, nunca a una tubería: si Janitor se cierra, el ejecutor sigue.
        proceso = subprocess.Popen(
            [sys.executable, "-m", "janitor.obreros.ejecutor", str(ruta)],
            cwd=str(ruta),
            stdin=subprocess.DEVNULL,
            stdout=registro,
            stderr=registro,
            env=_entorno_ejecutor(adaptador),
            **procesos.opciones_desligado(),
        )
    ident = procesos.identidad(proceso.pid)
    if ident is not None:
        escribir_json(ruta / EJECUTOR, ident)
    # Recoge al hijo cuando termine, para que un proceso largo (pasarela, app) no acumule zombis.
    threading.Thread(target=proceso.wait, name=f"obrero-{ruta.name}", daemon=True).start()


def _a_encargo(encargo) -> Encargo:
    if isinstance(encargo, Encargo):
        return encargo
    try:
        return validar(encargo)
    except ValueError as exc:
        raise Rechazo(str(exc)) from exc


def _enviar(
    *,
    programa: str,
    modo: str,
    encargo,
    carpeta: str | None,
    modelo: str | None,
    origen: str | None,
    home,
    detectar: Detectar | None,
    sesion: str | None = None,
    anterior: str | None = None,
    carpeta_reanudada: Path | None = None,
) -> Trabajo:
    if os.environ.get(VARIABLE_PROFUNDIDAD):
        raise Rechazo("Un obrero no puede encargar trabajo a otro obrero")
    if programa not in ADAPTADORES:
        raise Rechazo(f"Programa desconocido «{programa}»: usa «claude» o «codex»")
    try:
        comprobar_modo(modo)
        if modelo is not None:
            comprobar_modelo(modelo)
        if sesion is not None:
            comprobar_sesion(sesion)
    except ValueError as exc:
        raise Rechazo(str(exc)) from exc
    origen = _comprobar_origen(origen)
    encargo = _a_encargo(encargo)
    home = _home(home)
    try:
        ajustes = ajustes_mod.leer(home)
    except ValueError as exc:
        raise Rechazo(str(exc)) from exc
    _comprobar_activado(ajustes)

    if carpeta_reanudada is not None:
        carpeta_proyecto = carpeta_reanudada
    elif modo == "revision":
        carpeta_proyecto = comprobar_carpeta_revision(carpeta, home)
    elif carpeta:
        raise Rechazo("En modo consulta el obrero no ve ninguna carpeta: quita --carpeta o usa el modo revisión")
    else:
        carpeta_proyecto = None

    detectado = (detectar or _detectar_por_defecto)(programa)
    if not getattr(detectado, "disponible", False):
        raise Rechazo(f"«{programa}» no se puede usar: {detectado.detalle}")

    base = raiz(home)
    with _cerrojo_envio(base):
        # Releídos con el cerrojo tomado: una desactivación o un tope más bajo que
        # llegaron mientras se esperaba también cuentan.
        try:
            ajustes = ajustes_mod.leer(home)
        except ValueError as exc:
            raise Rechazo(str(exc)) from exc
        _comprobar_activado(ajustes)
        reconciliar(home)
        _comprobar_topes(ajustes, home)
        id_trabajo = nuevo_id()
        ruta = base / id_trabajo
        ruta.mkdir()
        if carpeta_proyecto is None:
            carpeta_proyecto = ruta / CARPETA_CONSULTA
            carpeta_proyecto.mkdir()
        adaptador = ADAPTADORES[programa]
        argv = adaptador.construir_argv(
            detectado.ruta, modo=modo, carpeta=str(carpeta_proyecto), modelo=modelo, sesion=sesion,
        )
        (ruta / ENTRADA).write_text(a_prompt(encargo, modo), encoding="utf-8", newline="\n")
        escribir_json(ruta / TRABAJO, {
            "id": id_trabajo,
            "programa": programa,
            "modo": modo,
            "carpeta": str(carpeta_proyecto),
            "modelo": modelo,
            "sesion": sesion,
            "anterior": anterior,
            "origen": origen,
            "creado": ahora(),
            "tope_segundos": ajustes.minutos_por_trabajo * 60,
            "argv": argv,
        })
        actualizar_estado(ruta, estado="en_cola", detalle="")
        try:
            _lanzar_ejecutor(ruta, adaptador)
        except OSError as exc:
            actualizar_estado(
                ruta, estado="fallido", fin=ahora(),
                detalle=f"No se pudo lanzar el ejecutor ({type(exc).__name__})",
            )
            raise Rechazo("No se pudo lanzar el trabajo en segundo plano") from exc
    return leer(id_trabajo, home)


def enviar(
    *,
    programa: str,
    modo: str,
    encargo,
    carpeta: str | None = None,
    modelo: str | None = None,
    origen: str | None = None,
    home=None,
    detectar: Detectar | None = None,
) -> Trabajo:
    """Comprueba autorización y topes, crea el trabajo y lo lanza en segundo plano.

    ``encargo`` es un :class:`Encargo` o el dict que valida ``encargo.validar``.
    Lanza :class:`Rechazo` con el motivo en español si no se puede enviar.
    """
    return _enviar(
        programa=programa, modo=modo, encargo=encargo, carpeta=carpeta, modelo=modelo,
        origen=origen, home=home, detectar=detectar,
    )


def reanudar(
    id_anterior: str,
    *,
    encargo,
    modelo: str | None = None,
    origen: str | None = None,
    home=None,
    detectar: Detectar | None = None,
) -> Trabajo:
    """Otro turno de la conversación de ``id_anterior``: un trabajo nuevo con la sesión que
    ese trabajo devolvió (nunca «la última»), el mismo programa, modo y carpeta."""
    anterior = leer(id_anterior, home)
    if anterior.activo:
        raise Rechazo(f"El trabajo {id_anterior} sigue en marcha; espera a que termine")
    sesion = (anterior.resultado or {}).get("sesion")
    if not isinstance(sesion, str):
        raise Rechazo(f"El trabajo {id_anterior} no dejó una sesión que se pueda reanudar")
    modo = anterior.datos.get("modo")
    carpeta_reanudada = None
    carpeta = anterior.datos.get("carpeta")
    if modo == "consulta":
        # La sesión de Claude va ligada a la carpeta: se reanuda en la carpeta vacía de
        # aquel trabajo, recalculada aquí en vez de fiarse de lo guardado.
        carpeta_reanudada = anterior.ruta / CARPETA_CONSULTA
        if not carpeta_reanudada.is_dir():
            raise Rechazo(f"Falta la carpeta de consulta del trabajo {id_anterior}")
        carpeta = None
    return _enviar(
        programa=anterior.datos.get("programa"), modo=modo, encargo=encargo, carpeta=carpeta,
        modelo=modelo if modelo is not None else anterior.datos.get("modelo"),
        origen=origen if origen is not None else anterior.datos.get("origen"),
        home=home, detectar=detectar, sesion=sesion, anterior=id_anterior,
        carpeta_reanudada=carpeta_reanudada,
    )


# ── Cancelar, esperar, avisar ──────────────────────────────────────────────


def _esperar_arranque(trabajo: Trabajo) -> Trabajo:
    """Da tiempo al ejecutor a publicar el PID del programa o a cerrar el trabajo.

    El programa corre en su propio grupo: si se matara al ejecutor justo entre lanzarlo y
    anotarlo, quedaría vivo y sin dueño. Con la marca ya puesta, el ejecutor lo mata él
    mismo en cuanto lo anota; aquí solo se espera a que eso sea visible.
    """
    limite = time.monotonic() + _ESPERA_ARRANQUE
    while (
        trabajo.activo
        and not trabajo.estado_datos.get("proceso_programa")
        and procesos.vive(_ejecutor_de(trabajo))
        and time.monotonic() < limite
    ):
        time.sleep(0.05)
        trabajo = _cargar(trabajo.ruta) or trabajo
    return trabajo


def cancelar(id_trabajo: str, home=None) -> Trabajo:
    """Mata el árbol de procesos del trabajo (ejecutor, programa e hijos) y lo deja ``cancelado``."""
    trabajo = leer(id_trabajo, home)
    if not trabajo.activo:
        raise Rechazo(f"El trabajo {id_trabajo} ya terminó ({trabajo.estado})")
    # La marca va primero: un ejecutor que aún no lanzó el programa ya no lo lanzará.
    (trabajo.ruta / MARCA_CANCELAR).touch()
    trabajo = _esperar_arranque(trabajo)
    procesos.matar_arbol(_ejecutor_de(trabajo), trabajo.estado_datos.get("proceso_programa"))
    actual = leer(id_trabajo, home)
    # Si el ejecutor cerró el trabajo justo antes, su estado es el bueno.
    if actual.activo or actual.estado == "cancelado":
        actualizar_estado(trabajo.ruta, estado="cancelado", fin=ahora(), detalle="Cancelado por el usuario")
    # Lo canceló el propio usuario: no hace falta avisarle.
    marcar_avisado(id_trabajo, home)
    return leer(id_trabajo, home)


def esperar(id_trabajo: str, home=None, *, tope_segundos: float | None = None,
            intervalo: float = 1.0) -> Trabajo:
    """Espera a que el trabajo termine (o a ``tope_segundos``) y lo devuelve."""
    limite = None if tope_segundos is None else time.monotonic() + tope_segundos
    while True:
        trabajo = leer(id_trabajo, home)
        if _reconciliar_uno(trabajo) is not None:
            trabajo = leer(id_trabajo, home)
        if not trabajo.activo or (limite is not None and time.monotonic() >= limite):
            return trabajo
        time.sleep(intervalo)


def pendientes_de_aviso(origen: str | None = None, home=None) -> list[Trabajo]:
    """Trabajos terminados cuyo resultado todavía no se entregó (de ``origen``, si se da)."""
    reconciliar(home)
    return [
        t for t in listar(home)
        if not t.activo
        and t.estado != "cancelado"
        and not t.avisado
        and (origen is None or t.datos.get("origen") == origen)
    ]


def marcar_avisado(id_trabajo: str, home=None) -> bool:
    """Reserva la entrega del aviso. Solo un llamador recibe True: la marca se crea de forma
    exclusiva, así que dos lectores a la vez no entregan el mismo resultado dos veces."""
    ruta = leer(id_trabajo, home).ruta
    try:
        os.close(os.open(ruta / MARCA_AVISADO, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return False
    return True


# ── Activación ─────────────────────────────────────────────────────────────


def activar(tope_tokens_dia: int | None = None, home=None) -> ajustes_mod.Ajustes:
    home = _home(home)
    try:
        actuales = ajustes_mod.leer(home)
    except ValueError as exc:
        raise Rechazo(str(exc)) from exc
    tope = tope_tokens_dia if tope_tokens_dia is not None else actuales.tope_tokens_dia
    if type(tope) is not int or tope <= 0:
        raise Rechazo("Hace falta un tope de tokens por día (un entero mayor que 0)")
    _guardar(home, activo=True, tope_tokens_dia=tope)
    return ajustes_mod.leer(home)


def desactivar(home=None) -> ajustes_mod.Ajustes:
    home = _home(home)
    _guardar(home, activo=False)
    return ajustes_mod.leer(home)


def _guardar(home: Path, **cambios) -> None:
    try:
        ajustes_mod.guardar(home, **cambios)
    except RuntimeError as exc:
        # config.yaml ilegible: el guardado se niega a pisarlo y explica cómo arreglarlo.
        raise Rechazo(str(exc)) from exc
