"""Trabajos de obrero (F7-03, F7-13): registro en disco, ejecutor desligado, cancelación,
tope de tiempo, reconciliación tras una caída, aviso de fin una sola vez y perfiles A→B→A.

Los programas son falsos (un script de Python que hace de ``claude``/``codex``); nunca se
lanza el programa real ni se toca la red. Cada prueba con procesos lanza pocos y cortos.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil
import pytest

from janitor.obreros import procesos, registro, trabajos
from janitor.obreros.deteccion import Programa
from janitor.obreros.encargo import VARIABLE_PROFUNDIDAD
from janitor.obreros.trabajos import Rechazo

ENCARGO = {
    "objetivo": "Explica qué hace un cerrojo exclusivo",
    "contexto": "",
    "entregables": ["Una respuesta corta"],
    "restricciones": [],
}

SALIDA_CLAUDE = {
    "type": "result", "subtype": "success", "is_error": False, "result": "hola",
    "session_id": "ses-claude-1", "usage": {"input_tokens": 10, "output_tokens": 5},
    "total_cost_usd": 0.01,
}
SALIDA_CODEX = [
    {"type": "thread.started", "thread_id": "hilo-codex-1"},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "revisado"}},
    {"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 7}},
]
ESPERA = 60.0


# ── Ayudas ─────────────────────────────────────────────────────────────────


def configurar(home: Path, **obreros) -> None:
    valores = {"activo": True, "tope_tokens_dia": 100000, **obreros}
    lineas = "".join(f"    {k}: {json.dumps(v)}\n" for k, v in valores.items())
    (home / "config.yaml").write_text(
        f"# cabecera del usuario\nmodel: modelo-x\njanitor:\n  obreros:\n{lineas}", encoding="utf-8"
    )


def programa_falso(carpeta: Path, cuerpo: str) -> str:
    """Un ejecutable que lee stdin y corre ``cuerpo``; en Windows, un .cmd que llama a Python."""
    carpeta.mkdir(parents=True, exist_ok=True)
    codigo = (
        "import json, os, subprocess, sys, time\n"
        "entrada = sys.stdin.buffer.read().decode('utf-8')\n" + cuerpo
    )
    if sys.platform == "win32":
        script = carpeta / "falso.py"
        script.write_text(codigo, encoding="utf-8")
        lanzador = carpeta / "falso.cmd"
        lanzador.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return str(lanzador)
    lanzador = carpeta / "falso"
    lanzador.write_text(f"#!{sys.executable}\n{codigo}", encoding="utf-8")
    lanzador.chmod(0o755)
    return str(lanzador)


def anota_y_responde(anotacion: Path, salida: str) -> str:
    return (
        f"open({str(anotacion)!r}, 'w', encoding='utf-8').write(json.dumps({{"
        "'argv': sys.argv[1:], 'cwd': os.getcwd(), 'entrada': entrada,"
        f" 'profundidad': os.environ.get({VARIABLE_PROFUNDIDAD!r}),"
        " 'pythonpath': os.environ.get('PYTHONPATH')}))\n"
        f"sys.stdout.write({salida!r})\n"
    )


def duerme_con_nieto(pid_nieto: Path) -> str:
    return (
        "nieto = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(pid_nieto)!r}, 'w').write(str(nieto.pid))\n"
        "time.sleep(120)\n"
    )


def detector(ruta: str | None, sesion: bool = True):
    def detectar(nombre):
        detalle = "Instalado y con sesión iniciada." if sesion else "Instalado, pero sin sesión."
        return Programa(nombre, ruta, "1.0", sesion, None, detalle)
    return detectar


def fabricar(home: Path, *, estado="terminado", programa="claude", modo="consulta", origen=None,
             resultado=None, estado_extra=None, creado=None, carpeta=None) -> str:
    """Un trabajo escrito a mano en el formato de disco, sin lanzar procesos."""
    id_trabajo = registro.nuevo_id()
    ruta = trabajos.raiz(home) / id_trabajo
    (ruta / registro.CARPETA_CONSULTA).mkdir(parents=True)
    registro.escribir_json(ruta / registro.TRABAJO, {
        "id": id_trabajo, "programa": programa, "modo": modo,
        "carpeta": carpeta or str(ruta / registro.CARPETA_CONSULTA), "modelo": None,
        "sesion": None, "anterior": None, "origen": origen,
        "creado": creado or registro.ahora(), "tope_segundos": 60, "argv": ["x"],
    })
    registro.escribir_json(ruta / registro.ESTADO, {"estado": estado, **(estado_extra or {})})
    if resultado is not None:
        registro.escribir_json(ruta / registro.RESULTADO, resultado)
    return id_trabajo


def resultado_ok(final="terminado", sesion="ses-claude-1", tokens=(10, 5)) -> dict:
    return {
        "estado": "ok", "respuesta": "hola", "sesion": sesion, "modelos": [],
        "tokens_entrada": tokens[0], "tokens_salida": tokens[1], "coste_usd": None,
        "detalle": "", "codigo": 0, "final": final, "terminado": registro.ahora(),
    }


MUERTO = {"pid": os.getpid(), "arranque": 1.0}  # PID vivo, arranque distinto: un PID reutilizado


def esperar_archivo(ruta: Path) -> None:
    limite = time.monotonic() + ESPERA
    while not (ruta.is_file() and ruta.read_text().strip()):
        assert time.monotonic() < limite, f"no apareció {ruta}"
        time.sleep(0.2)


def muerto(pid: int) -> bool:
    try:
        proceso = psutil.Process(pid)
        proceso.wait(timeout=10)
    except psutil.NoSuchProcess:
        return True
    except psutil.TimeoutExpired:
        return False
    return True


@pytest.fixture
def home(tmp_path, monkeypatch):
    # La carpeta personal falsa no contiene tmp_path: las carpetas de proyecto de las
    # pruebas no chocan con la regla «ni la carpeta personal ni una que la contenga».
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "personal")
    monkeypatch.delenv(VARIABLE_PROFUNDIDAD, raising=False)
    h = tmp_path / "janitor-home"
    h.mkdir()
    configurar(h)
    return h


# ── Ciclo completo con el ejecutor real ────────────────────────────────────


def test_consulta_en_segundo_plano_de_punta_a_punta(home, tmp_path):
    anotacion = tmp_path / "anotacion.json"
    ruta = programa_falso(tmp_path / "bin", anota_y_responde(anotacion, json.dumps(SALIDA_CLAUDE)))

    enviado = trabajos.enviar(programa="claude", modo="consulta", encargo=ENCARGO,
                              origen="conversacion-1", home=home, detectar=detector(ruta))
    assert enviado.activo
    trabajo = trabajos.esperar(enviado.id, home, tope_segundos=ESPERA, intervalo=0.2)

    assert trabajo.estado == "terminado", trabajo.estado_datos
    vista = trabajo.a_dict()
    assert vista["respuesta"] == "hola" and vista["sesion"] == "ses-claude-1"
    assert trabajo.tokens == 15
    visto = json.loads(anotacion.read_text(encoding="utf-8"))
    # El obrero trabaja en la carpeta vacía del trabajo, con el encargo por stdin, marcado
    # contra la recursión y sin el PYTHONPATH que necesita el ejecutor.
    assert Path(visto["cwd"]).resolve() == (trabajo.ruta / registro.CARPETA_CONSULTA).resolve()
    assert ENCARGO["objetivo"] in visto["entrada"]
    assert visto["profundidad"] == "1" and visto["pythonpath"] is None
    assert "-p" in visto["argv"]
    assert procesos._identidad_valida(trabajo.estado_datos["proceso_ejecutor"])
    assert trabajos.tokens_ultimas_24h(home) == 15


def test_revision_con_codex_en_la_carpeta_del_proyecto(home, tmp_path):
    proyecto = tmp_path / "proyecto con espacios"
    proyecto.mkdir()
    anotacion = tmp_path / "anotacion.json"
    jsonl = "".join(json.dumps(e) + "\n" for e in SALIDA_CODEX)
    ruta = programa_falso(tmp_path / "bin", anota_y_responde(anotacion, jsonl))

    enviado = trabajos.enviar(programa="codex", modo="revision", encargo=ENCARGO,
                              carpeta=str(proyecto), home=home, detectar=detector(ruta))
    trabajo = trabajos.esperar(enviado.id, home, tope_segundos=ESPERA, intervalo=0.2)

    assert trabajo.estado == "terminado", trabajo.estado_datos
    assert trabajo.a_dict()["sesion"] == "hilo-codex-1"
    visto = json.loads(anotacion.read_text(encoding="utf-8"))
    assert Path(visto["cwd"]).resolve() == proyecto.resolve()
    assert visto["argv"][visto["argv"].index("-C") + 1] == str(proyecto.resolve())


def test_reanudar_usa_la_sesion_explicita_y_la_misma_carpeta(home, tmp_path):
    anterior = fabricar(home, origen="conversacion-1", resultado=resultado_ok(sesion="ses-anterior"))
    anotacion = tmp_path / "anotacion.json"
    ruta = programa_falso(tmp_path / "bin", anota_y_responde(anotacion, json.dumps(SALIDA_CLAUDE)))

    nuevo = trabajos.reanudar(anterior, encargo=ENCARGO, home=home, detectar=detector(ruta))
    trabajo = trabajos.esperar(nuevo.id, home, tope_segundos=ESPERA, intervalo=0.2)

    assert trabajo.estado == "terminado"
    assert trabajo.datos["anterior"] == anterior and trabajo.datos["origen"] == "conversacion-1"
    visto = json.loads(anotacion.read_text(encoding="utf-8"))
    assert visto["argv"][visto["argv"].index("--resume") + 1] == "ses-anterior"
    carpeta_anterior = trabajos.leer(anterior, home).ruta / registro.CARPETA_CONSULTA
    assert Path(visto["cwd"]).resolve() == carpeta_anterior.resolve()


def test_reanudar_sin_sesion_o_en_marcha_se_niega(home):
    sin_sesion = fabricar(home, resultado={**resultado_ok(), "sesion": None})
    en_marcha = fabricar(home, estado="en_curso",
                         estado_extra={"proceso_ejecutor": procesos.identidad_propia()})
    for id_trabajo in (sin_sesion, en_marcha):
        with pytest.raises(Rechazo):
            trabajos.reanudar(id_trabajo, encargo=ENCARGO, home=home, detectar=detector("/x"))


# Señales reales a procesos propios: al morir el ejecutor sus hijos cambian de padre y la
# guarda de conftest (que solo admite el subárbol de la prueba) los tomaría por ajenos.
@pytest.mark.live_system_guard_bypass
def test_cancelar_mata_el_arbol_entero(home, tmp_path):
    pid_nieto = tmp_path / "nieto.pid"
    ruta = programa_falso(tmp_path / "bin", duerme_con_nieto(pid_nieto))
    enviado = trabajos.enviar(programa="claude", modo="consulta", encargo=ENCARGO,
                              home=home, detectar=detector(ruta))
    esperar_archivo(pid_nieto)
    limite = time.monotonic() + ESPERA
    while "proceso_programa" not in (en_curso := trabajos.leer(enviado.id, home).estado_datos):
        assert time.monotonic() < limite
        time.sleep(0.2)

    trabajo = trabajos.cancelar(enviado.id, home)

    assert trabajo.estado == "cancelado" and trabajo.avisado
    for pid in (en_curso["proceso_ejecutor"]["pid"], en_curso["proceso_programa"]["pid"],
                int(pid_nieto.read_text())):
        assert muerto(pid), pid
    assert trabajos.pendientes_de_aviso(home=home) == []
    with pytest.raises(Rechazo):
        trabajos.cancelar(enviado.id, home)


def test_tope_de_tiempo_deja_el_trabajo_caducado(home, tmp_path):
    configurar(home, minutos_por_trabajo=0.05)  # 3 segundos
    pid_nieto = tmp_path / "nieto.pid"
    ruta = programa_falso(tmp_path / "bin", duerme_con_nieto(pid_nieto))
    enviado = trabajos.enviar(programa="claude", modo="consulta", encargo=ENCARGO,
                              home=home, detectar=detector(ruta))

    trabajo = trabajos.esperar(enviado.id, home, tope_segundos=ESPERA, intervalo=0.5)

    assert trabajo.estado == "caducado", trabajo.estado_datos
    assert trabajo.resultado["final"] == "caducado"
    assert muerto(int(pid_nieto.read_text()))


# ── Reconciliación tras una caída (sin procesos) ───────────────────────────


def test_caida_despues_de_guardar_el_resultado_lo_conserva(home):
    id_trabajo = fabricar(home, estado="en_curso", resultado=resultado_ok(),
                          estado_extra={"proceso_ejecutor": MUERTO})
    assert trabajos.reconciliar(home) == {id_trabajo: "terminado"}
    assert trabajos.leer(id_trabajo, home).estado == "terminado"
    assert trabajos.reconciliar(home) == {}


@pytest.mark.parametrize("resultado", [None, "{\"estado\": \"ok\", \"respu"])
def test_caida_antes_de_guardar_el_resultado_queda_perdido(home, resultado):
    id_trabajo = fabricar(home, estado="en_curso", estado_extra={"proceso_ejecutor": MUERTO})
    if resultado is not None:
        (trabajos.raiz(home) / id_trabajo / registro.RESULTADO).write_text(resultado)
    assert trabajos.reconciliar(home) == {id_trabajo: "perdido"}
    assert trabajos.leer(id_trabajo, home).estado == "perdido"


def test_reconciliar_no_pisa_un_resultado_publicado_mientras_miraba(home, monkeypatch):
    id_trabajo = fabricar(home, estado="en_curso", estado_extra={"proceso_ejecutor": MUERTO})
    ruta = trabajos.raiz(home) / id_trabajo

    def publica_y_muere(_ident):
        # El ejecutor cierra el trabajo justo después de que el reconciliador lo leyera.
        registro.escribir_json(ruta / registro.RESULTADO, resultado_ok())
        registro.actualizar_estado(ruta, estado="terminado", fin=registro.ahora(), detalle="")
        return False

    monkeypatch.setattr(procesos, "vive", publica_y_muere)
    assert trabajos.reconciliar(home) == {}
    assert trabajos.leer(id_trabajo, home).estado == "terminado"


def test_reconciliar_respeta_lo_vivo_y_la_gracia_de_arranque(home):
    vivo = fabricar(home, estado="en_curso",
                    estado_extra={"proceso_ejecutor": procesos.identidad_propia()})
    recien = fabricar(home, estado="en_cola")
    viejo = fabricar(home, estado="en_cola",
                     creado=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
    assert trabajos.reconciliar(home) == {viejo: "perdido"}
    assert trabajos.leer(vivo, home).estado == "en_curso"
    assert trabajos.leer(recien, home).estado == "en_cola"


def test_registros_danados_no_rompen_la_lista(home):
    bueno = fabricar(home, resultado=resultado_ok())
    roto = trabajos.raiz(home) / registro.nuevo_id()
    roto.mkdir()
    (roto / registro.TRABAJO).write_text("{ a medias")
    estado_roto = fabricar(home, estado="en_curso",
                           creado=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
    (trabajos.raiz(home) / estado_roto / registro.ESTADO).write_text("[1, 2")

    assert {t.id for t in trabajos.listar(home)} == {bueno, estado_roto}
    assert trabajos.reconciliar(home) == {estado_roto: "perdido"}
    with pytest.raises(Rechazo):
        trabajos.leer(roto.name, home)


@pytest.mark.parametrize("malo", ["../fuera", "20261126-000000-zzzzzzzz", ""])
def test_ids_no_validos_nunca_llegan_a_ser_ruta(home, malo):
    with pytest.raises(Rechazo):
        trabajos.leer(malo, home)
    with pytest.raises(Rechazo):
        trabajos.marcar_avisado(malo, home)


# ── Aviso de fin ───────────────────────────────────────────────────────────


def test_aviso_se_entrega_una_sola_vez_y_por_origen(home):
    a = fabricar(home, origen="conv-a", resultado=resultado_ok())
    b = fabricar(home, origen="conv-b", estado="fallido")
    fabricar(home, origen="conv-a", estado="cancelado")
    fabricar(home, origen="conv-a", estado="en_curso",
             estado_extra={"proceso_ejecutor": procesos.identidad_propia()})

    assert [t.id for t in trabajos.pendientes_de_aviso("conv-a", home)] == [a]
    assert {t.id for t in trabajos.pendientes_de_aviso(home=home)} == {a, b}
    assert trabajos.marcar_avisado(a, home) is True
    assert trabajos.marcar_avisado(a, home) is False
    assert trabajos.pendientes_de_aviso("conv-a", home) == []


def test_un_trabajo_perdido_tambien_se_avisa(home):
    id_trabajo = fabricar(home, estado="en_curso", origen="conv",
                          estado_extra={"proceso_ejecutor": MUERTO})
    pendientes = trabajos.pendientes_de_aviso("conv", home)
    assert [(t.id, t.estado) for t in pendientes] == [(id_trabajo, "perdido")]


# ── Perfiles A→B→A ─────────────────────────────────────────────────────────


def test_dos_homes_sin_fugas(tmp_path, monkeypatch):
    monkeypatch.delenv(VARIABLE_PROFUNDIDAD, raising=False)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    configurar(a)  # b queda sin activar

    monkeypatch.setenv("HERMES_HOME", str(a))
    id_a = fabricar(trabajos._home(None), origen="conv", resultado=resultado_ok())
    assert trabajos.raiz() == a / "obreros"

    monkeypatch.setenv("HERMES_HOME", str(b))
    assert trabajos.listar() == [] and trabajos.pendientes_de_aviso() == []
    with pytest.raises(Rechazo):
        trabajos.leer(id_a)
    with pytest.raises(Rechazo, match="desactivados"):
        trabajos.enviar(programa="claude", modo="consulta", encargo=ENCARGO, detectar=detector("/x"))

    monkeypatch.setenv("HERMES_HOME", str(a))
    assert [t.id for t in trabajos.pendientes_de_aviso("conv")] == [id_a]
    assert not (b / "obreros").exists() or list((b / "obreros").iterdir()) == []


# ── Autorización y topes ───────────────────────────────────────────────────


def _enviar(home, **kw):
    datos = {"programa": "claude", "modo": "consulta", "encargo": ENCARGO,
             "home": home, "detectar": detector("/no/se/lanza"), **kw}
    return trabajos.enviar(**datos)


def test_desactivado_o_sin_tope_de_tokens_se_niega(home):
    configurar(home, activo=False)
    with pytest.raises(Rechazo, match="janitor obreros activar"):
        _enviar(home)
    (home / "config.yaml").write_text("janitor:\n  obreros:\n    activo: true\n", encoding="utf-8")
    with pytest.raises(Rechazo, match="tope de tokens"):
        _enviar(home)
    assert trabajos.listar(home) == []


def test_desactivar_mientras_se_prepara_el_envio_tambien_cuenta(home):
    def detecta_y_desactiva(nombre):
        trabajos.desactivar(home)
        return detector("/no/se/lanza")(nombre)

    with pytest.raises(Rechazo, match="janitor obreros activar"):
        _enviar(home, detectar=detecta_y_desactiva)
    assert trabajos.listar(home) == []


@pytest.mark.macos_only
def test_otra_grafia_de_una_carpeta_protegida_se_rechaza(home, tmp_path):
    # El volumen por defecto de macOS no distingue mayúsculas: «.SSH» es «.ssh».
    (Path.home() / ".ssh").mkdir(parents=True)
    otra = Path.home() / ".SSH"
    if not otra.is_dir():
        pytest.skip("volumen que distingue mayúsculas")
    with pytest.raises(Rechazo):
        trabajos.comprobar_carpeta_revision(str(otra), home)


def test_recursion_se_niega(home, monkeypatch):
    monkeypatch.setenv(VARIABLE_PROFUNDIDAD, "1")
    with pytest.raises(Rechazo, match="otro obrero"):
        _enviar(home)


def test_programa_sin_sesion_o_desconocido_se_niega(home):
    with pytest.raises(Rechazo, match="sin sesión"):
        _enviar(home, detectar=detector("/x", sesion=False))
    with pytest.raises(Rechazo):
        _enviar(home, detectar=detector(None, sesion=False))
    with pytest.raises(Rechazo):
        _enviar(home, programa="gemini")
    with pytest.raises(Rechazo):
        _enviar(home, modo="construccion")
    with pytest.raises(Rechazo):
        _enviar(home, encargo={"objetivo": "x"})
    assert trabajos.listar(home) == []


def test_reglas_de_carpeta(home, tmp_path):
    personal = Path.home()
    (personal / ".ssh" / "claves").mkdir(parents=True)
    proyecto_en_personal = personal / "proyectos" / "web"
    proyecto_en_personal.mkdir(parents=True)

    with pytest.raises(Rechazo, match="consulta"):
        _enviar(home, carpeta=str(tmp_path))
    malas = [None, "relativa/carpeta", str(tmp_path / "no-existe"), str(personal), str(tmp_path),
             str(personal / ".ssh"), str(personal / ".ssh" / "claves"), str(home),
             str(home / "obreros"), tmp_path.anchor]
    for carpeta in malas:
        with pytest.raises(Rechazo):
            trabajos.comprobar_carpeta_revision(carpeta, home)
    assert trabajos.comprobar_carpeta_revision(str(proyecto_en_personal), home) == proyecto_en_personal.resolve()


def test_un_perfil_protege_la_raiz_de_janitor(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "personal")
    raiz_janitor = tmp_path / "raiz"
    perfil = raiz_janitor / "profiles" / "lupa"
    perfil.mkdir(parents=True)
    with pytest.raises(Rechazo):
        trabajos.comprobar_carpeta_revision(str(raiz_janitor), perfil)


def test_tope_de_trabajos_a_la_vez(home):
    for _ in range(2):
        fabricar(home, estado="en_curso", estado_extra={"proceso_ejecutor": procesos.identidad_propia()})
    with pytest.raises(Rechazo, match="a la vez"):
        _enviar(home)
    assert len(trabajos.listar(home)) == 2


def test_tope_de_tokens_cuenta_solo_las_ultimas_24_horas(home):
    configurar(home, tope_tokens_dia=1000)
    hace_dos_dias = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    fabricar(home, resultado=resultado_ok(tokens=(5000, 5000)), creado=hace_dos_dias)
    assert trabajos.tokens_ultimas_24h(home) == 0
    fabricar(home, resultado=resultado_ok(tokens=(900, 100)))
    with pytest.raises(Rechazo, match="tope de tokens del día"):
        _enviar(home)


def test_activar_y_desactivar_conservan_el_resto_del_config(home):
    (home / "config.yaml").write_text("# mi cabecera\nmodel: modelo-x\nterminal:\n  backend: local\n",
                                      encoding="utf-8")
    with pytest.raises(Rechazo):
        trabajos.activar(None, home)
    conf = trabajos.activar(5000, home)
    assert conf.activo and conf.tope_tokens_dia == 5000 and conf.trabajos_a_la_vez == 2
    texto = (home / "config.yaml").read_text(encoding="utf-8")
    assert texto.startswith("# mi cabecera") and "backend: local" in texto
    assert trabajos.desactivar(home).activo is False
    assert trabajos.activar(None, home).tope_tokens_dia == 5000
