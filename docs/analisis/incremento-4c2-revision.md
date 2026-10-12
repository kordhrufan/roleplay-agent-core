# Revisión 4c2 — instancia cerrada e instrucciones generadas

## Versión y veredicto

- Rama revisada: `feature/incremento-4-rebanada-vertical`.
- Base: `8e3185c`; cambios sin commit descritos en el encargo.
- Veredicto inicial: **NO APROBADO**. La forma persistida, las plantillas actuales, el filtrado del corpus y
  la recarga sin workspace son correctos, pero hay dos incumplimientos de seguridad/atomicidad y
  uno de recarga estricta reproducidos. La suite de 4c2 no los detecta.
- Primera verificación de correcciones: **NO APROBADO, un pendiente**. REV4C2-01, REV4C2-03 y REV4C2-04
  están resueltos; REV4C2-02 está resuelto para las carreras reproducidas y para Windows, pero
  conserva una ventana POSIX que aún contradice el criterio de no sobrescribir al ganador.
- Verificación final: **APROBADO**. REV4C2-02 queda resuelto al rechazar conservadoramente toda
  creación de workspaces e instancias fuera de Windows, antes de escribir, sin impedir carga ni
  consulta en otras plataformas.

## Defectos

### REV4C2-01 — Alta — `core/runtime/instance.py:305`, `core/runtime/instance.py:430`

**Problema y condición.** La creación y la recarga comprueban con `_is_link` únicamente el
`target`/`physical` final. No rechazan una symlink o junction en un componente padre, pese al
contrato de rechazar enlaces en cada componente. En creación, una junction padre puede redirigir el
staging y el destino después de la comprobación de solapes; en recarga, la misma ruta indirecta se
acepta porque `_identity` resuelve el enlace.

**Evidencia.** En un temporal externo de Windows se creó `parent-junction -> parent-real` y se pidió
crear `parent-junction/instancia`. `create_instance` terminó con éxito, la recarga interna también,
y `instance.json` guardó `parent-real/instancia` mientras `LoadedInstance.instance_root` devolvió la
ruta por la junction. `test_junction_destination` solo cubre que el destino final sea una junction,
no que lo sea uno de sus padres.

**Criterio de resolución.** Tanto creación como recarga deben rechazar con el código previsto toda
symlink/junction en cada componente existente de la ruta, incluidos padres, antes de leer o escribir;
la comprobación debe repetirse donde sea necesario para no reabrir una redirección durante la
publicación. Añadir tests con junction padre para `init` y `load_instance`, comprobando que no se
escribe en el destino real.

### REV4C2-02 — Alta — `core/runtime/instance.py:386-403`

**Problema y condición.** `_materialize` no conserva el estado inicial del destino. Si estaba
ausente al validarlo pero otro actor crea una carpeta vacía antes de publicar, el código la considera
un destino vacío legítimo, ejecuta `rmdir()` y publica encima. Por tanto pisa al ganador de esa
carrera en vez de devolver `CONFLICT`; también pierde sus metadatos/ACL. El mismo hueco impide
distinguir que una carpeta inicialmente vacía fue sustituida por otra vacía.

**Evidencia.** En un temporal externo se inyectó la creación de `output` vacío al terminar la segunda
`_read_source`. `create_instance` eliminó esa carpeta y devolvió `created=True` con la instancia
publicada. `test_races` solo crea contenido extranjero justo dentro de `os.replace`; no cubre la
transición ausente→vacío ni la sustitución vacío→vacío.

**Criterio de resolución.** Registrar y comprobar la identidad/estado inicial del destino y hacer
que cualquier transición o sustitución dé `CONFLICT` sin borrar ni alterar el árbol ganador. La
publicación tampoco debe reemplazar un destino aparecido en la última ventana de carrera en ningún
sistema soportado. Añadir pruebas deterministas de ausente→vacío, vacío sustituido y ganador
idéntico/distinto, verificando contenido y metadatos preservados en los casos conflictivos.

### REV4C2-03 — Media — `core/runtime/instance.py:477-485`

**Problema y condición.** El recorrido de `dossier/`, `corpus/` y `work/` solo contrasta pertenencia
para entradas que estén en `files`; los directorios se revisan únicamente para saber si son enlaces.
Así, uno o varios directorios extra vacíos pasan la recarga, contra el layout exacto y el rechazo de
todo extra.

**Evidencia.** Tras crear una instancia íntegra en un temporal externo se añadió
`dossier/vacio-extra/`; `load_instance(..., expected_core_root=ROOT)` la aceptó. La prueba
`test_extra_files_are_rejected` solo añade archivos extra.

**Criterio de resolución.** Validar el árbol completo, incluidos directorios, contra el conjunto
exacto de directorios implícitos por los archivos gestionados y los tres directorios raíz. Añadir
casos de directorio vacío extra bajo cada raíz gestionada y de anidamiento vacío.

### REV4C2-04 — Baja — `tests/test_instance_templates.py:38-63`, `tests/test_instance_cli.py:91-199`

**Problema y condición.** Los tests no fijan todo el contrato que el plan exige como exacto. Las
plantillas se comprueban mediante fragmentos, número de viñetas y semejanza entre AGENTS/CLAUDE, no
contra los cuatro contenidos completos independientes; varias salidas CLI se validan con regex,
`json.loads`, conjuntos de claves o fragmentos, perdiendo orden, escaping ASCII y bytes exactos. Un
cambio de redacción común que conserve esos fragmentos, o una desviación de serialización/salida,
puede quedar verde.

**Evidencia.** La inspección de los asserts muestra que no existe una constante esperada completa
para cada plantilla ni comparación byte a byte de todas las salidas nuevas. Además, los tres
defectos anteriores fueron reproducidos con las 40 pruebas de 4c2 en verde.

**Criterio de resolución.** Incorporar expectativas completas e independientes para los cuatro
archivos y comparar sus bytes, incluidos LF final y el bloque común; para CLI, comparar las salidas
representativas completas (texto y JSON serializado), además de conservar casos semánticos. Añadir
las regresiones REV4C2-01 a REV4C2-03.

## Contraste de los criterios y preguntas

1. **Plantillas:** los cuatro archivos actuales coinciden byte a byte con los cuatro bloques de
   `ANALISIS.md`; son UTF-8 sin BOM, solo LF y con newline final. El bloque común renderizado es la
   política exacta, las rutas PowerShell van entre comillas simples y `_powershell` duplica `'`.
   No aparecen nonce, bypass ni comandos futuros. REV4C2-04 afecta a la protección frente a
   regresiones, no al contenido actual.
2. **Creación:** exige y vuelve a validar cierre, estado, expediente y ausencia de lock; copia todos
   los archivos declarados y el sobre completo sin guardar la ruta del workspace; compara las tres
   fuentes de bytes entre lecturas y el retry idéntico no reescribe. No cumple por completo la
   seguridad/atomicidad debido a REV4C2-01 y REV4C2-02.
3. **Recarga:** detecta cambios de bytes gestionados, archivos extra, movimientos, identidad de
   instancia/checkout y divergencia al volver a renderizar instrucciones; funciona tras borrar el
   workspace. No rechaza todo árbol extra por REV4C2-03, ni todos los componentes enlazados por
   REV4C2-01.
4. **Corpus aprobado:** `approved_corpus` recorre solo versiones vigentes y conserva exclusivamente
   decisiones `APPROVED`; `get_approved_candidate` exige la clave exacta. Pendientes, rechazadas y
   sustituidas no salen por API ni CLI, y `UNCERTAINTY` conserva
   `requires_confirmation=True`/`REQUIERE CONFIRMACIÓN`.
5. **Desviaciones anotadas:** reutilizar auxiliares privados no es un defecto por sí solo, pero no
   cubre el contrato de componentes padre (REV4C2-01) y crea acoplamiento privado que habrá que
   mantener conscientemente. Hacer pública `render_instructions` no altera la seguridad porque la
   recarga usa plantillas fijas, aunque amplía la superficie más allá de las cuatro firmas pedidas.
   Guardar la capitalización real y comparar por identidad normalizada es coherente con el contrato.
   Los dos ajustes de tests 4a/4b son necesarios al existir ya `instance`. La única coincidencia de
   `rg` está en la lista negativa del propio test y no constituye contenido temático.
6. **Tests:** cubren bien cierre, copia, hashes, consultas y casos básicos de carreras/manipulación,
   pero no fallan ante las regresiones reproducidas ni fijan por completo los contratos exactos;
   véanse REV4C2-01 a REV4C2-04.

## Verificación realizada

- `py -3.14 -B -m unittest tests.test_instance tests.test_instance_templates tests.test_instance_cli -v`:
  **40 OK**, 0 omitidos.
- Comparación dirigida de los cuatro archivos de plantilla con los bloques 4c2 de `ANALISIS.md`:
  **4/4 idénticos**, formato correcto.
- Temporales externos: junction padre aceptada; carrera ausente→vacío pisada; directorio extra vacío
  aceptado. Los tres casos fueron limpiados.
- `git diff --check`: sin errores de whitespace (solo avisos de conversión LF→CRLF de Git).
- `git diff --name-only 8e3185c -- reference`: sin salida.
- `rg` de nombres prohibidos: solo las dos líneas de la lista negativa en
  `tests/test_instance_templates.py`.

Limitaciones: Python 3.11 no está instalado en este entorno (`py -0p` solo ofrece 3.14), por lo que
no repetí esa ejecución ni la suite completa de 335 tests; tomo sus resultados aportados como
antecedente, no como verificación propia. Pude crear junctions de Windows, pero no probé una symlink
real adicional; la junction padre basta para reproducir el incumplimiento de componentes enlazados.

## Verificación de correcciones — 2026-10-12

Versión verificada: mismo estado sin commit de `feature/incremento-4-rebanada-vertical`, base
`8e3185c`, con las correcciones descritas en las notas de 4c2 de `ANALISIS.md`.

### REV4C2-01 — RESUELTO

`_linked_component` recorre desde el ancla todos los componentes existentes y se aplica a la
creación, la carga y de nuevo en `_publish`. La instancia y el workspace rechazan una junction
padre, no escriben en su destino real y siguen cargando por la ruta real. Las regresiones dirigidas
de ambos flujos pasan en Windows. La ampliación a `workspace.py` está justificada: el defecto estaba
en la lógica compartida heredada de 4a, no cambia formatos persistidos y evita dos implementaciones
divergentes.

### REV4C2-02 — PARCIALMENTE RESUELTO; pendiente residual Media

La identidad inicial mediante `(st_dev, st_ino, S_IFMT)` y `_publish` resuelve los casos
reproducidos: ausente→vacío y vacío→otra carpeta vacía dan `CONFLICT` sin tocar al ganador; una
carpeta vacía que no cambia sigue siendo utilizable. En Windows, si el destino aparece después de
la última comprobación, `os.replace` falla y `_ConcurrentDestination` permite distinguir retry
idéntico de conflicto. Las regresiones de instancia y 4a pasan.

No obstante, el propio docstring de `_publish` documenta que en POSIX `rename` puede reemplazar una
carpeta vacía creada entre la última comprobación y el rename. No hay una operación no-replace ni
una reserva atómica del nombre que cierre esa ventana; por tanto aún no se cumple «nunca
sobrescribir al ganador» en todos los sistemas que el código contempla. Para resolver el hallazgo,
la publicación POSIX debe usar una primitiva realmente no-replace/reserva atómica y demostrar la
carrera, o el contrato y la plataforma soportada deben limitarse explícitamente a un entorno donde
la garantía sí se sostenga.

### REV4C2-03 — RESUELTO

`load_instance` calcula los directorios implicados por los archivos gestionados y rechaza cualquier
otro directorio bajo `dossier/`, `corpus/` o `work/`. Pasan los casos de directorio vacío extra y
anidamiento extra, y la instancia vuelve a cargar correctamente tras retirar cada intruso.

### REV4C2-04 — RESUELTO

`tests/expected_instance_templates.py` contiene expectativas independientes completas. Se comprobó
que las cuatro coinciden tanto con los bloques de 4c2 de `ANALISIS.md` como con los archivos reales;
las instrucciones renderizadas también se comparan byte a byte. `ExactOutputTest` compara la salida
completa de los cuatro comandos, en texto y JSON, incluidos orden/escaping y LF final.

### Comprobaciones dirigidas

- 16 pruebas dirigidas: **OK**, 0 omitidas, con Python 3.14. Incluyeron `Rev4C2Test`, expectativas y
  render exactos, `ExactOutputTest`, junction padre y carreras/publicación del workspace 4a.
- Comparación independiente `expected_instance_templates` ↔ bloques del plan ↔ plantillas:
  **4/4 idénticas**.
- `git diff --check`: limpio salvo los avisos ya conocidos de conversión LF→CRLF.
- `git diff --name-only 8e3185c -- reference`: sin salida.
- La suite completa de **348 OK** en Python 3.11 y 3.14, 0 omitidos, es resultado aportado por el
  implementador; no se repitió por eficiencia. Python 3.11 sigue sin estar instalado en este
  entorno de revisión.

## Segunda verificación de REV4C2-02 — 2026-10-12

### REV4C2-02 — RESUELTO

`_publish_supported()` limita de forma explícita la creación a Windows y
`_require_publish_support()` se ejecuta al principio de `_check_destination` tanto para workspace
como para instancia, antes de crear staging o escribir el destino. `_publish` repite la barrera
antes del rename. En una plataforma no soportada el workspace devuelve
`WorkspaceError("UNSAFE_DESTINATION", ...)`; `create_instance` lo traduce al mismo código de
`InstanceError`, que la CLI conserva como salida 4. No queda activa en POSIX la operación que podía
reemplazar una carpeta vacía en la última ventana de carrera.

La restricción no alcanza a `load_workspace`, `load_instance`, `approved_corpus` ni las consultas
CLI: instancias y workspaces ya existentes siguen siendo legibles fuera de Windows. La regresión
parchea `_publish_supported` a falso y comprueba el rechazo de ambas creaciones sin crear destino,
además de la carga del workspace. Una comprobación adicional de revisión confirmó también la carga
de una instancia y seis entradas aprobadas con la barrera simulada.

Limitar la creación a Windows es una decisión de soporte y amplía el comportamiento de 4a, pero el
encargo actual la establece expresamente. Es coherente con las instrucciones PowerShell y el
lanzador `py` fijados por este incremento, está documentada como conservadora/reversible y mantiene
el soporte de lectura multiplataforma; por ello no queda como duda abierta ni bloquea la aprobación.
Añadir creación POSIX en el futuro exigirá una publicación no-replace y pruebas ejecutadas allí.

Comprobaciones dirigidas:

- `tests.test_instance.Rev4C2Test.test_creation_is_refused_where_rename_could_replace_a_folder`:
  **OK** con Python 3.14.
- Simulación adicional en temporal externo: creación denegada con `UNSAFE_DESTINATION` y sin
  destino; `load_workspace`, `load_instance` y `approved_corpus` operativos: **OK**.
- `git diff --check`: limpio salvo avisos conocidos LF→CRLF; `reference/` sin cambios desde
  `8e3185c`.
- Suite completa de **349 OK** en Python 3.11 y 3.14, 0 omitidos: resultado aportado por el
  implementador; no se repitió. Python 3.11 no está instalado en este entorno de revisión.

## Sugerencias no bloqueantes

No hay sugerencias de estilo separadas. Las restantes desviaciones anotadas son aceptables con las
salvedades anteriores y no justifican cambios fuera del alcance 4c2.
