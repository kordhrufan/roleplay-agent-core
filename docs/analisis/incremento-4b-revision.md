# Revisión — incremento 4b: candidatos manuales citados

## Alcance y veredicto

Revisado el estado de trabajo sin commit de `feature/incremento-4-rebanada-vertical`, con base
`91289a7564001a655a11795e9168be05f6159a74`, contra los pasos 1–18, los criterios de aceptación,
«Candidatos manuales y citas exactas» y «CLI mínimo de la rebanada» de `ANALISIS.md`.

**Veredicto: requiere cambios.** La resolución y persistencia de citas, la recarga cerrada del
estado, la idempotencia/versionado y las formas JSON cumplen el contrato revisado. No observé una
ruta nominal que escriba después de un conflicto o una entrada inválida. Quedan una desviación
real de la salida de texto —relevante para la revisión humana— y huecos de pruebas expresamente
pedidos que permitirían regresar ramas importantes sin que fallen las suites.

## Defectos

### REV4B-01 — Media — `core/runtime/cli.py:296-303,340-344`; `tests/test_assimilation_cli.py:204-218,256-267`

**Problema y condición:** `assimilation candidate show` no conserva siempre `candidate.text`
carácter por carácter después de `Texto:`. En Windows, un texto válido con CRLF pasa por la
traducción de saltos de `sys.stdout` y cada `\r\n` se emite como `\r\r\n`; si el texto ya termina en
salto, `print(candidate.text)` añade otro y muestra una línea vacía adicional. Además, al ejecutar
el módulo, `reconfigure(errors="replace")` sustituye silenciosamente cualquier carácter UTF-8 que
no represente la codificación activa. Esto contradice el texto «sin modificar» y puede mostrar al
humano un candidato distinto del persistido, aunque la salida JSON siga siendo exacta.

**Evidencia:** en temporales externos, un `LITERAL` con `text="one\r\ntwo"` produjo tras la cabecera
los bytes `b"one\r\r\ntwo\r\n"`; otro cuyo texto terminaba en LF produjo
`'Texto:\n- Llanura central\n\n'`. Ejecutando el módulo con `PYTHONIOENCODING=ascii:strict`, un
`INTERPRETATION` con `text="Conclusión 🧭"` terminó con código 0 y mostró `Conclusi?n ??`. Las 42
pruebas de 4b y la suite completa pasan porque solo cubren texto sin salto final y una codificación
capaz de representar los caracteres usados.

**Criterio de resolución:** emitir el valor de `candidate.text` sin traducción, sustitución ni
salto añadido, manteniendo un separador inequívoco tras `Texto:`; no usar `errors="replace"` para
contenido que el contrato presenta como exacto. Añadir regresiones de subprocess en Windows para
CRLF, texto con salto final y Unicode bajo una codificación de salida estrecha, además de la prueba
directa de `main`.

### REV4B-02 — Media — `tests/test_assimilation_candidates.py:64-107,198-230,339-368`; `tests/test_assimilation_cli.py:101-167,170-224`

**Problema y condición:** las pruebas nuevas no cubren varias ramas que los pasos 17–18 exigen de
forma expresa. No hay un expediente con una declaración idéntica repetida; la supuesta prueba de
ambigüedad tiene en realidad una sola declaración para esa sección/ID/versión; las dos secciones
RULES opcionales solo se prueban sin fuentes, nunca como citas válidas; y `candidate list` nunca se
consulta después de crear dos versiones del mismo ID. Tampoco se comprueba la inmutabilidad de
`CandidateCitation`/`CandidateAddResult` ni la exactitud del texto del hallazgo REV4B-01.

**Evidencia:** eliminar el colapso de `_source_declarations`, eliminar la rama
`len(matches) > 1`, clasificar como WORLD una de las dos secciones RULES opcionales o filtrar
`candidate list` a la versión vigente no afectaría a ninguna aserción actual. En comprobaciones
dirigidas externas, la implementación sí colapsó dos declaraciones idénticas y resolvió la cita
una sola vez; con dos pasajes distintos de la misma sección/ID/versión, `source show` sin selector
devolvió 3 e indicó las dos opciones. Son ramas correctas hoy, pero desprotegidas.

**Criterio de resolución:** añadir casos positivos y negativos que fijen el colapso, la ambigüedad
y ambos selectores, las seis secciones RULES con fuentes, el historial completo de `candidate
list`, la inmutabilidad de los tres modelos y las reproducciones de REV4B-01. Las pruebas deben
fallar si se elimina cualquiera de esas garantías, no limitarse a comprobar el camino nominal del
fixture actual.

## Respuestas a las preguntas concretas

1. Sí. La búsqueda es literal, conserva LF/CRLF y Unicode, cuenta solapamientos, exige
   `occurrence` base 1 cuando corresponde y no lo persiste. Sección, ID, versión y pasaje —incluido
   `null`— forman una identidad exacta; las declaraciones idénticas se colapsan y el material
   suelto no puede coincidir. Los offsets semiabiertos y el SHA-256 de la fuente cargada se
   persisten correctamente y se vuelven a contrastar al cargar.
2. Sí para las manipulaciones e invariantes enumeradas: el sobre canónico detecta hash/forma,
   `decode_candidate_state` exige claves exactas, citas resolubles, substring, hash de fuente,
   hash del candidato, estado pendiente, versiones contiguas y decisiones/cierre vacíos, y
   `load_workspace` lo aplica contra la copia íntegra del expediente. Como declara el propio
   contrato, no autentica al actor: quien reescriba de forma coherente datos y todos sus hashes
   queda fuera de la garantía, no es una propiedad de seguridad ofrecida.
3. Sí en el modelo de concurrencia declarado. El retry exacto con la revisión actual no escribe ni
   cambia mtime; las claves conflictivas, saltos, versiones 1 incorrectas, revisiones obsoletas y
   versiones semánticamente vacías fallan antes de `atomic_write_bytes`; un alta válida añade al
   final e incrementa una revisión. Un fallo de `os.replace` conserva el estado anterior. No hay
   exclusión entre procesos: dos escritores que superen simultáneamente la lectura pueden perder
   una actualización; el plan aplaza los locks al incremento 9 y no promete evitar esa carrera.
4. Las claves JSON de éxito/error, acciones, códigos 0/2/3/4/5, selectores, solo lectura de
   `source` y ausencia de decisión, cierre, instancia y publicación son correctos. `argparse`
   conserva su salida propia para código 2. El modo texto de `candidate show` no es exacto en las
   condiciones de REV4B-01.
5. Los imports privados desde `cli.py` son aceptables en 4b: mantienen una sola implementación de
   selección y serialización dentro del mismo paquete y el plan pide que esos helpers sigan sin
   reexportarse. El colapso de `source list` coincide con la identidad de resolución; mostrar todas
   las versiones en `candidate list` preserva el historial exigido. `reconfigure(errors="replace")`
   no es aceptable para contenido exacto por REV4B-01.
6. Las pruebas protegen bien búsqueda literal, solapamientos, offsets, hash, estado pendiente,
   conflictos principales, fallo de replace, formas JSON y comandos prohibidos. No fallarían ante
   las regresiones concretas de REV4B-02 y ya dejan pasar REV4B-01; por tanto no satisfacen todavía
   toda la matriz pedida.

## Sugerencias no bloqueantes

- Mantener los helpers privados es razonable mientras CLI y asimilación evolucionen juntas; si un
  segundo consumidor necesita estas vistas, convendrá exponer una función pública de consulta en
  vez de ampliar los imports con guion bajo.
- La comparación por `candidate_sha256` para el retry es coherente con el modelo de hashes del
  incremento; no hace falta duplicar una comparación profunda salvo que el contrato cambie para
  tratar colisiones deliberadas.

## Verificación realizada

- `py -3.14 -B -m unittest tests.test_assimilation_candidates tests.test_assimilation_cli -v`:
  **42 ejecutados, 42 OK**.
- `py -3.14 -B -m unittest discover -s tests -v`: **245 ejecutados; 236 OK y 9 omitidos** porque
  este usuario no puede crear symlinks ordinarios. Las pruebas de junction disponibles sí pasaron.
- Python 3.11 no está instalado (`py -0p` solo enumera 3.14), por lo que no pude reproducir esa
  ejecución. Se conserva como evidencia aportada la ejecución previa indicada de 245 OK y 0
  omitidos en 3.11 y 3.14, pero aquí tampoco pude reproducir el «0 omitidos» por la limitación de
  symlinks.
- Reproducciones dirigidas, todas en temporales externos: declaración idéntica colapsada y cita
  resuelta; dos pasajes distintos detectados como ambigüedad; CRLF duplicado por la salida de
  Windows; salto final duplicado; y sustitución de Unicode con codificación ASCII estrecha.
- `rg` de nombres del legado: sin coincidencias. `git diff --name-only 91289a7 -- reference`: sin
  salida. `git diff --check`: limpio, salvo los avisos informativos de futura conversión LF→CRLF.
  Rama y merge-base coinciden con los indicados.

## Verificación

Verificación limitada a REV4B-01..02 y sus regresiones relacionadas sobre el mismo estado de
trabajo sin commit, rama `feature/incremento-4-rebanada-vertical` y base
`91289a7564001a655a11795e9168be05f6159a74`.

- **REV4B-01 — Resuelto.** Las salidas de los handlers pasan por `_line`/`_write_exact`; el camino
  de streams reales hace `flush`, codifica explícitamente como UTF-8 y escribe en el buffer
  binario, mientras `StringIO` recibe el texto directamente. Ya no hay `print` ni
  `reconfigure(errors="replace")`. `candidate show` escribe `candidate.text` sin añadirle ni
  traducirle caracteres y lo separa de la salida estructural mediante el encabezado, el aviso
  condicional de ausencia de salto final y `Fin del texto.`. Las regresiones directas y de
  subprocess confirmaron CRLF sin `\r\r\n`, salto final sin línea vacía añadida y Unicode sin
  sustitución bajo `PYTHONIOENCODING=ascii:strict`. `source show` conserva deliberadamente su
  representación visual numerada; su JSON sigue entregando el literal exacto.
- **REV4B-02 — Resuelto.** `CustomDossierTest` fija el colapso de declaraciones idénticas, la
  ambigüedad real de dos pasajes y ambos selectores, las seis secciones RULES con rechazo de WORLD
  y el historial v1+v2 completo en las salidas JSON y texto. `ExactTextTest` protege los tres casos
  de REV4B-01 por `main` y subprocess, y los modelos `CandidateCitation` y `CandidateAddResult`
  tienen aserciones de inmutabilidad. Las mutaciones descritas en el hallazgo ya harían fallar una
  prueba específica.

Comprobaciones de esta verificación:

- `py -3.14 -B -m unittest tests.test_assimilation_candidates tests.test_assimilation_cli -v`:
  **49 ejecutados, 49 OK**.
- `py -3.14 -B -m unittest discover -s tests -v`: **252 ejecutados; 243 OK y 9 omitidos** porque
  este usuario no puede crear symlinks ordinarios. Los casos nuevos de 4b y las pruebas de
  junction disponibles sí se ejecutaron y pasaron.
- Python 3.11 continúa sin estar instalado en esta sesión. Se conserva como evidencia aportada la
  ejecución de **252 OK, 0 omitidos** en Python 3.11 y 3.14, pero aquí no pude reproducir Python
  3.11 ni el «0 omitidos» por la limitación de symlinks.
- `git diff --check`: limpio, salvo avisos informativos LF→CRLF;
  `git diff --name-only 91289a7 -- reference`: sin salida.

**Veredicto final: aprobado; REV4B-01 y REV4B-02 están resueltos y no quedan pendientes de esta
verificación.**
