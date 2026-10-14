# Revisión 5a — fase 1: ampliación aditiva del corpus

Versión revisada: estado de trabajo sin commit de
`feature/incremento-5a-ampliacion-corpus` sobre `1265600`, a 2026-10-14. Se incluyeron los
archivos sin seguimiento `tests/test_corpus_expansion.py` y
`tests/test_corpus_expansion_cli.py`. Se excluyó expresamente la fase 2 (`instance update`,
instancia v2, historial, cerrojos de actualización y `tests/test_instance_update.py`).

## Veredicto

**APROBADO — FASE 1.** REV5A-01 y REV5A-02 están resueltos. El cierre conserva y vuelve a comparar
bajo el cerrojo los bytes completos de todas sus entradas estáticas, incluida una reescritura
coherente de configuración e integridad; el decoder rechaza también los descriptores históricos
semánticamente inválidos. No quedan hallazgos pendientes dentro del alcance de la fase 1.

## Hallazgos

### REV5A-01 — Media — RESUELTO — `core/runtime/assimilation.py:2167-2253`; `core/runtime/workspace.py:821-828`

**Problema y condición.** Tras la confirmación, `close_expansion` adquiere el cerrojo y relee solo
`corpus/state.json`. El `dossier` y el `ExpansionContext` usados para validar y construir el cierre
son los objetos cargados antes del prompt; no se releen `corpus/base.json`, el expediente base, el
expediente sucesor ni sus manifiestos. Si cualquiera de esas entradas cambia mientras la persona
responde, el comando registra el cierre, incrementa la revisión y devuelve éxito. La siguiente
carga detecta la alteración, pero el requisito era `CONFLICT` sin escritura.

**Evidencia.** Se reprodujo sobre una ampliación válida: el callback de lectura del terminal añadió
un byte a `base/dossier/expediente.md`. `close_expansion` devolvió `created=True`, pasó la revisión
22→23 y dejó `closure` no nulo; `load_workspace` falló después con `INVALID_STATE`. La prueba
entonces existente `test_answers_and_changes_during_the_prompt` solo modificaba el delta mediante
otra alta, por lo que no cubría la base ni los expedientes.

**Corrección.** Conservar una huella verificable de todas las entradas mostradas en el prompt y,
bajo el mismo cerrojo del delta, releer desde el workspace la base, ambos expedientes/configuración
e integridad además del delta. Cualquier diferencia o error de integridad respecto de lo mostrado
debe producir `CONFLICT` antes de escribir. Añadir casos separados que cambien
`corpus/base.json`, `base/dossier/**`, `dossier/**`, `workspace.json` e integridad durante la
confirmación y comprueben bytes y revisión idénticos.

**Criterio de resolución.** Ninguna entrada que determine padre, descriptor, cobertura, hash o
prompt puede cambiar entre carga y commit sin que el cierre termine en `CONFLICT` y sin escritura.

**Verificación.** Tras cargar el delta y antes de construir el prompt, `_expansion_inputs` obtiene
los bytes de `workspace.json`, integridad, `corpus/base.json` y los árboles completos `dossier/` y
`base/`; `_tree_bytes` incluye contenido/rutas y rechaza enlaces. La función lee esos bytes antes y
después de una carga completa y exige además los mismos expediente y `ExpansionContext`, evitando
asociar la huella con una lectura intermedia. Bajo `_corpus_lock` vuelve a calcular la misma huella
y exige igualdad exacta antes de releer el delta o escribir.

El test de las cinco entradas sigue demostrando `CONFLICT` sin cambio de estado, cierre ni lock
residual. La nueva regresión reescribe canónicamente
`base_instance.instance_json_sha256`, recalcula la entrada de `workspace.json` en integridad y
confirma el mismo resultado aunque el workspace modificado siga cargando. Las tres pruebas
dirigidas y las 27 pruebas de 5a pasan; no observé una regresión relacionada.

### REV5A-02 — Media — RESUELTO — `core/runtime/assimilation.py:1932-1969,2379-2388,2456-2462`

**Problema y condición.** `DossierFileRef` solo exige una cadena no vacía sin controles, y
`_check_chain` no exige que el `schema_version` del expediente sea constante ni que las versiones
de expediente sean únicas en la cadena. Como el hash original LEGACY no incluía el descriptor de
expediente, se puede cambiar el descriptor histórico, recalcular únicamente
`dossier.snapshot_sha256` y obtener una cadena aceptada sin cambiar el hash, recibo o evidencia del
cierre LEGACY ni el snapshot aditivo. Esto admite historia incompatible con las reglas usadas para
crear la ampliación y debilita la promesa de versión no reutilizada.

**Evidencia.** Sobre una cadena `LEGACY_V1 → ADDITIVE_V2` válida se probaron, por separado, estos
cambios al descriptor del primer snapshot, recalculando su hash canónico: (a) cambiar su versión a
la misma del snapshot actual, (b) cambiar `schema_version` de 1 a 2 y (c) cambiar la primera ruta a
`../expediente.md`. `decode_closed_corpus` aceptó los tres. Las pruebas existentes alteran hashes o
campos sin reconstruir un descriptor autoconsistente y no ejercitan estas invariantes.

**Corrección.** Validar las rutas de `DossierFileRef` como rutas gestionadas relativas bajo
`dossier/`, exigir en `_check_chain` un único `schema_version` compatible con el expediente actual
y rechazar cualquier `dossier_version` repetida. Añadir pruebas con descriptores autoconsistentes
(hash recalculado), no solo con un hash deliberadamente incorrecto. Documentar además el límite ya
existente: los SHA-256 detectan inconsistencias, pero no autentican a quien pueda reescribir y
rehashear todas las capas.

**Criterio de resolución.** El decoder rechaza rutas no gestionadas, cambios de schema entre
snapshots y versiones de expediente repetidas aunque cada descriptor tenga un SHA-256 canónico
correcto; las cadenas emitidas actualmente siguen cargando sin cambios.

**Verificación.** `DossierFileRef` limita las rutas a rutas POSIX gestionadas bajo `dossier/`, sin
segmentos vacíos, de navegación o con sufijo inseguro; `DossierSnapshot` exige el expediente
principal. `_check_chain` exige un único esquema y versiones de expediente únicas, y documenta el
límite de autenticación. El nuevo test recalcula correctamente el hash del descriptor tras forjar
versión repetida, schema distinto, dos variantes de escape de ruta y ausencia del expediente
principal: las cinco se rechazan y la cadena válida sigue cargando. El test dirigido y las 26
pruebas de 5a pasan; no observé una regresión relacionada.

## Contraste de criterios y preguntas

1. **Cadena y LEGACY.** Contadores, revisiones, ordinales, padres, prefijos de candidatos/decisiones,
   IDs nuevos por ronda, hashes de snapshot y evidencia se validan conforme al plan. La
   representación `LEGACY_V1` conserva `closure_id`, `snapshot_sha256`, recibo y evidencia
   originales y vuelve a comprobar el algoritmo v1; la validación adicional
   `base_revision == altas + decisiones` es compatible con cierres producidos por el core. No hay
   autenticación criptográfica: los hashes son integridad autocontenida. Las invariantes semánticas
   señaladas por REV5A-02 se comprueban ahora incluso después de un rehash parcial.
2. **Expediente aditivo.** `compare_additive_dossier` conserva cada sección en orden fijo, exige las
   ocurrencias antiguas como subsecuencia, rechaza claves antiguas añadidas/movidas/duplicadas,
   cambios de bytes/metadatos/notas/estado y material suelto que no sea anexo final. Admite
   correctamente clave nueva, nueva versión opaca de un ID de fuente y `MISSING → PROVIDED` solo
   con fuente nueva; rechaza versión de expediente actual o ya usada. No encontré un cambio no
   aditivo que pase esta función.
3. **Delta, cobertura, cierre y retry.** Alta y decodificación prohíben IDs presentes en cualquier
   snapshot base y exigen una cita nueva por candidato; las decisiones solo resuelven el delta; la
   cobertura usa base+delta; el cierre exige al menos un candidato y decisión sobre cada vigente,
   permite todos rechazados y el retry es no-op. El prompt y las salidas CLI coinciden byte a byte
   con el plan. REV5A-01 garantiza ahora la igualdad byte a byte de todas las entradas estáticas
   antes y después del prompt, además de la relectura separada del delta.
4. **`base/dossier` y `base_dossier`.** La desviación es aceptable y compatible con el plan. La
   copia está cubierta por integridad, permite recalcular el delta y validar el corpus base sin
   reabrir la instancia, y conserva el vínculo por contenido. Guardar solo el delta derivado sería
   menos verificable; no recomiendo sustituirla.
5. **Compatibilidad v1 y cobertura.** Los formatos, comandos y salidas v1 mantienen el despacho y
   defaults anteriores; `instance init` sigue siendo v1 y rechaza el workspace v2. Las suites
   existentes y los golden no muestran cambios. Persisten como mejoras de evidencia, no como
   hallazgos de esta verificación, casos explícitos para movimiento/reordenación/duplicación de fuentes, fuente
   nueva en todas las secciones, y carreras/fallos de publicación y limpieza específicos de
   `create_expansion_workspace`; los helpers compartidos sí tienen cobertura general, por lo que
   estos últimos son una carencia de evidencia, no otro defecto demostrado.

## Verificación ejecutada

- Tests dirigidos de REV5A-01 y REV5A-02 en Python 3.14: 3 OK.
- `py -3.14 -B -m unittest tests.test_corpus_expansion tests.test_corpus_expansion_cli -v`:
  27 OK.
- Suite completa aportada para la versión corregida: 501 OK tanto en Python 3.11 como en 3.14.
  Python 3.11 no está instalado en este entorno y las suites completas no se repitieron aquí; la
  comprobación local se limitó a los hallazgos y regresiones relacionadas, conforme al encargo.
- `git diff --check 1265600`: limpio.
- Plantillas y `tests/expected_instance_templates.py`: sin diff desde `1265600`.
- `reference/`: sin cambios; búsquedas de nombres legacy y comandos prohibidos: vacías.

# Revisión 5a — fase 2: actualización de instancia e historial

Versión revisada: estado de trabajo sin commit de
`feature/incremento-5a-ampliacion-corpus` sobre `854acaf`, a 2026-10-14. Se incluyó el archivo sin
seguimiento `tests/test_instance_update.py` y se ignoraron los archivos cuyo único cambio es la
normalización de saltos de línea indicada en el encargo.

## Veredicto de la fase 2 y de 5a

**APROBADO — FASE 2 Y 5a COMPLETO.** REV5A-03 a REV5A-06 están resueltos. La carga semántica, los
bytes mostrados y los bytes publicados proceden ahora de las mismas lecturas estables; los restos
de recuperación bloquean incluso el no-op; la consulta del snapshot de origen está expuesta para
v1/v2; y las regresiones requeridas cubren las carreras y fallos señalados. No quedan hallazgos
pendientes dentro del alcance de 5a.

## Hallazgos de la fase 2

### REV5A-03 — Alta — RESUELTO — `core/runtime/instance.py:532-679,742-764`

**Problema y condición.** `_plan_update` carga primero `LoadedInstance` y `LoadedWorkspace`, y
después captura por separado `static`, `characters` y `workspace_files`. Su `fingerprint` contiene
solo estos diccionarios de bytes, no los objetos semánticos de los que salen el prompt, el snapshot
y el plan de escritura. Si una entrada cambia coherentemente entre ambas lecturas, el primer plan
puede combinar semántica antigua con bytes nuevos; la relectura bajo lock obtiene semántica y bytes
nuevos, pero su huella compara igual y la actualización continúa.

**Evidencia.** Se reprodujo sustituyendo, dentro de la primera llamada a
`expansion_input_bytes`, un workspace cerrado `2026-10-14` por otro workspace cerrado y válido
`2026-10-18`, ambos hijos de la misma instancia. El prompt mostró el hash y la versión del primero,
pero `update_instance` devolvió éxito y la instancia terminó en el hash y la versión del segundo.
También se reprodujo una creación de personaje completada entre `load_instance` y
`_characters_bytes`: el prompt dijo `Personajes preservados: 1`, la huella pasó y la instancia
actualizada conservó 2. No hubo pérdida en este segundo caso, pero demuestra que el recuento
confirmado tampoco está ligado a la huella.

**Corrección.** Construir cada plan desde lecturas estables ligadas a los objetos usados: capturar
los bytes completos de instancia/workspace antes y después de su carga, exigir igualdad y usar
precisamente la carga situada entre ambas capturas. Evitar relecturas no ligadas al generar
`expected`, o comprobarlas del mismo modo. Además, la comparación bajo lock debe incluir los
campos semánticos confirmados (snapshot, versiones, recuentos y personajes), no solo los
diccionarios de bytes.

**Criterio de resolución.** Un reemplazo coherente del workspace o la finalización de una creación
en cualquier punto de la planificación se incorpora íntegramente antes del prompt o produce
`CONFLICT`; nunca se aplica un snapshot, versión o recuento distinto del mostrado. Añadir las dos
regresiones anteriores y comprobar que no hay escritura.

**Verificación.** `_plan_update` obtiene `_tree_bytes` completos de instancia y workspace antes y
después de cargar ambos objetos, exige igualdad y deriva de esos diccionarios todos los estáticos,
personajes, expediente y corpus del staging. `_expected_update_files` ya no relee el workspace. La
huella añade el snapshot, padre, versiones, conteos de decisiones y número de personajes mostrados;
se compara bajo el lock, y `_swap_in` vuelve a exigir el árbol completo de instancia justo antes del
rename. Las regresiones sustituyen coherentemente el workspace durante planificación y durante el
prompt, y completan una creación durante la carga: las tres dan `CONFLICT` sin escritura; el retry
estable cuenta los dos personajes. El criterio queda satisfecho.

### REV5A-04 — Media — RESUELTO — `core/runtime/instance.py:561-586,709-718`

**Problema y condición.** No se buscan ni rechazan los hermanos
`.<nombre>.update-staging-*`/`.<nombre>.update-backup-*` antes del no-op, el prompt o un nuevo swap.
`_swap_in` solo crea nombres aleatorios nuevos. Por ello un resto que representa una recuperación
pendiente se ignora y puede acumularse mientras se aplica otra actualización, contra el requisito
explícito de rechazar restos hermanos inesperados.

**Evidencia.** Se creó `.<nombre>.update-backup-deadbeefdeadbeef` junto a una instancia v1 válida y
se ejecutó la actualización: devolvió `updated=True`, dejó la instancia v2 válida y conservó el
resto sin advertencia. No hay prueba de esta precondición en `tests/test_instance_update.py`.

**Corrección.** Detectar cualquier hermano que coincida con los namespaces de staging/backup y
devolver `CONFLICT` con sus rutas antes del no-op o del prompt; repetir la comprobación bajo el lock
antes de crear el staging. No borrar ni reutilizar automáticamente un resto recuperable.

**Criterio de resolución.** Con cualquier resto de staging o backup previo, incluido archivo,
directorio o enlace, `update_instance` no pregunta ni escribe y da una instrucción inequívoca de
inspección/recuperación; sin restos conserva el comportamiento actual.

**Verificación.** `_reject_update_leftovers` enumera por prefijo ambos namespaces hermanos sin
depender del tipo de entrada y devuelve `CONFLICT` con todas las rutas y una instrucción de
recuperación. Se ejecuta antes de decidir el no-op y otra vez bajo el lock antes del staging. Las
pruebas cubren backup como directorio, staging como archivo y backup tras una actualización ya
aplicada; todos bloquean sin prompt ni escritura. El criterio queda satisfecho.

### REV5A-05 — Baja — RESUELTO — `core/runtime/instance.py:301-307`; `core/runtime/__init__.py:52-76,273`

**Problema y condición.** Falta la API planificada
`snapshot_for_candidate(instance, *, candidate_id, version)`. Existe
`ClosedCorpus.snapshot_for`, y las pruebas llaman a esa implementación tras
`closed_corpus_of`, pero no existe ni se exporta el adaptador común de instancia pedido para v1 y
v2.

**Corrección y criterio de resolución.** Añadir y exportar el helper con la firma prevista,
delegando en la cadena obtenida de la instancia, y cubrir candidato legacy, candidato aditivo y
candidato ausente. Debe funcionar igual con una instancia v1 sintetizada y con una v2.

**Verificación.** `snapshot_for_candidate` delega en `closed_corpus_of(instance).snapshot_for`,
devuelve el primer snapshot que contiene la versión exacta y convierte la ausencia en
`INVALID_STATE`; está exportado por `core.runtime`. Las pruebas cubren origen legacy y aditivo en
una cadena de tres snapshots, ausencia y una instancia v1 sintetizada. El criterio queda satisfecho.

### REV5A-06 — Baja — RESUELTO — `tests/test_instance_update.py:44-82,231-367,469-528`

**Problema.** La suite nueva cubre v1→v2, history v1/v2, no-op, base obsoleta, varios locks y fallos
de rename/limpieza, pero no deja regresión automatizada para v2→v2 con personajes, la carrera real
de creación, los estados completos prometidos (propuestas aprobada y rechazada y respuesta de
staff), restos hermanos, ni fallos separados de copia/escritura y validación posterior al swap. El
smoke aportado de dos rondas da evidencia puntual, no protege esos contratos en la suite.

**Corrección y criterio de resolución.** Añadir los casos requeridos por el plan, priorizando las
regresiones de REV5A-03/04, v2→v2 con el árbol completo de personajes byte a byte y la validación
posterior al swap. `instance corpus history` v2 ya está cubierto y no necesita duplicarse.

**Verificación.** La fixture incluye propuestas pendiente, rechazada y aprobada, composición
resultante, ficha y respuesta de staff. `ChainTest` prueba v2→v2, tres snapshots y conservación de
árbol, estados y revisiones; `StableReadTest` cubre las carreras y restos de REV5A-03/04; y
`FailureTest` añade fallo de escritura y fallo de verificación posterior conservando el backup.
Junto con history v2 ya existente, la cobertura relacionada pedida queda incorporada.

## Contraste de criterios y preguntas de la fase 2

1. **Swap y recuperación.** El staging se valida con la ruta lógica final, los archivos se
   sincronizan, los dos renames son de árboles completos y el backup solo se elimina tras validar la
   publicación. Los fallos del primer/segundo rename, restauración, borrado y lock dejan una copia
   anterior o nueva recuperable y sus mensajes distinguen si el cambio se aplicó. Una lectura puede
   fallar mientras la ruta final está entre renames, pero no puede aceptar una mezcla de snapshots.
   REV5A-04 garantiza ahora que una recuperación anterior pendiente impida comenzar otro swap.
2. **Cerrojos.** El orden update-lock → rechazo de locks de personaje, y character/create-lock →
   guard de update, no introduce espera circular: el segundo actor falla. Los guards antes de las
   frases, tras adquirir lock y antes del replace cubren las escrituras. REV5A-03 liga además la
   carga y la huella completas antes del prompt, y la relectura bajo lock impide adoptar contenido
   distinto del confirmado.
3. **Instancia v2 y compatibilidad.** Schema 2, integridad 2, corpus encadenado, expediente actual y
   copia byte a byte de instrucciones/personajes cargan conforme al plan. La ruta v1 conserva su
   decoder y sus bytes; las regresiones existentes pasan. REV5A-05 aporta el helper público común
   de trazabilidad sin alterar el formato.
4. **Prompt, CLI y no-op.** En una lectura estable, el prompt, las frases, los textos/JSON/códigos de
   `instance update` y `instance corpus history`, y el no-op sin nonce ni mtime coinciden con el
   plan. History v2 está cubierto, y las lecturas estables aseguran que el prompt representa el
   contenido aplicado. REV5A-06 completa las regresiones relacionadas.

## Verificación ejecutada

- `py -3.14 -B -m unittest tests.test_instance_update -v`: 22 OK.
- Suite completa aportada para la versión corregida: 523 OK tanto en Python 3.11 como en 3.14.
  Python 3.11 no está instalado en este entorno y la suite completa no se repitió aquí; la
  verificación local se limitó a los hallazgos y regresiones relacionadas, conforme al encargo.
- Las regresiones dirigidas de los cuatro hallazgos pasan y ya no reproducen los estados inseguros
  descritos; no se observó una regresión relacionada.
- `git diff --check 854acaf`: limpio. Plantillas, `tests/expected_instance_templates.py` y
  `reference/`: sin diff desde la base indicada.
