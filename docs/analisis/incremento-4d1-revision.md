# Revisión 4d1 — estado de personaje y declaración del concepto humano

Versión revisada: cambios sin commit de `feature/incremento-4-rebanada-vertical` sobre
`45f667a`, a 2026-10-12.

## Veredicto

**Aprobado.** REV4D1-01 y REV4D1-02 están resueltos. Las regresiones dirigidas demuestran que una
junction no desvía el estado del personaje y que ningún fallo de liberación del cerrojo queda sin
informar, conservando la semántica apropiada para cada tipo de excepción.

## Hallazgos

### REV4D1-01 — Alta — RESUELTO — `core/runtime/character.py:212-225`

**Problema original y condición.** `_append_concept` comprobaba `_linked_component(state_path)` antes de
entrar en `_corpus_lock`, pero no volvía a comprobar los componentes al adquirir el cerrojo ni justo
antes de `atomic_write_bytes`. Si otro proceso sustituye `characters/<id>` por una junction en esa
ventana, tanto el cerrojo como la lectura y la sustitución atómica siguen la junction. El core llega
a modificar un `state.json` externo a la instancia; la recarga posterior rechaza la junction, pero
lo hace después de la escritura. Esto incumple la revalidación exigida por 4d1 y la garantía de
destino seguro.

**Evidencia.** Reproducción dirigida en un temporal de Windows con Python 3.14: tras importar v1 se
sustituyó `characters/aria` por una junction justo al entrar en el cerrojo. El import de v2 terminó
con `CharacterError(INVALID_STATE)` al recargar, pero el estado externo pasó de revisión 1 a 2,
mientras el directorio original apartado permaneció en revisión 1. `test_junction_in_characters_is_rejected`
solo cubre una junction ya presente al cargar y `test_change_between_prompt_and_write` solo cambia
datos, no componentes de ruta; por eso la suite no detecta esta carrera.

**Criterio de resolución aplicado.** La adquisición del cerrojo y la escritura deben quedar ligadas a
componentes normales cuya identidad no pueda cambiar sin ser detectada; como mínimo, revalidar los
componentes en la propia frontera de adquisición y de nuevo bajo el cerrojo inmediatamente antes de
crear el temporal/reemplazar el estado. Añadir una prueba que sustituya un componente por junction
en esa ventana y demuestre que no se modifica el estado externo ni queda un lock fuera de la
instancia.

### REV4D1-02 — Media — RESUELTO — `core/runtime/assimilation.py:1393-1437`, `core/runtime/character.py:214-225`

**Problema original y condición.** El fallo al retirar el lock podía quedar oculto cuando el cuerpo
del contexto lanzaba un error distinto de `AssimilationError`; tras la primera corrección aún
ocurría con excepciones sin `code`/`reason`, como `RuntimeError`.

**Evidencia de resolución.** `_corpus_lock` reconstruye y encadena los errores con `code`/`reason`,
convierte `OSError` en `AssimilationError(IO)` y, para cualquier otro `BaseException`, usa
`exc.add_note(note)` antes de relanzar el mismo objeto. La regresión cubre `CharacterError`,
`PersistenceError`, `RuntimeError` y `KeyboardInterrupt`; en los dos últimos comprueba identidad y
que `__notes__` contiene el aviso y la ruta del cerrojo.

**Criterio de resolución aplicado.** Todo doble fallo informa que no se guardó el cambio, identifica
el lock huérfano y pide retirarlo manualmente. Los errores de dominio conservan tipo y código; las
excepciones restantes, incluidas las interrupciones, conservan tipo e identidad mediante una nota.

## Comprobaciones y valoración de las decisiones

- La CLI exige simultáneamente stdin y stdout TTY antes incluso del retry idempotente. Crear v1 o
  ampliar a N+1 siempre pasa por la frase exacta; el retry idéntico no escribe ni vuelve a retar,
  como pide el contrato. El prompt exacto y los prompts de 4c1 quedan cubiertos por aserciones
  byte a byte en tests anteriores no modificados. El estado no contiene nonce ni ruta de entrada.
- La publicación de v1 usa staging y publicación sin reemplazo solo en Windows, detecta el ganador
  de una carrera y limpia el staging. La escritura N+1 se serializa y relee estado e input; queda
  protegida por el guard verificado en REV4D1-01.
- `load_instance` mantiene cerrado el árbol estático y abre únicamente
  `characters/<id>/state.json` más el lock regular opcional. Rechaza IDs inválidos, extras,
  stagings, profundidad adicional, estados incoherentes y links/junctions ya presentes; ordena los
  personajes por ID. `work/integrity.json` y las plantillas permanecen sin cambios.
- Los modelos recalculan hash y tamaño desde el UTF-8 exacto y el decoder reconstruye recibo y
  evidencia para comparar el registro completo. Rechaza manipulaciones incoherentes y sobres no
  canónicos. Como en el contrato existente, los hashes son autoconsistencia, no autenticación: un
  actor capaz de reescribir coherentemente todos los hashes no queda criptográficamente impedido.
- Parametrizar `_corpus_lock` evita duplicación; su contrato de excepciones ya cubre los consumidores
  de asimilación y personaje, incluidos errores inesperados e interrupciones. La redacción «esta
  acción humana» describe mejor el uso compartido y no cambia los prompts. Que `instance init`
  repetido tras crear personajes dé `CONFLICT` es conservador: evita presentar como idempotente una
  materialización cuyo árbol ya contiene estado mutable no generado por `instance init`.
- Los tests cubren forma cerrada, manipulación de campos, secuencia, salidas exactas, idempotencia,
  locks ordinarios, las dos ventanas de junction y el doble fallo de liberación para errores de
  dominio, persistencia, ejecución e interrupción.

## Verificación

- **REV4D1-01: resuelto.** `_path_guard` captura la identidad de la carpeta y comprueba identidad y
  ausencia de links antes del lock, desde el propio lock y justo antes de escribir. Las dos
  regresiones sustituyen la carpeta por una junction al adquirir el lock y tras la lectura bajo el
  lock: ambas terminan sin cambiar la revisión 1 ni dejar cerrojo fuera. La ventana mínima posterior
  a la última comprobación está documentada y no reabre el caso reproducido por el hallazgo.
- **REV4D1-02: resuelto.** `CharacterError` y `PersistenceError` conservan tipo/código, encadenan el
  error original e informan el lock; `OSError` se convierte en `AssimilationError(IO)`. Los demás
  errores reciben el mismo aviso con `add_note` y se relanzan conservando tipo e identidad. La
  regresión verifica expresamente `RuntimeError` y `KeyboardInterrupt`, incluida la ruta en
  `__notes__`.
- El riesgo conocido de junctions en las mutaciones del corpus del workspace existe porque sus
  llamadas a `_corpus_lock` no pasan `guard`, pero es anterior y separable de 4d1; **no bloquea esta
  verificación específica** y queda pendiente para 4b–4c1.
- Segunda verificación dirigida en Python 3.14 (regresión nueva y liberación de locks de 4c1):
  **5 OK**; la verificación dirigida anterior quedó en **85 OK**. El entorno sigue sin Python 3.11,
  por lo que no se repitió aquí el resultado completo comunicado de 391 OK en 3.11 y 3.14.

## Sugerencias fuera de alcance

Ninguna.
