"""Obreros: Janitor dirige los programas de agente que el usuario ya tiene instalados.

Los obreros son Claude Code (``claude``) y Codex (``codex``), ejecutados tal cual
los instaló el usuario y con su propia sesión. Janitor nunca lee ni copia sus
credenciales (plan ``docs/janitor/plans/obreros-claude-codex.md``, sección 4.5).

Módulos:

- ``deteccion``: si cada programa está instalado y con sesión iniciada.
"""
