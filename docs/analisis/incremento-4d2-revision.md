# Revisión 4d2 — propuestas citadas y composición efectiva

Versión revisada: estado de trabajo sin commit de
`feature/incremento-4-rebanada-vertical` sobre `67a7284`, a 2026-10-12. Se incluyeron en la
revisión los dos tests nuevos sin seguimiento.

## Veredicto

**APROBADO.** REV4D2-01 está resuelto. La reproducción del registro, los hashes, la evidencia, las
operaciones bajo cerrojo, la compatibilidad 4d1, los modelos y la CLI cumplen el plan en los
caminos revisados. No quedan hallazgos de código pendientes en 4d2.

## Hallazgos

### REV4D2-01 — Baja — RESUELTO — `core/character/models.py:333-358`; `tests/test_character_proposals.py:192-230`

**Problema y condición.** `ProposalView.__post_init__` comprueba que el valor de
`decision.review_status` coincida con `status`, pero no que la decisión corresponda a
`proposal`; tampoco comprueba que `base` sea la composición citada por esa propuesta. Por ello se
puede construir una vista `APPROVED` de `a v1` con la decisión válida de `b v1`, o mostrar como
base una composición de otro personaje, concepto o hash. Esto incumple la coherencia exigida al
modelo, aunque `_replay` actualmente le suministre objetos correctos.

**Evidencia.** Una reproducción dirigida construyó dos propuestas `a v1` y `b v1` y ejecutó
`ProposalView(a, ProposalStatus.APPROVED, decision_of_b, False, root)`: el constructor la aceptó y
devolvió una vista cuya clave de propuesta era `('a', 1)` y cuya decisión refería `('b', 1)`.
`test_views_and_applied_steps_must_be_coherent` cubre estados y decisiones de signo contrario,
pero no una decisión homónima de otra propuesta ni una base ajena.

**Corrección propuesta.** Validar los tipos de `proposal`, `decision` y `base`; para estados
decididos exigir `decision.matches(proposal)` además del mismo estado; y exigir que la base tenga
el mismo `character_id` y concepto y que `base.composition_sha256 ==
proposal.base_composition_sha256`. Añadir regresiones con decisión de otra clave/hash y con base
de otro personaje, concepto o composición. Mantener permitido `applied_to_effective=False` para
una aprobación histórica.

## Contraste de los criterios y preguntas

1. **Replay y registros manipulados.** `_replay` asigna a los conceptos, en orden v1..vN, las
   revisiones no ocupadas por propuestas o decisiones; rechaza revisiones explícitas duplicadas,
   fuera de rango o desordenadas. Una propuesta exige concepto y base vigentes y versión contigua.
   Una aprobación solo avanza si sigue siendo la versión mayor del ID, cita el concepto vigente y
   parte de la composición efectiva del instante; un rechazo admite cualquier propuesta anterior
   aún no decidida. Los estados finales y `applied_to_effective` se derivan exactamente desde el
   último concepto. No encontré un registro persistido manipulado que supere codec y replay.
2. **Hashes y evidencia.** `concept_root`, `_proposal_core`/`proposal_sha256` y
   `result_composition_sha256` usan `canonical_json_bytes(..., pretty=False)` y las claves exactas
   del plan. La evidencia de decisión incluye `character_id` y todas las claves persistidas salvo
   `evidence`; locator y segmentos se codifican como se exige. Las comparaciones de recarga
   recalculan los registros completos.
3. **Desviación 4d1.** Usar `_write_event` desde `_append_concept` es aceptable y necesario para
   recargar historiales con citas mediante el resolvedor único. Conserva el lock y el mismo guard
   antes de tomarlo, al tomarlo y antes de escribir, además del mensaje de conflicto de 4d1. Mover
   la inyección de carrera de `load_state` a `encode_state` prueba la misma frontera relevante:
   después de la recarga bajo lock y antes del guard final.
4. **Carreras, lock y liberación.** `add_proposal` construye sobre el snapshot inicial, toma el
   cerrojo, recarga la instancia completa, compara revisión y estado, vuelve a resolver citas y
   escribe un único evento. La decisión valida antes del prompt, evita nonce/escritura en retries,
   y tras la frase vuelve a pasar por la misma comparación y por el replay. Los fallos de replace
   y de retirada del lock conservan códigos y mensajes del cerrojo compartido. No observé una
   ventana adicional respecto de la limitación mínima ya documentada en 4d1.
5. **CLI, prompt y cobertura.** Los seis comandos, obligatoriedad, rechazo de `--json`, códigos
   2/3/4/5, formas JSON, texto, marcadores y frase del prompt coinciden con el plan byte a byte en
   el código y las pruebas. La carencia relevante de cobertura es la de REV4D2-01. Las pruebas del
   prompt usan los auxiliares compartidos que también cubren orden y rotulado de incertidumbres en
   `proposal show`; no vi otra ausencia que justifique un hallazgo.

## Verificación realizada

- Python 3.14, suites dirigidas solicitadas (propuestas, CLI, modelos, estado, CLI 4d1 e instancia):
  **115 OK**, 0 omitidas.
- Python 3.14, suite completa: **436 OK**, 9 omitidas por falta de permisos para crear symlinks;
  las pruebas 4d2 de junction de Windows sí se ejecutaron y pasaron.
- Reproducción directa de REV4D2-01: la vista incoherente fue aceptada.
- `git diff --check 67a7284`: limpio, salvo avisos informativos LF→CRLF.
- Rutas congeladas desde `67a7284`, nombres heredados y whitespace de los dos archivos nuevos:
  sin incidencias.
- Python 3.11 no está disponible en este entorno. Los **436 OK** comunicados para 3.11 y 3.14 y la
  prueba funcional por subprocess se toman como antecedente, no como verificación propia.

## Pendientes externos

- Sigue pendiente, como ya estaba previsto, la validación funcional de aprobación en una TTY real.

## Verificación de REV4D2-01 — 2026-10-12

**Resuelto.** `ProposalView.__post_init__` exige ahora una `CharacterProposal` y una
`EffectiveComposition` cuya identidad de personaje, concepto y hash coincidan con la base citada.
Para `APPROVED`/`REJECTED`, además del mismo estado, exige una `CharacterProposalDecision` y
`decision.matches(proposal)`. La comprobación no obliga a que toda aprobación esté aplicada, por
lo que una aprobación histórica con `applied_to_effective=False` conserva la semántica prevista.

La regresión nueva cubre la decisión de otra clave, la misma clave con otro hash, una composición
posterior, otro concepto, otro personaje y tipos ajenos; también fija el caso histórico válido. No
se observaron regresiones relacionadas en replay ni en los modelos.

Comprobaciones:

- Python 3.14, regresión nueva y suites relacionadas de propuestas, modelos y estado: **71 OK**.
- `git diff --check 67a7284`: limpio, salvo los avisos informativos LF→CRLF ya conocidos.
- Rutas congeladas desde `67a7284`: sin cambios.
- Suite completa de **437 OK** en Python 3.11 y Python 3.14: resultado aportado por el
  implementador. En este entorno solo está disponible Python 3.14, por lo que no se repitió la
  ejecución completa ni la de 3.11 en esta verificación focalizada.

## Sugerencias fuera de alcance

Ninguna.
