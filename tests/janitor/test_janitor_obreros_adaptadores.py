"""Contratos de los adaptadores de obreros (F7-02): encargo, línea de comando, entorno
y análisis de la salida de `claude` y `codex`. Funciones puras: no se lanza nada."""

from __future__ import annotations

import json

import pytest

from janitor.obreros import claude, codex, encargo
from janitor.obreros.encargo import Resultado

ADAPTADORES = {"claude": claude, "codex": codex}
CARPETA = "/srv/proyecto"


def _datos(**cambios):
    base = {
        "objetivo": "Revisar el módulo de pagos",
        "contexto": "Proyecto en Python",
        "entregables": ["Lista de hallazgos"],
        "restricciones": [],
    }
    base.update(cambios)
    return base


def _argvs(adaptador):
    """Todas las combinaciones de modo, modelo y sesión que puede producir un adaptador."""
    for modo in adaptador.MODOS:
        for modelo in (None, "modelo-x"):
            for sesion in (None, "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"):
                yield modo, sesion, adaptador.construir_argv(
                    "obrero", modo=modo, carpeta=CARPETA, modelo=modelo, sesion=sesion
                )


# --- Encargo -------------------------------------------------------------------------


def test_validar_devuelve_encargo_inmutable_con_tuplas():
    resultado = encargo.validar(_datos(restricciones=["No tocar la base"]))
    assert resultado.entregables == ("Lista de hallazgos",)
    assert resultado.restricciones == ("No tocar la base",)
    with pytest.raises(AttributeError):
        resultado.objetivo = "otro"


@pytest.mark.parametrize(
    "datos",
    [
        _datos(objetivo="   "),
        _datos(objetivo=3),
        _datos(contexto=None),
        _datos(entregables=[]),
        _datos(entregables="uno"),
        _datos(entregables=["bien", ""]),
        _datos(restricciones=[7]),
        {k: v for k, v in _datos().items() if k != "contexto"},
        {**_datos(), "extra": "x"},
        _datos(contexto="x" * (64 * 1024)),
        ["no", "es", "un", "objeto"],
    ],
)
def test_validar_rechaza_encargos_mal_formados_en_espanol(datos):
    with pytest.raises(ValueError) as error:
        encargo.validar(datos)
    assert str(error.value)


def test_prompt_lleva_el_encargo_y_los_limites_del_modo():
    tarea = encargo.validar(_datos(restricciones=["No tocar la base"]))
    for modo in encargo.MODOS:
        texto = encargo.a_prompt(tarea, modo)
        for parte in (tarea.objetivo, tarea.contexto, *tarea.entregables, *tarea.restricciones):
            assert parte in texto
        assert "español" in texto
        assert "agente" in texto
    assert encargo.a_prompt(tarea, "consulta") != encargo.a_prompt(tarea, "revision")


# --- Línea de comando ----------------------------------------------------------------


@pytest.mark.parametrize("nombre", ADAPTADORES)
def test_el_prompt_nunca_va_en_argv(nombre):
    adaptador = ADAPTADORES[nombre]
    tarea = encargo.validar(_datos(objetivo="OBJETIVO-SECRETO-UNICO"))
    for modo, _sesion, argv in _argvs(adaptador):
        prompt = encargo.a_prompt(tarea, modo)
        assert all("OBJETIVO-SECRETO-UNICO" not in a and a != prompt for a in argv)


@pytest.mark.parametrize("nombre", ADAPTADORES)
@pytest.mark.parametrize("modo", ["construccion", "escritura", ""])
def test_modos_que_escriben_o_desconocidos_se_rechazan(nombre, modo):
    with pytest.raises(ValueError):
        ADAPTADORES[nombre].construir_argv("obrero", modo=modo, carpeta=CARPETA)
    with pytest.raises(ValueError):
        encargo.a_prompt(encargo.validar(_datos()), modo)


@pytest.mark.parametrize("nombre", ADAPTADORES)
def test_la_carpeta_debe_ser_absoluta(nombre):
    with pytest.raises(ValueError):
        ADAPTADORES[nombre].construir_argv("obrero", modo="consulta", carpeta="relativa/dir")


@pytest.mark.parametrize("nombre", ADAPTADORES)
@pytest.mark.parametrize("valor", ["--last", "-x", "a b", ""])
def test_sesion_y_modelo_no_pueden_inyectar_opciones(nombre, valor):
    adaptador = ADAPTADORES[nombre]
    with pytest.raises(ValueError):
        adaptador.construir_argv("obrero", modo="consulta", carpeta=CARPETA, sesion=valor)
    with pytest.raises(ValueError):
        adaptador.construir_argv("obrero", modo="consulta", carpeta=CARPETA, modelo=valor)


def _valor_de(argv, opcion):
    return argv[argv.index(opcion) + 1]


def test_claude_consulta_sin_herramientas_y_revision_solo_lectura():
    for modo, _sesion, argv in _argvs(claude):
        herramientas = _valor_de(argv, "--tools")
        if modo == "consulta":
            assert herramientas == ""
            assert "--allowedTools" not in argv
        else:
            concedidas = set(herramientas.split(","))
            assert concedidas == set(_valor_de(argv, "--allowedTools").split(","))
            assert concedidas <= {"Read", "Grep", "Glob"}


def test_claude_sin_preguntas_ni_configuracion_ajena_y_con_sesion_guardada():
    for _modo, sesion, argv in _argvs(claude):
        assert argv[:4] == ["obrero", "-p", "--output-format", "json"]
        assert _valor_de(argv, "--permission-mode") not in {"bypassPermissions", "acceptEdits", "auto"}
        assert _valor_de(argv, "--permission-prompts") == "none"
        assert _valor_de(argv, "--mcp-config") == '{"mcpServers":{}}'
        assert _valor_de(argv, "--setting-sources") == ""
        for opcion in ("--strict-mcp-config", "--safe-mode", "--restricted", "--disable-slash-commands"):
            assert opcion in argv
        # `--bare` apaga la sesión de la suscripción; sin persistencia no hay reanudación.
        assert "--bare" not in argv and "--no-session-persistence" not in argv
        assert ("--resume" in argv) == (sesion is not None)
        if sesion:
            assert _valor_de(argv, "--resume") == sesion
        assert "--continue" not in argv and "-c" not in argv


def test_codex_siempre_solo_lectura_y_sin_aprobaciones():
    for _modo, sesion, argv in _argvs(codex):
        inicio = argv.index("exec")
        # `-a` solo existe como opción global, antes de `exec`.
        assert _valor_de(argv[:inicio], "-a") == "never"
        assert _valor_de(argv[:inicio], "-C") == CARPETA
        assert 'sandbox_mode="read-only"' in argv and 'approval_policy="never"' in argv
        if sesion is None:
            assert _valor_de(argv, "--sandbox") == "read-only"
        texto = " ".join(argv)
        for peligro in ("workspace-write", "danger-full-access", "dangerously", "--approve-for-me", "--trust", "--search"):
            assert peligro not in texto
        assert "--json" in argv and argv[-1] == "-"


def test_codex_aisla_la_configuracion_del_usuario_y_guarda_la_sesion():
    for _modo, _sesion, argv in _argvs(codex):
        for opcion in ("--skip-git-repo-check", "--ignore-user-config"):
            assert opcion in argv
        desactivadas = {argv[i + 1] for i, a in enumerate(argv) if a == "--disable"}
        assert {"hooks", "plugins", "multi_agent", "multi_agent_v2"} <= desactivadas
        assert "mcp_servers={}" in argv and 'web_search="disabled"' in argv
        assert any("JANITOR_OBRERO_PROFUNDIDAD" in a for a in argv)
        assert "--ephemeral" not in argv


def test_codex_reanuda_por_id_y_nunca_la_ultima():
    sesion = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
    argv = codex.construir_argv("codex", modo="revision", carpeta=CARPETA, sesion=sesion)
    assert argv[argv.index("exec") + 1 : argv.index("exec") + 3] == ["resume", sesion]
    assert "--last" not in argv
    for _modo, _s, otro in _argvs(codex):
        assert "--last" not in otro


# --- Entorno -------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ADAPTADORES)
def test_entorno_lista_blanca_y_marcador_de_profundidad(nombre):
    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "LC_ALL": "es_ES.UTF-8",
        "SystemRoot": "C:\\Windows",
        "OPENAI_API_KEY": "x",
        "ANTHROPIC_API_KEY": "x",
        "MINIMAX_API_KEY": "x",
        "GITHUB_TOKEN": "x",
        "HERMES_HOME": "/home/u/.janitor",
        "JANITOR_SKILLS_ROOT": "/x",
        "JANITOR_OBRERO_PROFUNDIDAD": "0",
    }
    resultado = ADAPTADORES[nombre].entorno(base)
    assert resultado["JANITOR_OBRERO_PROFUNDIDAD"] == "1"
    assert {"PATH", "HOME", "LC_ALL", "SystemRoot"} <= set(resultado)
    for clave in resultado:
        assert not clave.endswith(("_API_KEY", "_TOKEN"))
        assert not clave.startswith("HERMES_")
        assert not clave.startswith("JANITOR_") or clave == "JANITOR_OBRERO_PROFUNDIDAD"
    assert base["JANITOR_OBRERO_PROFUNDIDAD"] == "0"


def test_cada_programa_conserva_solo_su_carpeta_de_configuracion():
    base = {"CLAUDE_CONFIG_DIR": "/c", "CODEX_HOME": "/x"}
    assert set(claude.entorno(base)) - {"JANITOR_OBRERO_PROFUNDIDAD"} == {"CLAUDE_CONFIG_DIR"}
    assert set(codex.entorno(base)) - {"JANITOR_OBRERO_PROFUNDIDAD"} == {"CODEX_HOME"}


# --- Salida de Claude ----------------------------------------------------------------


def _claude(**cambios):
    base = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Hallazgos: ninguno",
        "session_id": "sesion-1",
        "total_cost_usd": 0.12,
        "usage": {
            "input_tokens": 10,
            "cache_creation_input_tokens": 5,
            "cache_read_input_tokens": 100,
            "output_tokens": 40,
        },
        "modelUsage": {"claude-modelo-a": {"inputTokens": 10}, "alias": {"canonicalModel": "claude-modelo-b"}},
        "permission_denials": [],
    }
    base.update(cambios)
    return json.dumps(base)


def test_claude_ok_con_sesion_tokens_coste_y_modelos():
    r = claude.analizar_salida(_claude(), 0)
    assert isinstance(r, Resultado)
    assert (r.estado, r.respuesta, r.sesion) == ("ok", "Hallazgos: ninguno", "sesion-1")
    assert r.tokens_entrada == 115 and r.tokens_salida == 40
    assert r.coste_usd == pytest.approx(0.12)
    assert r.modelos == ("claude-modelo-a", "claude-modelo-b")


def test_claude_negacion_de_permiso_es_bloqueado():
    salida = _claude(permission_denials=[{"tool_name": "Bash", "tool_use_id": "t1"}])
    r = claude.analizar_salida(salida, 0)
    assert r.estado == "bloqueado"
    assert "Bash" in r.detalle
    assert r.sesion == "sesion-1"


@pytest.mark.parametrize(
    "salida, codigo",
    [
        (_claude(is_error=True, subtype="error_during_execution"), 1),
        (_claude(subtype="error_max_turns"), 0),
        (_claude(), 1),
    ],
)
def test_claude_error(salida, codigo):
    assert claude.analizar_salida(salida, codigo).estado == "error"


@pytest.mark.parametrize("salida", ["", "no es json", "[1, 2]", json.dumps({"type": "system"}), _claude(result="  ")])
def test_claude_salida_invalida(salida):
    assert claude.analizar_salida(salida, 0).estado == "salida_invalida"


# --- Salida de Codex -----------------------------------------------------------------


def _jsonl(*eventos):
    return "\n".join(json.dumps(e) for e in eventos) + "\n"


HILO = {"type": "thread.started", "thread_id": "hilo-1"}
INICIO = {"type": "turn.started"}
RAZONA = {"type": "item.completed", "item": {"id": "i0", "type": "reasoning", "text": "pensando"}}
MSG1 = {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "borrador"}}
MSG2 = {"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": "respuesta final"}}
FIN = {"type": "turn.completed", "usage": {"input_tokens": 200, "cached_input_tokens": 150, "output_tokens": 30}}


def test_codex_ok_ultima_respuesta_hilo_y_tokens():
    salida = _jsonl(HILO, INICIO, RAZONA, MSG1, {"type": "evento.desconocido", "x": 1}, MSG2, FIN)
    r = codex.analizar_salida("\n" + salida + "\n\n", 0)
    assert (r.estado, r.respuesta, r.sesion) == ("ok", "respuesta final", "hilo-1")
    assert (r.tokens_entrada, r.tokens_salida) == (200, 30)
    assert r.coste_usd is None


@pytest.mark.parametrize(
    "eventos",
    [
        (HILO, INICIO, {"type": "turn.failed", "error": {"message": "límite alcanzado"}}),
        (HILO, {"type": "error", "message": "sin conexión"}),
        (HILO, MSG2, {"type": "error", "message": "reconectando"}, FIN),
    ],
)
def test_codex_fallo_es_error_y_conserva_el_hilo(eventos):
    r = codex.analizar_salida(_jsonl(*eventos), 1)
    assert r.estado == "error"
    assert r.sesion == "hilo-1"
    assert r.detalle


def test_codex_codigo_distinto_de_cero_es_error():
    assert codex.analizar_salida(_jsonl(HILO, MSG2, FIN), 2).estado == "error"


@pytest.mark.parametrize(
    "salida",
    [
        "no es json\n",
        _jsonl(HILO, MSG2, FIN) + "basura\n",
        _jsonl(HILO, MSG2),
        _jsonl(HILO, RAZONA, FIN),
        "[1]\n",
        "",
    ],
)
def test_codex_salida_invalida(salida):
    assert codex.analizar_salida(salida, 0).estado == "salida_invalida"
