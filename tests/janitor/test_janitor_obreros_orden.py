"""Comando ``janitor obreros`` (F7-05, F7-10 mínimo): analizador de argumentos, códigos de
salida, ``--json``, activación con aviso y registro en el plugin Janitor."""

from __future__ import annotations

import io
import json
import sys
from argparse import ArgumentParser
from pathlib import Path

import pytest

from janitor.obreros import orden, registro, trabajos
from janitor.obreros.deteccion import Programa
from janitor.obreros.encargo import VARIABLE_PROFUNDIDAD

ENCARGO = {
    "objetivo": "Di hola",
    "contexto": "",
    "entregables": ["Un saludo"],
    "restricciones": [],
}
SALIDA_CLAUDE = {
    "type": "result", "subtype": "success", "is_error": False, "result": "hola",
    "session_id": "ses-1", "usage": {"input_tokens": 3, "output_tokens": 2},
}


def parser() -> ArgumentParser:
    p = ArgumentParser(prog="janitor obreros")
    orden.setup_parser(p)
    return p


def detector(ruta="/no/se/lanza", sesion=True):
    return lambda n: Programa(n, ruta, "1.0", sesion, None, "Instalado y con sesión iniciada.")


class Consola:
    def __init__(self):
        self.lineas: list[str] = []

    def __call__(self, texto=""):
        self.lineas.append(str(texto))

    @property
    def texto(self) -> str:
        return "\n".join(self.lineas)

    def json(self):
        return json.loads(self.texto)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "personal")
    monkeypatch.delenv(VARIABLE_PROFUNDIDAD, raising=False)
    h = tmp_path / "janitor-home"
    h.mkdir()
    (h / "config.yaml").write_text(
        "janitor:\n  obreros:\n    activo: true\n    tope_tokens_dia: 10000\n", encoding="utf-8"
    )
    return h


def correr(home, argv, *, entrada=None, preguntar=None, detectar=None):
    consola = Consola()
    codigo = orden.handle(
        parser().parse_args(argv), out=consola, home=home, detectar=detectar or detector(),
        entrada=entrada, preguntar=preguntar,
    )
    return codigo, consola


def fabricar(home, estado="terminado", **resultado) -> str:
    id_trabajo = registro.nuevo_id()
    ruta = trabajos.raiz(home) / id_trabajo
    ruta.mkdir(parents=True)
    registro.escribir_json(ruta / registro.TRABAJO, {
        "id": id_trabajo, "programa": "claude", "modo": "consulta", "carpeta": str(ruta),
        "origen": "conv", "creado": registro.ahora(), "tope_segundos": 60, "argv": ["x"],
    })
    registro.escribir_json(ruta / registro.ESTADO, {"estado": estado})
    registro.escribir_json(ruta / registro.RESULTADO, {
        "respuesta": "hola", "sesion": "ses-1", "tokens_entrada": 1, "tokens_salida": 1, **resultado,
    })
    return id_trabajo


# ── Analizador ─────────────────────────────────────────────────────────────


def test_analizador_acepta_cada_orden():
    p = parser()
    args = p.parse_args(["enviar", "--programa", "codex", "--modo", "revision", "--carpeta", "/srv/p",
                         "--encargo", "-", "--modelo", "m", "--origen", "conv", "--esperar", "--json"])
    assert (args.obreros_orden, args.programa, args.modo, args.carpeta, args.encargo) == (
        "enviar", "codex", "revision", "/srv/p", "-")
    assert args.esperar and args.json
    assert p.parse_args(["activar", "--si", "--tope-tokens-dia", "500"]).tope_tokens_dia == 500
    assert p.parse_args(["reanudar", "20261126-000000-abcdef01", "--encargo", "e.json"]).id
    for orden_simple in (["estado"], ["desactivar"], ["lista", "--json"], ["ver", "x"],
                         ["seguir", "x"], ["cancelar", "x", "--json"]):
        assert p.parse_args(orden_simple).obreros_orden == orden_simple[0]


@pytest.mark.parametrize("argv", [
    ["enviar", "--modo", "consulta", "--encargo", "-"],
    ["enviar", "--programa", "claude", "--modo", "construccion", "--encargo", "-"],
    ["enviar", "--programa", "gemini", "--modo", "consulta", "--encargo", "-"],
    ["activar", "--tope-tokens-dia", "mucho"],
    ["ver"],
])
def test_analizador_rechaza_lo_mal_formado(argv, capsys):
    with pytest.raises(SystemExit) as salida:
        parser().parse_args(argv)
    assert salida.value.code == 2


# ── Órdenes ────────────────────────────────────────────────────────────────


def test_sin_orden_muestra_el_estado(home):
    codigo, consola = correr(home, [])
    assert codigo == 0 and "activados" in consola.texto


def test_estado_en_json(home):
    fabricar(home)
    codigo, consola = correr(home, ["estado", "--json"])
    datos = consola.json()
    assert codigo == 0 and datos["activo"] is True
    assert datos["topes"]["trabajos_a_la_vez"] == 2 and datos["topes"]["tope_tokens_dia"] == 10000
    assert datos["topes"]["tokens_ultimas_24h"] == 2
    assert set(datos["programas"]) == {"claude", "codex"} and datos["en_curso"] == []


def test_activar_pide_confirmacion_y_tope(home):
    (home / "config.yaml").write_text("model: x\n", encoding="utf-8")
    codigo, consola = correr(home, ["activar"])
    assert codigo == 1 and "Anthropic" in consola.texto and "OpenAI" in consola.texto

    respuestas = iter(["no"])
    codigo, _ = correr(home, ["activar"], preguntar=lambda _: next(respuestas))
    assert codigo == 1 and not trabajos.ajustes_mod.leer(home).activo

    respuestas = iter(["sí", "7000"])
    codigo, _ = correr(home, ["activar"], preguntar=lambda _: next(respuestas))
    conf = trabajos.ajustes_mod.leer(home)
    assert codigo == 0 and conf.activo and conf.tope_tokens_dia == 7000

    assert correr(home, ["desactivar"])[0] == 0
    assert not trabajos.ajustes_mod.leer(home).activo
    assert correr(home, ["activar", "--si"])[0] == 0  # conserva el tope anterior
    assert correr(home, ["activar", "--si", "--tope-tokens-dia", "900"])[0] == 0
    assert trabajos.ajustes_mod.leer(home).tope_tokens_dia == 900


def test_activar_sin_tope_no_activa(home):
    (home / "config.yaml").write_text("model: x\n", encoding="utf-8")
    codigo, consola = correr(home, ["activar", "--si"])
    assert codigo == 1 and consola.lineas[-1].startswith("error:")
    assert not trabajos.ajustes_mod.leer(home).activo


def test_enviar_y_esperar_de_punta_a_punta(home, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codigo_falso = (
        "import json, sys\nsys.stdin.read()\n"
        f"sys.stdout.write({json.dumps(SALIDA_CLAUDE)!r})\n"
    )
    if sys.platform == "win32":
        script = bin_dir / "falso.py"
        script.write_text(codigo_falso, encoding="utf-8")
        ruta = bin_dir / "falso.cmd"
        ruta.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        ruta = bin_dir / "falso"
        ruta.write_text(f"#!{sys.executable}\n{codigo_falso}", encoding="utf-8")
        ruta.chmod(0o755)

    codigo, consola = correr(
        home,
        ["enviar", "--programa", "claude", "--modo", "consulta", "--encargo", "-",
         "--origen", "conv", "--esperar", "--json"],
        entrada=io.StringIO(json.dumps(ENCARGO)), detectar=detector(str(ruta)),
    )
    datos = consola.json()
    assert codigo == 0, datos
    assert datos["estado"] == "terminado" and datos["respuesta"] == "hola" and datos["origen"] == "conv"


def test_rechazos_salen_con_codigo_1_y_error_en_json(home, tmp_path, monkeypatch):
    encargo = tmp_path / "encargo.json"
    encargo.write_text(json.dumps(ENCARGO), encoding="utf-8")
    base = ["enviar", "--programa", "claude", "--encargo", str(encargo), "--json"]

    codigo, consola = correr(home, [*base, "--modo", "revision"])
    assert codigo == 1 and "carpeta" in consola.json()["error"]

    codigo, consola = correr(home, [*base, "--modo", "consulta"], detectar=detector(sesion=False))
    assert codigo == 1 and "error" in consola.json()

    monkeypatch.setenv(VARIABLE_PROFUNDIDAD, "1")
    assert correr(home, [*base, "--modo", "consulta"])[0] == 1
    monkeypatch.delenv(VARIABLE_PROFUNDIDAD)

    encargo.write_text("{no es json", encoding="utf-8")
    codigo, consola = correr(home, [*base, "--modo", "consulta"])
    assert codigo == 1 and "JSON" in consola.json()["error"]
    assert trabajos.listar(home) == []


def test_lista_ver_seguir_y_cancelar(home):
    bueno = fabricar(home)
    malo = fabricar(home, estado="fallido")

    codigo, consola = correr(home, ["lista", "--json"])
    # El orden es el del id (por segundo de creación); dentro del mismo segundo no se fija.
    assert codigo == 0 and {t["id"] for t in consola.json()} == {bueno, malo}

    codigo, consola = correr(home, ["ver", bueno])
    assert codigo == 0 and "hola" in consola.texto and bueno in consola.texto

    assert correr(home, ["seguir", bueno])[0] == 0
    assert correr(home, ["seguir", malo, "--json"])[0] == 1
    assert correr(home, ["ver", "../fuera"])[0] == 1
    assert correr(home, ["cancelar", bueno])[0] == 1


def test_lista_vacia(home):
    codigo, consola = correr(home, ["lista"])
    assert codigo == 0 and consola.lineas == ["No hay trabajos."]


# ── Plugin ─────────────────────────────────────────────────────────────────


def test_el_plugin_registra_la_orden(tmp_path, monkeypatch):
    from hermes_cli import plugins

    from janitor.seed import ensure_home

    root = tmp_path / ".janitor"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(root))
    ensure_home(root)

    plugins._reset_plugin_managers_for_tests()
    try:
        plugins.discover_plugins(force=True)
        comando = plugins.get_plugin_manager()._cli_commands["obreros"]
    finally:
        plugins._reset_plugin_managers_for_tests()

    p = ArgumentParser(prog="janitor obreros")
    comando["setup_fn"](p)
    consola = Consola()
    # Un home recién sembrado no tiene la función activada.
    codigo = comando["handler_fn"](p.parse_args(["lista", "--json"]), out=consola)
    assert codigo == 0 and consola.json() == []
    assert not trabajos.ajustes_mod.leer(root).activo
