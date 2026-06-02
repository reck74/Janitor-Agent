## 2026-05-30
+ Added `SKILLS AVAILABLE: ...` to specialized child-agent prompts when `agent_spec["skills"]` is present.

## 2026-05-30 (delegate_task routing)
+ Imported `get_best_agent` into `tools/delegate_tool.py` and applied auto-routing only in the single-goal branch, after role normalization and before task list construction.
