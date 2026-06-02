## 2026-05-30 final verification
+ `registry.register(... handler=lambda ...)` in `tools/delegate_tool.py` does not pass `agent_type=args.get("agent_type")` into `delegate_task()`, so model/tool invocations cannot explicitly request a specialized agent despite the schema exposing the parameter.
+ Required verification commands fail with bare `python` because `python` is not on PATH; equivalent commands pass under `./.venv/bin/python`.
+ `lsp_diagnostics` for `tools/delegate_tool.py` reports existing basedpyright errors, including new `agent_spec.skills` typing at line 992 and `agent_type` typing at line 2143.
