# Revisión — incremento 1: procedencia y estados de revisión genéricos

## Alcance y veredicto

Revisado el estado de trabajo sin commit de `feature/incremento-1-procedencia-revision`, con base
`96eca81`, contra los pasos 1–6 y los criterios de aceptación del incremento 1 de `ANALISIS.md`,
los requisitos generales aplicables y el legado indicado.

**Veredicto: requiere cambios.** La separación estructural de vigencia, revisión y publicación es
correcta, no hay publicación/canon implícitos ni nombres específicos en `core/`, pero hay dos
defectos funcionales y una carencia de pruebas antes de aceptar el incremento.

## Defectos

### REV1-01 — Media — `core/memory/provenance.py:9-42`, `tests/test_provenance.py:49-55`

**Problema y condición:** `SourceRef` rechaza SHA-256 válidos escritos con hexadecimales en
mayúsculas. La decisión anotada en `ANALISIS.md:432-433` no estaba fijada por el plan (que pide 64
hexadecimales) y rompe la ingestión directa de la procedencia existente: los hashes de
`reference/migration-source/memory/events.jsonl`, por ejemplo líneas 1 y 14, están en mayúsculas.
Se activa al construir un `SourceRef` con cualquiera de esos valores; además, el test actual
convierte la incompatibilidad en comportamiento exigido.

**Evidencia:** reproducido con `SourceRef(..., sha256="A" * 64)`, que lanza `ValueError: sha256
must be 64 lowercase hexadecimal characters`. `events.jsonl:14` contiene
`52BC...D66F3F5`, un SHA-256 hexadecimal de 64 caracteres válido.

**Criterio de resolución:** aceptar hashes hexadecimales válidos sin depender de mayúsculas o
minúsculas y definir una representación canónica para comparar/serializar si se desea evitar
duplicados. Sustituir el test que exige rechazar mayúsculas por uno con al menos un hash real o
saneado en el formato del legado, manteniendo el rechazo de longitud o caracteres inválidos.

### REV1-02 — Media — `core/review/models.py:88-99,133-139`, `tests/test_review_models.py:199-206`

**Problema y condición:** `approve` y `reject` no pueden registrar una decisión acreditada sobre
una versión exacta si el borrador ya quedó `STALE` o `RETIRED`. Esto acopla revisión y vigencia y
hace el estado final depender del orden de observación: aprobar y después marcar obsoleto produce
`STALE + APPROVED`, pero marcar obsoleto y después recibir la misma aprobación la rechaza. Una
decisión humana es un hecho sobre esa versión; su vigencia para uso es la que debe quedar
controlada por el eje de ciclo de vida.

**Evidencia:** reproducido: `approve(mark_stale(draft, "CONTEXT_CHANGED"), 2, evidence)` lanza
`ReviewStateError`, mientras el constructor acepta la combinación coherente
`lifecycle=STALE`, `review_status=APPROVED`, su evidencia y su razón. La misma combinación también
es alcanzable invirtiendo las transiciones. El plan declara los ejes independientes y exige que
`STALE` conserve una aprobación previa; el legado no aporta una regla que invalide una aprobación
por llegar después de la marca de obsolescencia.

**Criterio de resolución:** permitir que `approve`/`reject` registren, con versión exacta y
`SourceRef`, una decisión todavía pendiente con independencia de `lifecycle`, preservando sin
cambios vigencia y publicación. Mantener la decisión única/definitiva para esa versión es
compatible con el alcance actual; una futura rectificación requeriría una transición/evento de
supersesión explícito, no reutilizar silenciosamente estas funciones.

### REV1-03 — Baja — `tests/test_review_models.py:135-138,199-217`

**Problema y condición:** los tests no fijan la decisión documentada de que
`confirm_publication` funciona en cualquier ciclo de vida. Todos la invocan mientras el borrador
está `ACTIVE`; por tanto, una regresión que añadiera el mismo bloqueo por ciclo de vida que hoy
tienen `approve`/`reject` dejaría pasar las 34 pruebas. Tampoco existe un caso positivo de decisión
humana recibida después de `STALE`/`RETIRED`, que será necesario al resolver REV1-02.

**Evidencia:** `test_publication_can_be_recorded_without_prior_approval` solo cubre el estado de
revisión; `test_stale_keeps_previous_approval_and_publication` y `test_three_axes_coexist` publican
antes de llamar a `mark_stale`. Los 34 tests pasan aunque no se compruebe publicación sobre
`STALE` ni `RETIRED`.

**Criterio de resolución:** añadir casos que confirmen publicación directamente sobre `STALE` y
`RETIRED`, verificando versión/evidencia y que los demás ejes no cambian; añadir casos positivos
equivalentes para `approve`/`reject` tras resolver REV1-02. Los casos deben fallar si reaparece una
restricción cruzada por ciclo de vida.

## Respuestas a las preguntas concretas

1. Las funciones sí exigen coincidencia de `expected_version` y evidencia `SourceRef`, y las
   transiciones no publican ni canonizan implícitamente. El constructor permite hidratar todas las
   combinaciones coherentes de los tres ejes; la asimetría problemática es que acepta
   `STALE/RETIRED + APPROVED/REJECTED`, mientras las funciones impiden registrar esa misma decisión
   si la vigencia cambió primero (REV1-02). La asociación de la evidencia con la versión queda
   representada por el `DraftVersion` que la contiene; su contenido semántico no puede validarse
   estructuralmente con el `SourceRef` actual.
2. Es correcto que una decisión sea definitiva para una versión de contenido dentro del contrato
   actual, y correcto registrar publicación acreditada en cualquier estado: el legado permite
   importar texto ya publicado sin aprobación redundante (`instructions/memoria.md:9`). No es
   correcto bloquear `approve`/`reject` por `STALE`/`RETIRED`; eso mezcla la acreditación histórica
   de revisión con la elegibilidad vigente del borrador. Confirmar publicación en cualquier estado
   está bien implementado, pero falta probarlo (REV1-03).
3. Los tests cubren nominalmente todos los puntos enumerados en el paso 5 y detectan las
   regresiones principales de versión/evidencia y efectos implícitos. No cubren toda la conducta
   añadida en las notas ni fallarían ante una restricción de publicación a `ACTIVE` (REV1-03). El
   test de SHA-256, además, protege actualmente una decisión incompatible con la procedencia del
   legado (REV1-01).

## Sugerencias no bloqueantes

Ninguna.

## Verificación realizada

- `py -3.14 -B -m unittest discover -s tests -v`: **34 OK**.
- Python 3.11 no está disponible en el entorno actual (`py -0p` solo enumera 3.14), por lo que no
  se pudo repetir aquí; se toma como evidencia aportada el resultado previo de **34 OK** en 3.11.
- Búsqueda de nombres/IDs prohibidos en `core/`: sin coincidencias.
- `git diff --check`: limpio, con la salvedad de que Git no incluye archivos sin versionar en ese
  diff.
- Rama y base verificadas: `feature/incremento-1-procedencia-revision`, merge-base
  `96eca81d5337e7d8af6dfd58d8dcd304486e634d`.
- `git status --short` antes del informe: únicamente `ANALISIS.md`, `core/` y `tests/` sin
  versionar; ninguna ruta bajo `reference/` modificada.

## Verificación

Verificación de REV1-01..03 sobre el mismo estado de trabajo sin commit, rama
`feature/incremento-1-procedencia-revision` y base `96eca81`.

- **REV1-01 — Resuelto.** `SourceRef` acepta las dos cajas hexadecimales y normaliza a minúsculas;
  se comprobó con un hash en el formato de `events.jsonl` que las referencias creadas desde
  mayúsculas y minúsculas son iguales. Los tests mantienen el rechazo de longitud, caracteres,
  cadena vacía y tipo inválidos.
- **REV1-02 — Resuelto.** `_check_decidable` conserva las comprobaciones de versión, evidencia y
  revisión pendiente, pero ya no condiciona la decisión al ciclo de vida. Los casos `STALE`,
  `RETIRED` y `RETIRED` procedente de `STALE` preservan ciclo, razón y publicación; la comprobación
  dirigida confirmó además que decisión y publicación pueden registrarse juntas en esos estados.
- **REV1-03 — Resuelto.** Los nuevos tests ejercitan decisión posterior a `STALE`/`RETIRED`,
  independencia del orden con `mark_stale` y publicación directa sobre `STALE`, `RETIRED` y
  `RETIRED` procedente de `STALE`, incluida la versión incorrecta y la conservación de los otros
  ejes. Fallarían si reapareciera el bloqueo cruzado que motivó el hallazgo.

**Veredicto final: aprobado; REV1-01, REV1-02 y REV1-03 están resueltos y no se observaron
regresiones relacionadas.**

Comprobaciones de esta verificación:

- `py -3.14 -B -m unittest discover -s tests -v`: **37 OK**.
- Comprobación dirigida de hash canónico y transiciones combinadas en los tres ciclos inactivos:
  **OK**.
- Búsqueda de nombres/IDs prohibidos en `core/`: sin coincidencias.
- Rama y merge-base: correctos; ninguna ruta bajo `reference/` aparece modificada.
- El launcher visible en este sandbox solo enumera Python 3.14; no se repitió 3.11 aquí. Se
  conserva como evidencia aportada el resultado de **37 OK** en Python 3.11.
