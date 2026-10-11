# Hito 5 — ciclo periódico cada cuatro horas

Estado a 2026-09-13: **FORUM WATCH ACTIVO**.

La suite pasa: **177/177 pruebas** (142 anteriores y 35 del Hito 5), más
**5/5 comprobaciones locales de selectores con Edge**. El ciclo manual real
verificó la cuenta 59 y leyó el tema 275 sin novedades. El tema permanece
`ACTIVE`. Tras la aprobación explícita del usuario, la tarea `\NozomuForumWatch`
está registrada y habilitada. Su única ejecución manual desde Task Scheduler
terminó con código 0 y un run SCHEDULED completado; verificó la cuenta 59 sin
novedades ni invocaciones del modelo o Discord.

## Componentes y archivos

Se reutilizan el almacenamiento, el lector autenticado, la evaluación aislada,
los borradores y la cola Discord de los hitos anteriores.

| Archivo del Hito 5 | Responsabilidad |
| --- | --- |
| [workflow.py](workflow.py) | Un ciclo, selección ACTIVE, recuperación y fases independientes. |
| [workflow_config.py](workflow_config.py) | Configuración local explícita, rutas externas y límites. |
| [workflow_state.py](workflow_state.py) | Barreras NEEDS_LOGIN/ACCESS_DENIED e incidentes deduplicados. |
| [workflow_audit.py](workflow_audit.py) | Lock del sistema operativo y diario de ejecuciones. |
| [scheduler.py](scheduler.py) | Plan inmutable revisable, comprobación de hashes y puente Windows. |
| [run-forum-watch.py](../scripts/run-forum-watch.py) | Entrada absoluta para Python del entorno virtual, sin depender del IDE. |
| [manage-forum-watch-scheduler.ps1](../scripts/manage-forum-watch-scheduler.ps1) | Estado, registro y administración de la tarea. |
| [test_workflow.py](../tests/test_workflow.py) | 35 pruebas del ciclo y del scheduler sin servicios reales. |

Cambios en componentes existentes: [cli.py](cli.py) incorpora los comandos;
[store.py](store.py) expone el estado efectivo, permite reanudar explícitamente
y enlaza errores con incidentes; [codex_runner.py](codex_runner.py) admite el
ejecutable nativo fijado; [notifications.py](notifications.py) proyecta un único
aviso por incidente de acceso. Se actualiza la navegación documental en
[README.md](README.md), [READER.md](READER.md), [NARRATIVE.md](NARRATIVE.md)
y [DISCORD.md](DISCORD.md). El resto del trabajo previo se conserva.

## Un ciclo y estados durables

`run-once` adquiere el lock, carga la configuración, obtiene los temas y lee
únicamente los `ACTIVE`. Cada lectura usa el lector existente: exige verificar
la identidad antes de extraer mensajes en cada página. En modo real siguen
autorizados exclusivamente `narutorol.jcink.net`, tema 275 y cuenta 59.
La capacidad de varios temas se prueba solamente con datos sintéticos.

La captura completa y sus cambios se confirman primero. La evaluación reclama
los trabajos de forma durable; la generación conserva su propia transacción.
Después se proyectan los eventos notificables y se procesa la cola Discord.
Una caída de Discord conserva la captura y el borrador válidos. Un fallo de un
tema permite procesar los demás. No existe transacción global ni bucle residente.

`PAUSED` y `CLOSED` no se leen. Los estados efectivos `NEEDS_LOGIN` y
`ACCESS_DENIED` añaden una barrera operativa a la intención original del tema,
sin sustituir las tablas de capturas ni reconstruir la base. Se consulta el
estado antes de leer y antes de evaluar. Pausar durante una lectura conserva
la captura completada y difiere la generación pendiente.

Una sesión expirada crea un incidente y un aviso «Inicio de sesión necesario».
Una sesión que no se pudo verificar utiliza el mismo título, explicando que
la causa no quedó confirmada. Una cuenta incorrecta o acceso denegado impone
`ACCESS_DENIED`. Los ciclos posteriores omiten el tema hasta una reanudación
explícita. No automatizan el login ni vuelven a crear avisos del mismo incidente.

La ausencia de cambios y de trabajos pendientes no llama al modelo ni al
transporte Discord. Si hay trabajos reales pendientes tras una interrupción
anterior, una captura sin nuevas diferencias permite terminarlos una vez.
La cola puede entregar avisos pendientes de una ejecución anterior; no genera
heartbeats ni avisos «sin novedades».

El modelo usa el contrato y aislamiento del Hito 3: contexto mínimo, primera
persona, separación IC/OOC, entradas `UNTRUSTED_INPUT`, sin herramientas,
sin secretos y sin escritura canónica. La configuración fija el ejecutable
nativo `codex-cli 0.147.0`, comprobado localmente, y un máximo de **300 segundos
por generación**. Cada trabajo se reclama una vez: un fallo o interrupción
conserva `GENERATION_FAILED` y no se regenera automáticamente.

Discord conserva los eventos y reglas del Hito 4: DRAFT_READY,
NEEDS_HUMAN_REVIEW, COMBAT_REVIEW_REQUIRED, GENERATION_FAILED, STALE,
SESSION_EXPIRED y ACCESS_DENIED. Un aviso por evaluación agrupa sus cambios.
No incluye el borrador completo. Se mantienen los máximos de tres intentos de
entrega, los plazos de rate limit y la ausencia de reintento automático cuando
el resultado remoto es incierto. Un envío `SENDING` interrumpido se cierra como
`FAILED_FINAL / INTERRUPTED_UNCERTAIN` en la siguiente recuperación.

## Datos operativos y recuperación

Todos los datos de ejecución están fuera del árbol del personaje:

```text
C:\Users\neko_\AppData\Local\NozomuForumWatch\
  workflow-config.json
  workflow-runs.sqlite3
  workflow.lock
  scheduler-plan-3f8989c5fdf7f7c2.json
  forum-watch-real.sqlite3       (base existente)
  edge-profile\                 (perfil existente)
  forum-watch-drafts\            (borradores existentes y futuros)
  discord-delivery\              (control de entrega compartido)
  secrets\discord-webhook.dpapi  (secreto existente, DPAPI del usuario)
```

No se guardan secretos en configuración, XML, argumentos, descripción de tarea
ni diario. Cada run registra ID, inicio/fin, trigger MANUAL/SCHEDULED, estado,
fase, hash de configuración, temas y contadores de lecturas, cambios, trabajos,
borradores y avisos. Los errores contienen códigos, no excepciones completas.
El diario no guarda cookies, webhook, prompts, publicaciones ni borradores.
`draft inspect` sí muestra el texto del borrador por petición local explícita.

El lock usa `msvcrt.locking` en Windows. El archivo permanente no representa
por sí solo un lock ocupado: la propiedad pertenece al proceso y Windows la
libera tras su terminación. No se debe borrar el archivo para forzar ejecución.
Otro ciclo sale con `SKIPPED_LOCKED`, sin matar al propietario. El diario puede
anotar esa salida mediante una transacción corta separada.

El siguiente propietario legítimo marca runs incompletos como `INTERRUPTED`,
conserva los trabajos reclamados e identifica generaciones interrumpidas sin
reintentar el modelo. La recuperación de evaluaciones también respeta el lock
del Hito 3, por lo que no toma una evaluación manual que aún se esté ejecutando.
Las escrituras ya confirmadas permanecen válidas. Las transacciones SQLite
incompletas se revierten por SQLite.

## Comandos operativos

Desde la raíz del repositorio, con la configuración externa ya preparada:

```powershell
$watchPython = 'D:\Rol\Naruto\potential man\brain\nozomu-codex\.venv-forum-watch\Scripts\python.exe'
& $watchPython -B -m forum_watch status
& $watchPython -B -m forum_watch run-once
& $watchPython -B -m forum_watch topic list
& $watchPython -B -m forum_watch topic inspect 275
& $watchPython -B -m forum_watch topic pause 275
& $watchPython -B -m forum_watch topic resume 275
& $watchPython -B -m forum_watch topic close 275
& $watchPython -B -m forum_watch topic add 'https://narutorol.jcink.net/index.php?showtopic=275'
& $watchPython -B -m forum_watch draft list
& $watchPython -B -m forum_watch draft inspect '<draft_id>'
& $watchPython -B -m forum_watch notifications pending
& $watchPython -B -m forum_watch notifications --preview
& $watchPython -B -m forum_watch scheduler status
& $watchPython -B -m forum_watch scheduler disable
& $watchPython -B -m forum_watch scheduler enable
& $watchPython -B -m forum_watch scheduler remove
```

`topic add` exige una orden explícita de CLI; el foro no controla los argumentos
ni la configuración. Los comandos anteriores de los hitos 1–4 siguen disponibles.
`--workflow-config <ruta absoluta>` permite seleccionar una configuración externa
explícita antes del subcomando. Los límites iniciales son 14400 segundos,
300 segundos de generación, 180 de lectura, 20 páginas y 10 avisos por ciclo.
La configuración requiere una base existente; no la crea ni restablece cursores.

`status` y `topic inspect` no comprueban la sesión ni consultan Windows. Para
conocer la tarea se usa `scheduler status`; los runs muestran cuándo se verificó
efectivamente la cuenta. Deshabilitar evita futuros disparos; no interrumpe el
ciclo que ya corre. Eliminar exige que la tarea no esté ejecutándose y conserva
configuración, base, borradores, perfil y secreto. Ninguna de esas operaciones
modifica tareas ajenas.

Para recuperar una sesión bloqueada: ejecutar el login manual existente, cerrar
su ventana y reanudar explícitamente. No introducir credenciales en Codex:

```powershell
$watchProfile = Join-Path $env:LOCALAPPDATA 'NozomuForumWatch\edge-profile'
& $watchPython -B -m forum_watch login --profile "$watchProfile" --timeout-seconds 1200
& $watchPython -B -m forum_watch topic resume 275
& $watchPython -B -m forum_watch run-once
```

La reanudación limpia la barrera operativa; la siguiente lectura debe verificar
de nuevo la cuenta 59. Nunca declara válida la sesión por ejecutar `resume`.

## Configuración aprobada y registrada en Windows

| Propiedad | Valor |
| --- | --- |
| Nombre / carpeta | `NozomuForumWatch` / `\` |
| Usuario | `DESKTOP-PB96O8E\neko_` |
| Inicio periódico | `2026-09-13T16:53:40+02:00` (hora de Madrid) |
| Repetición | `PT4H`, 14400 segundos, sin fecha final |
| Múltiples instancias | `IgnoreNew` |
| StartWhenAvailable | `true` |
| WakeToRun | `false` |
| Inicio de sesión | `InteractiveToken` |
| Privilegios | `LeastPrivilege` |
| Límite total de tarea | 30 minutos |
| Estado real comprobado | Enabled, Ready; último resultado 0 |
| Próxima ejecución comunicada por Windows | `2026-09-13T16:53:53+02:00` |
| Directorio de trabajo | `C:\Users\neko_\AppData\Local\NozomuForumWatch` |
| Ejecutable | `D:\Rol\Naruto\potential man\brain\nozomu-codex\.venv-forum-watch\Scripts\pythonw.exe` |

Argumentos exactos, sin secretos:

```text
-B "D:\Rol\Naruto\potential man\brain\nozomu-codex\scripts\run-forum-watch.py" --workflow-config C:\Users\neko_\AppData\Local\NozomuForumWatch\workflow-config.json --trigger SCHEDULED
```

`pythonw.exe` pertenece al mismo entorno virtual que el Python validado del
lector. La entrada absoluta localiza el código incluso desde el directorio
operativo. No abre una consola ni necesita Visual Studio o Codex UI.

Se requiere que el usuario mantenga iniciada su sesión de Windows; puede estar
bloqueada. No se almacena una contraseña de Windows. `InteractiveToken` necesita
una sesión existente; S4U no permite acceso a red ni archivos cifrados, por lo que
no sirve para el perfil y DPAPI de este flujo. Véase la documentación oficial de
[LogonType](https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype).

El equipo apagado o suspendido no ejecuta el ciclo, y la tarea no lo despierta.
Windows puede ejecutar una comprobación al volver a estar disponible; no se
promete que sea instantánea. `StartWhenAvailable` puede aplicar una espera
predeterminada de diez minutos. El programa ejecuta una sola comprobación del
estado actual, sin calcular ni repetir periodos perdidos. Véanse
[StartWhenAvailable](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-startwhenavailable),
[RepetitionPattern](https://learn.microsoft.com/en-us/windows/win32/taskschd/repetitionpattern)
y [MultipleInstances](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances).

El plan externo contiene el XML y hashes de configuración y bootstrap. SHA-256:

```text
3f8989c5fdf7f7c27f3fb0db26205c35555e5cb390ebb8f5587fb03b4bc268c1
```

**Aprobación explícita recibida y aplicada.** El usuario autorizó registrar este
plan y ejecutar manualmente una vez la tarea. Preparar un plan por sí solo no
instala la tarea. El instalador comprueba el hash aprobado y rechaza una tarea existente
con el mismo nombre, incluso si procede de este proyecto. Nunca la sobrescribe.

Comandos utilizados para registrar y comprobar este plan concreto (ya ejecutados;
la aprobación recibida cubría una única ejecución manual):

```powershell
$watchPlan = Join-Path $env:LOCALAPPDATA 'NozomuForumWatch\scheduler-plan-3f8989c5fdf7f7c2.json'
& $watchPython -B -m forum_watch scheduler install --plan "$watchPlan" --approved-plan-sha256 '3f8989c5fdf7f7c27f3fb0db26205c35555e5cb390ebb8f5587fb03b4bc268c1'
& $watchPython -B -m forum_watch scheduler status
& $watchPython -B -m forum_watch scheduler run
& $watchPython -B -m forum_watch scheduler status
& $watchPython -B -m forum_watch status
```

La última comprobación debe esperar a que termine la ejecución y contrastar
`last_task_result=0` con un nuevo run `SCHEDULED` completado. Que Windows acepte
el registro o el disparo no demuestra por sí solo que se haya leído el foro.
Las tres condiciones se comprobaron: tarea existente, habilitada y ejecución
manual completada. Por ello el estado actual es **FORUM WATCH ACTIVO**.

## Validación realizada

La suite previa pasó antes de editar: 142/142. La suite final pasó 177/177.
Las cinco comprobaciones de selectores usan HTML local, red bloqueada y un perfil
temporal, sin novedades fabricadas en el foro. Comandos:

```powershell
python -B -m unittest discover -s tests -q
& '.\.venv-forum-watch\Scripts\python.exe' -B tests/reader_dom_smoke.py
```

Las 35 pruebas nuevas incluyen los 23 escenarios solicitados: cero ACTIVE,
silencio sin cambios, nueva respuesta, mensaje propio, aviso único, fallo de
generación, fallo de Discord, sesión expirada, ausencia de spam, reanudación,
exclusión concurrente, liberación tras terminación abrupta, PAUSED, CLOSED,
ausencia de catch-up, idempotencia tras reapertura, STALE, edición manual,
inyección en posts, aislamiento entre temas, fallo parcial, diario sin secretos
y conservación del baseline. Cubren también pausa durante lectura, recuperación
de envío/generación interrumpidos, configuración inválida, timeout/ejecutable,
CLI, aprobación, cambio de plan, XML, rechazo nativo de tarea existente y entrada
con `pythonw` desde un directorio distinto sin consola ni IDE.

Las pruebas de snapshots usan datos sintéticos. La conservación del baseline
real se comprueba adicionalmente por IDs y hashes antes y después del ciclo
autorizado. No se importan fixtures en la base AUTHENTICATED_ONLY.

| Ejecución real | Resultado |
| --- | --- |
| `887e50facde948bc8ed8ee565af77cd8` · MANUAL · 10:51:38 UTC | Tema PAUSED; 0 lecturas, trabajos, borradores y avisos. |
| `49868183927445be81c8e515fa71229a` · MANUAL · 10:52:00–10:52:02 UTC | Tema ACTIVE; cuenta 59 verificada; 1 lectura; NO_RELEVANT_CHANGES; 0 trabajos, borradores y avisos. |
| `75b36e7526444c06b503ab1f99bf1cde` · SCHEDULED · 13:18:13–13:18:35 UTC | Disparo manual de la tarea registrada; COMPLETED, código Windows 0; tema ACTIVE, cuenta 59 verificada, 1 lectura, 0 cambios, trabajos, borradores y avisos; modelo no invocado. |

La activación y esa única lectura real estaban autorizadas expresamente en el
apartado 14. Se conservó el baseline y no se alteraron cursores artificialmente.
El analizador COM de Task Scheduler aceptó el XML preparado sin registrarlo,
confirmando PT4H, IgnoreNew (2), StartWhenAvailable y WakeToRun=false.

Discord conserva la validación real del Hito 4, con dos confirmaciones remotas
SENT y un intento por aviso, documentadas en [DISCORD.md](DISCORD.md). Este hito
no envió un mensaje de prueba adicional: el ciclo sin novedades verificó el
silencio. La sesión se verificó nuevamente a las 13:18:35 UTC; su validez futura
se comprueba en cada lectura, no se supone permanente.

Preservación verificada: **57/57 archivos con hashes idénticos** (53 archivos
protegidos del personaje, tres borradores operativos preexistentes y el secreto
cifrado). El perfil autenticado se reutilizó sin sustituirlo ni exportarlo.
La base real conserva las tres capturas previas al registro y todas sus revisiones
con los mismos IDs y hashes; añade una cuarta captura UPDATE válida y mantiene
un único BASELINE. El cursor procesado sigue sin alteración artificial.
`integrity_check=ok`, cero errores de claves foráneas, enlaces locales válidos
y `git diff --check` sin errores. No se inicializó Git ni se hicieron commits.

La instalación no requirió cambios de código ni repetir la suite completa:
su último resultado sigue siendo 177/177 más 5/5 selectores. Se ejecutaron de
nuevo dos pruebas específicas del lock (exclusión concurrente y recuperación
tras terminación abrupta): 2/2 correctas. La comprobación del lock operativo
después de finalizar el ciclo también pudo adquirirlo y liberarlo sin iniciar
otro workflow. No se disparó una segunda ejecución manual de la tarea.

La consulta real confirmó una sola acción y un solo trigger; ejecutable,
argumentos y directorio coinciden exactamente con el plan. Windows confirmó
PT4H, IgnoreNew, StartWhenAvailable=true, WakeToRun=false, usuario esperado,
InteractiveToken y privilegios Limited. El StartBoundary conserva 16:53:40;
se informa por separado del próximo tiempo calculado por Windows, 16:53:53.
El informe sin secretos se conserva en la raíz operativa:
`scheduler-verification-75b36e7526444c06b503ab1f99bf1cde.json`.

Errores de la ejecución: ninguno. No hubo operaciones de publicación, edición
ni envío en el foro; la lectura puede actualizar sus indicadores de lectura,
como se documentó en el Hito 2. No se ampliaron permisos ni se añadieron temas.
Registro e instalación completados; no quedan bloqueos de este hito.
Publicación: **NO IMPLEMENTADA**. Aprobación Discord:
**NO IMPLEMENTADA**. Memoria automática: **DESACTIVADA**.
