# Revisión 4f — recorrido vertical y contrato integrado

Versión revisada: estado de trabajo sin commit de
`feature/incremento-4-rebanada-vertical` sobre `24874f3`, a 2026-10-12. Se incluyeron los
archivos sin seguimiento de `tests/fixtures/vertical-neutral/` y `tests/test_vertical_slice.py`.

## Veredicto

**APROBADO.** REV4F-01 está resuelto. El recorrido funcional está completo, persiste entre
procesos, conserva el historial ante repeticiones y vigila las invocaciones prohibidas con alcance
de ejecución. Los fixtures son neutros, mínimos y están correctamente normalizados. No quedan
hallazgos pendientes en 4f.

## Hallazgos

### REV4F-01 — Media — RESUELTO — `tests/test_vertical_slice.py:42-86,103-138,177-184,289-302,319-377`

**Problema y condición.** `test_core_has_no_network_model_or_database_imports` usa una lista negra
de imports sobre todos los módulos presentes y futuros de `core/` como prueba de que este recorrido
no invoca red, modelo ni SQLite. Esa condición es más amplia que el contrato de 4f y no equivale a
él: rechaza por mera presencia `sqlite3` y `subprocess`, aunque el plan reserva SQLite para el
incremento 9 y `core/runtime/codex_cli_provider.py` para el 13, incluso si esas implementaciones no
participan en el recorrido manual. A la vez, no detecta una llamada a un proveedor de modelo sin
uno de esos imports, imports dinámicos, procesos lanzados mediante `os`, ni código ejecutado desde
`adapters/`.

El bloqueo dinámico tampoco cierra esa diferencia: en el hijo intercepta `connect`, `connect_ex` y
`create_connection`, y en las fases humanas solo `connect` y `create_connection`. Una salida como
`sendto`, un proceso externo o una excepción de bloqueo capturada por la ruta no deja una marca que
el test compruebe. Por tanto, la prueba puede fallar ante una dependencia opcional no recorrida y
puede pasar aunque una ruta prohibida intente una invocación no cubierta. La inspección del código
actual confirma que el recorrido presente no hace esas llamadas; el defecto está en el contrato de
regresión que 4f pretende fijar.

**Corrección.** Sustituir la prohibición global como criterio principal por vigilancia acotada a la
ejecución vertical, tanto en cada hijo de CLI como en las llamadas humanas del proceso padre.
Interceptar de forma verificable las salidas de red y procesos/proveedor de modelo relevantes; un
intento debe dejar un indicador comprobado o terminar el hijo de forma que no pueda ocultarlo un
`except`. Mantener, si se desea, una comprobación estática auxiliar limitada a la frontera que deba
permanecer pura, sin prohibir dependencias opcionales por el solo hecho de existir. Se dará por
resuelto cuando una invocación prohibida simulada haga fallar el recorrido incluso si la ruta
captura la excepción, mientras un módulo opcional no alcanzado no haga fallar 4f.

**Verificación.** Se eliminó la lista negra de imports y se añadieron audit hooks acotados a la
ejecución. Cada hijo registra el evento y termina mediante `os._exit(97)`; la prueba reproduce y
detecta intentos de socket, subprocess y SQLite aun rodeados por `except BaseException`. El hook
del padre permanece inerte fuera de `watched()` y registra un intento tragado durante una fase
humana. Todas las decisiones y el cierre, ambos conceptos, las decisiones de propuestas y la
respuesta de staff pasan por `human()`. Un paso hijo y uno padre limpios no registran eventos, y la
mera existencia de módulos opcionales no recorridos ya no se inspecciona ni falla. No observé una
regresión relacionada.

## Contraste de criterios y preguntas

1. **Reinicio e idempotencia.** Cada paso de agente se ejecuta en un intérprete nuevo mediante
   `runpy.run_module(..., alter_sys=True)`. Los helpers humanos recargan la instancia o workspace
   desde disco en cada llamada y, después de cada fase humana relevante, otra CLI nueva vuelve a
   leer el resultado. Esto demuestra persistencia entre fases sin depender de objetos del proceso
   de prueba. Las repeticiones cubren init de workspace, alta de candidato, decisión, cierre, init
   de instancia, concepto, alta de propuesta, rechazo, ficha y respuesta; comparan todos los bytes
   de workspace e instancia antes y después. La rama específica de retry de una aprobación ya está
   cubierta por `tests/test_character_proposals.py`. No hay una comprobación vacía en estos puntos.
2. **Recorrido y referencias.** Están presentes los ocho hitos pedidos: cuatro clases de candidato,
   siete decisiones aprobadas y una rechazada, cierre, instancia, concepto v1, dos propuestas sobre
   el mismo hash, aprobación que vuelve obsoleta la alternativa, rechazo posterior, composición,
   ficha v1 pendiente, concepto v2 con `STALE` derivado, ficha v2 y respuesta aprobada de staff.
   La igualdad exacta de `corpus_refs` de v1 incluye solo `normas` y `clima`, citadas por la
   propuesta aplicada; excluye tanto las citas de la propuesta rechazada como el candidato de
   asimilación rechazado. V2 queda sin referencias de corpus. Los modelos y el replay cargados en
   cada reinicio validan además concepto, `source_refs` y `context_refs`. La respuesta conserva la
   composición, los estáticos y `NOT_CONFIRMED`; las instrucciones coinciden byte a byte con v1.
   No falta un paso esencial del plan.
3. **Red, modelo y publicación.** El estado y la CLI prueban que no hay publicación: ambas fichas
   terminan `NOT_CONFIRMED`, los estáticos no cambian y las pruebas de parser existentes impiden un
   subcomando de publicación. Los audit hooks cubren durante el recorrido eventos de socket, URL y
   protocolos, procesos/ejecución del sistema, navegadores y SQLite; los procesos son la frontera
   prevista para el proveedor Codex CLI. Los intentos del hijo no pueden ser absorbidos y los del
   padre quedan registrados aunque la ruta capture la excepción. REV4F-01 queda resuelto.
4. **Fixtures.** Los quince archivos son JSON o Markdown, UTF-8 sin BOM, LF sin CR y LF final. Se
   copian junto con el expediente a un temporal externo antes de toda importación; los dos hashes
   se sustituyen solo en esa copia. Los cinco literales cubren las fuentes obligatorias del cierre
   y los otros tres candidatos aportan exactamente `INTERPRETATION`, `PROPOSAL` y `UNCERTAINTY`.
   Conceptos, propuestas, fichas y respuesta usan un foro/personaje genéricos y el dominio
   reservado `.example`; no contienen nombres, IDs ni ambientación del caso legado. Son adecuados
   para 4f.

## Verificación realizada

- Python 3.14, `tests.test_vertical_slice`: **5 OK**, 0 omitidas.
- Python 3.14, suite completa: **474 ejecutadas, 465 OK y 9 omitidas** por condiciones del entorno.
  El resultado aportado de 474 OK sin omitidas en 3.11 y 3.14 queda como antecedente; Python 3.11
  no está instalado en este entorno.
- Regresiones de guard: socket, subprocess y SQLite en hijo terminan con código 97 y marcador;
  socket capturado en padre queda registrado; pasos limpios no producen falsos positivos.
- Inspección del recorrido, helpers humanos, replay, creación de ficha y copia íntegra del snapshot
  cerrado.
- Comprobación byte a byte de los fixtures: UTF-8 sin BOM, CR=0 y LF final en todos.
- `git diff --check`: limpio, salvo avisos informativos LF→CRLF de Git.
- `git diff --name-only 24874f3 -- reference core tests/expected_instance_templates.py`: vacío.

## Pendientes

Ninguno.

## Sugerencias no bloqueantes

- Hacer explícitos en el test vertical el conjunto completo de siete candidatos del corpus y la
  vista `draft show` de v2 con su respuesta. Hoy esas propiedades ya quedan validadas por la copia
  exacta del snapshot, el retry de staff, el codec/replay y sus suites unitarias; las aserciones
  mejorarían la legibilidad del contrato integrado.
