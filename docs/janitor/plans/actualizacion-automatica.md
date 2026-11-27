# Actualización automática y completa de Janitor (motor y app)

> **Estado: APROBADA por el dueño el 2026-11-27** («Sí, apruébalo»), con las seis
> propuestas de la sección 7 tal como están. La pidió ese mismo día, tras actualizar la
> instalación de su equipo a `v0.21.5-janitor.3`: el motor se actualizó, la app (paquete
> de Arch) quedó en la `.2` y el aviso le pidió reinstalar a mano. **Nada implementado.**
> El plan general sigue siendo [`janitor-desktop-app.md`](janitor-desktop-app.md).
> **Sustituye una decisión registrada**: ese plan decía (2026-11-22) «el AppImage nuevo
> llega por descarga guiada desde los releases del fork; no hay actualización
> automática». El cambio queda anotado allí y en
> [`actualizacion-diseno.md`](actualizacion-diseno.md) (tarea F9-00, hecha).

## 1. Qué pide el dueño

1. Al abrir la app, se comprueba sola si hay una versión nueva.
2. La actualización es completa: motor **y** app. Si hace falta contraseña, se le pide al
   usuario; lo demás ocurre solo.
3. Vale para Linux, macOS y Windows.

## 2. Hechos verificados (2026-11-27)

Leídos en el código por un subagente de solo lectura; las rutas son de `main`.

- **La comprobación al abrir ya existe, pero solo mira el motor.** `startUpdatePoller`
  (`apps/desktop/src/store/updates.ts`) comprueba al montar la app, cada 24 h y al
  recuperar el foco. Compara el commit del motor instalado con la punta de `stable`
  (`checkUpdates` en `apps/desktop/electron/main.ts`, rama cambiada por el parche P19).
  Nada compara la versión de la app con la publicada.
- **Nada descarga ni reemplaza la app.** El guion (`scripts/desktop-update/posix.sh`,
  `windows.ps1`) ejecuta `janitor update` y después:
  AppImage → reabre el mismo archivo viejo; paquete de Arch → resultado «skew», aviso de
  reinstalar y **no se reabre**; Windows → reabre el `.exe` viejo; macOS → reabre el
  `.app` viejo. Upstream sí reemplaza la app, pero compilándola en el equipo del usuario,
  cosa que Janitor no hace (`janitor/update_core.py` no compila la app).
- **Compatibilidad.** El parche P13 compara un número de contrato (`janitor/desktop-compat.json`,
  hoy `1`) y solo si el motor exige una app más nueva bloquea con un enlace de descarga.
- **Publicación.** Cada versión adjunta `Janitor-linux-x86_64.AppImage`,
  `Janitor-win-x64.exe`, `Janitor-mac-arm64.dmg`, `Janitor-mac-x64.dmg`, el paquete de
  Arch y un `SHA256SUMS`. Nombres estables, sin versión. No hay archivos de un
  actualizador estándar, ni `.zip` de macOS, ni firma de ningún tipo.
- **Sin certificados.** macOS va firmado ad hoc y Windows sin firmar.
- **Windows**: el instalador deja elegir «solo para mí» o «para todos»; la segunda opción
  obliga a pedir permiso de administrador en cada actualización.

Investigado en documentación y código fuente de terceros (segundo subagente; nada probado
en un equipo real):

- `electron-updater` **no sirve en macOS con firma ad hoc**: Apple y Electron exigen app
  firmada, y Squirrel.Mac compara la firma de la versión nueva con la de la que corre,
  que con ad hoc cambia en cada compilación.
- `electron-updater` **no reconoce nuestro paquete de Arch** (se arma extrayendo el
  AppImage, no con el empaquetador de pacman), y su actualizador de pacman reintenta con
  `pacman -Sy`, que Arch desaconseja.
- En Windows y AppImage sí funcionaría, pero la versión estable no verifica nada más que
  una suma publicada en el mismo sitio, y nuestras versiones con sufijo `-janitor.N`
  caen en un caso raro de su comparación de versiones.
- Una suma (`SHA256SUMS`) bajada del mismo sitio que el binario protege de errores de
  descarga, no de alguien que pueda escribir en las versiones del repositorio.

## 3. Opciones

| | A. `electron-updater` | B. Actualizador propio dentro del relevo que ya existe |
|---|---|---|
| Cubre | Windows y AppImage | Los cuatro tipos de instalación |
| macOS y Arch | Necesitan otro mecanismo de todos modos | El mismo mecanismo |
| Cambios en `apps/desktop` (upstream) | Dependencia nueva y `package-lock.json`: conflicto en cada sincronización | Solo parches de compilación y los guiones que ya son nuestros |
| Verificación | Suma del mismo sitio (firma propia solo en versión alfa) | Firma propia desde el primer día |
| Coste | Menos código propio en dos sistemas | Más código propio, pero uno solo |

## 4. Recomendación: opción B

Un solo mecanismo, montado sobre lo que ya hay: el guion de relevo que hoy corre cuando la
app se cierra para actualizar el motor.

### 4.1 Qué ve el usuario

1. Abre Janitor. En segundo plano se comprueba si `stable` tiene una versión más nueva
   que el motor **o que la app**.
2. Si la hay, aparece «Hay una versión nueva de Janitor» con **Actualizar ahora** y
   **Más tarde** (decisión 7.1: esto, o actualizar sin preguntar).
3. Al aceptar, la app descarga y verifica el instalador nuevo **antes de cerrar nada**.
   Si la descarga o la verificación fallan, no se toca nada y se dice por qué.
4. La app se cierra, **se instala primero la app nueva** (aquí se pide la contraseña si
   el sistema la exige), después se actualiza el motor al commit exacto de esa versión, y
   Janitor **se vuelve a abrir solo**, ya en la versión nueva.
5. Si el usuario cancela la contraseña o la instalación de la app falla, **no se toca el
   motor**: Janitor se reabre tal como estaba, con un aviso exacto de qué pasó. Si la app
   se instaló y falla el motor, se reabre la app nueva, que ya sabe ofrecer la
   actualización del motor. Nunca queda cerrado sin explicación, y el paso en que iba
   queda anotado para poder terminar la misma entrega al siguiente intento.

### 4.2 Piezas

- **Comprobación (proceso principal, parche de compilación).** Además del commit del
  motor, se lee la versión publicada en `stable` y se compara con la de la app en
  ejecución. Con eso se detecta también el caso «motor al día, app vieja», que es el del
  equipo del dueño hoy.
- **Manifiesto firmado por versión.** La publicación adjunta un archivo con la versión,
  el commit y, por cada instalador, nombre, tamaño y SHA-256; y su firma Ed25519 hecha en
  el flujo de publicación. La clave pública va dentro de la app. La app solo instala lo
  que ese manifiesto firmado describe. La clave privada vive como secreto del
  repositorio en un entorno protegido (decisión 7.2).
- **Tipo de instalación.** Una sola función decide: AppImage (variable `APPIMAGE` válida),
  paquete de sistema (el ejecutable pertenece a un paquete de pacman), Windows por
  usuario o por máquina, macOS (`.app`), o «desconocido» (compilación local, ruta rara).
  «Desconocido» no se actualiza solo: conserva el aviso de hoy.
- **Descarga y verificación (proceso principal).** Baja el manifiesto, comprueba la
  firma, baja el instalador que corresponde a una carpeta propia dentro de `~/.janitor`,
  comprueba tamaño y suma. Entrega al guion la ruta y la suma esperada.
- **Motor fijado a un commit.** Hoy el motor sigue la punta de la rama en el momento de
  actualizar; si `stable` avanza durante la descarga, motor y app serían de versiones
  distintas. `janitor update` gana un destino por commit (en `janitor/update_core.py`,
  directiva #13): el del manifiesto firmado, comprobado antes de activar el código.
- **Instalación (guion de relevo), antes de actualizar el motor:**

  | Instalación | Cómo se reemplaza | ¿Contraseña? |
  |---|---|---|
  | AppImage | Se sustituye el archivo por el nuevo (copia al lado y renombrado) y se abre | No, si la carpeta es del usuario; si no lo es, aviso con la ruta |
  | Paquete de Arch | Un auxiliar que instala el propio paquete, propiedad de root y con su permiso de polkit: copia el paquete a una carpeta privada de root, verifica ahí firma, versión, nombre y arquitectura con la clave pública del paquete, y ejecuta `pacman -U` sobre esa copia. La app solo le pasa la ruta | Sí, la del sistema |
  | Windows | Instalador en modo silencioso sobre la misma carpeta | No si es por usuario; aviso de permisos de Windows si se instaló «para todos» |
  | macOS | Se extrae el `.zip`, se comprueban arquitectura, identidad y firma del paquete y se intercambia el `.app`; la copia anterior se conserva hasta confirmar que la nueva arranca | No si la app es del usuario; la de administrador si no |

  Quien instala vuelve a verificar dentro de su propia frontera de permisos: no basta
  con que lo haya comprobado la app (ver 8, hallazgo 1).
- **Reapertura y resultado.** Se reabre siempre: la app nueva si se instaló, la anterior
  si no. El resultado («todo actualizado», «motor sí, app no: motivo») llega a la app por
  el archivo de resultado que ya existe, con textos nuevos en español.
- **Publicación.** Se añaden: `.zip` de macOS por arquitectura, el manifiesto y su firma.
  **Se invierte el orden del flujo**: hoy mueve `stable` y después adjunta los archivos;
  pasará a adjuntar y verificar todo primero y mover `stable` al final, para que nadie
  vea «hay versión nueva» antes de que exista completa. Windows nuevo se instala solo
  por usuario (decisión 7.3); las instalaciones «para todos» ya hechas conservan su
  alcance hasta probar la transición.
- **Qué versión corresponde a `stable`.** La app toma el commit de `stable`, deduce la
  etiqueta con la misma regla que el flujo de publicación y exige que el manifiesto
  firmado nombre ese commit. Si falta el instalador de su sistema (el de Mac Intel es
  opcional hoy), lo dice antes de tocar nada.
- **Contrato de compatibilidad.** Se mantiene como red de seguridad para quien tenga una
  app sin actualizador o cancele siempre.

### 4.3 Reglas

- Solo se instala desde `github.com/reck74/Janitor-Agent`, por HTTPS, con manifiesto
  firmado. Ninguna variable de entorno ni ajuste cambia el origen ni la clave.
- Nunca se pide ni se guarda la contraseña en Janitor: la pide el sistema (polkit, UAC,
  el diálogo de macOS). Nunca `sudo`.
- No se baja de versión: el manifiesto lleva un número de entrega creciente y la app
  recuerda el mayor aceptado. La misma entrega sí se puede repetir, para terminar una
  actualización a medias («motor al día, app vieja»).
- Descarga primero, cambios después. El motor no se toca si la app nueva no se pudo
  bajar y verificar.
- Todo el flujo del motor sigue en `janitor/update_core.py` (directiva #13); los cambios
  en archivos de upstream se declaran en `janitor/overlay.yaml` (#16); los de la app son
  parches de compilación en `apps/desktop-janitor/` (#17); todo texto en español (#18).

## 5. Riesgos y lo que no está confirmado

- **macOS con firma ad hoc.** Sin confirmar si macOS 13 o posterior deja que una app sin
  equipo de desarrollo reemplace su propio paquete («Gestión de apps»). Además, con ad hoc
  cada actualización hace que el sistema olvide los permisos concedidos (micrófono,
  captura de pantalla). Solo se resuelve con una cuenta de desarrollador de Apple. Hay
  que probarlo en un Mac real antes de darlo por hecho.
- **Windows sin firma.** El Control inteligente de aplicaciones de Windows 11 puede
  bloquear ejecutables sin firmar, también el instalador de la actualización. Sin
  confirmar cómo se comporta una instalación ya hecha «para todos» al pasar a instalador
  por usuario.
- **Arch sin agente de permisos gráfico.** `pkexec` falla en sesiones sin agente polkit.
  En ese caso queda el aviso con el comando exacto.
- **Arch y `pacman`.** Instalar con `pacman -U` desde la app es correcto para un paquete
  que no está en ningún repositorio, pero no es lo habitual en Arch; la alternativa
  (repositorio propio firmado) es más trabajo y queda fuera.
- **Primera versión con actualizador.** Las instalaciones actuales (hasta la `.3`) no lo
  llevan: necesitan **una última instalación manual**. A partir de ahí, sola.
- **Clave de firma.** Si se pierde o se filtra, hay que publicar una app con clave nueva
  e instalarla a mano. Quien pueda ejecutar el flujo de publicación puede firmar.
- **Interrumpir trabajo en curso.** Actualizar reinicia los gateways (Telegram, tareas
  programadas). De ahí la decisión 7.1.
- **Tamaño.** Cada actualización de la app baja entre 120 y 150 MB completos; no hay
  descarga diferencial.

## 6. Tareas propuestas (Fase 9)

| Id | Tarea | Dónde | Verificación |
|---|---|---|---|
| F9-00 | **Hecho (2026-11-27).** Registrar el cambio de decisión en el plan general y en `actualizacion-diseno.md` | `docs/janitor/plans/` | lectura |
| F9-01 | Manifiesto y firma en la publicación; `.zip` de macOS; Windows solo por usuario | flujo de publicación, `electron-builder.janitor.json`, guion nuevo en `apps/desktop-janitor/scripts/` | prueba del guion; corrida manual del flujo sin etiqueta |
| F9-02 | Verificación en la app: firma Ed25519, suma, tamaño, no bajar de versión, origen fijo | módulo nuevo en `apps/desktop-janitor/brand/` | pruebas con manifiestos alterados, firma falsa, versión menor |
| F9-03 | Tipo de instalación, función única | mismo sitio | pruebas por tipo, con la plataforma como dato |
| F9-04 | Comprobación de la versión de la app al abrir, aviso único motor+app | parche de compilación sobre `main.ts` y `updates.ts` | prueba del parche; caso «motor al día, app vieja» |
| F9-05 | Descarga previa y entrega al guion | parche de compilación | pruebas con servidor local |
| F9-06 | Guion POSIX: AppImage, Arch con `pkexec`, macOS; reabrir siempre; resultados | `scripts/desktop-update/posix.sh` (ya declarado en el inventario) | `tests/janitor/` con el arnés que ya existe; contenedor de Arch en CI |
| F9-07 | Guion de Windows: instalador silencioso, reabrir, resultados | `scripts/desktop-update/windows.ps1` | pruebas en el ejecutor de Windows |
| F9-08 | Textos en español y retirada del aviso «AppImage/deb/rpm» | `apps/desktop-janitor/brand/`, guiones | la prueba de marca e idioma |
| F9-09 | Prueba de punta a punta por sistema en CI: instalar la versión N, actualizar a una N+1 de prueba, comprobar que arranca la nueva | flujo de publicación | corrida en verde en los cuatro tipos |
| F9-10 | Prueba real: equipo del dueño (Arch) y, si hay equipos, Windows y Mac | — | evidencia anotada; lo no probado se anota como no probado |
| F9-11 | Revisión por un revisor distinto y consulta a Codex del código de seguridad (F9-02, F9-06, F9-07) | — | directiva #20 |

| F9-12 | `janitor update` con destino por commit, validado antes de activar | `janitor/update_core.py` | `tests/janitor/` |
| F9-13 | Auxiliar con permisos para Arch (acción de polkit, verificación como root) | `apps/desktop-janitor/packaging/arch/` | contenedor de Arch en CI; sesión gráfica real para el diálogo |
| F9-14 | Flujo de publicación: archivos primero, `stable` al final | flujo de publicación | corrida manual sin etiqueta |

Orden (ajustado tras la revisión de Codex): F9-00; **ensayos tempranos en equipos
reales** de lo que puede tumbar el diseño (reemplazo del `.app` en macOS con firma ad
hoc, instalador silencioso en Windows 11, diálogo de polkit en Arch); F9-01, F9-02,
F9-03, F9-12 y F9-14; F9-05, F9-06, F9-07 y F9-13; F9-04 y F9-08 al final, cuando lo de
debajo funciona. La revisión de seguridad (F9-11) se hace dos veces: sobre el diseño de
permisos antes de escribirlo y sobre el código final. F9-09 y F9-10 van **antes** de
etiquetar, con dos compilaciones de prueba y claves de ensayo, e incluyen: N→N+1,
contraseña cancelada, corte a mitad, `stable` que cambia durante la descarga, archivo
sustituido tras verificarlo y repetición de la misma entrega. Dos entregas posibles:
primero Linux (AppImage y Arch), que se puede probar en el equipo del dueño; después
Windows y macOS.

Aparte, visto en los registros del 2026-11-27 y sin investigar: al reabrir la app tras
actualizar había un backend ya escuchando al que no se conectó, y arrancó otro.

## 7. Decisiones del dueño (tomadas el 2026-11-27: se acepta cada propuesta)

Quedan dos cosas que la aprobación no contesta: si un botón al abrir cumple «totalmente
automático» o debe arrancar sin preguntar (7.1 queda con el botón y la opción en
Ajustes), y si el dueño dispone de un Mac y un Windows 11 para los ensayos reales.

1. **¿Preguntar o actualizar sin preguntar?** Propuesta: preguntar al abrir («Actualizar
   ahora» / «Más tarde») y ofrecer en Ajustes «Actualizar siempre sin preguntar». El
   dueño dijo «totalmente automático»: falta que confirme si un botón al abrir lo
   cumple o si quiere que arranque sin preguntar.
2. **Clave de firma.** Propuesta: par Ed25519 creado por el dueño, privada como secreto
   del repositorio en un entorno protegido que solo usa el flujo de publicación. El
   agente no crea ni ve la clave privada. Codex recomienda además una segunda clave
   guardada fuera de GitHub que autorice y revoque la de publicación: protege si se
   filtra la primera, a cambio de que el dueño la custodie. Decidir si se hace desde el
   principio o después.
3. **Windows solo por usuario.** Propuesta: sí; quita la pregunta «para todos» del
   instalador y con ella el permiso de administrador en cada actualización.
4. **Arch.** Propuesta: auxiliar con permisos dentro del paquete (sección 4.2).
   Alternativa: repositorio propio.
5. **macOS.** Propuesta: implementarlo y probarlo en un Mac real antes de prometerlo; si
   macOS lo impide con firma ad hoc, queda la descarga guiada hasta tener certificado.
6. **Entregas.** Propuesta: Linux primero, Windows y macOS después.

## 8. Revisión de Codex (2026-11-27)

Consulta de solo lectura por el puente (modelo solicitado `gpt-6.2-astra`). Veredicto:
**la opción B es la arquitectura correcta**, pero el primer borrador no se podía aprobar
tal cual para los cuatro destinos. Seis hallazgos; los tres primeros hechos comprobados
por Claude en el código, y todos incorporados arriba salvo lo que se indica:

1. **Crítico — en Arch se podía cambiar el paquete después de verificarlo.** El archivo
   estaba en una carpeta del usuario y `pacman` lo abría como root tras el diálogo de
   contraseña: otro programa del usuario podía sustituirlo en ese intervalo y obtener
   root. Corregido en el diseño: verifica e instala un auxiliar de root sobre su propia
   copia (4.2, F9-13).
2. **Crítico — la firma no cubría el motor.** Comprobado: `update_core.py` hace
   `pull --ff-only` o `reset --hard origin/<rama>`, es decir, la punta de la rama, no un
   commit. Corregido: destino por commit del manifiesto (4.2, F9-12).
3. **Alta — «reabrir la anterior» no garantizaba una app que funcione** si el motor ya
   era nuevo y el contrato había subido. Corregido: app primero, motor después, y paso
   anotado (4.1). **No incorporado**: exigir una versión intermedia para saltos de
   contrato; se decide el día que el contrato suba por primera vez.
4. **Alta — `stable` se mueve antes de que la versión esté completa.** Comprobado en el
   flujo de publicación: el paso «Move the release channel to the tag» va antes de
   «Attach the files to the release». Ocurre ya hoy. Corregido en el plan (F9-14).
5. **Alta — faltaban frescura y recuperación de claves.** Incorporado el número de
   entrega y la repetición de la misma entrega (4.3). **Sin incorporar, a decisión del
   dueño**: segunda clave fuera de línea (7.2) y metadatos con caducidad para detectar
   que alguien congela las actualizaciones.
6. **Alta — macOS y Windows necesitan pruebas de admisión del sistema.** Comprobado: el
   intercambio actual hace dos movimientos seguidos y borra la marca de cuarentena.
   Incorporado: conservar la copia anterior hasta confirmar el arranque, no forzar el
   cambio de alcance en Windows, y los ensayos tempranos en equipos reales (6).

Límites que Codex declaró: revisión estática, sin equipos macOS ni Windows, sin sesión
gráfica de Arch, sin ejecutar CI. Siguen sin verificar la conservación de permisos en
macOS, el Control inteligente de aplicaciones y la transición de instalaciones «para
todos» en Windows.
