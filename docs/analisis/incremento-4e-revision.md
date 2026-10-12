# Revisión 4e — ficha mínima y respuesta del staff

Versión revisada: estado de trabajo sin commit de
`feature/incremento-4-rebanada-vertical` sobre `130d0bf`, a 2026-10-12. Se incluyeron los
archivos sin seguimiento `tests/test_character_draft.py` y `tests/test_staff_review_cli.py`.

## Veredicto

**APROBADO.** REV4E-01 está resuelto. Replay, persistencia, hashes, evidencia, operaciones bajo
cerrojo, modelos y CLI cumplen el plan en los caminos revisados. No quedan hallazgos de código
pendientes en 4e ni observé un estado persistido manipulado que supere codec y replay.

## Hallazgos

### REV4E-01 — Baja — RESUELTO — `core/character/models.py:518-570`; `tests/test_character_draft.py:284-321`

**Problema y condición.** `CharacterDraftView.__post_init__` solo exige que una vista no vigente
tenga una razón que empiece por `SUPERSEDED_BY:`. No relaciona esa razón con `current`,
`character-sheet` ni la versión sustituida, y para una vista vigente acepta cualquier
`stale_reason`. Por ello se pueden construir y serializar vistas imposibles como
`current=True` + `SUPERSEDED_BY:character-sheet:v999`, o `current=False` sustituida por
`otro:v1` o por su propia `character-sheet:v1`. Incumple que solo la versión mayor sea vigente,
que las menores usen exactamente `SUPERSEDED_BY:character-sheet:v<N>` y que una vigente solo
pueda quedar obsoleta por el cambio exacto de composición. El replay actual sí construye las
vistas correctas, por lo que no permite cargar estos casos desde `state.json`.

**Evidencia.** Una reproducción directa creó una ficha v1 válida, aplicó `mark_stale` con las
tres razones anteriores y construyó `CharacterDraftView`; las tres fueron aceptadas. La prueba
de coherencia existente solo rechaza una vista no vigente que conserva `ACTIVE` y no cubre la
relación inversa ni la forma de la razón.

**Corrección propuesta.** Validar conjuntamente `current`, ciclo y razón: una vista sustituida
debe ser `STALE` con forma exacta `SUPERSEDED_BY:character-sheet:v<N>` y `N > record.version`;
una vista vigente no puede tener una razón `SUPERSEDED_BY` y, si está `STALE`, su razón debe ser
`EFFECTIVE_COMPOSITION_CHANGED:<record.composition_sha256>-><sha256 canónico distinto>`.
Añadir regresiones para las tres construcciones reproducidas y para una vista vigente con razón
arbitraria. Se dará por resuelto cuando todas fallen con `CharacterError` y sigan siendo válidas
las vistas generadas por `_draft_views`.

## Contraste de los criterios y preguntas

1. **Replay y vigencia.** Las revisiones explícitas de propuesta, decisión, ficha y respuesta son
   únicas, ordenadas y acotadas; los huecos se asignan a conceptos. El alta exige composición,
   concepto, fuentes, contexto y corpus exactos del instante, y la respuesta debe ser posterior,
   única y coincidir con versión, `draft_sha256` y composición. `_draft_views` aplica primero
   `APPROVED`/`REJECTED`, da prioridad a `SUPERSEDED_BY:character-sheet:v<N>` para versiones
   menores y usa `EFFECTIVE_COMPOSITION_CHANGED:<anterior>-><actual>` para la vigente. Admite una
   respuesta tardía sobre `STALE`; el eje de publicación permanece `NOT_CONFIRMED` y staff no
   cambia `EffectiveComposition`. No encontré un registro persistido manipulado que cargue; el
   defecto de REV4E-01 solo afecta a construcción directa del modelo de vista.
2. **Hashes, referencias y compatibilidad.** `draft_sha256` cubre exactamente el registro de alta
   salvo su propia clave; `response_sha256` son los bytes UTF-8 literales y
   `staff_review_sha256` cubre todas las claves persistidas de la respuesta salvo él mismo. La
   unión de `corpus_refs` conserva primera aparición; `source_refs`, `context_refs`, locators
   percent-encoded y la evidencia de staff coinciden con el plan. El decoder solo acepta cuatro
   o seis claves; el encoder conserva cuatro mientras no haya eventos 4e. La ruta de cuatro
   claves no cambió y se recodifica canónicamente igual, por lo que los estados 4d1/4d2 mantienen
   compatibilidad byte a byte.
3. **Desviaciones anotadas.** Son aceptables. Los IDs no persistidos se inyectan desde la
   instancia y se verifican por modelo/replay; derivar `response_sha256` evita aceptar un hash
   aportado; rechazar la forma vacía de seis claves da una única codificación canónica; un path
   inexistente es entrada inválida igual que en 4d1, mientras un fallo real de lectura sigue
   siendo `IO`; validar `--composition-sha256` en el core produce el código 3 que fija la tabla
   del plan. Las coincidencias de `rg` son el auxiliar heredado de publicación atómica en disco y
   docstrings negativos, no una operación de publicación de ficha.
4. **Concurrencia e idempotencia.** `create_draft` construye desde un snapshot, toma el cerrojo,
   recarga toda la instancia, compara revisión y estado, vuelve a resolver las citas y pasa el
   guard antes de tomar el lock, al tomarlo y antes del replace. `record_staff_response` comprueba
   lock antes del reto, relee bytes después de la frase y pasa por la misma relectura bajo lock.
   Cualquier evento concurrente del personaje da `CONFLICT`; los retries idénticos no toman lock,
   no escriben ni cambian mtime. No encontré una ventana nueva respecto del límite 4d1 ya
   documentado entre el último guard y `os.replace`; un retry sin lock puede devolver su snapshot
   justo antes de un evento posterior, pero no pierde ni sobrescribe datos y es consecuencia del
   no-op exigido.
5. **Prompt, CLI y cobertura.** Los cuatro comandos, obligatoriedad, frase/nonce de un intento,
   prompt LF sin normalizar contenido, texto/JSON, claves, resúmenes y códigos 0/2/3/4/5 coinciden
   con el plan en código y pruebas. `REJECTED` conserva literalmente «cambios solicitados» y no
   existe `CHANGES_REQUESTED`. La carencia funcional de cobertura es REV4E-01. Como refuerzo no
   bloqueante, faltan una aserción byte a byte sobre un fixture 4d2 anterior real y un prompt
   completo con varias citas (el prompt se cubre con cero y una; `show` sí cubre dos). La prueba
   manual en TTY real sigue siendo externa.

## Verificación realizada

- Python 3.14, suites 4e: **31 OK**, 0 omitidas.
- Python 3.14, suite completa: **468 OK**, 9 omitidas por condiciones/permisos del entorno.
- Reproducción directa de REV4E-01: las tres vistas incoherentes fueron aceptadas.
- Inspección y pruebas dirigidas de codec/replay: formas de cuatro/seis claves, alteraciones de
  campos, fuentes, hashes, evidencia, revisiones, respuestas tardías y prioridad de obsolescencia.
- `git diff --check 130d0bf`: limpio; rutas congeladas y `core/review`: sin cambios; nombres del
  legado: sin coincidencias.
- Python 3.11 no está disponible en este entorno. Los resultados aportados de **468 OK** sin
  omitidos en 3.11 y 3.14 quedan como antecedente, no como reproducción propia.

## Pendientes externos

- Validación funcional de `character staff record` en una TTY real.

## Sugerencias fuera de alcance

Ninguna.

## Verificación de REV4E-01 — 2026-10-12

**Resuelto.** `CharacterDraftView.__post_init__` valida ahora conjuntamente el registro, la
vigencia y `stale_reason`. Una versión sustituida solo admite la forma completa
`SUPERSEDED_BY:character-sheet:v<N>`, sin ceros a la izquierda y con una versión posterior a la
suya. Una versión vigente admite ausencia de razón o la forma completa
`EFFECTIVE_COMPOSITION_CHANGED:<hash citado>-><otro hash minúsculo distinto>`. Con ello quedan
rechazadas las tres construcciones reproducidas y las variantes de ID, versión, formato y hashes
que podían representar vistas imposibles; las razones válidas derivadas por `_draft_views`
continúan aceptándose.

La regresión nueva cubre las tres reproducciones originales, `v02`, sustitución por otro ID o por
la propia versión, razón de composición en una vista sustituida, razón arbitraria, hash de origen
ajeno, destino igual y destino en mayúsculas; fija además los dos casos `STALE` válidos. No se
observaron regresiones relacionadas.

Comprobaciones:

- Python 3.14, regresión exacta: **1 OK**.
- Python 3.14, suites relacionadas de fichas, modelos, estado y propuestas: **96 OK**.
- `git diff --check 130d0bf`: limpio, salvo avisos informativos LF→CRLF.
- Suite completa de **469 OK** en Python 3.11 y Python 3.14: resultado aportado por el
  implementador; en este entorno solo está disponible Python 3.14 y no se repitió la suite
  completa para esta verificación focalizada.
