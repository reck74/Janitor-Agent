"""The relay installs the new app BEFORE the engine and always reopens it.

Plan ``docs/janitor/plans/actualizacion-automatica.md`` (Fase 9: F9-06, and the
relay half of F9-09). The app downloads and verifies the installer before it
closes and passes it to ``scripts/desktop-update/posix.sh``; these tests drive
the real script end to end (version N → N+1) with stand-in executables:

- the "AppImage" is a script that records which version was launched and stays
  up like an app that booted;
- ``janitor update`` is the real parser with the core replaced by a recorder
  (``desktop_update_harness``);
- ``pkexec`` is a stand-in on PATH (the real one needs a polkit agent and
  root): it records its argv and answers with a chosen exit code. The real
  helper is exercised as root in the Arch container of CI
  (``apps/desktop-janitor/scripts/arch-update-e2e.sh``).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests.janitor.desktop_update_harness import run_posix_handoff

pytestmark = pytest.mark.linux_only

COMMIT = "a" * 40
NEW_VERSION = "0.21.5-janitor.5"

# Says which build it is, then stays up like an app that booted.
_APP = """#!/bin/bash
printf '%s\\n' "{version}" "$@" > "$JANITOR_TEST_APPIMAGE_RECORD"
echo $$ > "$JANITOR_TEST_APPIMAGE_RECORD.pid"
exec sleep 30
"""


def _app(path: Path, version: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_APP.format(version=version), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def install(tmp_path):
    """Version N running from an AppImage, and the verified N+1 the app downloaded."""
    running = _app(tmp_path / "Apps" / "Janitor.AppImage", "N")
    downloaded = _app(tmp_path / "desktop-update" / "21005005" / "Janitor-linux-x86_64.AppImage", "N+1")
    downloaded.chmod(0o600)  # a download is not executable; the relay makes the installed copy so
    record = tmp_path / "launch.txt"
    yield {"running": running, "downloaded": downloaded, "record": record, "root": tmp_path}
    pid_file = Path(f"{record}.pid")
    if pid_file.exists():
        subprocess.run(["kill", pid_file.read_text(encoding="utf-8").strip()], check=False)


def _delivery(installer: Path, kind: str = "appimage") -> list[str]:
    data = installer.read_bytes()
    return [
        "--target-commit", COMMIT, "--app-kind", kind, "--app-version", NEW_VERSION,
        "--app-installer", str(installer),
        "--app-sha256", hashlib.sha256(data).hexdigest(), "--app-size", str(len(data)),
        "--app-manifest", str(installer.parent / "janitor-update.json"),
        "--app-manifest-sig", str(installer.parent / "janitor-update.json.sig"),
    ]


def _run(install, *args: str, env: dict | None = None, relaunch: Path | None = None) -> dict:
    root = install["root"]
    return run_posix_handoff(
        root,
        "--relaunch-target", str(relaunch or root / ".mount_Janitor" / "janitor"),
        *args,
        env={
            "APPIMAGE": str(install["running"]),
            "JANITOR_TEST_APPIMAGE_RECORD": str(install["record"]),
            "HERMES_UPDATE_SHIM_GRACE_SECONDS": "0",
            **(env or {}),
        },
    )


def _launched(install) -> str:
    return install["record"].read_text(encoding="utf-8").splitlines()[0]


def _step(install) -> str:
    return json.loads((install["root"] / "desktop-update" / "paso.json").read_text(encoding="utf-8"))["step"]


# ---------------------------------------------------------------------------
# AppImage
# ---------------------------------------------------------------------------


def test_n_to_n_plus_1_installs_the_app_pins_the_engine_and_reopens_the_new_app(install):
    seen = _run(install, *_delivery(install["downloaded"]))

    assert install["running"].read_bytes() == install["downloaded"].read_bytes()
    assert _launched(install) == "N+1"
    # The engine went to the manifest's commit, not to the branch tip.
    assert [call["commit"] for call in seen["core"]] == [COMMIT]
    result = seen["result"]
    assert result["ok"] is True and result["manual"] is False, result
    assert NEW_VERSION in result["message"] and "app y motor" in result["message"], result
    assert _step(install) == "completa"
    # Nothing staged is left next to the AppImage.
    assert [p.name for p in install["running"].parent.iterdir()] == ["Janitor.AppImage"]


def test_a_file_replaced_after_it_was_verified_is_not_installed_and_the_engine_is_left_alone(install):
    args = _delivery(install["downloaded"])
    install["downloaded"].write_text(_APP.format(version="evil"), encoding="utf-8")

    seen = _run(install, *args)

    assert "evil" not in install["running"].read_text(encoding="utf-8")
    assert seen["core"] == [], "the engine must not be touched when the app was not installed"
    assert _launched(install) == "N", "the previous app must reopen"
    result = seen["result"]
    assert result["ok"] is False, result
    assert "cambió después de descargarlo" in result["message"] and "El motor no se tocó" in result["message"], result
    assert _step(install) == "app-fallida"
    assert [p.name for p in install["running"].parent.iterdir()] == ["Janitor.AppImage"]


def test_an_appimage_folder_the_user_cannot_write_says_which_one(install):
    folder = install["running"].parent
    folder.chmod(0o555)
    try:
        seen = _run(install, *_delivery(install["downloaded"]))
    finally:
        folder.chmod(0o755)

    assert seen["core"] == []
    assert _launched(install) == "N"
    assert str(folder) in seen["result"]["message"], seen["result"]


def test_a_download_that_vanished_fails_before_anything_changes(install):
    args = _delivery(install["downloaded"])
    install["downloaded"].unlink()

    seen = _run(install, *args)

    assert seen["core"] == [] and _launched(install) == "N"
    assert seen["result"]["ok"] is False


def test_app_installed_but_engine_failed_reopens_the_new_app_and_keeps_the_step(install):
    """Cut halfway: the next attempt finishes the same delivery (engine only)."""
    seen = _run(install, *_delivery(install["downloaded"]), env={"JANITOR_TEST_CORE_EXIT": "1"})

    assert _launched(install) == "N+1"
    assert {call["commit"] for call in seen["core"]} == {COMMIT}
    result = seen["result"]
    assert result["ok"] is False, result
    assert "quedó instalada" in result["message"] and "motor no se pudo actualizar" in result["message"], result
    assert _step(install) == "motor-fallido"

    # Second attempt of the same delivery: the app is current, only the engine pin travels.
    Path(f"{install['record']}.pid").unlink()
    install["record"].unlink()
    for leftover in ("core-args.jsonl", ".hermes-update-result.json"):
        (install["root"] / leftover).unlink(missing_ok=True)
    again = run_posix_handoff_again(install, "--target-commit", COMMIT, "--app-kind", "appimage", "--app-version", NEW_VERSION)

    assert [call["commit"] for call in again["core"]] == [COMMIT]
    assert again["result"]["ok"] is True and "motor" in again["result"]["message"], again["result"]
    assert _launched(install) == "N+1"
    assert _step(install) == "completa"


def run_posix_handoff_again(install, *args: str) -> dict:
    """A second hand-off on the same fake install (its venv already exists)."""
    import shutil

    shutil.rmtree(install["root"] / "hermes-agent")
    return _run(install, *args)


def test_without_a_delivery_the_engine_follows_the_branch_as_before(install):
    seen = _run(install)

    assert [call["commit"] for call in seen["core"]] == [None]
    assert _launched(install) == "N"


@pytest.mark.parametrize(
    "bad",
    [
        ["--target-commit", "main"],
        ["--target-commit", "A" * 40],
        ["--app-kind", "deb"],
        ["--target-commit", COMMIT, "--app-kind", "appimage", "--app-installer", "relative/path",
         "--app-sha256", "0" * 64, "--app-size", "1"],
        ["--app-kind", "appimage", "--app-installer", "/x", "--app-sha256", "0" * 64, "--app-size", "1"],
        ["--target-commit", COMMIT, "--app-kind", "appimage", "--app-installer", "/x", "--app-sha256", "zz", "--app-size", "1"],
    ],
)
def test_malformed_delivery_arguments_are_refused_before_any_work(tmp_path, bad):
    from tests.janitor.desktop_update_harness import POSIX_SH, handoff_env

    done = subprocess.run(
        ["/bin/bash", str(POSIX_SH), "--install-root", str(tmp_path / "hermes-agent"), "--no-ui", *bad],
        env=handoff_env(tmp_path), capture_output=True, text=True, timeout=30,
    )

    assert done.returncode == 64, done.stderr
    assert not (tmp_path / ".hermes-update-in-progress").exists()


# ---------------------------------------------------------------------------
# Arch package (pkexec stand-in)
# ---------------------------------------------------------------------------

_PKEXEC = """#!/bin/bash
printf '%s\\n' "$@" > "$JANITOR_TEST_PKEXEC_ARGV"
[ "${JANITOR_TEST_PKEXEC_EXIT:-0}" -eq 0 ] && [ -n "${JANITOR_TEST_PKEXEC_INSTALLS:-}" ] \\
  && cp "$JANITOR_TEST_PKEXEC_INSTALLS" "$JANITOR_TEST_INSTALLED_APP"
exit "${JANITOR_TEST_PKEXEC_EXIT:-0}"
"""


@pytest.fixture
def arch(install, tmp_path, monkeypatch):
    """The app installed by the package (/opt/janitor-desktop/Janitor stand-in) and a pkexec on PATH."""
    installed = _app(tmp_path / "opt" / "janitor-desktop" / "Janitor", "N")
    new_binary = _app(tmp_path / "new-binary", "N+1")
    package = tmp_path / "desktop-update" / "21005005" / "janitor-desktop-bin-0.21.5.janitor.5-1-x86_64.pkg.tar.zst"
    package.write_bytes(b"paquete")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    pkexec = fake_bin / "pkexec"
    pkexec.write_text(_PKEXEC, encoding="utf-8")
    pkexec.chmod(0o755)
    helper = tmp_path / "helper"
    helper.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    helper.chmod(0o755)
    import os

    env = {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "JANITOR_TEST_PKEXEC_ARGV": str(tmp_path / "pkexec-argv.txt"),
        "JANITOR_TEST_PKEXEC_INSTALLS": str(new_binary),
        "JANITOR_TEST_INSTALLED_APP": str(installed),
        "APPIMAGE": "",
    }
    return {**install, "installed": installed, "package": package, "env": env, "helper": helper, "argv": tmp_path / "pkexec-argv.txt"}


def _run_arch(arch, *, pkexec_exit: int = 0, helper_present: bool = True) -> dict:
    from tests.janitor.desktop_update_harness import POSIX_SH

    # The helper path is a constant of the relay; point a copy of the scripts at the stand-in.
    scripts = arch["root"] / "relay"
    scripts.mkdir(exist_ok=True)
    for name in ("posix.sh", "janitor-app.sh"):
        text = (POSIX_SH.parent / name).read_text(encoding="utf-8")
        if name == "janitor-app.sh":
            constant = "JANITOR_ARCH_HELPER=/usr/lib/janitor-desktop/janitor-update-helper"
            assert constant in text
            target = arch["helper"] if helper_present else arch["root"] / "no-helper"
            text = text.replace(constant, f"JANITOR_ARCH_HELPER={target}")
        (scripts / name).write_text(text, encoding="utf-8")
    return run_posix_handoff(
        arch["root"],
        "--relaunch-target", str(arch["installed"]),
        *_delivery(arch["package"], kind="pacman"),
        env={
            **arch["env"],
            "JANITOR_TEST_APPIMAGE_RECORD": str(arch["record"]),
            "HERMES_UPDATE_SHIM_GRACE_SECONDS": "0",
            "JANITOR_TEST_PKEXEC_EXIT": str(pkexec_exit),
        },
        script=scripts / "posix.sh",
    )


def test_arch_the_relay_only_hands_three_paths_to_the_packages_helper(arch):
    seen = _run_arch(arch)

    package = arch["package"]
    assert arch["argv"].read_text(encoding="utf-8").splitlines() == [
        str(arch["helper"]), str(package), str(package.parent / "janitor-update.json"),
        str(package.parent / "janitor-update.json.sig"),
    ]
    assert _launched(arch) == "N+1"
    assert [call["commit"] for call in seen["core"]] == [COMMIT]
    assert seen["result"]["ok"] is True and seen["result"]["manual"] is False, seen["result"]


def test_arch_cancelling_the_password_leaves_the_engine_alone_and_reopens_the_app(arch):
    seen = _run_arch(arch, pkexec_exit=126)

    assert seen["core"] == []
    assert _launched(arch) == "N"
    result = seen["result"]
    assert result["ok"] is False and "cancelaste la contraseña" in result["message"], result
    assert "El motor no se tocó" in result["message"], result


def test_arch_without_a_polkit_agent_gives_the_exact_manual_command(arch):
    seen = _run_arch(arch, pkexec_exit=127)

    assert seen["core"] == [] and _launched(arch) == "N"
    assert f"pacman -U {arch['package']}" in seen["result"]["message"], seen["result"]


@pytest.mark.parametrize("code, fragment", [(13, "cambió después de descargarlo"), (15, "no se baja de versión"), (12, "firma")])
def test_arch_a_refusal_of_the_root_helper_is_explained_and_changes_nothing(arch, code, fragment):
    seen = _run_arch(arch, pkexec_exit=code)

    assert seen["core"] == [] and _launched(arch) == "N"
    assert fragment in seen["result"]["message"], seen["result"]


def test_arch_a_package_older_than_the_updater_says_so(arch):
    seen = _run_arch(arch, helper_present=False)

    assert not arch["argv"].exists(), "pkexec must not run without the package's helper"
    assert seen["core"] == [] and _launched(arch) == "N"
    assert "no trae el actualizador" in seen["result"]["message"], seen["result"]


def test_arch_an_engine_only_update_reopens_the_installed_app_instead_of_asking_to_reinstall(arch):
    """The owner's case on 2026-11-27: the old «skew» notice left the app closed."""
    seen = run_posix_handoff(
        arch["root"],
        "--relaunch-target", str(arch["installed"]),
        "--target-commit", COMMIT, "--app-kind", "pacman", "--app-version", NEW_VERSION,
        env={**arch["env"], "JANITOR_TEST_APPIMAGE_RECORD": str(arch["record"]), "HERMES_UPDATE_SHIM_GRACE_SECONDS": "0"},
    )

    assert _launched(arch) == "N"
    assert seen["result"]["ok"] is True and seen["result"]["manual"] is False, seen["result"]
    assert "AppImage/deb/rpm" not in seen["result"]["message"]
