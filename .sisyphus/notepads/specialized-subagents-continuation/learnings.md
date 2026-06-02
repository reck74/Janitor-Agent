## 2026-05-30
+ `agent_spec.skills` can be surfaced directly in `_build_child_agent` without loading skill content.
+ Specialized child prompts should keep the spec prompt first, then task/context metadata, and only add skill names as a flat availability line.

## 2026-05-30 (delegate_task routing)
+ `delegate_task()` can auto-classify single-task goals by calling `get_best_agent(goal)` only when `agent_type` is unset.
+ Keep the fallback path intact: if routing returns `None`, the existing generic delegation behavior should remain unchanged.

## 2026-05-30 (registry handler)
+ `DELEGATE_TASK_SCHEMA` additions must be mirrored in the `registry.register(... handler=...)` lambda; otherwise model-facing dispatch drops new parameters before `delegate_task()` sees them.
