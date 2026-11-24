"""Janitor desktop plugin backend, mounted by Hermes at ``/api/plugins/janitor/``.

Seeded by ``janitor.desktop_plugin.sync``; the routes live in
``janitor.desktop_plugin.api`` so they update with the Janitor package.
"""

from janitor.desktop_plugin.api import build_router

router = build_router()
