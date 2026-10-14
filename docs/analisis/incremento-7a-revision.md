# Revisión 7a — flujo narrativo mínimo y memoria literal de temas

Versión verificada: estado de trabajo sin commit de
`feature/incremento-7-memoria-narrativa` sobre `620aea1`, a 2026-10-14, con las correcciones
de REV7A-01..04 descritas en el encargo. Se mantuvieron fuera de alcance los cambios solo de fin
de línea indicados por el usuario.

## Veredicto

**APROBADO — 7a COMPLETO.** REV7A-01..04 están resueltos. Las correcciones cierran los defectos
de concurrencia, procedencia histórica, reproducción semántica y fachada pública sin regresiones
observadas en las comprobaciones relacionadas. No quedan hallazgos abiertos dentro del alcance de
esta verificación.

## Hallazgos verificados

### REV7A-01 — Media — RESUELTO — `core/runtime/narrative.py:606-629`

**Problema original.** Tras cualquiera de las tres barreras, `_append` recargaba la instancia pero
solo comparaba el tema objetivo. Un cambio concurrente en personaje, corpus, expediente, otro tema
o archivos estáticos podía pasar inadvertido.

**Verificación.** Bajo el cerrojo del tema, `_append.prepare` conserva la comparación específica
del tema y ahora exige además `again == instance` antes de construir y escribir el nuevo estado.
Así cubre toda la instancia estable que originó el prompt, mientras el cerrojo transitorio no forma
parte del valor cargado.

Las pruebas dirigidas ejercitan las tres operaciones con cambios concurrentes de personaje u otro
tema, un `instance update` durante el prompt, el cambio de vigencia `SÍ→NO` durante confirmación y
una recarga sin cambios. En los conflictos se conservan bytes y revisión y no queda cerrojo; sin
cambios se añade exactamente un evento. Cumple el criterio de resolución.

### REV7A-02 — Media — RESUELTO — `core/character/models.py:633-650`; `core/runtime/instance.py:975-1019`

**Problema original.** `sheet_check` consultaba el estado final del personaje y no demostraba que
la ficha citada existiera, estuviera aprobada, activa y vigente en
`NarrativeDraftRecord.character_revision`.

**Verificación.** `CharacterState.at_revision` selecciona los eventos explícitos hasta la revisión
solicitada, calcula los conceptos iniciales que rellenan los huecos y reconstruye un
`CharacterState`, por lo que sus invariantes se vuelven a reproducir. `_load_topics.sheet_check`
usa ese estado histórico con caché por `(personaje, revisión)` y exige ficha vigente, `ACTIVE`,
respuesta `APPROVED`, hash de staff, hash y composición de ficha y composición efectiva histórica.
Los cambios posteriores siguen permitidos porque la comprobación se hace en el corte citado.

Las falsificaciones autoconsistentes para revisiones 1 y 2 y, tras una ficha v2/propuesta aprobada,
para 4, 5 y 6 se rechazan; la revisión histórica real 3 sigue cargando. Cumple el criterio de
resolución.

### REV7A-03 — Media — RESUELTO — `core/memory/narrative.py:534-544,583-611`; `core/runtime/narrative.py`

**Problema original.** Las operaciones rechazaban versiones consecutivas semánticamente idénticas
de semillas y borradores, pero la reproducción/códec aceptaba esas historias imposibles.

**Verificación.** `seed_semantics` y `draft_semantics` definen en memoria la semántica compartida
por runtime y reproducción. `_replay` compara cada versión con la inmediatamente anterior del
mismo ID y rechaza igualdad semántica bajo el mismo contexto, ignorando solo los campos derivados
que deben variar por versión. Las pruebas construyen estados y sobres canónicos: los duplicados se
rechazan tanto al construir como al decodificar, mientras que un cambio de campo, contexto o ID se
acepta. Cumple el criterio de resolución.

### REV7A-04 — Baja — RESUELTO — `core/memory/__init__.py`; `core/runtime/__init__.py`

**Problema original.** La fachada `core.memory` no exponía el modelo/códec narrativo exigido por el
plan.

**Verificación.** `core.memory` declara todos los símbolos públicos narrativos y los resuelve de
forma perezosa mediante `__getattr__`; `core.runtime` conserva reexports de los mismos objetos. La
importación temprana de `core.character.models` sí demuestra el ciclo comunicado
(`models → provenance → core.memory.__init__ → narrative → models`), por lo que la carga perezosa
es una solución justificada y corrige la apreciación del informe anterior. Pruebas en procesos
limpios cubren los distintos órdenes de importación, `import *` e identidad de objetos. Cumple el
criterio de resolución.

## Regresiones relacionadas

- Las tres barreras mantienen prompts byte a byte, relectura del input, guards y ausencia de
  escritura en cancelación o conflicto. No se observó una ruta que omita la confirmación.
- La validación histórica se integra con la carga estricta de temas; no altera la validez de una
  referencia histórica real tras cambios posteriores.
- El comparador semántico usado al crear y al reproducir es único, evitando divergencia entre
  operación y códec.
- La fachada perezosa no cambia la identidad de los tipos exportados ni introduce dependencia de
  red, modelo, SQLite o adaptadores de publicación.

## Verificación ejecutada

- `py -3.14 -B -m unittest tests.test_narrative_workflow.BarrierTest
  tests.test_instance_update.NarrativeUpdateTest tests.test_narrative_state.HistoricalSheetTest
  tests.test_narrative_models.SemanticRepeatTest tests.test_narrative_models.FacadeTest -v`:
  18 OK.
- `py -3.14 -B -m unittest tests.test_character_state tests.test_narrative_models
  tests.test_narrative_state -v`: 45 OK.
- La suite completa aportada para esta versión da 588 OK tanto en Python 3.11 como en 3.14.
  Python 3.11 no está instalado en este entorno; no se repitió aquí la suite completa.
- `git diff --check`: limpio. Plantillas y `tests/expected_instance_templates.py` sin cambios
  sustantivos desde `620aea1`; `reference/` sin cambios.
- No se modificó código de producción ni pruebas durante esta verificación.

## Pendiente no bloqueante

Sigue sin ejecutarse la validación funcional manual con un TTY real ya declarada en el encargo;
las rutas de prompt están cubiertas por terminal falsa. No hay un hallazgo abierto asociado.
