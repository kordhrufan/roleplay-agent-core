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
