# Revisión del sub-incremento 4c1

## Alcance y versión

- Rama: `feature/incremento-4-rebanada-vertical`.
- Base y `HEAD`: `91205fcb406c72fc8b66ba81ca566faf1a0569a2`; cambios revisados sin commit.
- Contrato contrastado: apartado 4c1 de `ANALISIS.md`, incluida la barrera A y su límite aceptado.

## Veredicto

**APROBADO.** REV4C1-01, REV4C1-02, REV4C1-03 y REV4C1-04 están resueltos. No quedan hallazgos
pendientes de esta revisión; se mantiene únicamente la validación manual ya acordada de los éxitos
CLI en una TTY real.

## Defectos

### REV4C1-01 — Alta — La segunda lectura no impide una actualización perdida

- **Ubicación:** `core/runtime/assimilation.py:1268-1288`, `core/runtime/assimilation.py:1321-1336`,
  `core/runtime/assimilation.py:1354-1358`; primitiva usada en
  `core/runtime/persistence.py:67-85`; cobertura actual en
  `tests/test_assimilation_decisions.py:291-298`.
- **Problema y condición:** decisión y cierre recargan y validan el corpus después de la
  confirmación, pero no mantienen exclusión ni realizan compare-and-swap entre esa carga y
  `os.replace`. Si otro proceso completa una mutación válida en esa ventana, el primer proceso
  escribe contenido derivado del estado anterior con la misma revisión siguiente y elimina en
  silencio la mutación concurrente. En cierre, además, puede quedar un cierre válido en apariencia
  tras haber descartado una versión que llegó a existir.
- **Evidencia:** reproducción focalizada en Python 3.14, insertando una alta válida de `formato v2`
  justo al entrar en `_write_corpus`, después de la segunda lectura. Tanto al decidir como al
  cerrar, la operación exterior terminó con éxito y `v2_preserved=False`; el cierre quedó grabado
  (`closure=True`) sobre el snapshot anterior. El test concurrente actual muta dentro de
  `read_line()`, antes de la segunda carga, por lo que no ejercita esta ventana.
- **Criterio de resolución:** serializar mediante una exclusión interproceso común, o aplicar un
  compare-and-swap realmente atómico, a todas las mutaciones de `corpus/state.json`
  (`add_candidate`, decisiones y cierre). Una revisión cambiada entre validación y commit debe
  producir `CONFLICT`, conservar íntegra la escritura ganadora y no grabar decisión ni cierre.
  Añadir regresiones deterministas para la ventana posterior a la segunda lectura, al menos en
  decisión y cierre.

### REV4C1-02 — Media — El límite aceptado de la barrera A no está en docstrings ni mensajes

- **Ubicación:** `core/runtime/assimilation.py:1110-1114`,
  `core/runtime/assimilation.py:1131-1138`, `core/runtime/assimilation.py:1236-1240`,
  `core/runtime/assimilation.py:1292-1295`, `core/runtime/cli.py:120-139` y
  `core/runtime/cli.py:357-375`.
- **Problema y condición:** la advertencia correcta —un `Terminal` falso, una pseudo-TTY o un core
  modificado eluden la barrera y esta no es una garantía criptográfica de humanidad— aparece solo
  en un comentario de implementación y en `ANALISIS.md`. Los docstrings públicos afirman que la
  confirmación la teclea una persona y el `Terminal` incluso dice que no hay forma de suministrar el
  código; la ayuda de CLI dice «solo la persona». Quien consulte la API, su documentación o la
  ayuda recibe una garantía más fuerte que la acordada.
- **Evidencia:** búsqueda focalizada de `fake Terminal`, `pseudo`, `criptogr` y `garant`: en código
  ejecutable/documentable solo aparece el comentario de las líneas 1110-1114; no aparece el límite
  en los docstrings ni en mensajes de usuario. Esto incumple expresamente el paso 17 de 4c1.
- **Criterio de resolución:** documentar en los docstrings públicos y en un mensaje o ayuda visible
  que la barrera bloquea el camino CLI automatizado normal, pero no autentica a una persona y puede
  ser eludida con `Terminal` falso, pseudo-TTY o modificación del core. Las pruebas deben fijar el
  texto elegido sin presentar la barrera como seguridad fuerte.

## Sugerencia no bloqueante

### REV4C1-03 — Baja — `candidate list/show` presenta `PENDING_HUMAN_REVIEW` tras decidir

- **Ubicación:** `core/runtime/cli.py:291-351`.
- **Problema y condición:** esos comandos muestran el `review_status` inmutable del registro del
  candidato, que siempre es `PENDING_HUMAN_REVIEW`, sin mostrar la decisión efectiva. Después de
  aprobar o rechazar, una persona que consulte el candidato puede creer que sigue pendiente; solo
  `decision list` aclara el estado.
- **Evidencia:** `_candidate_summary`, `_candidate_record` y `_candidate_line` no cruzan
  `workspace.decisions`. Es coherente con el modelo persistido de 4b y no incumple por sí solo un
  criterio de aceptación de 4c1, por lo que se clasifica como mejora de presentación.
- **Criterio de resolución:** sin mutar el candidato histórico, mostrar o etiquetar por separado la
  decisión efectiva en texto y JSON, o indicar de forma inequívoca que el campo es el estado del
  registro original y remitir a `decision list`.

## Respuestas a las preguntas de revisión

1. **Barrera CLI y nonce.** No encontré un camino de la CLI que cree una decisión o cierre sin
   `stdin` y `stdout` TTY y sin la frase exacta. No hay flags equivalentes, los valores de entorno
   probados no intervienen y `--json` se rechaza antes de cargar el workspace o crear el reto. La
   API exige interactividad antes de validar/cargar y el nonce se crea solo después de descartar
   errores, conflictos, cierre e idempotencia; los reintentos íntegros no crean nonce ni escriben.
   No se persiste el nonce en claro: se persiste, conforme al contrato, el SHA-256 de la frase que
   lo contenía. El `Terminal` falso y la pseudo-TTY siguen siendo el límite aceptado, no una ruta
   CLI ofrecida por el producto.
2. **Recarga y cancelaciones.** La recarga detecta cambios ocurridos hasta esa lectura, pero no los
   que ocurren después: véase `REV4C1-01`. EOF, frase errónea y `KeyboardInterrupt` durante la
   lectura no alcanzan la escritura. Si Ctrl+C llega una vez iniciada la sustitución, la garantía es
   solo estado anterior o nuevo por archivo, tal como ya documenta la persistencia; no una promesa
   de «nunca escribe» después de aceptar la frase.
3. **Decodificación.** `decode_candidate_state` comprueba claves exactas, candidatos y hashes
   recalculados, correspondencia exacta y unicidad de decisiones, recibos, evidencia recalculada,
   `base_revision + 1 == revision`, snapshot vigente y precondiciones de cierre. Las manipulaciones
   cubiertas vuelven a codificar el sobre y fallan cerrado. Como ya establece el diseño, los hashes
   no autentican frente a alguien que pueda modificar el core o recomputar también toda la cadena
   interna; ese límite debe quedar expuesto según `REV4C1-02`.
4. **Cierre.** La selección de máximas versiones, decisiones obligatorias solo para vigentes,
   cobertura de cada sección `PROVIDED` por un `LITERAL` vigente y aprobado, y exclusión de
   `REJECTED`/`UNCERTAINTY` son correctas. Las pendientes sustituidas no bloquean. El cierre es
   terminal y los reintentos íntegros conservan historial, salvo la pérdida concurrente descrita en
   `REV4C1-01`.
5. **Decisiones de detalle.** El orden anotado coincide con el plan: TTY primero, validación del
   estado, idempotencia antes del cierre y nonce solo para mutaciones nuevas. Es razonable que una
   decisión idéntica siga siendo idempotente tras cerrar. El riesgo de presentación de
   `candidate list/show` es real pero no bloqueante; queda como `REV4C1-03`.
6. **Calidad de pruebas.** Las pruebas ejercitan de forma útil prompts y respuestas exactas,
   cancelaciones, TTY, ausencia de bypasses, integridad, precondiciones, historial e idempotencia.
   Fallarían ante muchas regresiones reales, pero no ante la ventana entre segunda lectura y
   reemplazo (`REV4C1-01`). Los éxitos de la CLI real siguen pendientes de la validación manual en
   una TTY real, según lo acordado.

## Verificación de correcciones

### REV4C1-01 — RESUELTO

`add_candidate` toma el cerrojo durante toda la operación; decisión y cierre lo toman antes de la
segunda lectura y lo mantienen hasta terminar la escritura. Por tanto, todos los mutadores
cooperantes comparten la misma exclusión y ya no existe la ventana que permitía pisar una revisión
válida. Las tres regresiones de `LockTest` intentan una mutación justo antes de `_write_corpus` en
alta, decisión y cierre: el intruso recibe `CONFLICT` y la escritura ganadora queda íntegra. El
cerrojo no se mantiene mientras se espera la frase y un cerrojo existente bloquea antes del prompt.

`load_workspace` sigue funcionando durante un cerrojo —la lectura del estado es atómica— y esta
conducta queda ejercitada por `LockTest`. La creación e idempotencia normal del workspace siguen
cubiertas por la suite completa; un `.lock` presente hace que un `init` concurrente no considere el
árbol idéntico, lo que es un fallo conservador y no sobrescribe el workspace.

### REV4C1-02 — RESUELTO

El comentario de sección y los docstrings de `Terminal`, `record_candidate_decision` y
`close_assimilation` indican que la barrera no autentica a una persona y que un terminal falso o
pseudo-TTY puede eludirla. La ayuda de `approve`, `reject` y `close` expone el mismo límite. Las
pruebas de `BarrierLimitDocumentationTest` fijan ambos contratos.

### REV4C1-03 — RESUELTO

`candidate list` muestra la decisión efectiva en texto y JSON; `candidate show` muestra pendiente o
la decisión con su evidencia y añade el resumen separado en JSON. El `review_status` histórico del
candidato permanece intacto. `EffectiveDecisionDisplayTest` cubre candidatos decididos y
pendientes, y los tests de 4b fijan las nuevas claves.

### REV4C1-04 — RESUELTO

`_release_lock` considera retirado un archivo ya ausente y comunica cualquier otro fallo de
`unlink`. Tras un cuerpo correcto, `_corpus_lock` devuelve `IO` indicando que el cambio se guardó y
nombrando el cerrojo que debe borrarse; tras un `AssimilationError`, conserva el código, incorpora
el motivo original, declara que no se guardó ningún cambio y mantiene el error original como causa.
Los demás `BaseException` intentan liberar y se propagan. Un fallo de `os.close` también intenta la
retirada y devuelve `IO`, nombrando el archivo cuando permanece.

`LockReleaseTest` cubre fallo de retirada después de escritura correcta y fallida, revisión y bytes
resultantes, causa original y los dos casos de fallo de `close`. Una comprobación focalizada
adicional confirmó que `KeyboardInterrupt` dentro del cuerpo se propaga, retira el lock y conserva
el estado, y que un lock ya ausente cuenta como liberado. No se encontraron regresiones nuevas.

### Pruebas y limitaciones de esta verificación

- `py -3.14 -B -m unittest -q tests.test_assimilation_decisions tests.test_assimilation_decision_cli`:
  **43 OK**.
- Suite completa con Python 3.14: **295 OK, 9 omitidos**. Los nueve son pruebas de symlinks
  omitidas porque este usuario de Windows no puede crearlos; no pude reproducir localmente el
  resultado comunicado de cero omitidos.
- Python 3.11 no está instalado/visible para `py`; no pude repetir esa ejecución.
- Comprobaciones focalizadas externas: rutas `KeyboardInterrupt` y lock ya ausente correctas.
- `git diff --check`: limpio; `git diff --name-only 91205fc -- reference`: sin salida; búsqueda de
  nombres del legado en el alcance 4c1: sin coincidencias.
- No se repitió el éxito de CLI en una TTY real; sigue siendo la validación manual ya identificada.
