"""Corpus de tips en español para Janitor.

Este módulo reemplaza el corpus de tips en inglés de Hermes con una
versión traducida y adaptada al branding Janitor.
"""

import random

JANITOR_TIPS = [
    # --- Comandos Slash ---
    "/background <prompt> (alias /bg o /btw) ejecuta una tarea en una sesión separada mientras la actual permanece libre.",
    "/branch bifurca la sesión actual para que puedas explorar otra dirección sin perder el progreso.",
    "/compress comprime manualmente el contexto de la conversación cuando las cosas se alargan.",
    "/rollback lista los checkpoints del sistema de archivos — restaura los archivos modificados por el agente a cualquier estado anterior.",
    "/rollback diff 2 previsualiza qué cambió desde el checkpoint 2 sin restaurar nada.",
    "/rollback 2 src/archivo.py restaura un solo archivo desde un checkpoint específico.",
    "/title \"mi proyecto\" nombra tu sesión — reanúdala más tarde con /resume o janitor -c.",
    "/resume retoma donde la dejaste en una sesión con nombre previamente guardada.",
    "/queue <prompt> encola un mensaje para el siguiente turno sin interrumpir el actual.",
    "/undo elimina el último intercambio usuario/asistente de la conversación.",
    "/retry reenvía tu último mensaje — útil cuando la respuesta del agente no fue del todo correcta.",
    "/verbose alterna la visualización del progreso de herramientas: off → new → all → verbose.",
    "/reasoning high aumenta la profundidad de pensamiento del modelo. /reasoning show muestra el razonamiento.",
    "/fast alterna el procesamiento prioritario para respuestas más rápidas de la API (depende del proveedor).",
    "/yolo omite todos los prompts de aprobación de comandos peligrosos durante el resto de la sesión.",
    "/model te permite cambiar de modelo en medio de la sesión — prueba /model sonnet o /model gpt-5.",
    "/model --global cambia tu modelo predeterminado de forma permanente.",
    "/personality pirate establece una personalidad divertida — hay 14 opciones integradas desde kawaii hasta shakespeare.",
    "/skin cambia el tema del CLI — prueba ares, mono, slate, poseidon o charizard.",
    "/statusbar alterna una barra persistente que muestra modelo, tokens, porcentaje de contexto, costo y duración.",
    "/tools disable browser elimina temporalmente las herramientas del navegador para la sesión actual.",
    "/browser connect conecta las herramientas del navegador a tu navegador Chromium en ejecución vía CDP.",
    "/plugins lista los plugins instalados y su estado.",
    "/cron gestiona tareas programadas — configura prompts recurrentes con entrega a cualquier plataforma.",
    "/reload-mcp recarga la configuración de servidores MCP sin reiniciar.",
    "/usage muestra el uso de tokens, desglose de costos y duración de la sesión.",
    "/insights muestra análisis de uso de los últimos 30 días.",
    "/paste revisa tu portapapeles en busca de una imagen y la adjunta a tu siguiente mensaje.",
    "/profile muestra qué perfil está activo y su directorio principal.",
    "/config muestra tu configuración actual de un vistazo.",
    "/stop mata todos los procesos en segundo plano iniciados por el agente.",

    # --- Referencias de Contexto @ ---
    "@file:ruta/al/archivo.py inyecta el contenido del archivo directamente en tu mensaje.",
    "@file:main.py:10-50 inyecta solo las líneas 10-50 de un archivo.",
    "@folder:src/ inyecta un listado del árbol de directorios.",
    "@diff inyecta tus cambios git no staggeados en el mensaje.",
    "@staged inyecta tus cambios git staggeados (git diff --staged).",
    "@git:5 inyecta los últimos 5 commits con sus parches completos.",
    "@url:https://ejemplo.com obtiene e inyecta el contenido de una página web.",
    "Escribir @ activa la completación de rutas del sistema de archivos — navega a cualquier archivo de forma interactiva.",
    "Combina múltiples referencias: \"Revisa @file:main.py y @file:test.py para verificar consistencia.\"",

    # --- Atajos de Teclado ---
    "Alt+Enter inserta una nueva línea para entrada multilínea. (Windows Terminal intercepta Alt+Enter — usa Ctrl+Enter en su lugar.)",
    "Ctrl+C interrumpe al agente. Presiona dos veces dentro de 2 segundos para forzar la salida.",
    "Ctrl+Z suspende Janitor en segundo plano — ejecuta fg en tu shell para reanudar.",
    "Tab acepta el texto fantasma de sugerencia automática o autocompleta comandos slash.",
    "Escribe un mensaje nuevo mientras el agente trabaja para interrumpirlo y redirigirlo.",
    "Alt+V pega una imagen desde tu portapapeles en la conversación.",
    "Pegar 5+ líneas guarda automáticamente en un archivo e inserta una referencia compacta en su lugar.",

    # --- Banderas del CLI ---
    "janitor -c reanuda tu sesión más reciente del CLI. janitor -c \"nombre proyecto\" reanuda por título.",
    "janitor -w crea un git worktree aislado — perfecto para flujos de trabajo paralelos del agente.",
    "janitor -w -q \"Fix issue #42\" combina aislamiento de worktree con una consulta de una sola vez.",
    "janitor chat -t web,terminal habilita solo toolsets específicos para una sesión enfocada.",
    "janitor chat -s github-pr-workflow precarga una skill al iniciar.",
    "janitor chat -q \"consulta\" ejecuta una única consulta no interactiva y sale.",
    "janitor chat --max-turns 200 anula el límite predeterminado de 90 iteraciones por turno.",
    "janitor chat --checkpoints habilita snapshots del sistema de archivos antes de cada cambio destructivo.",
    "janitor --yolo omite todos los prompts de aprobación de comandos peligrosos durante toda la sesión.",
    "janitor chat --source telegram etiqueta la sesión para filtrar en janitor sessions list.",
    "janitor -p work chat ejecuta bajo un perfil específico sin cambiar tu predeterminado.",

    # --- Subcomandos del CLI ---
    "janitor doctor --fix diagnostica y repara automáticamente problemas de configuración y dependencias.",
    "janitor dump genera un resumen compacto de la configuración — ideal para reportes de errores.",
    "janitor config set KEY VALUE enruta secretos a .env y todo lo demás a config.yaml.",
    "janitor config edit abre config.yaml en tu editor predeterminado.",
    "janitor config check busca opciones de configuración faltantes u obsoletas.",
    "janitor sessions browse abre un selector interactivo de sesiones con búsqueda.",
    "janitor sessions stats muestra conteos de sesiones por plataforma y tamaño de base de datos.",
    "janitor sessions prune --older-than 30 limpia sesiones antiguas.",
    "janitor skills search react --source skills-sh busca en el directorio público de skills.sh.",
    "janitor skills check escanea skills instaladas del hub en busca de actualizaciones upstream.",
    "janitor skills tap add myorg/skills-repo agrega una fuente de skills personalizada de GitHub.",
    "janitor skills snapshot export setup.json exporta tu configuración de skills para respaldo o compartir.",
    "janitor mcp add github --command npx agrega servidores MCP desde la línea de comandos.",
    "janitor mcp serve ejecuta Janitor como un servidor MCP para otros agentes.",
    "janitor auth add te permite agregar múltiples claves API para rotación de credential pool.",
    "janitor completion bash >> ~/.bashrc habilita autocompletado para todos los comandos y perfiles.",
    "janitor logs -f sigue agent.log en tiempo real. --level WARNING --since 1h filtra la salida.",
    "janitor backup crea un zip de respaldo de todo tu directorio principal de Janitor.",
    "janitor profile create coder crea un perfil aislado que se convierte en su propio comando.",
    "janitor profile create work --clone copia tu configuración y claves actuales a un nuevo perfil.",
    "janitor update sincroniza nuevas skills incluidas a TODOS los perfiles automáticamente.",
    "janitor gateway install configura Janitor como un servicio del sistema (systemd/launchd).",
    "janitor memory setup te permite configurar un proveedor de memoria externo (Honcho, Mem0, etc.).",
    "janitor webhook subscribe crea rutas de webhook impulsadas por eventos con validación HMAC.",
    "Ahorra dinero: janitor tools desactiva herramientas no usadas, janitor skills config reduce las skills.",
    "/reasoning low o /reasoning minimal reduce la profundidad de pensamiento por debajo del predeterminado (medium) — respuestas más rápidas y baratas.",
    "janitor models enruta vision, compresión y tareas auxiliares a modelos más baratos — reduce el costo de tokens en segundo plano en más del 85% sin degradar tu modelo principal de chat.",

    # --- Configuración ---
    "Establece display.bell_on_complete: true en config.yaml para escuchar una campana cuando las tareas largas terminan.",
    "Establece display.streaming: true para ver los tokens aparecer en tiempo real mientras el modelo genera.",
    "Establece display.show_reasoning: true para ver el razonamiento paso a paso del modelo.",
    "Establece display.compact: true para reducir espacios en blanco en la salida para información más densa.",
    "Establece display.busy_input_mode: queue para encolar mensajes en lugar de interrumpir al agente, o steer para inyectarlos en medio de la ejecución vía /steer.",
    "Establece display.resume_display: minimal para omitir el resumen completo de la conversación al reanudar una sesión.",
    "Establece compression.threshold: 0.50 para controlar cuándo se dispara la compresión automática (predeterminado: 50% del contexto).",
    "Establece agent.max_turns: 200 para permitir que el agente dé más pasos de llamada a herramientas por turno.",
    "Establece file_read_max_chars: 200000 para aumentar el contenido máximo por llamada a read_file.",
    "Establece approvals.mode: smart para permitir que un LLM apruebe automáticamente comandos seguros y niegue los peligrosos.",
    "Establece fallback_model en config.yaml para fallar automáticamente a un proveedor de respaldo.",
    "Establece privacy.redact_pii: true para hashear IDs de usuario y números de teléfono antes de enviarlos al LLM.",
    "Establece browser.record_sessions: true para grabar automáticamente sesiones del navegador como videos WebM.",
    "Establece worktree: true en config.yaml para crear siempre un git worktree (igual que janitor -w).",
    "Establece security.website_blocklist.enabled: true para bloquear dominios específicos de las herramientas web.",
    "Establece cron.wrap_response: false para entregar la salida cruda del agente sin el encabezado/pie de cron.",
    "HERMES_TIMEZONE anula la zona horaria del servidor con cualquier cadena de zona IANA.",
    "La sustitución de variables de entorno funciona en config.yaml: usa la sintaxis ${VAR_NAME}.",
    "Los quick commands en config.yaml ejecutan comandos de shell al instante con uso cero de tokens.",
    "Las personalidades personalizadas pueden definirse en config.yaml bajo agent.personalities.",
    "provider_routing controla el ordenamiento, lista blanca y lista negra de proveedores en OpenRouter.",

    # --- Herramientas y Capacidades ---
    "execute_code ejecuta scripts de Python que llaman herramientas de Janitor programáticamente — los resultados se mantienen fuera del contexto.",
    "delegate_task genera hasta 3 subagentes concurrentes por defecto (delegation.max_concurrent_children) con contextos aislados para trabajo en paralelo.",
    "web_extract funciona en URLs de PDF — pasa cualquier enlace de PDF y lo convierte a markdown.",
    "search_files está respaldado por ripgrep y es más rápido que grep — úsalo en lugar de terminal grep.",
    "patch usa 9 estrategias de coincidencia difusa para que pequeñas diferencias de espacios en blanco no rompan las ediciones.",
    "patch soporta formato V4A para ediciones masivas de múltiples archivos en una sola llamada.",
    "read_file sugiere nombres de archivo similares cuando no encuentra uno.",
    "read_file desduplica automáticamente — releer un archivo sin cambios devuelve un stub ligero.",
    "browser_vision toma una captura de pantalla y la analiza con IA — funciona para CAPTCHAs y contenido visual.",
    "browser_console puede evaluar expresiones JavaScript en el contexto de la página.",
    "image_generate crea imágenes con FLUX 2 Pro y upscaling automático 2x.",
    "text_to_speech convierte texto a audio — se reproduce como burbujas de voz en Telegram.",
    "send_message puede alcanzar cualquier plataforma de mensajería conectada desde dentro de una sesión.",
    "La herramienta todo ayuda al agente a rastrear tareas complejas de múltiples pasos durante una sesión.",
    "session_search realiza búsqueda de texto completo a través de TODAS las conversaciones pasadas.",
    "El agente guarda automáticamente preferencias, correcciones y hechos del entorno en memoria.",
    "mixture_of_agents enruta problemas difíciles a través de 4 LLMs frontier de forma colaborativa.",
    "Los comandos de terminal soportan modo en segundo plano con notify_on_complete para tareas de larga duración.",
    "Los procesos en segundo plano del terminal soportan watch_patterns para alertar sobre líneas de salida específicas.",
    "La herramienta de terminal soporta 6 backends: local, Docker, SSH, Modal, Daytona y Singularity.",

    # --- Perfiles ---
    "Cada perfil obtiene su propia configuración, claves API, memoria, sesiones, skills y trabajos cron.",
    "Los nombres de perfil se convierten en comandos de shell — 'janitor profile create coder' crea el comando 'coder'.",
    "janitor profile export coder -o backup.tar.gz crea un archivo portable del perfil.",
    "Si dos perfiles comparten accidentalmente un token de bot, el segundo gateway es bloqueado con un error claro.",

    # --- Sesiones ---
    "Las sesiones generan títulos descriptivos automáticamente después del primer intercambio — no se necesita nombrar manualmente.",
    "Los títulos de sesión soportan linaje: \"mi proyecto\" → \"mi proyecto #2\" → \"mi proyecto #3\".",
    "Al salir, Janitor imprime un comando de reanudación con ID de sesión y estadísticas.",
    "janitor sessions export backup.jsonl exporta todas las sesiones para respaldo o análisis.",
    "janitor -r SESSION_ID reanuda cualquier sesión pasada específica por su ID.",

    # --- Memoria ---
    "La memoria es una instantánea congelada — los cambios aparecen en el system prompt solo al inicio de la siguiente sesión.",
    "Las entradas de memoria son escaneadas automáticamente en busca de patrones de inyección de prompts y exfiltración.",
    "El agente tiene dos almacenes de memoria: notas personales (~2200 caracteres) y perfil de usuario (~1375 caracteres).",
    "Las correcciones que le das al agente (\"no, hazlo así\") a menudo se guardan automáticamente en memoria.",

    # --- Skills ---
    "Más de 80 skills incluidas que cubren github, creativas, mlops, productividad, investigación y más.",
    "Cada skill instalada se convierte automáticamente en un comando slash — escribe / para verlas todas.",
    "janitor skills install official/security/1password instala skills opcionales del repositorio.",
    "Las skills pueden restringirse a plataformas específicas — algunas solo cargan en macOS o Linux.",
    "skills.external_dirs en config.yaml te permite cargar skills desde directorios personalizados.",
    "El agente puede crear sus propias skills como memoria procedural usando skill_manage.",
    "La skill plan guarda planes markdown bajo .janitor/plans/ en el espacio de trabajo activo.",

    # --- Cron y Programación ---
    "Los trabajos cron pueden adjuntar skills: janitor cron add --skill blogwatcher \"Revisa nuevas publicaciones\".",
    "Los destinos de entrega de cron incluyen telegram, discord, slack, email, sms y 12+ plataformas más.",
    "Si una respuesta de cron comienza con [SILENT], la entrega se suprime — útil para trabajos solo de monitoreo.",
    "Cron soporta retrasos relativos (30m), intervalos (every 2h), expresiones cron y timestamps ISO.",
    "Los trabajos cron se ejecutan en sesiones completamente nuevas del agente — los prompts deben ser autocontenidos.",

    # --- Voz ---
    "El modo de voz funciona con cero claves API si faster-whisper está instalado (STT local gratuito).",
    "Cinco proveedores de TTS disponibles: Edge TTS (gratis), ElevenLabs, OpenAI, NeuTTS (local gratuito), MiniMax.",
    "/voice on habilita el modo de voz en el CLI. Ctrl+B alterna la grabación push-to-talk.",
    "El TTS en streaming reproduce oraciones a medida que se generan — no esperas la respuesta completa.",
    "Los mensajes de voz en Telegram, Discord, WhatsApp y Slack se transcriben automáticamente.",

    # --- Gateway y Mensajería ---
    "Janitor corre en 21 plataformas de mensajería: Telegram, Discord, Slack, WhatsApp, Signal, Matrix, IRC, Microsoft Teams, email y más.",
    "janitor gateway install lo configura como un servicio del sistema que inicia al arrancar.",
    "DingTalk usa Stream Mode — no se necesitan webhooks ni URL públicas.",
    "BlueBubbles trae iMessage a Janitor vía un servidor local de macOS.",
    "Las rutas de webhook soportan validación HMAC, limitación de tasa y filtrado de eventos.",
    "El servidor API expone un endpoint compatible con OpenAI que funciona con Open WebUI y LibreChat.",
    "Modo de canal de voz de Discord: el bot se une al VC, transcribe el habla y responde.",
    "group_sessions_per_user: true le da a cada persona su propia sesión en chats grupales.",
    "/sethome marca un chat como el canal principal para entregas de trabajos cron.",
    "El gateway soporta timeouts basados en inactividad — los agentes activos pueden ejecutarse indefinidamente.",

    # --- Seguridad ---
    "La aprobación de comandos peligrosos tiene 4 niveles: once, session, always (lista de permitidos permanente), deny.",
    "El modo de aprobación inteligente usa un LLM para aprobar automáticamente comandos seguros y marcar los peligrosos.",
    "La protección SSRF bloquea redes privadas, loopback, link-local y direcciones de metadata en la nube.",
    "El escaneo pre-ejecución de Tirith detecta suplantación de URLs homógrafo y patrones de pipe-a-intérprete.",
    "Los subprocesos de MCP reciben un entorno filtrado — solo pasan variables de sistema seguras.",
    "Los archivos de contexto (.janitor.md, AGENTS.md) se escanean en busca de inyección de prompts antes de cargar.",
    "command_allowlist en config.yaml aprueba permanentemente patrones específicos de comandos de shell.",

    # --- Contexto y Compresión ---
    "El contexto se comprime automáticamente cuando alcanza el umbral — las memorias se vacían y el historial se resume.",
    "La barra de estado se vuelve amarilla, luego naranja, luego roja a medida que el contexto se llena.",
    "SOUL.md en ~/.janitor/SOUL.md es la identidad principal del agente — personalízalo para dar forma al comportamiento.",
    "Janitor carga contexto de proyecto desde .janitor.md, AGENTS.md, CLAUDE.md o .cursorrules (primera coincidencia).",
    "Los archivos AGENTS.md de subdirectorios se descubren progresivamente a medida que el agente navega en carpetas.",
    "Los archivos de contexto están limitados a 20,000 caracteres con truncamiento inteligente de cabeza/cola.",

    # --- Navegador ---
    "Cinco proveedores de navegador: Chromium local, Browserbase, Browser Use, Camofox y Firecrawl.",
    "Camofox es un navegador anti-detección — fork de Firefox con spoofing de huellas en C++.",
    "browser_navigate devuelve automáticamente un snapshot de la página — no necesitas llamar browser_snapshot después.",
    "browser_vision con annotate=true superpone etiquetas numeradas sobre elementos interactivos.",

    # --- MCP ---
    "Los servidores MCP se configuran en config.yaml — se soportan transportes stdio y HTTP.",
    "Filtrado por servidor de herramientas: tools.include lista blanca y tools.exclude lista negra herramientas específicas.",
    "Los servidores MCP generan toolsets automáticamente en tiempo de ejecución — janitor tools puede alternarlos por plataforma.",
    "Soporte OAuth de MCP: auth: oauth habilita autorización basada en navegador con PKCE.",

    # --- Checkpoints y Rollback ---
    "Los checkpoints tienen cero overhead cuando no se modifican archivos — habilitados por defecto.",
    "Un snapshot pre-rollback se guarda automáticamente para que puedas deshacer el deshacer.",
    "/rollback también deshace el turno de conversación, así que el agente no recuerda los cambios revertidos.",
    "Los checkpoints usan repos sombra en ~/.janitor/checkpoints/ — el .git de tu proyecto nunca se toca.",

    # --- Batch y Datos ---
    "batch_runner.py procesa cientos de prompts en paralelo para generación de datos de entrenamiento.",
    "janitor chat -Q habilita modo silencioso para uso programático — suprime el banner y el spinner.",
    "El guardado de trayectorias (--save-trajectories) captura trazas completas de uso de herramientas para entrenamiento de modelos.",

    # --- Plugins ---
    "Tres tipos de plugins: general (herramientas/hooks), proveedores de memoria y motores de contexto.",
    "janitor plugins install owner/repo instala plugins directamente desde GitHub.",
    "8 proveedores de memoria externos disponibles: Honcho, OpenViking, Mem0, Hindsight y más.",
    "Los hooks de plugin incluyen pre/post_tool_call, pre/post_llm_call y transform_terminal_output para canonicalización de salida.",

    # --- Misceláneos ---
    "El caching de prompts (Anthropic) reduce costos reutilizando prefijos de system prompt en caché.",
    "El agente genera títulos de sesión en un hilo en segundo plano — impacto de latencia cero.",
    "El enrutamiento inteligente de modelos puede enrutar consultas simples a un modelo más barato.",
    "Los comandos slash soportan coincidencia por prefijo: /h se resuelve a /help, /mod a /model.",
    "Arrastrar una ruta de archivo al terminal adjunta automáticamente imágenes o envía como contexto.",
    ".worktreeinclude en la raíz de tu repo lista archivos ignorados por git para copiar en worktrees.",
    "janitor acp ejecuta Janitor como un servidor ACP para integración con VS Code, Zed y JetBrains.",
    "Proveedores personalizados: guarda endpoints nombrados en config.yaml bajo custom_providers.",
    "HERMES_EPHEMERAL_SYSTEM_PROMPT inyecta un system prompt que nunca se persiste al historial.",
    "credential_pool_strategies soporta fill_first, round_robin, least_used y rotación random.",
    "janitor login soporta autenticación OAuth para proveedores Nous y OpenAI Codex.",
    "El servidor API soporta tanto Chat Completions como Responses API con estado del lado del servidor.",
    "tool_preview_length: 0 en config muestra rutas completas de archivos en el feed de actividad del spinner.",
    "janitor status --deep ejecuta chequeos de diagnóstico más profundos en todos los componentes.",

    # --- Gemas Ocultas y Trucos de Usuario Avanzado ---
    "Los trabajos cron pueden adjuntar un script de Python (--script) cuya salida estándar se inyecta en el prompt como contexto.",
    "Los scripts de cron viven en ~/.janitor/scripts/ y se ejecutan antes del agente — perfectos para pipelines de recolección de datos.",
    "prefill_messages_file en config.yaml inyecta ejemplos few-shot en cada llamada a la API, nunca guardados en el historial.",
    "SOUL.md reemplaza completamente la identidad predeterminada del agente — reescríbelo para hacer de Janitor tu propio agente.",
    "SOUL.md se siembra automáticamente con una personalidad predeterminada en la primera ejecución. Edita ~/.janitor/SOUL.md para personalizar.",
    "/compress <tema de enfoque> asigna 60-70% del presupuesto de resumen a tu tema y recorta agresivamente el resto.",
    "En la segunda+ compresión, el compresor actualiza el resumen anterior en lugar de empezar desde cero.",
    "Antes de un reinicio de sesión del gateway, Janitor vacía automáticamente hechos importantes a memoria en segundo plano.",
    "network.force_ipv4: true en config.yaml corrige bloqueos en servidores con IPv6 rota — hace monkey-patch de socket.",
    "La herramienta de terminal anota códigos de salida comunes: grep devolviendo 1 = 'No se encontraron coincidencias (no es un error)'.",
    "Los comandos de terminal en primer plano fallidos reintentan automáticamente hasta 3 veces con backoff exponencial (2s, 4s, 8s).",
    "Los comandos sudo simples se reescriben automáticamente para pipear SUDO_PASSWORD desde .env — sin prompt interactivo.",
    "execute_code tiene helpers integrados: json_parse() para parsing tolerante, shell_quote() y retry() con backoff.",
    "Las 7 herramientas sandbox de execute_code (web_search, terminal, read/write/search/patch) usan RPC — nunca entran en contexto.",
    "Leer la misma región de archivo 3+ veces dispara una advertencia. A las 4+, se bloquea duramente para prevenir bucles.",
    "write_file y patch detectan si un archivo fue modificado externamente desde la última lectura y advierten sobre obsolescencia.",
    "El formato de parche V4A soporta directivas Add File, Delete File y Move File — no solo Update.",
    "Los servidores MCP pueden solicitar completaciones de LLM de vuelta vía sampling — el agente se convierte en herramienta para el servidor.",
    "Los servidores MCP envían notifications/tools/list_changed para disparar re-registro automático de herramientas sin reiniciar.",
    "delegate_task con acp_command: 'claude' genera Claude Code como agente hijo desde cualquier plataforma.",
    "La delegación tiene un hilo de heartbeat — la actividad del hijo se propaga al padre, previniendo timeouts del gateway.",
    "Cuando un proveedor devuelve HTTP 402 (pago requerido), el cliente auxiliar falla automáticamente al siguiente.",
    "agent.tool_use_enforcement guía a modelos que describen acciones en lugar de llamar herramientas — auto para GPT/Codex.",
    "agent.restart_drain_timeout (predeterminado 60s) permite que los agentes en ejecución terminen antes de que un reinicio del gateway surta efecto.",
    "agent.api_max_retries (predeterminado 3) controla cuántas veces el agente reintenta una llamada a API fallida antes de mostrar el error — redúcelo para fallback rápido.",
    "El gateway cachea instancias de AIAgent por sesión — destruir este caché rompe el prompt caching de Anthropic.",
    "Cualquier sitio web puede exponer skills vía /.well-known/skills/index.json — el hub de skills las descubre automáticamente.",
    "El log de auditoría de skills en ~/.janitor/skills/.hub/audit.log rastrea cada operación de instalación y eliminación.",
    "Los git worktrees obsoletos se limpian automáticamente: 24-72h de antigüedad sin commits sin push se podan al iniciar.",
    "Cada perfil obtiene su propio HOME de subproceso en HERMES_HOME/home/ — configs aislados de git, ssh, npm, gh.",
    "La variable de entorno HERMES_HOME_MODE (octal, ej. 0701) establece permisos de directorio personalizados para traversal del servidor web.",
    "Modo contenedor: coloca .container-mode en HERMES_HOME y el CLI del host ejecuta automáticamente dentro del contenedor.",
    "Ctrl+C tiene 5 niveles de prioridad: cancelar grabación → cancelar prompts → cancelar picker → interrumpir agente → salir.",
    "Cada interrupción durante una ejecución del agente se registra en ~/.janitor/interrupt_debug.log con timestamps.",
    "BROWSER_CDP_URL conecta herramientas de navegador a cualquier navegador Chromium en ejecución — acepta WebSocket, HTTP o host:puerto.",
    "BROWSERBASE_ADVANCED_STEALTH=true habilita anti-detección avanzado con Chromium personalizado (Scale Plan).",
    "El CLI cambia automáticamente a modo compacto en terminales más angostas de 80 columnas.",
    "Los quick commands soportan dos tipos: exec (ejecuta comando de shell directamente) y alias (redirige a otro comando).",
    "delegation.model y delegation.provider en config enrutan subagentes a modelos más baratos.",
    "delegation.reasoning_effort controla independientemente la profundidad de pensamiento para subagentes.",
    "display.platforms en config.yaml permite overrides de visualización por plataforma: {telegram: {tool_progress: all}}.",
    "human_delay.mode en config simula velocidad de tipeo humana — rango configurable min_ms/max_ms.",
    "Las migraciones de versión de config se ejecutan automáticamente al cargar — las nuevas claves aparecen sin intervención manual.",
    "Los modelos GPT y Codex reciben guía especial de system prompt para disciplina de herramientas y uso obligatorio de herramientas.",
    "Los modelos Gemini reciben directivas a medida para rutas absolutas, llamadas paralelas a herramientas y comandos no interactivos.",
    "context.engine en config.yaml puede establecerse a un nombre de plugin para estrategias alternativas de gestión de contexto.",
    "Las páginas de navegador de más de 8000 tokens se resumen automáticamente por el LLM auxiliar antes de devolverlas al agente.",
    "El compresor hace un pre-pase económico: las salidas de herramientas de más de 200 caracteres se reemplazan con placeholders antes de que corra el LLM.",
    "Cuando la compresión falla, los intentos posteriores se pausan por 10 minutos para evitar martillar la API.",
    "Los comandos peligrosos largos (>70 caracteres) obtienen una opción 'ver' en el prompt de aprobación para ver el texto completo primero.",
    "La visualización de nivel de audio muestra barras ▁▂▃▄▅▆▇ durante la grabación de voz basadas en niveles RMS del micrófono.",
    "Los nombres de perfil no pueden colisionar con binarios existentes en PATH — 'janitor profile create ls' sería rechazado.",
    "janitor profile create backup --clone-all copia todo (config, claves, SOUL.md, memorias, skills, sesiones).",
    "La tecla de grabación de voz es configurable vía voice.record_key en config.yaml — no solo Ctrl+B.",
    ".cursorrules y archivos .cursor/rules/*.mdc se detectan y cargan automáticamente como contexto de proyecto.",
    "Los archivos de contexto soportan 10+ patrones de inyección de prompt — Unicode invisible, 'ignore instructions', intentos de exfil.",
    "GPT-5 y Codex usan el rol 'developer' en lugar de 'system' en el formato de mensajes.",
    "Overrides auxiliares por tarea: auxiliary.vision.provider, auxiliary.compression.model, etc. en config.yaml.",
    "El cliente auxiliar trata 'main' como alias de proveedor — resuelve a tu proveedor principal real + modelo.",
    "janitor claw migrate --dry-run previsualiza la migración a OpenClaw sin escribir nada.",
    "Las rutas de archivo pegadas con comillas o espacios escapados se manejan automáticamente — sin limpieza manual.",
    "Los comandos slash nunca disparan el colapso de pegado grande — /comando con argumentos grandes funciona correctamente.",
    "En modo de interrupción, los comandos slash escritos durante la ejecución del agente bypass la lógica de interrupción y se ejecutan inmediatamente.",
    "HERMES_DEV=1 bypassa la detección de modo contenedor para desarrollo local.",
    "Cada servidor MCP obtiene su propio toolset (mcp-servername) que puede alternarse independientemente vía janitor tools.",
    "Los placeholders ${ENV_VAR} de MCP en config se resuelven al iniciar el servidor — incluyendo vars desde ~/.janitor/.env.",
    "Las skills de repos confiables (NousResearch) obtienen un nivel de seguridad 'trusted'; las skills de comunidad obtienen escaneo extra.",
    "La cuarentena de skills en ~/.janitor/skills/.hub/quarantine/ retiene skills pendientes de revisión de seguridad.",

    # --- Comandos Slash Avanzados ---
    '/steer <prompt> inyecta una nota después de la siguiente llamada a herramienta — empuja la dirección a mitad de tarea sin interrumpir.',
    '/goal <texto> establece un objetivo permanente de bucle Ralph — Janitor auto-continúa turno tras turno hasta que un juez dice terminado.',
    '/snapshot create [etiqueta] guarda un snapshot completo del estado de configuración de Janitor; /snapshot restore <id> revierte más tarde.',
    '/copy [N] copia la última respuesta del asistente al portapapeles, o la N-ésima desde el final con un número.',
    '/redraw fuerza un repintado completo de la UI, corrigiendo desplazamiento de terminal después de resize de tmux o artefactos de selección con mouse.',
    '/agents (alias /tasks) muestra agentes activos y tareas en segundo plano en la sesión actual.',
    '/footer alterna el pie de página del gateway en respuestas finales mostrando modelo, conteo de herramientas y tiempo de turno.',
    '/busy queue|steer|interrupt controla qué sucede al presionar Enter mientras Janitor está trabajando.',
    '/topic en DMs de Telegram habilita modo de topics multi-sesión gestionado por el usuario — /topic <id> restaura sesiones pasadas inline.',
    '/approve session|always ejecuta un comando peligroso pendiente con el alcance de confianza elegido; /deny lo rechaza.',
    '/restart reinicia gracefulmente el gateway después de drenar ejecuciones activas, luego notifica al solicitante cuando vuelve.',
    '/kanban boards switch <slug> cambia el tablero Kanban activo de multi-proyecto desde dentro del chat.',
    '/reload recarga ~/.janitor/.env en la sesión en ejecución — recoge nuevas claves API sin reiniciar.',

    # --- Cron (no-agent & scripts) ---
    'cronjob con no_agent=True ejecuta un script programado y envía su stdout directamente — cero tokens, cero LLM.',
    'Un stdout vacío de script de cron significa tick silencioso — no se entrega nada, perfecto para watchdogs de umbral.',
    "HERMES_CRON_MAX_PARALLEL (predeterminado 4) limita cuántos trabajos cron corren por tick para que los picos no saturen tus claves.",

    # --- Gateway Hooks ---
    'Los hooks del gateway viven bajo ~/.janitor/hooks/<nombre>/ con HOOK.yaml + handler.py — el handler debe llamarse `handle`.',
    'Los eventos de hook incluyen gateway:startup, session:start, agent:step y suscripciones wildcard command:*.',
    'Coloca un checklist ~/.janitor/BOOT.md y un hook gateway:startup lo ejecuta como agente one-shot en cada arranque.',

    # --- Curator ---
    'janitor curator run --dry-run previsualiza lo que el curator archivaría o consolidaría sin mutar nada.',
    "janitor curator pin <skill> protege una skill contra archivado automático y contra la herramienta skill_manage del agente.",
    'janitor curator rollback restaura skills desde un snapshot pre-ejecución — los backups viven bajo skills/.curator_backups/.',

    # --- Credential Pools y Routing ---
    'janitor auth reset <proveedor> limpia todos los cooldowns y flags de agotamiento en un credential pool.',
    'credential_pool_strategies.<proveedor>: round_robin rota claves uniformemente en lugar del fill_first predeterminado.',
    'use_gateway: true por herramienta enruta web, imagen, tts o navegador a través de tu suscripción Nous — sin claves extra.',
    'provider_routing.data_collection: deny excluye proveedores que almacenan datos en OpenRouter.',
    'provider_routing.require_parameters: true solo enruta a proveedores que soportan cada parámetro en tu solicitud.',

    # --- TUI y Dashboard ---
    'HERMES_TUI_RESUME=1 se re-engancha automáticamente a la sesión TUI más reciente al lanzar — útil después de caídas de SSH.',
    "HERMES_TUI_THEME=light|dark|<hex> fuerza el tema TUI en terminales que no establecen COLORFGBG.",
    'Ctrl+G o Ctrl+X Ctrl+E en el TUI abre el buffer de entrada en $EDITOR para prompts multilínea largos.',
    'El TUI renderiza LaTeX inline — $E=mc^2$ se convierte en matemática Unicode en lugar de TeX crudo.',
    'janitor dashboard lanza una UI web local en 127.0.0.1:9119 — cero datos salen de localhost.',
    'janitor dashboard --tui incrusta el TUI completo de Janitor en tu navegador vía xterm.js y un WebSocket PTY.',
    'Coloca un YAML en ~/.janitor/dashboard-themes/ con dos colores de paleta para cambiar el tema completo del dashboard.',
    'Los plugins del dashboard son drop-in: manifest.json + JS bundle en ~/.janitor/dashboard-plugins/ — no se necesita npm build.',
    'layoutVariant: cockpit en un tema de dashboard agrega un riel izquierdo de 260px que los plugins pueden poblar vía el slot de sidebar.',

    # --- Variables de Entorno y Gates de Config ---
    "display.tool_progress_command: true expone /verbose en plataformas de mensajería; es solo CLI por defecto.",
    'HERMES_BACKGROUND_NOTIFICATIONS=result solo notifica cuando las tareas en segundo plano terminan (vs all/error/off).',
    'HERMES_WRITE_SAFE_ROOT restringe write_file y patch a un prefijo de directorio; escrituras fuera requieren aprobación.',
    'HERMES_IGNORE_RULES omite la inyección automática de AGENTS.md, SOUL.md, .cursorrules, memoria y skills precargadas.',
    'HERMES_ACCEPT_HOOKS aprueba automáticamente hooks de shell no vistos declarados en config.yaml sin prompt TTY.',
    'auxiliary.goal_judge.model enruta el juez de /goal a un modelo rápido y barato para mantener el costo del bucle cerca de cero.',
    'Los checkpoints omiten directorios con más de 50,000 archivos para evitar operaciones git lentas en monorepos masivos.',

    # --- TTS ---
    'tts.provider: piper ejecuta TTS local en 44 idiomas por CPU — las voces se descargan automáticamente a ~/.janitor/cache/piper-voices/.',
    'tts.providers.<nombre>.type: command conecta cualquier motor TTS CLI con placeholders {input_path} y {output_path}.',

    # --- API Server y Proxy ---
    'API_SERVER_ENABLED=true ejecuta un endpoint compatible con OpenAI junto al gateway para Open WebUI y LibreChat.',
    'GATEWAY_PROXY_URL ejecuta una configuración dividida: E/S de plataforma localmente, trabajo de agente delegado a un servidor API remoto.',

    # --- Específico por Plataforma ---
    'MATRIX_DEVICE_ID fija un ID de dispositivo estable para E2EE — sin él, las claves rotan en cada inicio y el descifrado histórico se rompe.',
    'TELEGRAM_WEBHOOK_SECRET es requerido siempre que TELEGRAM_WEBHOOK_URL esté establecido — genera con openssl rand -hex 32.',

    # --- Batch ---
    "batch_runner.py --resume coincide contenidos completados por texto para que reordenamientos de datasets no re-ejecuten trabajo terminado.",

    # --- Comandos Slash Menos Conocidos ---
    '/new inicia una sesión nueva en el lugar (alias /reset) — ID de sesión fresco, historial limpio, CLI permanece abierto.',
    '/clear limpia la pantalla del terminal Y inicia una nueva sesión — un atajo para reinicio visual.',
    '/history imprime la conversación actual inline sin salir del CLI — útil para una relectura rápida.',
    '/save escribe la conversación actual a disco sin terminar la sesión.',
    '/status muestra info de la sesión de un vistazo: ID, título, modelo, uso de tokens y tiempo transcurrido.',
    '/image <ruta> adjunta un archivo de imagen local para tu siguiente prompt sin pegar o arrastrar.',
    '/platforms muestra el estado de conexión del gateway y plataformas de mensajería directamente desde el chat.',
    '/commands pagina la lista completa de comandos slash + skills instaladas — útil en plataformas sin autocompletado con Tab.',
    '/toolsets lista todos los toolsets disponibles para que sepas qué acepta -t/--toolsets.',
    '/gquota muestra el uso de cuota de Google Gemini Code Assist con barras de progreso cuando ese proveedor está activo.',
    '/voice tts alterna modo solo-TTS — el agente responde en voz alta pero tú sigues escribiendo tus prompts.',
    '/reload-skills re-escanea ~/.janitor/skills/ para que skills drop-in aparezcan sin reiniciar la sesión.',
    '/indicator kaomoji|emoji|unicode|ascii elige el estilo de indicador de ocupado del TUI mostrado durante ejecuciones del agente.',
    '/debug sube un bundle de soporte (info de sistema + logs) y devuelve links compartibles — funciona en chat también.',

    # --- Subcomandos y Banderas del CLI ---
    'janitor -z "<prompt>" es la consulta one-shot más pura: respuesta final en stdout, nada más — ideal para piping en scripts.',
    'janitor chat --pass-session-id inyecta el ID de sesión en el system prompt para que el agente pueda auto-referenciarlo.',
    'janitor chat --image ruta/a/foto.png adjunta una imagen local a una única consulta -q sin paso de carga separado.',
    'janitor chat --ignore-user-config omite ~/.janitor/config.yaml — reportes de errores reproducibles y ejecuciones CI.',
    "janitor chat --source tool etiqueta chats programáticos para que no desordenen janitor sessions list.",
    'janitor dump --show-keys incluye huellas de claves API redactadas para depuración de soporte más profunda.',
    'janitor sessions rename <ID> "nuevo título" renombra cualquier sesión pasada; janitor sessions delete <ID> elimina una.',
    'janitor import restaura una exportación de sesión o un archivo de perfil producido por sessions export o profile export.',
    'janitor fallback gestiona la cadena fallback_model interactivamente — sin editar config.yaml a mano.',
    'janitor pairing rota el token de emparejamiento de DM — el primer mensajero después de la rotación reclama acceso al bot.',
    'janitor setup guía a usuarios primerizos a través de proveedor, claves y cableado de plataforma en un flujo interactivo.',
    'janitor status --deep ejecuta el barrido completo de salud en cada componente; janitor status simple es la vista rápida.',

    # --- Variables de Entorno de Comportamiento del Agente ---
    'HERMES_AGENT_TIMEOUT=0 desactiva el kill de inactividad del gateway para un agente en ejecución — útil para ejecuciones de investigación largas.',
    'HERMES_ENABLE_PROJECT_PLUGINS=1 auto-carga plugins locales del repo desde ./.janitor/plugins/ — protegido por trust-gate por diseño.',
    "HERMES_DISABLE_FILE_STATE_GUARD=1 desactiva la protección 'archivo cambiado desde que lo leíste' en patch y write_file.",
    'HERMES_ALLOW_PRIVATE_URLS=true permite que las herramientas web accedan a localhost y redes privadas — desactivado por defecto en modo gateway.',
    'HERMES_OPTIONAL_SKILLS=name1,name2 auto-instala skills extra del catálogo opcional en la primera ejecución por perfil.',
    'HERMES_BUNDLED_SKILLS apunta a un árbol de skills incluidas personalizado — usado por empaquetado Homebrew y Nix.',
    'HERMES_DUMP_REQUEST_STDOUT=1 vuelca cada payload de solicitud API a stdout en lugar de archivos de log.',
    'HERMES_OAUTH_TRACE=1 registra intercambios de tokens OAuth redactados y intentos de refresco para depurar auth de proveedor.',
    'HERMES_STREAM_RETRIES (predeterminado 3) controla reintentos de reconexión mid-stream en errores de red transitorios.',

    # --- Variables de Entorno de Comportamiento del Gateway ---
    'HERMES_GATEWAY_BUSY_ACK_ENABLED=false silencia los mensajes de ack ⚡/⏳/⏩ cuando un usuario mensajea a un agente ocupado.',
    'HERMES_AGENT_NOTIFY_INTERVAL (predeterminado 180s) establece cada cuánto el gateway hace ping con progreso en turns largos.',
    'HERMES_RESTART_DRAIN_TIMEOUT (predeterminado 900s) limita cuánto espera /restart a ejecuciones en vuelo antes de forzar.',
    'HERMES_CHECKPOINT_TIMEOUT (predeterminado 30s) limita la creación de checkpoints del sistema de archivos — aumenta en monorepos enormes.',

    # --- Tareas Auxiliares y Generación de Imágenes ---
    'image_gen.model en config.yaml selecciona el modelo de FAL: flux-2/klein, gpt-image-2, nano-banana-pro y más.',
    'image_gen.provider enruta la generación de imágenes a través de un plugin (OpenAI Images, Codex, FAL) en lugar del predeterminado.',
    'AUXILIARY_VISION_BASE_URL + AUXILIARY_VISION_API_KEY apuntan el análisis de visión a cualquier endpoint compatible con OpenAI.',

    # --- Seguridad ---
    'security.tirith_fail_open: false hace que Janitor bloquee comandos cuando el escáner tirith mismo falla.',
    'La variable de entorno TIRITH_FAIL_OPEN anula tirith_fail_open de config — un toggle rápido sin editar config.yaml.',

    # --- Sesiones y Source Tags ---
    '--source tool chats se excluyen de janitor sessions list por defecto — establece --source explícitamente para verlos.',
    'Los IDs de sesión tienen prefijo de timestamp (20250305_091523_abcd) para que el ordenamiento funcione naturalmente en ls y jq.',

    # --- Misc ---
    'API_SERVER_MODEL_NAME personaliza el nombre del modelo en /v1/models — esencial para setups multi-perfil de Open WebUI.',
    'Los plugins del dashboard se sirven desde /dashboard-plugins/<nombre>/ — coloca archivos en ~/.janitor/dashboard-plugins/.',
]


def get_janitor_tip(exclude_recent: int = 0) -> str:
    """Devuelve un tip aleatorio del corpus de Janitor.

    Args:
        exclude_recent: no se usa actualmente; reservado para futura
            deduplicación entre sesiones.
    """
    return random.choice(JANITOR_TIPS)
