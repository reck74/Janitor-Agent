"""Child process that creates one specialist for the "Agentes" screen.

``python -m janitor.desktop_plugin.crear_agente <plantilla> <nombre>`` with
``HERMES_HOME`` at the Janitor root; prints one JSON line (no secrets). See
:func:`janitor.desktop_plugin.perfiles.create_agent`.
"""

import sys

from janitor.desktop_plugin.perfiles import _main

if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
