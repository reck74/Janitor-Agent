# Agentes especializados de Janitor

Las capacidades activas se entregan como skills bajo `skills/janitor-*-agent/`. El agente carga el skill y delega explícitamente mediante las interfaces upstream disponibles.

El diseño anterior proponía un router automático y `agent.yaml`; ese prototipo no forma parte del contrato de ejecución actual. Su documentación se conserva en `legacy/docs/pre-1.0/specialized-agents/` como referencia. No se debe afirmar que el core enruta automáticamente tareas o que acepta nuevos parámetros de delegación sin validar primero la interfaz real.

Los nuevos skills deben seguir `AGENTS.md`, vivir en `skills/janitor-*/` y registrarse en el onboarding. Consulta [la arquitectura actual](../janitor-project.md).
