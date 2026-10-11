# Forum Watch — hito 1, núcleo simulado

El ciclo del Hito 5 y su estado actual están en [WORKFLOW.md](WORKFLOW.md).
`run-once` coordina lectura, evaluación y avisos únicamente para temas ACTIVE;
la tarea de Windows ya está registrada, habilitada y comprobada tras la
aprobación explícita del usuario.

El lector autenticado manual del Hito 2, su validación real y sus comandos
están documentados en [READER.md](READER.md). Usa una base operativa separada
con selección explícita `--storage-mode AUTHENTICATED_ONLY`.

La evaluación manual y la generación aislada del Hito 3 están documentadas
en [NARRATIVE.md](NARRATIVE.md), con pruebas, límites y resultados reales.
El comando explícito `evaluate` y el orquestador del Hito 5 pueden invocar al
intérprete; los comandos individuales de importar o leer no generan respuestas.

El Hito 4 añade una cola y avisos manuales por webhook, documentados en
[DISCORD.md](DISCORD.md). `notify` realiza el envío manual; el Hito 5 lo reutiliza
para los eventos notificables producidos por su ciclo.

Esta guía describe el modo predeterminado del núcleo local Python/SQLite:
importa únicamente muestras `SYNTHETIC` en bases `SYNTHETIC_ONLY`, sin navegador.
El núcleo de ingesta no llama a modelos ni envía avisos. La programación del
orquestador se administra por separado; no hay componentes de publicación.
Cada comando termina al completar su operación; no hay servicio residente.

Requisitos: Python 3.11 o posterior con `sqlite3`. Desarrollo y pruebas en
Windows con Python 3.14.7. No requiere instalación ni dependencias externas.
Ejecutar los comandos desde la raíz `nozomu-codex`. `-B` evita escribir bytecode.

## Pruebas

```powershell
python -B -m unittest discover -s tests -v
```

Las pruebas crean sus bases con `TemporaryDirectory`, incluida la prueba de
CLI en procesos Python independientes. Cubren rollback mediante un fallo SQL
inyectado después de escrituras parciales y dos importaciones concurrentes
mediante conexiones SQLite independientes. Ninguna usa servicios externos.

## Demostración con una base temporal explícita

Esta ubicación es exclusivamente de demostración; no reutilizar la base para
un futuro lector real. Cada ejecución del bloque de preparación usa un nombre
nuevo. Las muestras incluidas no son mensajes reales ni turnos narrativos.

```powershell
$demoRoot = Join-Path ([IO.Path]::GetTempPath()) ('forum-watch-demo-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $demoRoot | Out-Null
$demoDb = Join-Path $demoRoot 'synthetic.sqlite3'
$topicUrl = 'https://narutorol.jcink.net/index.php?showtopic=275&st=0#entry1144'

# Crear explícitamente el registro inicial: PAUSED y contexto sin confirmar.
python -B -m forum_watch --db "$demoDb" init --config forum_watch/config.example.json

# Historial inicial: BASELINE, cero cambios pendientes.
python -B -m forum_watch --db "$demoDb" import "$topicUrl" forum_watch/examples/initial.json
python -B -m forum_watch --db "$demoDb" pending "$topicUrl"

# Novedad: un NEW_MESSAGE del autor sintético 7001.
python -B -m forum_watch --db "$demoDb" import "$topicUrl" forum_watch/examples/update.json

# Repetición idéntica: REPLAY, ningún cambio adicional.
python -B -m forum_watch --db "$demoDb" import "$topicUrl" forum_watch/examples/update.json

# Edición: un CONTENT_EDIT, conservando ambas versiones del mensaje.
python -B -m forum_watch --db "$demoDb" import "$topicUrl" forum_watch/examples/edit.json
python -B -m forum_watch --db "$demoDb" versions "$topicUrl" --message-id synthetic-002
python -B -m forum_watch --db "$demoDb" pending "$topicUrl"
python -B -m forum_watch --db "$demoDb" captures "$topicUrl"
python -B -m forum_watch --db "$demoDb" inspect "$topicUrl"
python -B -m forum_watch --db "$demoDb" errors
```

Resultado del flujo: tres capturas aceptadas, dos mensajes, tres revisiones
totales y dos cambios pendientes (`NEW_MESSAGE`, `CONTENT_EDIT`).
`last_processed_message_id` permanece `null`. La repetición no vuelve a avanzar
la referencia, aunque se ejecute en un proceso nuevo o después de otra captura.

## Registro y estados

```powershell
# Alta explícita. Una URL equivalente conserva el primer enlace y estado.
python -B -m forum_watch --db "$demoDb" add "$topicUrl"
python -B -m forum_watch --db "$demoDb" list
python -B -m forum_watch --db "$demoDb" inspect "$topicUrl"
python -B -m forum_watch --db "$demoDb" resume "$topicUrl"
python -B -m forum_watch --db "$demoDb" pause "$topicUrl"
python -B -m forum_watch --db "$demoDb" close "$topicUrl"
```

- `init` y `add` son las únicas operaciones que pueden crear una base. Las
  demás exigen una ya inicializada. `init` no resetea un registro existente.
- La clave es `(host, topic_id)`. Se aceptan HTTPS, host configurado,
  `/index.php`, puerto predeterminado o 443, `showtopic` positivo y `st`
  opcional no negativo. Se rechazan credenciales en la URL, otros parámetros,
  hosts externos, identificadores inválidos y valores repetidos contradictorios.
- Host, ceros iniciales del ID, página y fragmento se normalizan para la
  identidad. El primer enlace original se conserva literalmente. Ningún
  enlace dentro del contenido crea registros.
- `PAUSED` y `ACTIVE` permiten importaciones sintéticas **manuales y explícitas**.
  Ninguno inicia lectura, procesamiento, modelo o tarea programada. La pausa
  no se presenta como un bloqueo para este instrumento local de importación.
- `CLOSED` conserva todo el historial y rechaza capturas nuevas. No se reabre
  con `add`, `pause` o `resume`. Repetir una captura aceptada devuelve `REPLAY`
  sin mutaciones del estado de lectura.
- La ingesta registra cambios `PENDING_EVALUATION`, tanto propios como ajenos.
  `is_own` compara el ID de autor con la cuenta esperada; no usa el nombre
  visible. No existe una petición automática de respuesta. Con el Hito 3,
  `pending` excluye los trabajos ya reclamados o evaluados; sus resultados
  se consultan con `evaluations`. El evento original se conserva íntegro.

`config.example.json` conserva host `narutorol.jcink.net`, cuenta esperada 59,
intervalo previsto 14400, procedencia `USER_CONFIRMED` y tema 275 en `PAUSED`.
El intervalo es un dato, no un horario activo. El permiso es una declaración
del usuario y la identidad de sesión permanece `NOT_VERIFIED`.

Título, participantes, clasificación, vínculo a memoria y último mensaje
procesado permanecen nulos. `entry1144` solo pertenece al enlace original.
No identifica la última lectura. No hay asociación automática con
`muelle-nozomu-arashi`.

## Contrato de captura normalizada v1

Consultar `examples/initial.json`, `examples/update.json` y `examples/edit.json`.

| Campo | Significado |
|---|---|
| `schema_version` | Entero `1`; distinto de la versión de esquema SQLite. |
| `origin` | Exactamente `SYNTHETIC`; se rechaza cualquier otro origen. |
| `capture_id` | ID inmutable y único dentro del tema; hasta 128 caracteres alfanuméricos y `._:-`, empezando por alfanumérico. |
| `captured_at` | Instante ISO 8601 con `T` y zona horaria. Es observación, nunca fecha IC. |
| `complete` | Booleano; solo `true` puede establecer o avanzar la referencia. |
| `topic` | Objeto con `host` y `topic_id` que deben coincidir con el tema registrado indicado en CLI. |
| `messages` | Array en orden de lectura; representa el historial completo, no un delta ni una página aislada. Puede estar vacío en una muestra completa inicial. |
| `messages[].message_id` | ID de dato, con las mismas restricciones de caracteres que `capture_id`. Nunca es una ruta. |
| `messages[].author_id` | Entero positivo; no certifica identidad autenticada. |
| `messages[].content` | Texto relevante, incluyendo diálogos, citas y atribuciones. |
| `metadata` | Objeto opcional de datos auxiliares de captura; no se convierte en contexto confirmado. |
| `messages[].metadata` | Objeto opcional de presentación; por ejemplo nombre visible, firma y contador. |

Los IDs enteros deben caber en un entero SQLite positivo de 64 bits. Se
rechazan booleanos en lugar de enteros, claves JSON duplicadas, NaN,
identificadores repetidos y campos desconocidos fuera de `metadata`.

No existe un parser HTML ni un extractor de firmas: el productor de la muestra
ya separa el contenido de su presentación. Los contratos y validaciones de un
lector real corresponden a otro hito.

## Normalización y revisiones

Se transforman únicamente los finales de línea CRLF y CR a LF para comparar
contenido mediante SHA-256. Se conservan espacios, líneas vacías, párrafos,
mayúsculas, caracteres Unicode, BBCode, signos de diálogo, citas y atribuciones.
No se elimina texto por parecer firma, orden al agente o enlace.

Los metadatos se guardan, pero no participan en el hash de contenido. Cada
captura aceptada conserva además su documento JSON con claves ordenadas y
valores íntegros, junto con su hash. No se conserva la indentación original
del archivo JSON. Las revisiones guardan contenido original y normalizado.

- Primera captura completa: historial y revisiones iniciales, sin pendientes.
- Captura posterior: `NEW_MESSAGE`, `CONTENT_EDIT` o `NO_RELEVANT_CHANGES`.
- Misma captura: `REPLAY`, sin duplicar ni mover la referencia a una captura
  antigua. Cambiar datos conservando su ID produce `CAPTURE_ID_CONFLICT`.
- Nuevo ID y contenido igual: otra observación sin una falsa edición.
- A→B→A genera tres revisiones; el hash no impide registrar reversiones.
- Un ID nuevo debe tener un instante de observación estrictamente posterior
  al último aceptado. Las capturas atrasadas o de igual instante se rechazan;
  no hay ordenación automática de un lote desordenado.
- La desaparición de un mensaje conocido rechaza la captura completa con
  `MISSING_MESSAGES`, conservando historial y referencia. No infiere borrados.
  Una reaparición con el mismo contenido no crea otro mensaje; con contenido
  distinto crea una edición cuando la captura vuelve a ser válida.
- Cambios de autor o del orden relativo de mensajes conocidos requieren
  investigación y se rechazan. No se inventa una resolución de la anomalía.

## Persistencia, errores y concurrencia

Se exige siempre `--db`. Su directorio padre debe existir y el archivo debe
terminar en `.sqlite3`, `.sqlite` o `.db`. Se rechazan rutas resueltas bajo
`.codex/`, `.git/`, `instructions/`, `memory/`, `shared/`, `reference/` y
`drafts/`. Usar ubicaciones temporales para toda demostración.

SQLite se identifica mediante `application_id=0x46575331`, `user_version=1` y
metadatos `SYNTHETIC_ONLY`. Una base ajena, no marcada, con otro modo o versión
se rechaza al abrirla, sin migrarla. Una configuración incompatible con la ya
almacenada tampoco se aplica. El futuro almacenamiento real debe ser separado.

Tablas: `metadata`, `topics`, `captures`, `messages`, `revisions`,
`capture_messages`, `pending_changes`, `import_errors`.

`BEGIN IMMEDIATE` serializa escritores. Captura, revisiones, orden de mensajes,
pendientes y última captura válida se confirman en una única transacción. Hay
claves únicas, claves foráneas activadas y una espera de bloqueo de cinco
segundos. No hay reintentos en bucle ni procesos residentes.

Un error revierte la transacción y se registra separadamente en
`import_errors`. No se anuncia ausencia de novedades tras fallar validación.
Si la base permanece bloqueada o indisponible y tampoco permite escribir el
error, se devuelve `ERROR_LOG_FAILED` junto al código original: no se afirma
que el error quedó persistido. Los fallos al abrir la base solo pueden
informarse por CLI porque todavía no hay un almacén validado para registrarlos.

CLI: código de salida 0 para éxito o repetición, 2 para validación/operación
rechazada, 3 para fallo local no recuperable. Los errores salen por stderr;
las respuestas por stdout como JSON. El escape de salida evita interpretar
caracteres de control del contenido en la terminal.

Los archivos de configuración, muestras y código son nuevos. El módulo no
escribe los archivos narrativos, memoria, perfil, borradores o configuración de
agentes existentes. Las muestras permanecen separadas del estado de Nozomu.

## Fuera de este hito

El núcleo simulado del Hito 1 no incluye navegador, clasificación IC/OOC,
semántica de combate ni generación. Sus ampliaciones manuales se describen
en [READER.md](READER.md) y [NARRATIVE.md](NARRATIVE.md).
Los avisos de Discord se añaden como operación manual en el Hito 4.
Programación, publicación y consolidación canónica automática no están
implementadas.
