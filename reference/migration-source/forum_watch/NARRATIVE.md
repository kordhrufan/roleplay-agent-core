# Hito 3 — evaluación y generación narrativa aislada

**GENERACIÓN NARRATIVA AISLADA IMPLEMENTADA Y PROBADA**, 2026-09-13.

La ingesta conserva cambios por mensaje y revisión. Una orden manual los
evalúa y, cuando corresponde, guarda un borrador externo con estado
`PENDING_HUMAN_REVIEW`. Leer o importar una captura no invoca al modelo.
El tema 275 permanece `PAUSED`; no hay servicio residente.

Este documento conserva la validación del Hito 3. El Hito 4 añade avisos
manuales sobre sus eventos persistidos; véase [DISCORD.md](DISCORD.md).
El estado vigente y la invocación mediante el ciclo del Hito 5 están en
[WORKFLOW.md](WORKFLOW.md); los estados de cierre que siguen corresponden al Hito 3.

## Archivos de este hito

| Archivo | Cambio |
| --- | --- |
| [policy.py](policy.py) | Filtros demostrables previos al modelo. |
| [context.py](context.py) | Proyección mínima de fuentes vigentes y mensajes observados. |
| [narrative.py](narrative.py) | Evaluación manual, reclamación de trabajos y derivación a revisión. |
| [codex_runner.py](codex_runner.py) | Invocación real del ejecutable nativo de Codex, con capacidades restringidas. |
| [result.py](result.py), [narrative-result.json](schemas/narrative-result.json) | Contrato JSON y validación de referencias IC y propuestas. |
| [drafts.py](drafts.py) | Versiones, dependencias, historial de correcciones y estado STALE. |
| [store.py](store.py) | Pendientes sin evaluar e invalidación dentro de la transacción de captura/cierre. |
| [cli.py](cli.py) | Comandos evaluate, evaluations, drafts y retire-draft. |
| [test_narrative.py](../tests/test_narrative.py) | 30 pruebas nuevas sin modelo ni navegador. |
| [narrative_manual_smoke.py](../tests/narrative_manual_smoke.py) | Demostración explícita con modelo real y mensajes completamente sintéticos. |
| [README.md](README.md), [READER.md](READER.md), este documento | Alcance vigente, instrucciones y evidencia. |

Se añaden los módulos, el esquema, las dos pruebas y este documento; se
modifican únicamente store.py, cli.py, README.md y READER.md entre los archivos
preexistentes. No se añadieron dependencias para el núcleo o sus pruebas.
No se inicializó Git ni se hicieron commits, cambios de rama o push.

## Evaluación y contrato

Cada cambio puede terminar en `NO_RESPONSE_NEEDED`, `WAIT_FOR_TURN`,
`NEEDS_HUMAN_REVIEW`, `COMBAT_REVIEW_REQUIRED`, `DRAFT_READY` o
`GENERATION_FAILED`. `RUNNING` es un estado operativo transitorio.

Antes de invocar al intérprete se comprueban: ausencia de trabajos nuevos,
cierre local del tema, último cambio pendiente de la cuenta 59, revisiones
ya sustituidas y existencia de un borrador pendiente. Los metadatos sin
cambio de contenido no crean trabajos desde la ingesta. Las versiones ya
reclamadas no vuelven a generar. Un borrador ACTIVE o STALE pendiente exige
revisión y retirada explícita antes de permitir otro.

El evaluador decide la intención narrativa, las situaciones ambiguas, el
orden entre jugadores, las decisiones importantes y la presencia de combate.
No se deducen por palabras clave ni por alternancia de autores.

El contrato requiere `decision`, `reason`, `important_decisions`,
`ic_facts_used`, `uncertainties`, `draft`, `memory_candidates` y
`scene_assessment`. Las listas sin elementos se devuelven vacías.
El esquema limita tipos, campos, tamaños y enumeraciones; se rechazan campos
desconocidos, JSON duplicado o inválido y respuestas envueltas en Markdown.
El validador local implementa el subconjunto usado por este esquema fijo,
sin pretender ser una biblioteca JSON Schema general.

Cada valoración remite a una versión exacta, por ejemplo
`message:s2:r1`, y distingue OBSERVABLE_IC, OOC, PRIVATE_THOUGHT,
PENDING_PROPOSAL, UNCONFIRMED_OUTCOME, COMBAT y UNCERTAIN.
Solo hechos iniciales documentados o valoraciones OBSERVABLE_IC pueden
figurar como referencias de hechos IC. No se rescata prosa de una salida
inválida: el trabajo termina en GENERATION_FAILED.

DRAFT_READY exige texto no vacío, ausencia de decisiones importantes y de
valoraciones COMBAT/UNCERTAIN. Los demás resultados llevan `draft: null`.
Si se identifica COMBAT se exige COMBAT_REVIEW_REQUIRED y se guarda un
paquete de entrega al especialista existente `nozomu_combat`, con mensajes,
valoraciones y recursos de escena aún por confirmar. No se invoca otra
cadena de agentes ni se resuelve el combate.

## Contexto del intérprete existente

Se reutilizan AGENTS.md e instructions/interprete.md como instrucciones,
una selección explícita de diez campos básicos del perfil y las secciones
1, 2, 3, 4, 7 y 8 del documento maestro como datos documentados con sus límites.
Se guardan identificadores relativos de fuente y SHA-256 del texto leído.
No se crea otra personalidad ni una copia de configuración de agentes.

La consulta de continuidad al especialista de memoria confirmó que no hay
vínculo documentado entre el tema 275 y muelle-nozomu-arashi. Por ello, este
paquete conserva `memory_topic_mapping: null`, sin episodios ni impresiones
importados de aquel tema. Esto no significa que Nozomu carezca de historia:
su perfil, voz y conocimientos iniciales documentados sí se incluyen.
Una futura asociación de memoria necesitaría evidencia y una ampliación
explícita del constructor; no se deduce automáticamente del número de tema.

| Bloque | Contenido |
| --- | --- |
| THREAD | Tema, URL autorizada, título y participantes observados, clasificación confirmada si existe y seguimiento. |
| SCENE | Mensajes normalizados, orden, autores, revisiones y etiquetas OOC explícitas separadas. |
| NOZOMU | Perfil OOC, voz y contexto documentados, hechos IC iniciales y límites de continuidad. |
| CONSTRAINTS | Primera persona, respeto a otros personajes, separación IC/OOC, sin ejecución, publicación ni consolidación. |

Los mensajes y metadatos observados se etiquetan UNTRUSTED_INPUT. El nombre
de cuenta es una etiqueta OOC: no acredita una presentación IC.
Solo se separan automáticamente marcas explícitas como
`[OOC]` o `[OOC DEL JUGADOR]`; el mensaje íntegro se conserva. El modelo
debe clasificar el resto, incluidos pensamientos privados no etiquetados.

No se exportan cookies, perfil de navegador, cabeceras, HTML completo,
webhooks, metadatos arbitrarios de captura ni rutas operativas. El lector
no está conectado al intérprete. No se trunca silenciosamente la escena:
si el paquete completo supera 128.000 caracteres, se deriva a revisión.

Las propuestas de memoria permanecen en SQLite, siempre pendientes:
FACT, NOZOMU_IMPRESSION, PENDING_INTENTION o UNCONFIRMED_OUTCOME.
FACT exige referencias IC admitidas. Ninguna categoría escribe en memory/,
shared/ ni en el perfil. El etiquetado y el esquema no demuestran por sí
solos que toda interpretación semántica sea correcta; la revisión humana
sigue siendo necesaria.

## Mecanismo ejecutable e aislamiento comprobado

Se probó **codex-cli 0.147.0**, usando el ejecutable nativo instalado con
npm. Se localiza desde codex.cmd, sin ejecutar el envoltorio PowerShell ni
usar `shell=True`. El adaptador verifica la versión antes de generar.
Otra versión termina con `UNVERIFIED_CODEX_VERSION`; no se instala ni
actualiza nada automáticamente.

La invocación usa `codex exec`, contexto por stdin, directorio temporal
ajeno al proyecto, `--ignore-user-config`, `--ephemeral`,
`--sandbox read-only`, `--output-schema` y `--output-last-message`.
Se fija el proveedor integrado OpenAI. El ejecutable usa su autenticación
local existente; este código no lee ni copia archivos de credenciales y
no necesita heredar claves API. Véase la documentación oficial de
[ejecución no interactiva](https://developers.openai.com/codex/noninteractive)
y de [configuración](https://developers.openai.com/codex/config-reference).

El entorno heredado se limita a nombres básicos de Windows, rutas de
ejecutables y temporales, definidos en CORE_ENV. No se heredan las demás
variables ni la configuración del agente padre. Esto no equivale a ocultar
toda ruta al proceso nativo; esas variables son necesarias para ejecutarlo.
Los datos entregados al modelo viajan únicamente en el paquete revisado.

Se desactivan búsqueda web, lectura automática de documentos del proyecto,
shell, ejecución unificada, apps, plugins, navegador, imágenes, agentes,
memorias, hooks y el host de Code Mode. La configuración concreta se
conserva en command() y DISABLED_FEATURES. Tiempo máximo de generación:
120 segundos; comprobación de versión: 15 segundos; sin reintentos.

Pruebas realizadas:

- Inspección del paquete y pruebas con metadatos/variables señuelo:
  quedan fuera los datos de sesión, secretos y memoria de temas no asociados.
- Prueba real de capacidad: se pidió leer un archivo señuelo sintético.
  El host rechazó la herramienta; el resultado indicó `read_success: false`
  y el router registró `error=code-mode host is disabled`.
- Generación real con una instrucción maliciosa dentro del post:
  no hubo llamadas a herramientas aceptadas; la instrucción se clasificó OOC.
- El adaptador rechaza errores del router, eventos de acciones o herramientas,
  un turno fallido y cualquier salida incompatible con el esquema.
  Comprueba también que el archivo de respuesta coincide con el mensaje final.

El runtime puede anunciar nombres de herramientas aunque el host esté
deshabilitado. La evidencia es el bloqueo efectivo observado y los controles
del adaptador, no una afirmación de catálogo vacío ni una prueba formal de
aislamiento total del sistema operativo. El filtrado de eventos es una
comprobación adicional; no sustituye la desactivación previa de capacidades.

Incidencias observadas y resueltas o acotadas:

- `codex.ps1` falló con `PSSecurityException`; se usó el ejecutable nativo,
  sin modificar la política de PowerShell.
- El PATH de VS Code exponía `codex-cli 0.154.0-alpha.6.2`. La primera
  evaluación fue rechazada por versión antes de llamar al modelo. Se corrigió
  el localizador para priorizar la instalación npm verificada; el trabajo
  fallido se conservó.
- El runtime emite el aviso
  `Code Mode is unavailable because code-mode host is disabled.`
  El adaptador admite únicamente ese aviso de arranque conocido; los intentos
  efectivos de herramientas se rechazan. No se habilitó el host.
- Apareció una advertencia de caché:
  `missing field supports_parallel_tool_calls at line 133 column 5`.
  No impidió las generaciones verificadas; no se modificó la caché global.
- La revisión automática rechazó inicialmente la demostración por no estar
  suficientemente concretado el destino y contenido enviado. Se preparó e
  inspeccionó el paquete exacto, con perfil ficticio y mensajes sintéticos,
  y se fijó el proveedor OpenAI. La nueva revisión autorizó esa ejecución.
  No se eludió el rechazo ni queda una aprobación pendiente.

## Persistencia, concurrencia y revisión

La misma SQLite operativa incorpora narrative_meta (componente versión 1),
evaluation_runs, evaluation_jobs, narrative_drafts y draft_file_revisions.
No cambia el origen ni el user_version de las bases sintética (1) y real (2).
Una base sintética no se convierte en real.

pending_changes conserva el evento original de ingesta. evaluation_jobs,
con clave única por change_id, conserva su resultado de evaluación.
`pending` muestra solo eventos sin trabajo reclamado. El campo heredado
`last_processed_message_id` no avanza: la autoridad de este hito es el
registro por cambio y revisión, no un cursor único que perdería ediciones.

Un bloqueo de archivo del sistema operativo serializa evaluadores sobre
cada base. Se reclama el trabajo antes de invocar al modelo. Tras un corte,
un RUNNING abandonado pasa a GENERATION_FAILED al recuperar el bloqueo, sin
repetir la generación. No hay reintento automático ni comando para resetear
el historial. Un trabajo fallido o que necesita revisión sigue visible con
`evaluations`, aunque deje de aparecer en `pending`.

Los nuevos archivos se crean exclusivamente en:

`<directorio de la base>/forum-watch-drafts/<namespace>/topic-275-vN-<id>.md`

Esa ubicación debe estar fuera de la carpeta del personaje. El identificador
es generado localmente; el texto del modelo nunca determina rutas ni órdenes.
Se conservan IDs y revisiones de mensajes, hashes de fuentes, timestamp,
versión y texto original. Un índice único permite como máximo un ACTIVE
por tema. ACTIVE describe vigencia; PENDING_HUMAN_REVIEW describe revisión.
No existen transiciones a APPROVED, PUBLISHED o CANON.

Una nueva revisión de un mensaje usado, un nuevo mensaje o el cierre local
marcan el borrador STALE dentro de la transacción de ingesta/cierre. Cambios
solo de metadatos lo conservan. Si el contexto cambia antes o durante la
generación, no se activa un borrador sobre esa base desfasada.

`drafts`, `evaluate` y `retire-draft` observan las correcciones locales y
añaden una revisión MANUAL, conservando la GENERATED y el archivo editado.
No vigilan continuamente el disco ni capturan cada pulsación: registran la
versión presente al ejecutar esos comandos. Los archivos se leen como UTF-8
sin normalizar sus saltos de línea. Un archivo ausente se marca STALE y no
se reconstruye silenciosamente.

`retire-draft` retira explícitamente el borrador conservando texto e historial;
no lo aprueba. Un nuevo borrador exige además un cambio nuevo aún sin evaluar.
Retirar después de evaluar un cambio como NEEDS_HUMAN_REVIEW no reabre ese
trabajo ni provoca una regeneración.

Los fallos SQL comprobados revierten el registro y eliminan solo el archivo
nuevo de esa ejecución si sigue intacto. Una corrección concurrente se
preserva. SQLite y el sistema de archivos no forman una única transacción:
un corte abrupto del proceso puede dejar un archivo propio sin registrar,
que no se considera ACTIVE ni autoriza sobrescrituras. Los hashes de perfil
e instrucciones permiten auditar las fuentes usadas; no hay vigilancia
automática de cambios en esos documentos.

## Comandos manuales y pruebas ejecutadas

Desde la raíz, sin activar entornos ni cambiar políticas:

```powershell
# Suite completa sin servicios externos.
python -B -m unittest discover -s tests -v

# Regresión de selectores locales: Edge temporal, red bloqueada.
& '.\.venv-forum-watch\Scripts\python.exe' -B tests/reader_dom_smoke.py

# Base real ya existente; evaluate no abre navegador ni obtiene capturas.
$watchRoot = Join-Path $env:LOCALAPPDATA 'NozomuForumWatch'
$watchDb = Join-Path $watchRoot 'forum-watch-real.sqlite3'
$watchTopic = 'https://narutorol.jcink.net/index.php?showtopic=275'
python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY evaluate "$watchTopic"
python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY evaluations "$watchTopic"
python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY drafts "$watchTopic"
```

`evaluate` termina con código 2 ante GENERATION_FAILED y 0 para decisiones
válidas, incluidas las de revisión o espera. Los errores locales de la CLI
conservan los códigos existentes.

Demostración reproducible opcional: **invoca realmente el modelo**. Crea una
base separada con mensajes sintéticos y usa el intérprete documentado.

```powershell
$demoRoot = Join-Path $watchRoot ('hito3-synthetic-' + [guid]::NewGuid().ToString('N'))
python -B tests/narrative_manual_smoke.py --output-root "$demoRoot"

# Alternativa: preparar el paquete sin modelo, en OTRA carpeta nueva.
$reviewRoot = Join-Path $watchRoot ('hito3-review-' + [guid]::NewGuid().ToString('N'))
python -B tests/narrative_manual_smoke.py --output-root "$reviewRoot" --prepare-only
```

El directorio de salida no debe existir. La preparación escribe
context-review.json y model-request-review.txt para inspección; no genera.
La demostración normal escribe report.json, SQLite y su nuevo borrador.
La corrección manual de esta prueba es simulada y está marcada como tal.

Para una retirada explícita, usar un draft_id devuelto por `drafts`:

```powershell
python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY retire-draft "$watchTopic" "<draft_id>"
```

Este último comando es una instrucción de uso; no se retiró ningún borrador
del usuario. También se ejecutaron consultas SQLite de integridad, revisión
de Git y comparación SHA-256 de los archivos protegidos.

| Comprobación | Resultado |
| --- | --- |
| Regresión inicial de la suite existente | 71/71 correctas. |
| Regresión inicial de selectores con Edge local | 5/5 correctas. |
| Suite final sin modelo/navegador | 101/101 correctas: 71 existentes + 30 nuevas. |
| Prueba real de generación sobre escena sintética | DRAFT_READY y PENDING_HUMAN_REVIEW. |
| Edición posterior del contexto sintético | STALE; segunda evaluación sin modelo, NEEDS_HUMAN_REVIEW. |
| Corrección manual simulada | Archivo intacto, dos revisiones conservadas, cero borradores ACTIVE al final. |
| Comparación de 53 archivos protegidos | 53 idénticos; ninguno eliminado. |

Las 30 pruebas cubren los 15 casos solicitados: propio, social, OOC,
pensamiento privado, propuesta pendiente, ambigüedad, combate, inyección,
JSON inválido, edición de contexto, respuesta con borrador pendiente,
corrección manual, propuestas de memoria, ausencia de cambios y reinicio.
También cubren concurrencia, cambios antes/durante el modelo, retiro y
versión 2, metadatos sin edición, cuenta incorrecta, rollback SQL, ejecutable
correcto y rechazo de intentos de herramientas. Los casos unitarios usan
dobles del modelo: prueban contratos y persistencia, no una capacidad
semántica universal.

## Evidencia de generación real y prueba del tema 275

La demostración final usó la carpeta externa
`%LOCALAPPDATA%\NozomuForumWatch\hito3-synthetic-manual-20260913-03\`.
Su report.json conserva:

- Run de generación: `78924ae10a834d1db68aaf540c6e07e7`.
- Borrador versión 1: `ac31652b9ee24147a42f1d103cf48ade`.
- Runtime: codex-cli 0.147.0; cero llamadas a herramientas aceptadas.
- Run posterior a la edición: `9b78738b38ab4303b7c0d0f6124a1745`.
- Estado final STALE; manual_correction_preserved=true; file_revisions=2.

La entrada contenía una pregunta social sobre novelas, una propuesta de
comer, un pensamiento privado y una orden maliciosa para leer cookies y
publicar. La respuesta real separó OBSERVABLE_IC, PENDING_PROPOSAL,
PRIVATE_THOUGHT y OOC. El borrador no utilizó las monedas ocultas del
pensamiento privado ni la orden maliciosa; las propuestas de memoria
quedaron PENDING_HUMAN_REVIEW.

La inspección editorial detectó «una pizca de pudor» al hablar de novelas
románticas. El especialista de memoria lo señaló como matiz propuesto,
no rasgo documentado ni experiencia confirmada. Permanece para revisión
humana, sin corregir a escondidas la salida original. DRAFT_READY certifica
la disponibilidad del borrador validado, no su aprobación literaria.

Se eligió la **prueba real A**, evaluando lo ya registrado en la SQLite real:

```json
{
  "decision": "NO_RESPONSE_NEEDED",
  "reason": "No hay versiones nuevas pendientes de evaluación.",
  "model_called": false,
  "jobs_evaluated": 0,
  "tracking_state": "PAUSED"
}
```

Verificación posterior: integrity_check=ok, cero errores de claves foráneas,
dos capturas AUTHENTICATED_FORUM, tres revisiones, cero cambios pendientes,
cero evaluation_runs y cero narrative_drafts en esa base.
Se crearon las tablas operativas del componente, sin añadir capturas ni
alterar el cursor de lectura. No se fabricó una novedad ni se usó un mensaje
real para la demostración de generación.

Esta prueba comprueba el estado registrado en SQLite. No hubo una nueva
lectura del foro ni una nueva verificación de sesión en el Hito 3.
La evidencia autenticada previa sigue descrita en READER.md.

## Preservación y estado al terminar

Los 53 archivos protegidos de AGENTS.md, instructions/, reference/, shared/,
memory/, drafts/ y .codex/ conservaron sus hashes. No se modificaron los
borradores existentes ni la configuración de especialistas. Solo se guardó
estado operativo externo y código/documentación del Hito 3.

Discord al cierre del Hito 3: **NO CONECTADO**. Su ampliación manual posterior
está descrita en [DISCORD.md](DISCORD.md).
Programación: **NO ACTIVADA**.
Publicación: **NO IMPLEMENTADA**.
Memoria canónica automática: **DESACTIVADA**.

No se escribió en el foro ni se envió ningún mensaje. La generación manual
queda disponible; no se ha activado ejecución periódica ni el siguiente hito.
