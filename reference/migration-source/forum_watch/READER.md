# Hito 2 — lector autenticado manual del tema 275

**LECTOR IMPLEMENTADO Y VALIDADO EN PRUEBA MANUAL**, 2026-09-13.

Este documento conserva la evidencia y el alcance del Hito 2. La ampliación
posterior de evaluación manual está en [NARRATIVE.md](NARRATIVE.md).
La orquestación y el estado vigente del seguimiento están en [WORKFLOW.md](WORKFLOW.md).

El usuario completó el login manual. Dos lecturas reales verificaron la cuenta
59 y leyeron una página con tres publicaciones. La primera estableció BASELINE;
la segunda dio NO_RELEVANT_CHANGES. Al cerrar ese hito, el tema quedó PAUSED,
sin evaluación narrativa ni vínculo con muelle-nozomu-arashi.

## Archivos y extensión mínima

Modificados: AGENTS.md, forum_watch/README.md, forum_watch/cli.py,
forum_watch/models.py y forum_watch/store.py.

Creados: .gitignore, forum_watch/READER.md, forum_watch/browser.py,
forum_watch/adapter.py, forum_watch/reader.py,
forum_watch/requirements-reader.txt, tests/test_reader_bootstrap.py,
tests/test_forum_reader.py, tests/reader_dom_smoke.py y
tests/fixtures/topic275-derived.json.

El entorno .venv-forum-watch/ queda excluido de Git. No se inicializó Git ni
se hicieron commits, cambios de rama, push o limpieza del repositorio.

Se reutilizan Capture, la normalización y Store._accept_capture: mismas tablas,
revisiones, comparación y transacción del Hito 1. La base sintética conserva
esquema 1 y origen exclusivo SYNTHETIC. La nueva base real usa esquema 2,
modo AUTHENTICATED_ONLY y restricción SQL de origen AUTHENTICATED_FORUM.
La extensión del esquema solo cambia el origen admitido; los metadatos de
ejecución se guardan en captures.source_json.metadata.

El modo se selecciona explícitamente al abrir; no hay migración ni adopción
automática de una base. import y los JSON externos siguen siendo sintéticos.
Store.read_once obtiene una lectura nueva del navegador y la entrega a la
misma transacción. Un JSON con account_id=59 no habilita la ingesta real.
Las funciones internas Python no son una frontera frente a quien modifique
o ejecute código arbitrario dentro del proceso.

## Entorno comprobado

| Componente | Versión utilizada |
| --- | --- |
| Python AMD64 | 3.14.7 |
| Windows | 10, build 19045 |
| Edge existente, canal msedge | 153.0.4234.32 |
| playwright | 1.62.0 |
| greenlet | 3.5.5 |
| pyee | 13.0.1 |
| typing-extensions | 4.16.0 |

Dependencias instaladas únicamente en .venv-forum-watch. pip check devolvió
“No broken requirements found.” No hubo instalación global ni descarga o
reemplazo de navegadores.

La [documentación de Playwright](https://playwright.dev/python/docs/intro#system-requirements)
enumera Windows 11 o posterior. La prueba demuestra funcionamiento en esta
combinación de Windows 10, sin atribuirle soporte oficial. Se usa el
[Edge instalado](https://playwright.dev/python/docs/browsers#google-chrome--microsoft-edge).

Dentro del sandbox de Codex, pip falló con WinError 10013 y Edge agotó 30
segundos con errores de acceso/cifrado. Funcionaron fuera del sandbox, sin
cambiar configuración global ni ejecutar Edge como administrador de Windows.

## Comandos reproducibles en PowerShell

Desde la raíz del proyecto. Si aún no existe el entorno:

    python -B -m venv .venv-forum-watch
    & '.\.venv-forum-watch\Scripts\python.exe' -B -m pip --isolated install -r forum_watch/requirements-reader.txt --only-binary=:all: --index-url https://pypi.org/simple --no-cache-dir --disable-pip-version-check --retries 0 --timeout 30
    & '.\.venv-forum-watch\Scripts\python.exe' -B -m pip check

No ejecutar playwright install ni playwright install msedge. No hace falta
activar el entorno ni modificar la política de ejecución de PowerShell.

Rutas usadas realmente:

    $readerRoot = Join-Path $env:LOCALAPPDATA 'NozomuForumWatch'
    $readerProfile = Join-Path $readerRoot 'edge-profile'
    $readerDb = Join-Path $readerRoot 'forum-watch-real.sqlite3'
    $readerTopic = 'https://narutorol.jcink.net/index.php?showtopic=275&st=0#entry1144'

Login manual, solo cuando haga falta iniciar o renovar la sesión:

    & '.\.venv-forum-watch\Scripts\python.exe' -B -m forum_watch login --profile "$readerProfile" --timeout-seconds 1200

El usuario introduce las credenciales en la ventana dedicada y la cierra.
El comando devuelve LOGIN_WINDOW_CLOSED, NOT_VERIFIED, cero mensajes y cero
importaciones. No se automatizan formularios. No visitar privados, otros
temas, perfiles ni controles de cuenta. Si Codex no muestra la ventana,
ejecutar el mismo comando en una terminal local.

Preparación del registro; si existe conserva su estado y URL original:

    & '.\.venv-forum-watch\Scripts\python.exe' -B -m forum_watch --db "$readerDb" --storage-mode AUTHENTICATED_ONLY add "$readerTopic"

Lectura explícita. Se ejecutó dos veces para la prueba real:

    & '.\.venv-forum-watch\Scripts\python.exe' -B -m forum_watch --db "$readerDb" --storage-mode AUTHENTICATED_ONLY read-once --profile "$readerProfile" --max-pages 20 --time-budget-seconds 180

Consulta operativa sin navegador:

    & '.\.venv-forum-watch\Scripts\python.exe' -B -m forum_watch --db "$readerDb" --storage-mode AUTHENTICATED_ONLY inspect "$readerTopic"
    & '.\.venv-forum-watch\Scripts\python.exe' -B -m forum_watch --db "$readerDb" --storage-mode AUTHENTICATED_ONLY captures "$readerTopic"
    & '.\.venv-forum-watch\Scripts\python.exe' -B -m forum_watch --db "$readerDb" --storage-mode AUTHENTICATED_ONLY pending "$readerTopic"

inspect mantiene NOT_VERIFIED como identidad actual: consultar registros
pasados no acredita que la sesión siga vigente. Cada captura conserva su
propia evidencia y momento.

Perfil y base reales: C:\Users\neko_\AppData\Local\NozomuForumWatch\, fuera
del proyecto y de su carpeta narrativa. Nunca se copia el perfil personal.
Se rechaza un directorio no vacío sin la marca propia. Un bloqueo de archivo
impide dos ejecuciones sobre el perfil; no se cierran otros procesos de Edge.

## Identidad y adaptación observadas

Antes de extraer cada página se exige un único contenedor
“#wrapper > .header > #userlinks”, texto “Logged in as:”, un único enlace
“strong > a” con destino de perfil válido de la cuenta 59 y un único control
con texto “Log Out”. El enlace de salida no se exporta ni pulsa.
No se abre showuser=59 ni se buscan coincidencias en los posts.
La evidencia registra cuenta esperada, observada, método y hora UTC.
Cuenta incorrecta, invitado, desafío, sesión caducada o señal desconocida
detienen la extracción y requieren intervención manual, sin bucles.

Se observaron “#innerwrapper > .tableborder”, título en
“.maintitle > .topic-title” y posts directos “.postarea”.
Autor: “.posttop > .posttopinner > .posttopleft > .postname > a”.
Cuerpo: “.postmid > .postmidleft > .postmidleft2 > div[id^=pid_] > .postcolor”.
Se comprueba el ID frente al ancla entry... del bloque de fecha
“.postmidleft1 > .postmidleft1a”. La firma observada está fuera de .postcolor.
Se excluyen perfiles laterales, menús, formularios y contadores.

Se preservan párrafos, saltos, diálogos, citas y atribuciones textuales,
contenido oculto por CSS y spoilers. blockquote, details y summary conservan
delimitadores textuales. Los enlaces se guardan como datos inertes y nunca
dirigen la navegación. No se elimina texto por palabras como “firma”.

Las fechas relativas se conservan como representación visible; date_iso es
nulo. No hubo una marca DOM de edición verificable: edit_indicator queda
nulo, mientras que las ediciones se detectan por versiones y hashes.
El título observado queda en la captura, sin aprobar metadatos narrativos.

## Navegación, completitud y limitaciones

Solo documentos GET de HTTPS narutorol.jcink.net/index.php, tema 275 y
parámetros showtopic/st. Se comprueban destino final y redirecciones.
Se bloquean otros documentos, frames, POST, scripts del sitio, imágenes,
adjuntos y recursos externos. Solo se permiten CSS/fuentes del mismo host
por tipo/extensión, sin query ni fragmento. La prueba funcionó sin recursos
estáticos externos.

No se pulsa ningún control de cuenta o tema. No hay trazas, HAR, vídeo,
capturas de pantalla, exportaciones de cookies, cabeceras, formularios ni
almacenamiento web. No se guarda HTML autenticado completo. Las proyecciones
DOM se limitan a la sesión saneada y datos del tema; el contenido operativo
real solo se persiste en la base externa.

La muestra real tenía una página: celdas superior e inferior vacías al excluir
los botones observados. Se admiten también listas completas de enlaces
numéricos explícitos en esas celdas, comprobadas con fixtures locales.
**No hubo muestra real multipágina.** Paginadores truncados, puntos suspensivos,
destinos ambiguos o estructura desconocida provocan rechazo. No se inventan
offsets. entry1144 no es cursor.

Por defecto: 20 páginas como máximo, 180 segundos de lectura y hasta 30
segundos por navegación. Se recorre el conjunto completo y después cada página
en orden inverso. Se comprueban paginación, título, IDs, orden, autoría, fechas
y contenido. Una inconsistencia permite como máximo una repetición completa,
compartiendo presupuestos; si persiste, se conserva el estado válido previo y
se registra el error. Dos barridos coincidentes son consistencia observable,
**no una captura atómica del foro**.

Se observó #topic_open y se registra OPEN_CONTROL_PRESENT; su ausencia da
UNKNOWN, no un cierre inventado. No se obtuvo muestra real de tema cerrado,
CAPTCHA o error. Las páginas sin estructura verificable se rechazan; los
fallos se simulan localmente. Medios, contenido activo o etiquetas no
soportadas dentro del post provocan UNEXTRACTABLE_CONTENT; no se siguen
adjuntos para completar pérdidas.

La transacción conserva el estado válido ante desapariciones de posts,
cambios de autor/orden o fallos SQL. BASELINE no crea pendientes históricos.
Otra captura idéntica añade una observación, sin duplicar revisiones.
Última captura, último mensaje observado y last_processed_message_id son
distintos; este último permanece nulo porque no hubo evaluación.

## Pruebas y resultados

    python -B -m unittest discover -s tests -v
    & '.\.venv-forum-watch\Scripts\python.exe' -B tests/reader_dom_smoke.py

- Regresión inicial: **38/38** pruebas del Hito 1.
- Suite sin Playwright ni sesión de navegador: **71/71**. Conserva las 38 y
  añade 12 de arranque/perfil y 21 de identidad, lectura y BD real simulada.
  Incluye rollback SQL tras escrituras y ausencia de avance tras fallos.
- Selectores en Edge temporal, red bloqueada y HTML local sustituido: **5/5**.
  Perfil falso en post, cuenta equivocada, pantalla sustitutiva, extracción
  de citas/spoilers/firma y paginación numérica. Sin perfil autenticado.
- pip check y git diff --check correctos. Git avisa de su política LF/CRLF
  al leer los cambios, sin errores de espacios.

Fixtures saneadas con contenido sustituido. Multipágina y fallos son
simulaciones; no se provocaron modificando el foro. Durante el desarrollo una
prueba falló por un plazo infinito del doble de navegador; se corrigió el
cálculo acotado del timeout y la suite completa quedó correcta.

| Ejecución | Hora UTC del 2026-09-13 | Resultado | Páginas / posts | Nuevos / ediciones |
| --- | --- | --- | --- | --- |
| read-22319186636c4169a54a4c4205e3ba13 | 00:43:06.588168 | BASELINE | 1 / 3 | 0 / 0 |
| read-2364c105eb894e98b389c8a4700025d0 | 00:43:41.211009 | NO_RELEVANT_CHANGES | 1 / 3 | 0 / 0 |

Cada ejecución hizo dos observaciones y verificaciones de cuenta 59, en un
intento. IDs observados: 1120, 1140 y 1144. El último proviene del orden leído.

Verificación SQLite posterior de solo lectura: integrity_check=ok, cero
errores de claves foráneas, 2 capturas, 3 mensajes, 3 revisiones, 0 pendientes,
0 errores de importación. Estado PAUSED; título, participantes, clasificación,
vínculo de memoria y último mensaje procesado nulos. La demostración sintética
del Hito 1 no se migró ni se reutilizó.

## Preservación y excepción autorizada

La comparación SHA-256 de 53 archivos protegidos iniciales mostró 52
idénticos y únicamente AGENTS.md modificado. Se conservaron .codex/,
reference/, shared/, memory/, instrucciones y borradores; no hubo
consolidaciones narrativas.

Diff exacto de AGENTS.md:

```diff
diff --git a/AGENTS.md b/AGENTS.md
index 9da7b06..2428200 100644
--- a/AGENTS.md
+++ b/AGENTS.md
@@ -20,6 +20,8 @@ Si no están disponibles, dilo expresamente y no simules haberlos invocado. Pued
 6. Consolida hechos sustentados, preservando pendientes. Aprobar un borrador no equivale a publicarlo. Un ataque publicado no equivale a un impacto confirmado.
 No publiques en el foro, no envíes mensajes ni accedas a cuentas en este flujo.
 
+Excepción de lectura autorizada para el Hito 2: únicamente el lector determinista de `forum_watch/` puede abrir un perfil de navegador dedicado para login manual del usuario, verificar en esa ejecución la cuenta conectada 59 y leer el tema 275 de `narutorol.jcink.net` con su paginación, guardando los datos operativos fuera del árbol del personaje. Esta excepción no habilita navegación general del agente narrativo, otros temas o perfiles, mensajes privados, publicaciones, ediciones, eliminaciones, suscripciones ni cambios voluntarios de la cuenta. Leer puede actualizar indicadores propios del foro; no se automatizan acciones explícitas para modificarlos. Se mantienen la revisión humana y las demás restricciones.
+
 ## Persistencia
 Sigue instructions/memoria.md. Actualiza índice, entidades y estado desde el mismo evento fuente. Antes de escribir revisa el estado actual y evita duplicados por tema+turno+autor. Conserva revisiones anteriores; corrige por anotación, sin borrar el original. No guardes suposiciones como hechos.
 Antes de terminar una consolidación comprueba que cada afirmación tiene fuente y que los enlaces locales existen.
```

Leer puede actualizar indicadores de actividad o lectura del foro. No se
implementan acciones explícitas para alterarlos.

Al cierre del Hito 2, generación narrativa: **DESACTIVADA**. El Hito 3 añade
su invocación manual aislada, sin enlazarla automáticamente a `read-once`.
Discord al cierre de este hito: **NO CONECTADO**. La ampliación posterior
de avisos manuales se describe en [DISCORD.md](DISCORD.md).
Programación cada cuatro horas: **NO ACTIVADA**. Publicación: **NO IMPLEMENTADA**.
