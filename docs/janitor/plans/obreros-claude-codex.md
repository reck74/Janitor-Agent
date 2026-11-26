# Janitor dirige a Claude Code y a Codex («obreros»)

> **Estado: PROPUESTA (2026-11-25). Nada de esto está decidido ni implementado.**
> Lo pidió el dueño el 2026-11-25. Este documento compara las opciones, recomienda una y
> propone las tareas. Las decisiones de la sección 7 son del dueño (directiva #20); hasta
> que las tome, ninguna tarea de la sección 6 se empieza.
> El plan general sigue siendo [`janitor-desktop-app.md`](janitor-desktop-app.md).
> «Obreros» es un nombre provisional (decisión 7.1).

## 1. Objetivo

Que Janitor pueda mandar sobre los dos programas de código que el usuario ya tiene
instalados y con sesión iniciada en su equipo, **Claude Code** (`claude`) y **Codex**
(`codex`), y usarlos para sacar adelante proyectos largos:

- Solo se enciende si el programa está instalado **y** con sesión iniciada. Con uno solo,
  funciona con ese; sin ninguno, la función no aparece.
- Los modelos más capaces (Fable en Claude, Astra en Codex) planifican.
- Janitor reparte trabajo a uno y a otro, y les hace revisarse mutuamente: «Claude, haz
  esto; Astra, haz esto otro; Claude, mira lo que hizo Astra; Astra, mira lo que hizo
  Claude; opinen».
- Sirve para procesos de larga duración con un objetivo: desarrollar, crear, estructurar.

## 2. Hechos verificados (2026-11-25)

Tres investigaciones de solo lectura. Lo marcado «doc» sale de la documentación oficial y
no se comprobó aquí; lo demás se comprobó en el equipo de desarrollo o en el código.

### 2.1 Qué hay ya en Janitor

- Las skills de upstream `claude-code`, `codex` y `opencode`
  (`skills/autonomous-ai-agents/`) ya están en `janitor/catalog.yaml` para la plantilla
  **Creador de proyectos**. Son recetas en prosa: el agente escribe a mano el comando
  (`claude -p …`, `codex exec …`) en la terminal. No guardan estado ni reanudan nada.
- **Nada comprueba hoy que un programa exista.** El campo `prerequisites.commands` de
  las skills no se aplica (`tools/skills_tool.py` lo deja vacío). Lo que sí funciona:
  `check_fn` de una herramienta (`tools/registry.py`) y `requires_tools` en la skill
  (`agent/prompt_builder.py`).
- Para trabajo largo upstream ofrece: terminal en segundo plano con
  `notify_on_complete`, `watch_patterns` y `heartbeat`; `delegate_task` (hijos que son
  agentes Hermes, en segundo plano); cron; y **kanban**, cuyo trabajador tiene que ser
  un perfil (`hermes -p <perfil> chat -q`), no un programa externo. El kanban ya está
  traducido en la app.
- `approvals.mode: manual` hace que cada comando peligroso pida permiso; lanzar `claude`
  o `codex` desde la terminal cae ahí.
- `janitor/opencode/` (retirado en F2-04) era lo más parecido a esto: un cliente de
  `opencode serve` con un registro de sesiones y reintentos.
- El plan vigente (§2, líneas de «Especialista y subagente») dice que el principal no
  delega en perfiles especialistas y que no se crean sistemas de agentes paralelos
  (directiva #19).

### 2.2 El puente `claude_codex` (el que usan hoy Claude y Codex entre sí)

- Un solo script, `tools/bridge.py` (659 líneas, solo biblioteca estándar, v0.1.0, sin
  licencia, 51 pruebas con un CLI falso). Sirve en las dos direcciones.
- Lo aprovechable: el esquema del encargo (`objetivo`, `contexto`, `entregables`,
  `restricciones`), las líneas de comando endurecidas de cada programa, la lista blanca
  de variables de entorno, la carpeta de evidencia por corrida, los analizadores de la
  salida JSON y la detección de «pedí un modelo y contestó otro».
- Lo que le falta para este objetivo:
  - **No corre en Windows** (usa `fcntl`, `getuid`, `killpg`).
  - Cada llamada bloquea hasta terminar; no hay trabajos en segundo plano ni consulta
    de estado.
  - **No reanuda conversaciones** (lanza los dos programas en modo efímero).
  - **Codex solo lee**; solo Claude puede escribir.
  - No comprueba la sesión iniciada, solo `--version`.

### 2.3 Los dos programas

| | Claude Code 2.1.332 | Codex 0.172.0 |
|---|---|---|
| Sesión iniciada | `claude auth status` → JSON con `loggedIn`; salida 0/1 | `codex login status` → una línea de texto; salida 0 (la de «sin sesión» no está documentada) |
| Sin pantalla | `claude -p --output-format json\|stream-json` | `codex exec --json` |
| Reanudar | `--resume <id>`; se puede fijar con `--session-id` | `codex exec resume <thread_id>` |
| Escribir en el proyecto | `--permission-mode` + `--allowedTools` | `--sandbox workspace-write` |
| Coste | `total_cost_usd` estimado + tokens | solo tokens |
| Windows (doc) | nativo | nativo |

- Otras interfaces: el Agent SDK de Claude (envuelve el mismo binario), `codex
  app-server` (JSON-RPC, **marcado experimental**), y `codex mcp-server`, que **ya no
  existe**. Ninguno de los dos habla ACP de forma nativa.
- Los dos cambian deprisa (opciones ocultas, opciones retiradas). `claude --bare`, que
  la documentación anuncia como futuro valor por defecto de `-p`, **no usa la
  suscripción**.
- `claude -p` en una carpeta ejecuta los hooks y servidores MCP del proyecto sin
  preguntar (doc): no se lanza sobre carpetas que el usuario no haya elegido.

### 2.4 Condiciones de uso (leer antes de decidir)

- **Anthropic** (doc, <https://code.claude.com/docs/en/legal-and-compliance>): prohíbe a
  terceros ofrecer el inicio de sesión de Claude.ai en su aplicación o encaminar
  peticiones con credenciales de un plan en nombre de sus usuarios. La misma página dice
  que eso no impide que el usuario final use el binario **sin modificar** de Claude Code
  con su propia suscripción. Condiciones: binario sin modificar, el usuario se autentica
  y paga él, y **no usar «Claude Code» en el nombre del producto o de la función**. Los
  límites del plan suponen «uso individual ordinario».
- **OpenAI** (doc): `codex exec` reutiliza la sesión guardada; recomienda clave de API
  para automatización. No encontramos una frase que permita o prohíba que una
  herramienta local lance el `codex` del usuario.
- **Lectura nuestra, no asesoría legal:** lanzar el binario del usuario sin tocar sus
  archivos de credenciales parece permitido. Leer sus credenciales para usarlas como
  proveedor de IA de Janitor queda del lado prohibido en Anthropic. Un uso automático
  intenso puede salirse de «uso individual ordinario»: es una zona gris.

## 3. Opciones

| | Qué es | A favor | En contra |
|---|---|---|---|
| **A. Solo skills** | Mejorar las recetas actuales; el agente escribe los comandos | Casi sin código | Sin estado, sin reanudar, sin detección; el modelo debe recordar opciones que cambian; un permiso por comando; nada que mostrar en la app |
| **B. Motor propio + comando + skill** | Un módulo `janitor/` que lanza los dos programas, guarda cada trabajo y lo reanuda; se usa con `janitor obreros …`; una skill enseña el método | Estado y evidencia en disco; funciona en los tres sistemas; lo usan el agente, el terminal y la app; no añade peso a cada llamada al modelo; es el peldaño 2 de la «escalera» del proyecto | Hay que escribirlo y mantenerlo al ritmo de los dos programas |
| **C. Herramientas del plugin** | Igual que B, pero el agente lo llama como herramienta con `check_fn` | Parámetros estructurados; desaparece sola si no hay programas | Ocupa sitio en cada llamada al modelo; conviene solo como capa fina sobre B |
| **D. Kanban con perfiles** | El tablero de upstream reparte tareas a perfiles que llaman a los programas | Ya existe, con pantalla; pensado para trabajo largo | El trabajador es un perfil con su propio modelo: una capa más entre Janitor y el obrero; choca con «el principal no delega en especialistas» |
| **E. Usarlos como proveedor de IA** | Que el cerebro de Janitor sea Fable o Astra vía la suscripción | Janitor «piensa» con el mejor modelo | Con Claude queda del lado prohibido (2.4); con Codex depende de un modo experimental. Y no da obreros: da otro cerebro |

## 4. Recomendación

**B como base, con una capa fina de C, y D más adelante solo si hace falta. A se
descarta por frágil; E se descarta para Claude y se aparca para Codex.**

### 4.1 Quién hace qué

Janitor no planifica con su propio modelo (MiniMax-M3): **dirige**. Mantiene el objetivo,
habla con el usuario, reparte y decide cuándo algo está terminado.

| Papel | Quién | Permisos |
|---|---|---|
| Director | Janitor | habla con el usuario; lanza y lee trabajos |
| Planificadores | Fable (Claude) y Astra (Codex), los dos | solo lectura |
| Constructores | modelo intermedio de cada lado (Sonnet, Sol) | escriben, cada uno en su copia de trabajo |
| Revisores | el del lado contrario al que construyó | solo lectura |

Los modelos por papel son valores por defecto en `config.yaml`, no fijos en el código.

### 4.2 El ciclo de un objetivo

1. **Encargo.** Janitor convierte lo que pide el usuario en un encargo (objetivo,
   contexto, entregables, restricciones) y lo confirma con él.
2. **Dos planes.** Fable y Astra planifican por separado, sin verse.
3. **Crítica cruzada.** Cada uno lee el plan del otro y opina.
4. **Plan único.** Janitor lo consolida y **el usuario lo aprueba**. Sin aprobación no
   se escribe nada.
5. **Construcción.** Cada parte va a un obrero, en una copia de trabajo propia
   (`git worktree`), nunca dos escribiendo en la misma carpeta.
6. **Revisión cruzada.** El otro lado revisa el cambio; los hallazgos vuelven al
   constructor, con un tope de rondas.
7. **Entrega.** Janitor muestra el resultado y las pruebas; integrar o descartar lo
   decide el usuario.

Con un solo programa disponible, los pasos cruzados se hacen con dos modelos del mismo
lado, y Janitor avisa de que no hay segunda opinión independiente.

### 4.3 Piezas

- **Motor `janitor/obreros/`** (solo biblioteca estándar, tres sistemas):
  - detección: `shutil.which` + `--version` + estado de sesión, sin leer credenciales;
  - un adaptador por programa que construye la línea de comando y analiza la salida;
    las opciones se comprueban contra `--help` al arrancar, porque cambian;
  - registro de trabajos en `~/.janitor/obreros/` (por perfil): encargo, estado, id de
    sesión para reanudar, salida, tokens y coste;
  - trabajos en segundo plano, con consulta, reanudación y cancelación;
  - tres modos: consulta (sin herramientas), revisión (solo lectura) y construcción
    (escribe en su copia de trabajo);
  - topes: tiempo por trabajo, trabajos a la vez, rondas de revisión y gasto.
- **Comando `janitor obreros`**: `estado`, `enviar`, `ver`, `seguir`, `reanudar`,
  `cancelar`. Lo usan el agente, el usuario en el terminal y la app.
- **Herramienta fina del plugin Janitor** con `check_fn` (hay al menos un programa con
  sesión): solo «enviar» y «ver». Es lo que permite que la skill aparezca o no
  (`requires_tools`) sin tocar el core.
- **Skill `janitor-obreros`** (grupo `projects/`): el método de 4.2 y cuándo no usarlo.
- **Agentes.** Dos caminos, a decidir (7.3):
  - que **Creador de proyectos** use los obreros por defecto cuando estén disponibles;
  - una plantilla nueva de **director** para objetivos largos.
- **App**: en la pantalla del plugin de escritorio, el estado de cada programa
  (instalado, con sesión) y la lista de trabajos con su resultado. Sin esto, el usuario
  no ve qué está pasando en un proceso de horas.

### 4.4 Qué se reutiliza del puente

Del `bridge.py` se toman, reescritos dentro de `janitor/obreros/`, el esquema del
encargo, las opciones endurecidas, la lista blanca de variables, los analizadores y la
detección de modelo equivocado. No se toma como dependencia: no corre en Windows, no
tiene licencia y le faltan justo las tres cosas que este objetivo necesita (segundo
plano, reanudar, Codex escribiendo).

### 4.5 Reglas

- **Nunca se leen ni copian credenciales** de `~/.claude` ni `~/.codex`. Janitor solo
  ejecuta el binario del usuario, sin modificar.
- **Activación explícita.** Detectar los programas solo ofrece la función; el usuario la
  enciende, tras un aviso en español: su código sale hacia Anthropic u OpenAI y consume
  su plan o su saldo.
- **Solo en carpetas que el usuario eligió** como proyecto.
- **Nada se integra solo.** Los obreros escriben en copias de trabajo; fusionar, subir o
  borrar lo confirma el usuario (regla de `SOUL.md`, directiva #19).
- **Sin recursión**: un obrero no puede llamar a Janitor ni a otro obrero.
- **Nombre**: la función no se llama «Claude Code» ni lleva marcas ajenas en el nombre.
- No se añade nada a `apps/desktop/` ni al core fuera de touchpoints declarados
  (directivas #1, #16).

## 5. Riesgos

- **Condiciones de uso** (2.4). El uso automático e intenso con la suscripción es zona
  gris; se mitiga con activación explícita, topes y la opción de clave de API, pero no
  se elimina. Es decisión del dueño (7.2).
- **Los programas cambian.** Una opción retirada rompe el adaptador. Mitigación:
  comprobación contra `--help`, pruebas con un programa falso y una prueba real manual
  por versión.
- **Gasto.** Planificar con dos modelos caros y revisar en cruz multiplica el consumo.
  Topes por defecto conservadores.
- **Directiva #19.** Esto introduce trabajadores que no son perfiles. Hay que
  registrarlo como excepción explícita, o como decisión nueva, antes de escribir código
  (7.4).
- **Seguridad.** Un obrero con permiso de escritura ejecuta lo que el proyecto le diga.
  En Windows, Claude no tiene aislamiento nativo (doc).
- **Sin verificar**: todo lo marcado «doc» en la sección 2; que la sesión de Codex sin
  iniciar devuelva salida distinta de 0; el comportamiento de los dos programas en
  Windows y macOS.

## 6. Tareas propuestas (Fase 7)

Ninguna empieza hasta que el dueño decida la sección 7.

| Id | Tarea | Alcance | Verificación |
|---|---|---|---|
| F7-01 | Detección de los dos programas y de su sesión | `janitor/obreros/deteccion.py` | pruebas con binarios falsos; salida real en Linux |
| F7-02 | Adaptadores: línea de comando, análisis de salida, comprobación de opciones | `janitor/obreros/claude.py`, `codex.py` | pruebas con programa falso |
| F7-03 | Registro de trabajos, segundo plano, reanudar, cancelar, topes | `janitor/obreros/trabajos.py` | pruebas; un trabajo real de consulta por lado |
| F7-04 | Copias de trabajo por obrero y modo construcción | `janitor/obreros/copias.py` | prueba en un repositorio temporal |
| F7-05 | Comando `janitor obreros` | `janitor/plugin/` | pruebas del analizador de argumentos |
| F7-06 | Herramienta fina con `check_fn` | `janitor/plugin/` | la herramienta no existe sin programas |
| F7-07 | Skill `janitor-obreros` y entrada en el catálogo | `janitor/skills/projects/`, `janitor/catalog.yaml` | `python -m janitor.catalog check` |
| F7-08 | Agente: Creador de proyectos o plantilla nueva (según 7.3) | `janitor/templates/` | creación del perfil en un home temporal |
| F7-09 | Pantalla en la app: estado y trabajos | `janitor/desktop_plugin/` | captura con la app compilada |
| F7-10 | Aviso de activación y ajustes en `config.yaml` | semilla + plugin | prueba |
| F7-11 | Recorrido real: un objetivo pequeño de punta a punta con los dos programas | — | evidencia en la bitácora |
| F7-12 | Prueba en Windows y macOS | CI + equipo real | — |

Orden: F7-01 a F7-03 primero (dan valor por sí solas: consulta y revisión cruzada);
después F7-05 a F7-07; construcción (F7-04) y app (F7-09) al final.

## 7. Decisiones del dueño

1. **Nombre** de la función y del comando. Propuesta: «obreros» (`janitor obreros`).
2. **Suscripción o clave de API.** Propuesta: permitir la sesión del usuario con
   activación explícita y aviso, y ofrecer clave de API como alternativa. La otra opción
   es exigir clave de API y renunciar a la suscripción.
3. **Agentes.** Propuesta: Creador de proyectos usa los obreros por defecto; la
   plantilla de director se deja para después del recorrido real (F7-11).
4. **Directiva #19.** Propuesta: añadir que los obreros son programas externos del
   usuario dirigidos por un perfil, no un sistema de agentes paralelo, y que no tienen
   memoria ni identidad propias.
5. **Escritura.** Propuesta: la primera entrega es solo consulta y revisión; construir
   llega en una segunda entrega.
6. **Topes por defecto**: trabajos a la vez, rondas de revisión, minutos por trabajo y
   gasto. Propuesta: 2 a la vez, 2 rondas, 30 minutos, y un tope de gasto que el usuario
   fija al activar.
7. **Prioridad** frente a lo pendiente: probar la `.2` en equipos reales, los defectos
   pequeños ya anotados y la sincronización con upstream (PR #90).
