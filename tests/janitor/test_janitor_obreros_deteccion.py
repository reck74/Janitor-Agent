"""Detección de obreros (F7-01): instalado, versión y sesión sin exponer identificadores."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys

import pytest

from janitor.obreros.encargo import VARIABLE_PROFUNDIDAD
from janitor.obreros.deteccion import (
    PROGRAMAS,
    alguno_disponible,
    detectar,
    detectar_todos,
    entorno_hijo,
)

EMAIL = "persona@ejemplo.com"
ORG = "Organizacion Secreta SA"


def _claude_json(logged_in: bool, **extra) -> str:
    datos = {
        "loggedIn": logged_in,
        "authMethod": "claude.ai",
        "email": EMAIL,
        "orgName": ORG,
        "orgId": "org-1234",
        **extra,
    }
    return json.dumps(datos)


class Falso:
    """Runner que responde por subcomando y anota cada argv recibido."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas: list[list[str]] = []

    def __call__(self, argv, timeout):
        self.llamadas.append(list(argv))
        assert timeout > 0
        respuesta = self.respuestas[tuple(argv[1:])]
        if isinstance(respuesta, BaseException):
            raise respuesta
        return respuesta


def _buscar_en(rutas):
    return lambda nombre: rutas.get(nombre)


def _sin_identificadores(programa):
    vista = repr(programa) + json.dumps(dataclasses.asdict(programa))
    for secreto in (EMAIL, ORG, "org-1234", "sk-"):
        assert secreto not in vista


def test_no_instalado_no_ejecuta_nada():
    falso = Falso({})
    for nombre in PROGRAMAS:
        p = detectar(nombre, buscar=_buscar_en({}), ejecutar=falso)
        assert p.ruta is None and p.sesion is None and not p.disponible
        assert p.detalle
    assert falso.llamadas == []


def test_claude_con_sesion():
    falso = Falso({
        ("--version",): (0, "2.1.332 (Claude Code)\n", ""),
        ("auth", "status"): (0, _claude_json(True), ""),
    })
    p = detectar("claude", buscar=_buscar_en({"claude": "/x/claude"}), ejecutar=falso)
    assert p.disponible and p.sesion is True
    assert p.version == "2.1.332"
    assert p.metodo == "claude.ai"
    assert all(argv[0] == "/x/claude" for argv in falso.llamadas)
    _sin_identificadores(p)


def test_codex_con_un_aviso_antes_de_la_linea_de_estado():
    falso = Falso({
        ("--version",): (0, "codex-cli 0.172.0\n", ""),
        ("login", "status"): (0, "", "Hay una versión nueva de Codex\nLogged in using ChatGPT\n"),
    })
    assert detectar("codex", buscar=_buscar_en({"codex": "/x/codex"}), ejecutar=falso).disponible


def test_codex_con_salida_que_no_dice_nada_queda_desconocido():
    falso = Falso({
        ("--version",): (0, "codex-cli 0.172.0\n", ""),
        ("login", "status"): (0, "", "Hay una versión nueva de Codex\n"),
    })
    p = detectar("codex", buscar=_buscar_en({"codex": "/x/codex"}), ejecutar=falso)
    assert p.sesion is None and not p.disponible


def test_codex_con_sesion_chatgpt():
    falso = Falso({
        ("--version",): (0, "codex-cli 0.172.0\n", ""),
        ("login", "status"): (0, "", "Logged in using ChatGPT\n"),
    })
    p = detectar("codex", buscar=_buscar_en({"codex": "/x/codex"}), ejecutar=falso)
    assert p.disponible
    assert p.version == "0.172.0"
    assert p.metodo == "ChatGPT"


def test_codex_con_clave_api_no_conserva_la_clave():
    falso = Falso({
        ("--version",): (0, "codex-cli 0.172.0\n", ""),
        ("login", "status"): (0, "Logged in using an API key - sk-proj-***abcd\n", ""),
    })
    p = detectar("codex", buscar=_buscar_en({"codex": "/x/codex"}), ejecutar=falso)
    assert p.disponible and p.metodo == "api"
    _sin_identificadores(p)


@pytest.mark.parametrize(
    "nombre, orden, respuesta",
    [
        ("claude", ("auth", "status"), (1, _claude_json(False), "")),
        ("codex", ("login", "status"), (1, "", "Not logged in\n")),
    ],
)
def test_sin_sesion(nombre, orden, respuesta):
    falso = Falso({("--version",): (0, "1.0.0", ""), orden: respuesta})
    p = detectar(nombre, buscar=_buscar_en({nombre: f"/x/{nombre}"}), ejecutar=falso)
    assert p.ruta is not None and p.sesion is False and not p.disponible
    assert "login" in p.detalle
    _sin_identificadores(p)


def test_json_extra_de_claude_no_llega_al_resultado():
    salida = _claude_json(True, subscriptionType="max", planTier="x", authMethod=EMAIL)
    falso = Falso({("--version",): (0, "2.1.332", ""), ("auth", "status"): (0, salida, "")})
    p = detectar("claude", buscar=_buscar_en({"claude": "/x/claude"}), ejecutar=falso)
    assert p.sesion is True
    # Un authMethod con forma de identificador se descarta en lugar de copiarse.
    assert p.metodo is None
    _sin_identificadores(p)


@pytest.mark.parametrize("salida", ["{no es json", "", "[1, 2]", '{"loggedIn": "yes"}'])
def test_json_malformado_es_desconocido(salida):
    falso = Falso({("--version",): (0, "2.1.332", ""), ("auth", "status"): (0, salida, "")})
    p = detectar("claude", buscar=_buscar_en({"claude": "/x/claude"}), ejecutar=falso)
    assert p.sesion is None and not p.disponible


@pytest.mark.parametrize("fallo", [subprocess.TimeoutExpired(["x"], 10), OSError("roto")])
@pytest.mark.parametrize("nombre, orden", [("claude", ("auth", "status")), ("codex", ("login", "status"))])
def test_timeout_o_error_da_sesion_desconocida(fallo, nombre, orden):
    falso = Falso({("--version",): fallo, orden: fallo})
    p = detectar(nombre, buscar=_buscar_en({nombre: f"/x/{nombre}"}), ejecutar=falso)
    assert p.ruta == f"/x/{nombre}"
    assert p.version is None and p.sesion is None and not p.disponible


def test_detectar_todos_y_alguno_disponible():
    falso = Falso({
        ("--version",): (0, "1.2.3", ""),
        ("auth", "status"): (1, _claude_json(False), ""),
        ("login", "status"): (0, "", "Logged in using ChatGPT"),
    })
    kw = dict(buscar=_buscar_en({"claude": "/x/claude", "codex": "/x/codex"}), ejecutar=falso)
    todos = detectar_todos(**kw)
    assert set(todos) == set(PROGRAMAS)
    assert alguno_disponible(**kw)
    assert not alguno_disponible(buscar=_buscar_en({}), ejecutar=falso)


def _sin_marcador(claves):
    # El marcador contra la recursión es la única variable JANITOR_* que el hijo debe ver.
    return [k for k in claves if k != VARIABLE_PROFUNDIDAD]


def test_entorno_hijo_es_lista_blanca():
    base = {
        "PATH": "/bin", "HOME": "/h", "XDG_CONFIG_HOME": "/h/.config", "CODEX_HOME": "/c",
        "HERMES_HOME": "/j", "JANITOR_SKILLS_ROOT": "/s",
        "ANTHROPIC_API_KEY": "k", "OPENAI_API_KEY": "k", "MINIMAX_API_KEY": "k",
    }
    entorno = entorno_hijo(base)
    assert {"PATH", "HOME", "XDG_CONFIG_HOME", "CODEX_HOME"} <= set(entorno)
    assert not any(k.startswith(("HERMES_", "JANITOR_")) or "API_KEY" in k for k in _sin_marcador(entorno))


_FALSO_EJECUTABLE = """#!{python}
import json, os, sys
with open({volcado!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps(sorted(os.environ)) + "\\n")
args = sys.argv[1:]
if args == ["--version"]:
    print({version!r})
elif args == ["auth", "status"]:
    print({claude_json!r})
elif args == ["login", "status"]:
    sys.stderr.write("Logged in using ChatGPT\\n")
else:
    sys.exit(2)
"""


@pytest.mark.linux_only
def test_extremo_a_extremo_con_ejecutables_falsos(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    volcado = tmp_path / "entornos.jsonl"
    versiones = {"claude": "2.1.332 (Claude Code)", "codex": "codex-cli 0.172.0"}
    for nombre, version in versiones.items():
        exe = bin_dir / nombre
        exe.write_text(_FALSO_EJECUTABLE.format(
            python=sys.executable, volcado=str(volcado), version=version,
            claude_json=_claude_json(True),
        ))
        exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    for var in ("HERMES_HOME", "JANITOR_SKILLS_ROOT", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(var, "no-debe-llegar")

    todos = detectar_todos()

    assert todos["claude"].ruta == str(bin_dir / "claude")
    assert todos["claude"].version == "2.1.332" and todos["claude"].disponible
    assert todos["codex"].version == "0.172.0" and todos["codex"].disponible
    for p in todos.values():
        _sin_identificadores(p)
    entornos = [json.loads(l) for l in volcado.read_text().splitlines()]
    assert len(entornos) == 4
    for claves in entornos:
        assert "PATH" in claves
        assert not any(k.startswith(("HERMES_", "JANITOR_")) or "API_KEY" in k for k in _sin_marcador(claves))


def test_programa_desconocido_se_rechaza():
    with pytest.raises(ValueError):
        detectar("otro", buscar=_buscar_en({}), ejecutar=Falso({}))

