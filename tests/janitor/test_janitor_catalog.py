"""``janitor.catalog``: the catalog resolves in this tree and ``apply()`` drives the real skill index.

Every ``apply()`` test reads the result back through the code path the system
prompt uses (``agent.prompt_builder.build_skills_system_prompt``) against a temp
``HERMES_HOME`` that opted out of bundled skills, so "one ``external_dirs``
entry per skill directory" is proven end to end, not assumed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from janitor import catalog as cat
from janitor.home import SKILLS_ROOT

ESSENTIAL = "hermes-agent"


@pytest.fixture(scope="module")
def catalog():
    return cat.load_catalog()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("JANITOR_SKILLS_ROOT", raising=False)
    return tmp_path


def _make_home(root: Path, name: str, config: dict, header: str = "") -> Path:
    home = root / name
    home.mkdir(parents=True)
    (home / ".no-bundled-skills").write_text("essential skills only\n", encoding="utf-8")
    body = yaml.safe_dump(config, sort_keys=False, default_flow_style=False)
    (home / "config.yaml").write_text(header + body, encoding="utf-8")
    return home


def _index(home: Path, monkeypatch) -> set:
    """Skill names in the system-prompt skill index of ``home``."""
    from agent import skill_utils
    from agent.prompt_builder import build_skills_system_prompt, clear_skills_system_prompt_cache
    from tools.skills_sync import sync_skills

    monkeypatch.setenv("HERMES_HOME", str(home))
    skill_utils._external_dirs_cache_clear()
    clear_skills_system_prompt_cache()
    sync_skills(quiet=True)
    prompt = build_skills_system_prompt()
    block = prompt.split("<available_skills>", 1)[1].split("</available_skills>", 1)[0]
    return set(re.findall(r"^\s+- ([^:\s]+):", block, re.M))


def _available_ids(catalog, platform=None) -> list:
    platform = platform or cat.current_platform()
    return [e.id for e in catalog.entries
            if e.source != "hub" and cat.matches_platform(e, platform) and cat.resolve(e).is_dir()]


# --- the catalog itself ------------------------------------------------------


def test_every_entry_resolves_to_its_own_skill(catalog):
    problems = {e.id: p for e in catalog.entries if (p := cat.check_entry(e))}
    assert problems == {}
    for e in catalog.entries:
        if e.source == "janitor":
            assert cat.resolve(e).is_relative_to(SKILLS_ROOT.resolve())


def test_ids_unique_and_templates_and_purposes_declared(catalog):
    ids = [e.id for e in catalog.entries]
    assert len(ids) == len(set(ids))
    for e in catalog.entries:
        assert e.purpose in catalog.purposes
        assert set(e.templates) <= set(catalog.templates)
    # every declared template offers at least one skill on some platform
    for name in catalog.templates:
        assert any(name in e.templates for e in catalog.entries), name


def test_declared_platforms_are_accepted_by_the_skill_itself(catalog):
    """The catalog may narrow a skill's OS gate, never widen it."""
    for e in catalog.entries:
        if not e.platforms or e.source == "hub":
            continue
        front = yaml.safe_load((cat.resolve(e) / "SKILL.md").read_text(encoding="utf-8").split("---")[1])
        declared = front.get("platforms")
        if declared:
            assert set(e.platforms) <= {str(p).lower() for p in declared}, e.id


def test_every_os_gets_the_welcome_skill(catalog):
    """The orientation skill is the main agent's map of Janitor: no OS starts without it."""
    for platform in cat.PLATFORMS:
        assert "janitor-onboarding" in cat.skills_for_template("main", catalog=catalog, platform=platform)


@pytest.mark.windows_only
def test_windows_fresh_home_loads_the_welcome_skill(env, monkeypatch):
    """Catalog gate AND the skill's own frontmatter gate both let it through on Windows."""
    from janitor.seed import ensure_home

    home = env / ".janitor"
    ensure_home(home)
    assert "janitor-onboarding" in _index(home, monkeypatch)


@pytest.mark.parametrize("bad, message", [
    ({"source": "elsewhere"}, "unknown source"),
    ({"purpose": "nope"}, "unknown purpose"),
    ({"templates": ["nope"]}, "unknown template"),
    ({"platforms": ["beos"]}, "unknown platform"),
])
def test_load_catalog_rejects_malformed_entries(tmp_path, bad, message):
    entry = {"id": "x", "source": "janitor", "path": "core/x", "purpose": "p", "templates": []}
    data = {"schema": 1, "purposes": {"p": "P"}, "templates": {"t": "T"}, "skills": [{**entry, **bad}]}
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(cat.CatalogError, match=message):
        cat.load_catalog(path)


def test_load_catalog_rejects_duplicate_ids(tmp_path):
    entry = {"id": "x", "source": "janitor", "path": "core/x", "purpose": "p", "templates": []}
    data = {"schema": 1, "purposes": {"p": "P"}, "templates": {"t": "T"}, "skills": [entry, entry]}
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(cat.CatalogError, match="duplicate"):
        cat.load_catalog(path)


def test_platform_gated_entry_is_offered_only_on_its_platform():
    entries = (
        cat.Entry("everywhere", "janitor", "a/everywhere", "p", ("t",)),
        cat.Entry("mac-only", "janitor", "a/mac-only", "p", ("t",), ("macos",)),
        cat.Entry("not-in-t", "janitor", "a/not-in-t", "p", ()),
    )
    catalog = cat.Catalog({"p": "P"}, {"t": "T"}, entries)
    assert cat.skills_for_template("t", catalog=catalog, platform="macos") == ["everywhere", "mac-only"]
    assert cat.skills_for_template("t", catalog=catalog, platform="linux") == ["everywhere"]
    assert cat.skills_for_template("t", catalog=catalog, platform="windows") == ["everywhere"]
    with pytest.raises(KeyError):
        cat.skills_for_template("missing", catalog=catalog, platform="linux")


def test_real_template_lists_honour_platform_gates(catalog):
    for name in catalog.templates:
        for platform in cat.PLATFORMS:
            offered = cat.skills_for_template(name, catalog=catalog, platform=platform)
            by_id = catalog.by_id()
            assert all(cat.matches_platform(by_id[i], platform) for i in offered)
            assert all(name in by_id[i].templates for i in offered)


# --- apply() against the real skill index ------------------------------------


def test_template_list_becomes_exactly_the_skill_index(env, monkeypatch, catalog):
    wanted = cat.skills_for_template("main", catalog=catalog)
    user_dir = env / "my-skills"
    (user_dir / "mine").mkdir(parents=True)
    (user_dir / "mine" / "SKILL.md").write_text(
        "---\nname: my-own-skill\ndescription: A user skill.\n---\nBody.\n", encoding="utf-8")
    home = _make_home(env, ".janitor", {
        "janitor": {"skills": wanted},
        "skills": {"external_dirs": ["${JANITOR_SKILLS_ROOT}", str(SKILLS_ROOT), str(user_dir)]},
    })

    result = cat.apply(home)

    assert result.changed and not result.unknown and not result.unresolved
    assert _index(home, monkeypatch) == set(wanted) | {ESSENTIAL, "my-own-skill"}
    dirs = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))["skills"]["external_dirs"]
    assert str(user_dir) in dirs                      # user entry preserved
    assert "${JANITOR_SKILLS_ROOT}" not in dirs        # legacy whole-root entries replaced
    assert str(SKILLS_ROOT) not in dirs


def test_second_apply_is_a_byte_for_byte_noop(env, catalog):
    home = _make_home(env, ".janitor", {"janitor": {"skills": ["pdf", "janitor-onboarding"]}},
                      header="# Janitor config header\n\n")
    cat.apply(home)
    first = (home / "config.yaml").read_bytes()
    assert first.startswith(b"# Janitor config header\n")
    again = cat.apply(home)
    assert not again.changed
    assert (home / "config.yaml").read_bytes() == first


def test_config_without_janitor_skills_is_untouched(env, monkeypatch):
    home = _make_home(env, ".janitor", {"skills": {"external_dirs": ["${JANITOR_SKILLS_ROOT}"]}},
                      header="# keep me\n")
    before = (home / "config.yaml").read_bytes()
    result = cat.apply(home)
    assert not result.changed and not result.managed
    assert (home / "config.yaml").read_bytes() == before


def test_unknown_id_is_reported_and_skipped(env, monkeypatch):
    home = _make_home(env, ".janitor", {"janitor": {"skills": ["pdf", "no-such-skill"]}})
    result = cat.apply(home)
    assert result.unknown == ["no-such-skill"]
    assert _index(home, monkeypatch) == {"pdf", ESSENTIAL}


def test_stale_entry_from_a_moved_install_is_replaced(env, monkeypatch):
    stale = str(env / "old-install" / "skills" / "productivity" / "pdf")  # gone from disk
    home = _make_home(env, ".janitor", {
        "janitor": {"skills": ["pdf"]}, "skills": {"external_dirs": [stale]}})
    result = cat.apply(home)
    assert stale not in result.external_dirs
    assert _index(home, monkeypatch) == {"pdf", ESSENTIAL}


def test_two_homes_get_different_indexes_from_one_install(env, monkeypatch, catalog):
    a_ids = cat.skills_for_template("main", catalog=catalog)
    b_ids = cat.skills_for_template("creador-proyectos", catalog=catalog)
    assert set(a_ids) != set(b_ids)
    home_a = _make_home(env, "a", {"janitor": {"skills": a_ids}})
    home_b = _make_home(env, "b", {"janitor": {"skills": b_ids}})
    cat.apply(home_a)
    cat.apply(home_b)

    index_a = _index(home_a, monkeypatch)
    index_b = _index(home_b, monkeypatch)
    assert index_a == set(a_ids) | {ESSENTIAL}
    assert index_b == set(b_ids) | {ESSENTIAL}
    assert _index(home_a, monkeypatch) == index_a  # A -> B -> A


def test_every_available_entry_can_be_activated(env, monkeypatch, catalog):
    ids = _available_ids(catalog)
    home = _make_home(env, ".janitor", {"janitor": {"skills": ids}})
    result = cat.apply(home)
    assert not result.unknown and not result.unresolved
    assert _index(home, monkeypatch) == set(ids) | {ESSENTIAL}


# --- template evolution (janitor.template + janitor.catalog_seen) -------------


def _managed(skills, seen=None, template="t") -> dict:
    cfg = {"janitor": {"template": template, "skills": list(skills)}, "model": {"default": "m"}}
    if seen is not None:
        cfg["janitor"]["catalog_seen"] = list(seen)
    return cfg


def test_new_template_skill_is_offered_once():
    config = _managed(["a", "b"], seen=["a", "b"])
    new, change = cat.evolve_selection(config, ["a", "b", "c"], {"a", "b", "c"})
    assert change.added == ["c"] and change.dropped == []
    assert new["janitor"]["skills"] == ["a", "b", "c"]
    assert config["janitor"]["skills"] == ["a", "b"]  # input not mutated

    # the user removes it afterwards: it is never offered again
    new["janitor"]["skills"] = ["a", "b"]
    again, change = cat.evolve_selection(new, ["a", "b", "c"], {"a", "b", "c"})
    assert change.added == [] and again["janitor"]["skills"] == ["a", "b"]


def test_user_removed_template_skill_is_not_re_added():
    config = _managed(["a"], seen=["a", "b"])
    new, change = cat.evolve_selection(config, ["a", "b"], {"a", "b"})
    assert change.added == [] and new == config


def test_skill_dropped_from_catalog_is_removed_and_reported():
    config = _managed(["a", "gone", "extra"], seen=["a", "gone"])
    new, change = cat.evolve_selection(config, ["a"], {"a", "extra"})
    assert change.dropped == ["gone"]
    assert new["janitor"]["skills"] == ["a", "extra"]  # a user-ticked optional skill stays
    assert "gone" not in new["janitor"]["catalog_seen"]


def test_profile_without_seen_record_adds_nothing():
    """Written before the rule existed: today's template counts as already offered."""
    config = _managed(["a"])
    new, change = cat.evolve_selection(config, ["a", "b"], {"a", "b"})
    assert change.added == [] and new["janitor"]["skills"] == ["a"]
    assert new["janitor"]["catalog_seen"] == ["a", "b"]


@pytest.mark.parametrize("config", [
    {"skills": {"external_dirs": ["${JANITOR_SKILLS_ROOT}"]}},
    {"janitor": {"skills": ["a"]}},                       # no template: hand-picked list
    {"janitor": {"template": "t"}},                       # no selection
])
def test_unmanaged_configs_are_not_evolved(config):
    new, change = cat.evolve_selection(config, ["a", "b"], {"a", "b"})
    assert new == config and change.added == [] and change.dropped == []


def test_apply_evolves_a_real_home_and_is_idempotent(env, monkeypatch):
    """End to end with a catalog whose ``t`` template grew one skill and lost one."""
    entries = (
        cat.Entry("pdf", "upstream-bundled", "productivity/pdf", "p", ("t",)),
        cat.Entry("docx", "upstream-bundled", "productivity/docx", "p", ("t",)),
        cat.Entry("xlsx", "upstream-bundled", "productivity/xlsx", "p", ("t",)),
    )
    grown = cat.Catalog({"p": "P"}, {"t": "T"}, entries)
    # pdf + retired were offered and kept; docx was offered and removed by the user.
    home = _make_home(env, "p", _managed(["pdf", "retired"], seen=["pdf", "docx", "retired"]))

    result = cat.apply(home, catalog=grown)

    assert result.added == ["xlsx"] and result.dropped == ["retired"]
    assert _index(home, monkeypatch) == {"pdf", "xlsx", ESSENTIAL}
    first = (home / "config.yaml").read_bytes()
    again = cat.apply(home, catalog=grown)
    assert not again.changed and again.added == [] and again.dropped == []
    assert (home / "config.yaml").read_bytes() == first
