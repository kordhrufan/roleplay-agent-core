# Revisión — incremento 3: contrato y carga del expediente Markdown

## Alcance y veredicto

Revisado el estado de trabajo sin commit de `feature/plan-expediente-foro`, con base
`e4da791ad212b4c9593f87355250cf951227b022`, contra los pasos 1–15, los criterios de aceptación y
la gramática de «Plantilla de expediente del foro» de `ANALISIS.md`, incluida la enmienda de cuatro
metadatos obligatorios, orden libre y origen inferido por `archivo`.

**Veredicto: requiere cambios.** El camino nominal implementa correctamente la gramática cerrada,
la captura exacta de literales, los hashes y locators estables, la carga confinada y el modelo
inmutable. La plantilla, la guía y la fixture también cumplen el alcance. Quedan, no obstante, dos
familias de entradas inválidas que escapan como excepciones nativas en vez de `DossierError` y dos
invariantes de estado que señalan el encabezado de sección en vez de la declaración culpable.

## Defectos

### REV3-01 — Media — `core/runtime/assimilation.py:639-714,365-370`; `tests/test_forum_dossier.py:373-423,550-555`

**Problema y condición:** la validación de metadatos no falla cerrada con `DossierError` para todos
los valores JSON. Un elemento no hashable de `sugerencias` —por ejemplo
`sugerencias=[["Ambientación"]]` o una entrada objeto— llega a la consulta del diccionario de
secciones y deja escapar `TypeError`. Un entero JSON de más de 4.300 dígitos deja escapar el
`ValueError` del límite de conversión del intérprete porque `raw_decode` solo se envuelve para
`JSONDecodeError`, constantes y recursión. Además, un `id` o una `versión` con un sustituto Unicode
aislado escapado, como `"\ud800"`, supera `_check_text`; al cargar una fuente inline,
`urllib.parse.quote` deja escapar `UnicodeEncodeError`. En los tres casos se pierde el tipo de error
público y la línea útil exigidos.

**Evidencia:** reproducido con Python 3.14 sobre documentos completos: los tres casos produjeron,
respectivamente, `TypeError`, `ValueError` y `UnicodeEncodeError`, todos sin atributo `line`. Los
tests actuales cubren sugerencias string desconocidas/duplicadas, recursión profunda y constantes
no estándar, pero no estos tipos JSON, el límite de enteros ni sustitutos aislados.

**Criterio de resolución:** validar que cada sugerencia sea un `str` antes de consultarla; envolver
los errores de conversión que pueda emitir `raw_decode`, conservando `__cause__`; y rechazar de
forma determinista los strings que no puedan codificarse como UTF-8 antes de construir locators.
Todos los casos deben producir `DossierError` en la línea de `Metadatos:`. Añadir regresiones para
lista/objeto dentro de `sugerencias`, entero sobredimensionado y sustituto aislado en `id` o
`versión`, comprobadas al menos en Python 3.11 y 3.14.

### REV3-02 — Media — `core/runtime/assimilation.py:341-363,788-811`; `tests/test_forum_dossier.py:527-531,586-605`

**Problema y condición:** no todas las lecturas o formas inválidas de entrada se convierten en
`DossierError`, pese al contrato del paso 4. `document.read_bytes()`, `dossier_dir.resolve()` y
`candidate.read_bytes()` pueden propagar `OSError`/`PermissionError` sin envolver; asimismo,
`load_dossier(None)` deja escapar el `TypeError` de `Path`. El caso se activa, por ejemplo, si el
documento o una fuente desaparecen o dejan de ser legibles entre la comprobación y la lectura.

**Evidencia:** al sustituir temporalmente `Path.read_bytes` por una operación que lanza
`OSError("fallo simulado")`, `load_dossier` propagó `OSError` sin causa ni locator. Las pruebas solo
cubren ausencia, directorio en lugar de archivo, UTF-8 inválido y contenido vacío; ninguna fuerza
un fallo de E/S durante la lectura ni un tipo inválido de `dossier_dir`.

**Criterio de resolución:** envolver los fallos de resolución y lectura en `DossierError` mediante
`raise ... from exc`. Para `expediente.md`, informar su locator y `line=None`; para una fuente,
informar el locator del expediente y la línea de sus metadatos. Rechazar también un tipo de
`dossier_dir` no convertible a `Path` con `DossierError`. Añadir pruebas mediante mock que
comprueben tipo, locator, línea y `__cause__` tanto para documento como para material.

### REV3-03 — Baja — `core/runtime/assimilation.py:536-546,464-476`; `tests/test_forum_dossier.py:325-343`

**Problema y condición:** dos errores de estado se detectan tarde al construir
`DossierSectionSpec` y se reenvuelven siempre con `open_section.line`. Por ello, `Estado: NO APLICA`
en una sección obligatoria apunta al encabezado `##`, no a la línea `Estado:`; y una fuente añadida
después de `Estado: FALTA`/`NO APLICA` también apunta al encabezado, no a la declaración posterior
que crea la contradicción. La causa textual es comprensible, pero la línea incumple el requisito de
señalar la declaración culpable.

**Evidencia:** en un documento dirigido, `## Ambientación`, `Estado: NO APLICA` y la siguiente
línea estaban en 13 y 14, pero el error informó 13. En otro, encabezado, estado y `### Fuente`
estaban en 13, 14 y 15, y volvió a informar 13. El test agregado `test_invalid_status_and_notes`
solo exige que la línea no sea `None`, de modo que protege el comportamiento incorrecto.

**Criterio de resolución:** conservar la línea del marcador de estado y la de cada fuente, o
validar estas combinaciones al encontrarlas; informar la línea 14 para `NO APLICA` obligatorio y la
de la fuente posterior —`### Fuente` o sus metadatos, según la convención elegida y documentada—
para estado más fuentes. Fijar ambas líneas exactas en tests.

## Respuestas a las preguntas concretas

1. La gramática nominal es exacta: cabecera contigua, ocho encabezados fijos y ordenados,
   `### Fuente`, estado/nota, claves libres pero únicas, `raw_decode`, separador ` | `, valla
   variable, canonización CRLF→LF y rechazo de CR/BOM funcionan como se especifica. No encontré
   estructura inválida aceptada silenciosamente. REV3-01 recoge tres entradas inválidas que sí
   detienen la carga, pero con una excepción ajena al contrato; REV3-03 recoge las líneas
   incorrectas.
2. Sí. El literal inline reconstruye exactamente la secuencia canónica entre apertura y cierre,
   incluido el LF final, no interpreta Markdown interno y exige una valla más larga que cualquier
   racha interior. Hash y fragmento del locator dependen solo del literal, `id` y `versión`; las
   pruebas de LF/CRLF, edición de otras zonas y percent-encoding son adecuadas. El sustituto aislado
   de REV3-01 es la excepción de robustez al construir el locator.
3. Las rutas absolutas, UNC, unidades, `\`, `..`, segmentos ambiguos y symlinks detectables se
   rechazan, y el hash usa los bytes de archivo sin normalizar. Para una junction que apunte fuera,
   `resolve(strict=True)` seguido de `is_relative_to(root)` impide leer el archivo; una junction que
   apunte dentro no se reconoce como tal en Python 3.11 y se acepta. Esto no permite un escape, por
   lo que el riesgo anotado es aceptable para el criterio actual, aunque no serviría si la política
   futura fuera «rechazar cualquier reparse point». Falta un test Windows de junction que proteja
   la comprobación de contención. No pude ejecutar enlaces ni junctions en este entorno; los tests
   de symlink quedaron omitidos por permisos.
4. Son aceptables los mensajes en español, la regla común de texto para `pasaje`/`Nota`, el rechazo
   conservador de `:` y punto/espacio final en rutas, y conservar el criterio relativo/absoluto del
   locator recibido. No fijar tamaño es tolerable para este flujo local y manual, pero requerirá un
   límite antes de admitir expedientes arbitrarios no confiables. Permitir BOM en materiales es
   coherente con conservar y hashear sus bytes exactos; solo el documento estructural debe
   rechazarlo.
5. Sí. La plantilla es un expediente válido, enumera todos los faltantes sin fuentes ficticias y
   remite a una guía comprensible. El LEEME explica ambos orígenes, orden libre, valores opcionales,
   sugerencias y elección de valla; su ejemplo se parsea. La fixture cumple todas las condiciones
   del paso 13 y queda lista con las dos secciones opcionales como `NO APLICA`.
6. Los 53 tests son sólidos para el flujo nominal, estructura, bytes, hashes, repetición y rutas
   enumeradas, pero no fallarían ante las regresiones de REV3-01, REV3-02 o REV3-03. Tampoco fijan
   el comportamiento de junctions; los casos de symlink dependen de privilegios del SO.

## Sugerencias no bloqueantes

- Añadir, cuando el entorno Windows lo permita, una prueba de junction intermedia hacia fuera que
  falle por contención y decidir explícitamente si una junction cuyo destino sigue dentro se admite
  o se rechaza como cualquier otro reparse point.
- Antes de aceptar expedientes procedentes de terceros, fijar límites de bytes para documento y
  materiales y leer/verificar el mismo objeto de archivo para reducir ventanas de cambio entre
  comprobación y lectura. No es necesario para cerrar este incremento local.

## Verificación realizada

- `py -3.14 -B -m unittest tests.test_forum_dossier -v`: **53 tests OK, 3 omitidos** por falta de
  permisos para crear symlinks.
- `py -3.14 -B -m unittest discover -s tests -v`: **142 tests OK, 8 omitidos** por la misma
  limitación en los incrementos 2 y 3.
- Python 3.11 no está instalado en el entorno actual (`py -0p` solo enumera 3.14; `python` es
  3.10.6). Se toma como evidencia aportada la corrida previa de **53/142 OK, 0 omitidos** en 3.11
  y 3.14.
- Comprobaciones dirigidas: `sugerencias` con lista anidada → `TypeError`; entero JSON de 5.000
  dígitos → `ValueError`; sustituto aislado en `id` al cargar → `UnicodeEncodeError`; fallo simulado
  de lectura del documento → `OSError`; líneas de estado contradictorio → encabezado de sección.
- La rama y el merge-base son los indicados. La búsqueda de términos del legado no produjo
  coincidencias y `git diff --name-only e4da791 -- reference` no produjo salida. La comprobación
  aportada de `git diff --check` con `git add -N` temporal cubre también los archivos sin versionar.

## Verificación

Verificación de REV3-01..03 sobre el mismo estado de trabajo sin commit, rama
`feature/plan-expediente-foro` y base `e4da791ad212b4c9593f87355250cf951227b022`.

- **REV3-01 — Resuelto.** `_parse_suggestions` rechaza cada elemento no textual antes de consultar
  el mapa. `_parse_metadata` convierte el `ValueError` del límite de enteros en `DossierError` y
  conserva el error original en `__cause__`. `_check_utf8` impide que sustitutos Unicode aislados
  lleguen a `quote` y se aplica a los campos de texto, rutas y literales inline. Los nuevos casos de
  lista/objeto/número en `sugerencias`, entero de 5.000 dígitos e `id`/`versión` con sustituto
  aislado comprueban la línea exacta de `Metadatos:`. La reproducción dirigida confirmó
  `DossierError` y, para el entero sobredimensionado, causa `ValueError`.
- **REV3-02 — Resuelto.** `load_dossier` transforma tipos no convertibles a `Path` en
  `DossierError(locator="load_dossier", line=None)` con `TypeError` como causa. Las comprobaciones,
  lectura y resolución del documento envuelven `OSError` con el locator del documento y sin línea;
  `_read_source_file` hace lo mismo para materiales, usando el locator del expediente y la línea de
  metadatos. Los tests con mocks fijan tipo, locator, línea y `__cause__` en ambos recorridos.
- **REV3-03 — Resuelto.** `NO APLICA` en una sección obligatoria falla al leer la línea `Estado:` y
  una fuente posterior a cualquier `Estado:` falla en su línea `### Fuente`. El constructor sigue
  respaldando las invariantes para uso directo de la API y una sección aportada sin fuentes
  conserva correctamente el encabezado como ubicación. El test nuevo fija las tres convenciones.

No se observaron regresiones relacionadas en estructura, literales, hashes, locators, carga de
archivos ni modelos de los incrementos anteriores.

Comprobaciones de esta verificación:

- `py -3.14 -B -m unittest tests.test_forum_dossier -v`: **56 tests OK, 3 omitidos** porque este
  usuario no puede crear symlinks.
- `py -3.14 -B -m unittest discover -s tests -v`: **145 tests OK, 8 omitidos** por la misma
  limitación.
- Python 3.11 continúa sin estar disponible en esta sesión; se toma como evidencia aportada la
  ejecución corregida de **56/145 OK, 0 omitidos** tanto en Python 3.11 como en Python 3.14.
- Comprobaciones dirigidas de los errores de metadatos, tipos de ruta y líneas de contradicción:
  resultados y causas conformes al contrato corregido.

**Veredicto final: aprobado; REV3-01, REV3-02 y REV3-03 están resueltos y no quedan pendientes de
esta verificación.**
