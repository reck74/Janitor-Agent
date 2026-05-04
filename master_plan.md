<master_plan>
  <system_context>
    Estás actuando como OpenCode, ejecutando un Master Plan de Arquitectura diseñado por el CTO.
    El objetivo es crear un fork parasitario ("Janitor") sobre el repositorio de Hermes Agent.
    
    REGLA DE ORO DE ARQUITECTURA: TIENES PROHIBIDO realizar un buscar-y-reemplazar masivo de la palabra "hermes". El paquete interno mantiene su nombre original para garantizar que `git pull upstream main` funcione en el futuro sin conflictos destructivos.
    
    ENTORNO: WSL2 / Linux.
    TESTING: `pytest` para Python, `vitest` para TypeScript (TUI). TDD es obligatorio.
  </system_context>

  <agentic_topology>
    Usa la herramienta `bash` o `edit` para INYECTAR al principio del archivo raíz `AGENTS.md` la siguiente sección:
    
    "# JANITOR FORK DIRECTIVES (SUPREME RULES)
    1. ZERO-RENAMING POLICY: Nunca hagas buscar-y-reemplazar de la palabra 'hermes' en el core. El motor subyacente se mantiene intacto.
    2. CLI WRAPPER: Las extensiones de Janitor heredarán de HermesCLI en archivos separados (ej. janitor_cli.py).
    3. SKILLS AISLADOS: Toda habilidad nueva debe ir exclusivamente bajo `skills/janitor-*/`.
    4. TUI ISOLATION: Los cambios visuales del TUI deben ser condicionados o inyectados sin destruir la compatibilidad del protocolo JSON-RPC."[... mantén el resto de las instrucciones de merge-auditor y tui-compilation ...]
  </agentic_topology>

  <state_management>
    Inicia tu ejecución utilizando la herramienta `todowrite`. Mapea exactamente las 5 Fases del bloque `<execution_steps>` como tareas.
    Actualiza el estado con `todowrite` inmediatamente después de completar cada tarea. 
    Usa `todoread` cada vez que necesites recordar el progreso tras un reinicio de contexto. Ignorar el uso de `todowrite` es una violación crítica del protocolo.
  </state_management>

  <execution_steps>
    Fase 1: Configuración del Wrapper CLI "Janitor"
    - Usa `bash` para crear un archivo test `tests/test_janitor_cli.py` (Red). Verifica que espera la existencia del comando `janitor` y la clase `JanitorCLI`.
    - Usa `write` para crear `janitor_cli.py` en la raíz (o en `hermes_cli/`). Haz que contenga una clase `JanitorCLI` que herede de `HermesCLI`, con la propiedad de forzar el skin y la identidad visual de Janitor.
    - Usa `edit` para modificar `pyproject.toml`. En la sección `[project.scripts]`, añade `janitor = "janitor_cli:main"` (o la ruta correcta donde decidas exponer la función main).
    - Ejecuta `uv pip install -e .` vía `bash` y asegúrate de que el test `pytest tests/test_janitor_cli.py` pasa (Green).

    Fase 2: Instalador Condicionado (Janitor Wrapper)
    - Usa `bash` para analizar el script actual `scripts/install.sh`.
    - Usa `write` para crear `scripts/janitor-install.sh`. 
    - Este script debe: 
        1. Llamar a `install.sh` o replicar sus funciones de dependencias.
        2. Crear el archivo `~/.hermes/SOUL.md` inyectando automáticamente la personalidad cínica y de ciberseguridad de Janitor.
        3. Escribir forzosamente en `~/.hermes/config.yaml` la activación de Honcho (`memory.provider: honcho`) y el arranque automático del TUI (`display.tui: true`).
    - Usa `bash` para darle permisos de ejecución (`chmod +x`).

    Fase 3: Aislamiento del TUI (TypeScript)
    - Entra a `ui-tui/` con `bash`. Verifica dependencias con `npm install`.
    - Crea un test en `ui-tui/src/__tests__/` (Red) que valide la inyección del nombre "Janitor" en los componentes de branding.
    - Usa `edit` o `patch` en `ui-tui/src/components/branding.tsx` y `app.tsx` para aplicar las personalizaciones visuales de Janitor. Mantén los cambios encapsulados para minimizar conflictos de merge futuros.
    - Ejecuta el skill nativo `skill` llamando a la habilidad `tui-compilation` que creaste en la topología, para asegurar que la compilación (Green) y los tests TS pasen.

    Fase 4: Configuración Nativa de Honcho
    - Revisa `plugins/memory/honcho/` vía `read`.
    - Usa `edit` en la configuración inicial de Janitor (o en tu `janitor_cli.py` setup_hook) para que, al correr el agente por primera vez, se verifique si las variables de entorno para Honcho están presentes. Si no lo están, el agente debe abortar con un error controlado de validación de seguridad (OWASP - fail safe) exigiendo la configuración.

    Fase 5: Skills Preconfigurados
    - Usa `bash` para crear el directorio `skills/janitor-core/`.
    - Usa `write` para generar un `SKILL.md` dentro que contenga metadatos válidos (name, description, etc.).
    - Crea un script asociado en `skills/janitor-core/scripts/` que simule una tarea de limpieza de caché local, asegurando que se requiere interacción segura (TDD: escribe un test de ejecución de esta skill si es posible mockear el entorno de Hermes).
  </execution_steps>

  <fallback_and_doom_loop_protocol>
    Si en cualquier punto de las Fases 3 o 4 (especialmente manejando React/TypeScript o el TUI) experimentas 3 fallos consecutivos en compilación o testing:
    1. DETÉN LA EJECUCIÓN INMEDIATAMENTE.
    2. Revierte los archivos en conflicto utilizando el sistema de snapshots o con `git checkout -- <archivo>`.
    3. Deja un comentario de TODO detallado en el código.
    4. Usa la API nativa de invocación para llamar al auditor (`@merge-auditor por favor revisa por qué la extensión del CLI está fallando contra la versión actual de Hermes`) y espera a la validación antes de abortar.
  </fallback_and_doom_loop_protocol>

  <local_ci_and_security>
    Antes de marcar el Master Plan como completado:
    - Ejecuta `bash` con `npm audit` dentro de `ui-tui/`. Si hay vulnerabilidades altas introducidas, reviértelas.
    - Verifica explícitamente mediante un script temporal que al correr el nuevo comando `janitor`, el entorno de subagentes y la retención de memoria (Honcho) respeten el sandboxing original sin escalar privilegios.
    - Corre la suite completa `pytest tests/ -v -n0` para validar que ninguna funcionalidad base del motor de Hermes original se rompió por el wrapper.
  </local_ci_and_security>
</master_plan>