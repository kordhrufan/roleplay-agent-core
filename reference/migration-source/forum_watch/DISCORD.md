# Hito 4 — avisos manuales de Discord

**DISCORD IMPLEMENTADO Y VALIDADO**, 2026-09-13. Los dos avisos reales
recibieron confirmación e ID remoto, con un intento por aviso.
No hay seguimiento periódico, publicación en el foro, bot, botones ni aprobación
desde Discord.

Este documento conserva el cierre del Hito 4. La orquestación posterior y el
estado vigente del seguimiento están en [WORKFLOW.md](WORKFLOW.md).

## Archivos y conservación del trabajo anterior

Nuevos:

- [notifications.py](notifications.py): proyección de eventos persistidos, cola,
  deduplicación, intentos, vigencia del borrador y control compartido de entrega.
- [discord.py](discord.py): transporte HTTPS de salida, confirmación y errores.
- [discord_secret.py](discord_secret.py): entrada local oculta y cifrado DPAPI.
- [set-discord-secret.ps1](../scripts/set-discord-secret.ps1): envoltorio opcional.
- [test_notifications.py](../tests/test_notifications.py) y
  [test_discord_manual_demo.py](../tests/test_discord_manual_demo.py): pruebas
  aisladas del transporte y del pipeline.
- [discord_vault_smoke.py](../tests/discord_vault_smoke.py): comprobación DPAPI
  con un valor sintético y un temporal propio.
- [discord_manual_smoke.py](../tests/discord_manual_smoke.py): dos fases explícitas
  de envío sobre una nueva base SYNTHETIC_ONLY.
- Este documento.

Se amplía [cli.py](cli.py) y se actualizan las referencias de README.md,
READER.md y NARRATIVE.md. Se conserva íntegra la implementación del Hito 3
que ya estaba sin commit al comenzar este hito. No se modifican lector,
detector, generación, contrato narrativo ni reglas de memoria.
No se instalaron dependencias ni se modificaron Git, ramas o configuración
global de Windows/Codex.

## Configuración local del secreto

Desde una terminal PowerShell local situada en la raíz del proyecto:

    python -B -m forum_watch configure-discord

El programa pide la URL con entrada oculta mediante getpass. No se proporciona
por argumentos, chat, variables de entorno ni archivos del proyecto.
Se admite un webhook estándar HTTPS de discord.com, con ruta
/api/webhooks/ID/TOKEN o /api/v10/webhooks/ID/TOKEN, sin query, fragmentos,
otro host, destino de hilo o credenciales URL adicionales.
No se admiten canales que requieran crear o desarchivar hilos.

La respuesta correcta es DISCORD_SECRET_CONFIGURED, con
storage=WINDOWS_DPAPI_CURRENT_USER y message_sent=false. El comando configura;
no manda una notificación. La alternativa PowerShell llama al mismo comando:

    & '.\scripts\set-discord-secret.ps1'

Si PowerShell bloquea scripts, usar directamente el comando Python; no hace
falta cambiar la política de ejecución ni ejecutar como administrador.

El archivo operativo es:

    %LOCALAPPDATA%\NozomuForumWatch\secrets\discord-webhook.dpapi

Solo contiene el blob cifrado de Windows. Se escribe de forma atómica mediante
un temporal también cifrado. No se guarda una copia en claro, contraseña
maestra, clave DPAPI ni token en SQLite o en el repositorio.
La [API DPAPI de Windows](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
protege los datos para las credenciales del usuario que los cifra; el código
no utiliza el indicador LOCAL_MACHINE que permitiría descifrar a otros usuarios.
La operación de descifrado se limita al notificador explícito.

La prueba real de almacenamiento cifró y descifró un valor sintético,
comprobó que no estaba en claro en el archivo y eliminó su propio temporal.
No leyó el secreto de producción. La primera opción, CredWriteW, había
devuelto el error Windows 8; se sustituyó por DPAPI tras validar esta alternativa.
No se alteró el Administrador de credenciales ni se dejó un respaldo en claro.

Lector, narrador y capturas no importan ni llaman al descifrador. Preparar o
consultar avisos tampoco accede al secreto. El narrador conserva sus capacidades
restringidas del Hito 3. Esta separación controla el flujo de la aplicación;
DPAPI no es una barrera contra cualquier programa arbitrario ejecutado con
las mismas credenciales del usuario. La URL existe transitoriamente en la
memoria del proceso que configura/envía, pero no se imprime ni se registra.

## Fuentes y contenido de las notificaciones

El notificador consume registros ya confirmados en SQLite:

| Fuente persistida | Identidad del evento | Aviso |
| --- | --- | --- |
| evaluation_runs completado | evaluation:run_id | DRAFT_READY, NEEDS_HUMAN_REVIEW, COMBAT_REVIEW_REQUIRED o GENERATION_FAILED. |
| narrative_drafts con stale_reason | draft:draft_id:STALE | STALE, incluso si después se retiró el borrador. |
| import_errors con código conocido | reader-error:id | SESSION_EXPIRED, ACCESS_DENIED o revisión humana. |

No se usan los textos del modelo como órdenes. No se invoca a lectores,
modelos o especialistas para construir un aviso. No se consulta el texto del
post, del borrador, del prompt o del error; se proyectan únicamente metadatos
de título/autor, tipo, ID de tema y número de cambios de la evaluación.

Los códigos persistidos SESSION_EXPIRED y ACCESS_DENIED tienen avisos propios.
WRONG_ACCOUNT también produce ACCESS_DENIED. El lector existente puede
registrar SESSION_UNVERIFIABLE o HTTP_READ_FAILED sin acreditar la causa:
se notifican como NEEDS_HUMAN_REVIEW, sin inventar una sesión caducada,
CAPTCHA o denegación concreta.

NO_RESPONSE_NEEDED, WAIT_FOR_TURN, NO_RELEVANT_CHANGES y BASELINE no generan
avisos. Varios cambios de una misma evaluación se agrupan en una notificación
con su contador; no se envía un mensaje por cada cambio. No se agrupan
arbitrariamente decisiones independientes.

Ejemplo de aviso:

    Nozomu — Borrador preparado

    Tema: Título observado
    Autor de la actualización: Nombre observado
    Estado: Pendiente de revisión
    Tema: <https://narutorol.jcink.net/index.php?showtopic=275>

    No se ha publicado ningún mensaje en Naruto Rol.

El nombre observado es una etiqueta del foro, no conocimiento IC.
Los títulos/autores se limitan, se neutralizan controles y Markdown, y se
omiten URLs/rutas incluidas en esos campos. No se modifica el contenido
narrativo de las capturas o borradores almacenados.

El payload solo contiene content, allowed_mentions con parse vacío y flags=4
para suprimir vistas previas. No hay uploads, embeds narrativos, username,
avatar, botones, comandos o destinos derivados del foro. Todas las bases
sintéticas añaden PRUEBA / DATOS SINTÉTICOS, salvo el mensaje fijo de conexión
que reproduce literalmente el texto solicitado, incluido «Nozumo».

La [documentación del webhook](https://docs.discord.com/developers/resources/webhook)
establece el máximo de 2.000 caracteres y permite restringir las menciones.
Aquí se comprueba además el tamaño en unidades UTF-16, de forma conservadora
para emoji. Se usan POST y wait=true para obtener la confirmación y el ID
del mensaje remoto. No se siguen redirects, Location ni otras URLs devueltas.

## Entrega y reintentos

La misma base operativa añade notification_meta (versión 1), notifications
y notification_attempts. No cambia el esquema/origen de capturas ni las
tablas de evaluación existentes.

Cada notificación tiene notification_id propio, source_event_id único,
topic_id, tipo, created_at, attempt_count, last_attempt_at, estado,
remote_message_id, last_error resumido, next_attempt_at y delivery_uncertain.
El historial de intentos conserva sus estados y horas. Los avisos se
identifican por evento dentro de su base; no deben enviarse copias independientes
de una misma base como si fueran nuevos orígenes.

Estados: PENDING, SENDING, SENT, FAILED_RETRYABLE y FAILED_FINAL.
SUPERSEDED indica que el aviso DRAFT_READY quedó obsoleto antes de enviarse;
no es un error de Discord. Justo antes de enviarlo se comprueba que su borrador
sigue ACTIVE. STALE tiene un aviso propio. Si el contexto cambia mientras
Discord ya está procesando el POST, su aviso posterior de STALE se preparará
en la siguiente orden manual; no se edita el mensaje remoto.

SENDING se confirma en SQLite antes del intento. Un reinicio no repite SENT.
Un SENDING abandonado termina FAILED_FINAL con INTERRUPTED_UNCERTAIN y
requiere comprobar Discord; no se reenvía automáticamente. No se declara
una garantía de entrega «exactamente una vez» frente a cortes entre Discord
y SQLite, porque el webhook no ofrece una clave de idempotencia del cliente.

| Resultado | Tratamiento |
| --- | --- |
| 2xx con ID de mensaje válido | SENT; solo se conserva el ID, nunca el cuerpo completo recibido. |
| Conexión fallida antes de enviar HTTP | FAILED_RETRYABLE, con backoff. |
| HTTP 429 | FAILED_RETRYABLE, respetando Retry-After/retry_after. |
| 400/401/403/404, webhook mal configurado, TLS o redirect | FAILED_FINAL; se detiene el lote y se conserva el resto pendiente. |
| Timeout/error después de conectar, 5xx, confirmación ausente o corte en SENDING | Resultado incierto; FAILED_FINAL y sin reenvío automático. |

Se elige una estrategia conservadora también para 5xx: una respuesta del
intermediario no demuestra que la creación del mensaje se haya revertido.
Un fallo del transporte nunca borra/regenera un borrador ni revierte una
captura o escribe memoria. Los errores guardados son códigos locales breves;
no se interpolan excepciones ni cuerpos de Discord que puedan contener la URL.

Timeout de socket: 15 segundos. Hasta tres intentos totales por notificación.
Cada orden manual intenta una vez cada aviso elegible, con un lote limitado
a 10 por defecto y máximo 20. No hay esperas en bucle ni reintentos periódicos:
el siguiente intento necesita otra orden manual y que llegue su plazo.
Backoff mínimo de 2 y 4 segundos, ampliado por la espera indicada por Discord.

Los [límites de Discord](https://docs.discord.com/developers/topics/rate-limits)
se respetan mediante Retry-After/retry_after y X-RateLimit-Reset-After cuando
Remaining es cero. Un checkpoint común, fuera del proyecto, conserva la
espera entre órdenes y bases; un bloqueo del sistema operativo impide envíos
concurrentes al único webhook configurado para este usuario:

    %LOCALAPPDATA%\NozomuForumWatch\discord-delivery\

Si un fallo de configuración está resuelto, retry-notification permite
reabrirlo explícitamente cuando la no entrega es conocida y quedan intentos.
Conserva el contador/historial. Rechaza entregas inciertas y SENT; no equivale
a autorizar un duplicado. Los eventos y errores finales siguen consultables.

## Comandos de operación manual

Desde la raíz. Preparación/inspección no envían ni leen el secreto:

    $watchRoot = Join-Path $env:LOCALAPPDATA 'NozomuForumWatch'
    $watchDb = Join-Path $watchRoot 'forum-watch-real.sqlite3'

    python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY queue-notifications
    python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY notifications --preview

Envío explícito de un lote:

    python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY notify --limit 10

No abre navegador, no obtiene capturas nuevas y no cambia PAUSED.
Antes de utilizarlo con datos reales se puede revisar el payload con --preview.
La prueba de este hito utiliza otra base; estos comandos de base real se
documentan como uso, no como envíos reales ya efectuados.

Tras corregir un fallo definitivo de configuración, usando su ID local:

    python -B -m forum_watch --db "$watchDb" --storage-mode AUTHENTICATED_ONLY retry-notification "<notification_id>"

Una orden notify devuelve código 2 si un intento termina FAILED_*, 0 para
envíos válidos o espera sin intento. Los errores de uso/locales conservan
los códigos de la CLI. La consulta notifications muestra el estado persistido.

## Pruebas realizadas

    python -B -m unittest discover -s tests -q
    & '.\.venv-forum-watch\Scripts\python.exe' -B tests/reader_dom_smoke.py
    python -B tests/discord_vault_smoke.py
    git diff --check

Regresión inicial: **101/101**, más **5/5** selectores con Edge temporal y red
bloqueada. Suite final: **142/142**, con las 101 anteriores y 41 nuevas
(37 de notificaciones/transporte y cuatro de la demostración por fases).
La suite ampliada incluye los 18 casos requeridos, más reinicio SENDING,
entrega incierta, vigencia antes de enviar, cooldown entre bases, bloqueo
concurrente, ausencia de lectura del secreto durante preview, protección de
argumentos, límites Unicode, recuperación explícita de configuración y las
dos fases sintéticas sin duplicación. Las pruebas automáticas usan transporte
simulado y no requieren Discord, credenciales, navegador ni llamada al modelo.

La prueba DPAPI manual usa exclusivamente un valor sintético. Devuelve
DPAPI_CANARY_OK, read_matches_synthetic_value=true,
file_contains_no_plaintext=true y own_test_directory_removed=true.
El secreto de producción no se consultó durante esta comprobación.

## Prueba real controlada

Se reservó esta carpeta externa, sin utilizar la base real ni mensajes reales:

    %LOCALAPPDATA%\NozomuForumWatch\hito4-discord-manual-20260913-01\

La fase connection se preparó sin enviar. Contenido exacto:

    Nozumo Forum Watch — prueba de notificación.

    La conexión con Discord funciona.
    No se ha publicado ningún mensaje en Naruto Rol.

Después de configurar localmente el secreto:

    $discordDemo = Join-Path $watchRoot 'hito4-discord-manual-20260913-01'
    python -B tests/discord_manual_smoke.py --output-root "$discordDemo" --stage connection
    python -B tests/discord_manual_smoke.py --output-root "$discordDemo" --stage pipeline --prepare-only
    python -B tests/discord_manual_smoke.py --output-root "$discordDemo" --stage pipeline

La segunda fase exige que la primera conste SENT. Crea capturas sintéticas,
pasa por la evaluación existente con una salida sintética explícita
(sin invocar a Codex), conserva un borrador PENDING_HUMAN_REVIEW y consume
su evento DRAFT_READY. El aviso está marcado PRUEBA / DATOS SINTÉTICOS y no
incluye el borrador. No se inventa una novedad en la base AUTHENTICATED_ONLY.

Repetir una fase ya SENT devuelve ALREADY_SENT y cero intentos.
Los archivos connection-report.json y pipeline-report.json conservan estado,
ID local, ID remoto y contador, sin webhook. Las vistas previas quedan
separadas en archivos con sufijo -preview.

El usuario confirmó DISCORD_SECRET_CONFIGURED en su terminal. La ejecución
real posterior obtuvo estas confirmaciones, sin mostrar el secreto:

| Prueba | notification_id | ID remoto | Estado / intentos |
| --- | --- | --- | --- |
| Conexión | f30eb6be78c94dbd841d5f6cef0dc878 | 1548639181813719101 | SENT / 1 |
| DRAFT_READY sintético | 02747cf8406d418587fae64df8d5f8cd | 1548639270330441790 | SENT / 1 |

La segunda notificación deriva de
evaluation:856b77784b74468f8ef846c51115dd1a. Ambas confirmaciones proceden
del endpoint del webhook con wait=true; no se abrió la interfaz de Discord.
No hubo reintentos reales ni mensajes adicionales. Los casos de error,
rate limit y reinicio se provocaron únicamente con transporte simulado.

## Estado y preservación

Se mantiene PAUSED en el tema 275. Se contrastaron los hashes iniciales de
AGENTS.md, instructions/, reference/, shared/, memory/, drafts/, .codex/,
los borradores operativos preexistentes y la SQLite real. Las demostraciones
escriben únicamente en una nueva ubicación operativa sintética.

Resultado final: **56/56 hashes idénticos**, ninguno eliminado: 53 archivos
canónicos/protegidos, dos borradores operativos anteriores y la base real.
Ambas bases dieron integrity_check=ok y cero errores de claves foráneas.
La base real conserva sus dos capturas AUTHENTICATED_FORUM. La de prueba
contiene dos capturas SYNTHETIC, un borrador ACTIVE/PENDING_HUMAN_REVIEW y
dos notificaciones SENT con exactamente dos registros de intento.
Los enlaces documentales existen y git diff --check pasó; únicamente se
observó el aviso habitual de Git sobre LF/CRLF.

Discord: **CONECTADO PARA AVISOS MANUALES**.
Seguimiento periódico: NO ACTIVADO.
Publicación: NO IMPLEMENTADA.
Aprobación desde Discord: NO IMPLEMENTADA.
Memoria automática: DESACTIVADA.
