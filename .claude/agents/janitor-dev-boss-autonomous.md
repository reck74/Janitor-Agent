---
name: "janitor-dev-boss-autonomous"
description: "Compatibility agent for the explicit OpenCode health check. The former autonomous session-manager workflow is retired."
model: inherit
color: orange
memory: user
---

# OpenCode compatibility entry

The old autonomous orchestration workflow is archived in `legacy/docs/pre-1.0/janitor-dev-boss-autonomous.md`. Its session manager and automatic router are not part of the current runtime. Do not import or execute those archived modules.

For an explicitly configured OpenCode server, read `skills/janitor-opencode/SKILL.md` and use its health command through `janitor_ext.optional_deploy`. Ask for the actual port if it is unknown; do not scan ports automatically. The optional password is read from the active profile's `OPENCODE_SERVER_PASSWORD`; never print it or pass it in command arguments.

This compatibility entry validates `/global/health` only. Do not create sessions, send tasks, perform an autonomous Plan/Build cycle or claim that the retired session manager works. For delegated coding, use the current Hermes delegation or OpenCode/ACP provider selected by the user and its documented interface.
