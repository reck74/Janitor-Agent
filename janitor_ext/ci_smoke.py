"""Real Linux bootstrap acceptance against a local Git snapshot and provider stand-in.

Only network acquisition (PM tools, locked packages and pinned Honcho plugin)
uses the internet. Inference uses loopback and synthetic keys. Honcho service
acceptance is separate; this probe disables external memory for its one turn.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

STAGES = ("prerequisites", "repository", "venv", "python-deps", "products", "config", "complete")
REPLY = "JANITOR_SMOKE_PROVIDER_OK"
MINIMAX_KEY = "janitor-ci-synthetic-minimax"
HONCHO_KEY = "janitor-ci-synthetic-honcho"


def _run(command, *, env=None, cwd=None, timeout=1800):
    return subprocess.run(command, env=env, cwd=cwd, text=True, capture_output=True,
                          check=True, timeout=timeout)


def snapshot_source(source: Path, destination: Path) -> str:
    """Snapshot tracked + nonignored fork files without source .git or user state.

    A local fixture commit also makes a PR merge commit installable from the
    fixture's main branch and permits acceptance before the real merge commit.
    """
    names = _run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=source).stdout.split("\0")
    destination.mkdir(parents=True)
    for name in sorted(set(names) - {""}):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe source path in Git inventory")
        src, dst = source / relative, destination / relative
        if src.is_symlink():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(os.readlink(src))
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    _run(["git", "init", "-b", "main", str(destination)])
    _run(["git", "add", "--all"], cwd=destination)
    _run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
          "-c", "user.name=Janitor CI Fixture", "-c", "user.email=janitor-ci@example.invalid",
          "commit", "--quiet", "-m", "test: isolated bootstrap acceptance fixture"], cwd=destination)
    return _run(["git", "rev-parse", "HEAD"], cwd=destination).stdout.strip()


@contextmanager
def provider_stand_in():
    """Anthropic JSON and SSE wire formats consumed by the real MiniMax adapter."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4 * 1024 * 1024:
                self.send_error(413)
                return
            body = json.loads(self.rfile.read(length))
            call = {"path": self.path, "model": body.get("model")}
            calls.append(call)
            if self.path == "/v3/workspaces":
                call["accepted_auth"] = self.headers.get("Authorization") == f"Bearer {HONCHO_KEY}"
                if not call["accepted_auth"] or not body.get("name"):
                    self.send_error(401)
                    return
                payload = json.dumps({"id": body["name"], "name": body["name"], "metadata": {}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            message = {"id": "msg_janitor_smoke", "type": "message", "role": "assistant",
                       "model": body.get("model", "MiniMax-M2.7"), "content": [{"type": "text", "text": REPLY}],
                       "stop_reason": "end_turn", "stop_sequence": None,
                       "usage": {"input_tokens": 32, "output_tokens": 8}}
            if self.path.endswith("/count_tokens"):
                payload = json.dumps({"input_tokens": 32}).encode()
                content_type = "application/json"
            elif body.get("stream"):
                start = message | {"content": [], "stop_reason": None, "usage": {"input_tokens": 32, "output_tokens": 0}}
                events = [("message_start", {"message": start}),
                          ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
                          ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": REPLY}}),
                          ("content_block_stop", {"index": 0}),
                          ("message_delta", {"delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 8}}),
                          ("message_stop", {})]
                payload = "".join(f"event: {name}\ndata: {json.dumps({'type': name, **value})}\n\n" for name, value in events).encode()
                content_type = "text/event-stream"
            else:
                payload = json.dumps(message).encode()
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_acceptance(source: Path) -> None:
    import pwd
    home = Path(os.environ["HOME"]).resolve()
    if home == Path(pwd.getpwuid(os.getuid()).pw_dir).resolve():
        raise ValueError("Set HOME to an isolated directory before running bootstrap acceptance")
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    _run(["docker", "info"], timeout=30)
    with tempfile.TemporaryDirectory(prefix="janitor-bootstrap-acceptance-") as temporary, provider_stand_in() as (url, calls):
        temporary = Path(temporary)
        fixture = temporary / "source"
        commit = snapshot_source(source.resolve(), fixture)
        install = home / ".janitor/janitor-core"
        allowed = {"PATH", "LANG", "LC_ALL", "TZ", "TMPDIR", "HERMES_RUNTIME_DIR", "UV_CACHE_DIR",
                   "NPM_CONFIG_CACHE", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
        env = {key: value for key, value in os.environ.items() if key in allowed}
        env.update(HOME=str(home), JANITOR_HOME=str(home / ".janitor"), HERMES_HOME=str(home / ".janitor"),
                   JANITOR_REPO_URL=fixture.as_uri(), MINIMAX_API_KEY=MINIMAX_KEY,
                   HONCHO_API_KEY=HONCHO_KEY, HONCHO_BASE_URL=url, NO_PROXY="127.0.0.1,localhost")
        bootstrap = ["bash", str(fixture / "scripts/bootstrap.sh"), "--dir", str(install),
                     "--hermes-home", env["JANITOR_HOME"], "--branch", "main", "--commit", commit,
                     "--non-interactive", "--honcho-mode", "cloud"]
        for stage in STAGES:
            print(f"Janitor bootstrap acceptance: {stage}", flush=True)
            try:
                result = _run([*bootstrap, "--stage", stage, "--json"], env=env)
            except subprocess.CalledProcessError as exc:
                print(exc.stdout[-16000:], flush=True)
                print(exc.stderr[-16000:], flush=True)
                raise
            frames = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"ok":')]
            if not frames or frames[-1].get("stage") != stage or frames[-1].get("ok") is not True:
                raise RuntimeError(f"Bootstrap did not confirm stage {stage}: {result.stdout[-2000:]}")
        if not any(call["path"] == "/v3/workspaces" and call.get("accepted_auth") for call in calls):
            raise RuntimeError("Bootstrap did not verify the cloud memory API with its configured credential")
        if _run(["git", "rev-parse", "HEAD"], cwd=install).stdout.strip() != commit:
            raise RuntimeError("Bootstrap installed a different commit")
        for artifact in ("ui-tui/dist/entry.js", "hermes_cli/web_dist/index.html"):
            if not (install / artifact).is_file():
                raise RuntimeError(f"Bootstrap omitted {artifact}")
        command = home / ".local/bin/janitor"
        if not command.is_symlink() or not command.resolve().is_relative_to(install):
            raise RuntimeError("Published janitor command is not bound to this installation")
        profile = home / ".janitor"
        config_path = profile / "config.yaml"
        original = config_path.read_bytes()
        try:
            _run([str(install / ".hermes/bin/hermes"), "--run-module", "janitor_ext.ci_smoke",
                  "--configure-probe", str(config_path), url], env=env)
            try:
                result = _run([str(command), "chat", "--ignore-rules", "--oneshot", "-Q", "-q",
                               "Reply with the bootstrap test marker.", "--toolsets", "", "--max-turns", "2"], env=env, timeout=120)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"CLI provider probe failed: {exc.stdout[-4000:]} {exc.stderr[-4000:]}") from None
            if REPLY not in result.stdout or not any(call["path"].endswith("/messages") for call in calls):
                raise RuntimeError(f"Real MiniMax CLI probe failed: {result.stdout[-2000:]} {result.stderr[-2000:]}")
        finally:
            config_path.write_bytes(original)
        print("Janitor bootstrap acceptance passed: all stages, assets, launcher and real CLI provider path.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--configure-probe", nargs=2, metavar=("CONFIG", "BASE_URL"))
    args = parser.parse_args()
    if args.configure_probe:
        import hermes_yaml as yaml
        path, url = args.configure_probe
        config_path = Path(path)
        config = yaml.safe_load(config_path.read_text())
        config["model"].update(provider="minimax", base_url=url, api_mode="anthropic_messages")
        config["memory"]["provider"] = "builtin"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    else:
        run_acceptance(args.source)


if __name__ == "__main__":
    main()
