"""Wrapper signatures and forwarding stay compatible with the current upstream."""
from __future__ import annotations

import argparse
import inspect
from pathlib import Path

import pytest

import janitor_cli


@pytest.fixture(scope="module", autouse=True)
def install_runtime():
    janitor_cli._install_janitor_runtime()


def test_soul_wrapper_signature_covers_original():
    original = inspect.signature(janitor_cli._original_load_soul_md)
    wrapper = inspect.signature(janitor_cli._janitor_load_soul_md)
    assert set(original.parameters) <= set(wrapper.parameters), "Update wrapper when upstream adds parameters (AGENTS.md #14)"
    from agent import prompt_builder
    assert prompt_builder.load_soul_md is janitor_cli._janitor_load_soul_md


def test_soul_wrapper_forwards_profile_and_context(monkeypatch, tmp_path):
    seen = []
    def original(context_length=None, home_override=None):
        seen.append((context_length, home_override))
        return "profile soul"
    monkeypatch.setattr(janitor_cli, "_original_load_soul_md", original)
    assert janitor_cli._janitor_load_soul_md(8000, home_override=tmp_path) == "profile soul"
    assert seen == [(8000, tmp_path)]


def test_soul_reads_explicit_profile_instead_of_launch_home(tmp_path):
    named = tmp_path / "named"
    named.mkdir()
    (named / "SOUL.md").write_text("This is the named profile persona.\n")
    assert "named profile persona" in janitor_cli._janitor_load_soul_md(8000, home_override=named)


def test_argument_parser_forwards_stdlib_parameters():
    parser = argparse.ArgumentParser(prog="hermes", description="description", add_help=False, allow_abbrev=False)
    assert parser.prog == "janitor"
    assert parser.description == "description"
    assert parser.allow_abbrev is False


def test_update_wrapper_signature_and_single_delegation(monkeypatch):
    import janitor_update_core
    import hermes_cli.main as main_module
    original = main_module._janitor_original_cmd_update
    assert set(inspect.signature(original).parameters) <= set(inspect.signature(janitor_cli._janitor_cmd_update).parameters)
    args = argparse.Namespace(check=True)
    seen = []
    monkeypatch.setattr(janitor_update_core, "run_janitor_update", lambda value: seen.append(value) or 12)
    assert janitor_cli._janitor_cmd_update(args) == 12
    assert seen == [args]
