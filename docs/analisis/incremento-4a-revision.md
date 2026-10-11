# Revisión — incremento 4a: workspace externo e importación manual

## Alcance y veredicto

Revisado el estado de trabajo sin commit de `feature/incremento-4-rebanada-vertical`, con base
`42e724a95157b704ac5b5033675a75f8bf50915e`, contra «Persistencia provisional e integridad», los
pasos 1–16 y los criterios de aceptación de 4a en `ANALISIS.md`.

**Veredicto: requiere cambios.** El camino nominal crea de una vez un workspace completo, conserva
los bytes del expediente y materiales, valida la forma canónica y los hashes, detecta ediciones
simples, y el retry idéntico no altera los archivos. Los comandos y códigos nominales también son
correctos y no existe una vía de instancia o publicación. Quedan, sin embargo, dos elusiones de la
frontera de rutas en Windows, una carrera que clasifica como E/S un conflicto de destino, un
contrato JSON distinto del especificado y limpieza silenciosamente incompleta ante un segundo
fallo del sistema de archivos.

## Defectos

### REV4A-01 — Alta — `core/runtime/workspace.py:186-206,316-359,423-437`; `tests/test_assimilation_workspace_cli.py:98-131`; `tests/test_workspace_persistence.py:286-319`

**Problema y condición:** las comprobaciones comparan rutas `WindowsPath` sin llevar todos sus
alias a una identidad común y solo consultan `is_symlink()`. Una ruta extendida
`\\?\D:\...\roleplay-agent-core\hijo` no se considera relativa al mismo checkout escrito como
`D:\...\roleplay-agent-core`, por lo que permite crear el workspace dentro del repositorio. Una
junction en el último componente tampoco es un symlink para `pathlib`: como destino existente y
vacío, `create_workspace` la elimina y la sustituye por el workspace; dentro de uno ya creado,
`load_workspace` admite que `dossier/` sea una junction a una carpeta externa con los mismos
bytes. Esto incumple tanto el rechazo del destino enlazado/solapado como el rechazo de escapes en
los hijos gestionados.

**Evidencia:** en Python 3.14, `_check_destination` aceptó la ruta hipotética
`\\?\D:\Development\roleplay-agent-core\no-crear-aqui`; no se materializó nada dentro del repo.
En un temporal externo se creó una junction vacía: `is_symlink()==False`, `is_junction()==True`, y
`create_workspace` devolvió `created=True`, sustituyó la junction y dejó intacto su destino real.
En otro workspace temporal se sustituyó `dossier/` por una junction a una copia externa;
`load_workspace(..., expected_core_root=...)` la aceptó como íntegra. Las diferencias de
mayúsculas sí se rechazaron. El volumen no expone un alias 8.3 para este checkout, de modo que ese
caso concreto no pudo reproducirse; la corrección debe cubrirlo expresamente. Los tests solo
intentan un symlink POSIX/Windows ordinario, que además quedó omitido en esta sesión, y no cubren
junctions ni `\\?\`.

**Criterio de resolución:** comparar checkout, expediente y destino mediante una representación
Windows canónica que unifique prefijos de dispositivo, mayúsculas y alias 8.3 de los componentes
existentes; rechazar explícitamente cualquier reparse point —incluidas junctions— en el root,
destino y cada componente gestionado, con una solución compatible con Python 3.11. Añadir
regresiones Windows para `\\?\`, junction de destino y junction interna hacia fuera; ninguna debe
crear, sustituir ni cargar el workspace.

### REV4A-02 — Media — `core/runtime/workspace.py:243-273`; `tests/test_workspace_persistence.py:236-253`

**Problema y condición:** si el destino no existía durante `_check_destination` pero otro actor
crea allí una carpeta antes de `os.replace`, no hay una segunda comprobación del caso inicialmente
ausente. En Windows, el replace falla y el error se transforma en `WorkspaceError(code="IO")`,
aunque el contrato exige `CONFLICT` ante cualquier diferencia y reserva `IO` para fallos de E/S.
Un init concurrente idéntico tampoco llega a reconocerse como retry idempotente.

**Evidencia:** se forzó de forma determinista la aparición de una carpeta vacía justo al entrar en
`os.replace`: el resultado fue `IO`; el destino quedó vacío y no quedó staging. El test actual
solo simula un `os.replace` fallido sin crear un competidor y, por tanto, fija el código `IO` pero
no esta carrera.

**Criterio de resolución:** tratar la aparición/cambio concurrente del destino como conflicto,
sin sobrescribirlo; si el competidor terminó un árbol idéntico, permitir el resultado idempotente
sin escribir. Añadir una prueba que inserte un destino vacío y otra con contenido entre la
validación y el rename, y comprobar `CONFLICT`, ausencia de workspace parcial y limpieza del
staging.

### REV4A-03 — Media — `core/runtime/cli.py:103-107`; `ANALISIS.md:540-547`; `tests/test_assimilation_workspace_cli.py:98-192`

**Problema y condición:** los errores de aplicación en modo JSON emiten las claves `action`,
`error` y `reason`, mientras el contrato común exige exactamente
`{"ok":false,"code":"<código>","message":"<texto>"}`. Cualquier consumidor que siga el contrato
no encuentra `code` ni `message`. La nota de implementación registra la desviación, pero no hay
una decisión aprobada que reemplace el requisito.

**Evidencia:** `assimilation status` sobre un workspace ausente devolvió código 3 y
`{"action":"assimilation.status","error":"INVALID_STATE","ok":false,"reason":"..."}`. Los
tests consultan `error` y por ello protegen la forma divergente en lugar del contrato.

**Criterio de resolución:** emitir en todos los errores de aplicación JSON exactamente `ok`,
`code` y `message`, conservando un único objeto en stdout y el código de proceso correspondiente;
ajustar las pruebas de códigos 3, 4 y 5 para comparar el objeto completo. Si se desea conservar
`action`, debe cambiarse antes el contrato de forma explícita.

### REV4A-04 — Baja — `core/runtime/persistence.py:76-93`; `core/runtime/workspace.py:243-272`; `tests/test_workspace_persistence.py:94-103,240-253`

**Problema y condición:** la limpieza de temporales y staging es solo best effort y oculta todos
sus errores: `atomic_write_bytes` ignora el `OSError` de `unlink` y `_materialize` usa
`shutil.rmtree(..., ignore_errors=True)`. Si el replace falla y Windows niega después el borrado
por un handle abierto, antivirus o permisos cambiados, se devuelve únicamente el error original y
queda basura sin informar, pese a la promesa de limpieza.

**Evidencia:** al simular fallo de `os.replace` seguido de fallo de `os.unlink`, quedó un
`.state.json.*.tmp`; al simular que `rmtree` no pudo retirar el árbol, quedó
`.ws.staging-*`. Los tests comprueban la limpieza solo cuando la eliminación secundaria funciona.

**Criterio de resolución:** intentar la limpieza sin ocultar su resultado; si no puede
completarse, informar la ruta conocida y conservar una causa diagnóstica sin poner en riesgo el
destino anterior. Añadir regresiones de fallo secundario para temporal y staging. Si la garantía
pretendida es deliberadamente best effort, limitar así el contrato y documentar el residuo
posible.

## Respuestas a las preguntas concretas

1. La escritura atómica por archivo conserva el destino anterior ante un fallo normal de
   `os.replace`; el staging se valida antes del rename y el camino probado no deja un workspace
   parcial. El retry idéntico actual compara todo el árbol y no escribe; cualquier diferencia
   estable produce `CONFLICT`. REV4A-02 recoge la carrera que da `IO`, y REV4A-04 la limpieza que
   puede dejar residuo ante un segundo fallo. No observé una ruta nominal que trunque o pise un
   archivo existente.
2. Padre ausente, archivo en vez de carpeta, carpeta no vacía, solapamiento normal, mayúsculas y
   symlink ordinario están contemplados; el último no pudo ejecutarse aquí. `\\?\` y junctions
   eluden la protección según REV4A-01. No había nombre corto 8.3 disponible para probarlo; debe
   quedar cubierto por la misma canonicalización, no por una suposición sobre el volumen.
3. `load_workspace` exige JSON canónico, claves exactas, lista ordenada, tamaños/hashes, expediente
   recargable y el sobre canónico/autohasheado del corpus; las ediciones simples dan
   `INVALID_STATE`, y un core distinto da `CONFLICT`. La comparación byte a byte de `load_state`
   es coherente con el formato canónico exigido. Un actor que recalcula coherentemente los hashes
   queda fuera de la garantía declarada de autenticidad. La excepción relevante es la junction
   gestionada de REV4A-01.
4. Los códigos nominales 0/2/3/4/5, las salidas de éxito, stderr en modo texto y la ausencia de
   `instance`, `publish`, `send` y `post` cumplen. La forma de error JSON no cumple
   (REV4A-03). `argparse` conserva su salida propia para errores de uso, conforme al código 2.
5. Importar `_HEADINGS` privado es tolerable solo como deuda transitoria dado que el plan prohibía
   cambiar `assimilation.py`; conviene exponer una API pública antes de que otro adaptador dependa
   de ella. Que la CLI sea la raíz de composición y dependa de `adapters.manual` no crea un ciclo
   actual y es aceptable. La validación byte a byte del estado fortalece el formato canónico. Usar
   `Path.absolute()` conserva el último componente para detectarlo, pero no resuelve los alias
   Windows de REV4A-01. Considerar `CONFLICT` un retry después de avanzar el corpus es correcto:
   ya no es el mismo estado inicial y evita presentar una inicialización distinta como
   idempotente.
6. Los tests sí fallarían ante regresiones del camino nominal: bytes copiados, layout, hashes,
   edición simple, fallo ordinario de replace, retry estable, códigos principales y comandos
   prohibidos. No fallarían ante REV4A-01, REV4A-02 o REV4A-04; los de JSON actualmente consagran
   REV4A-03. Tampoco hay un caso específico para retry con `corpus_revision > 0`, y la prueba de
   «sin escrituras» observa bytes/mtime de archivos, no llamadas de escritura ni mtime de
   directorios.

## Sugerencias no bloqueantes

- Sustituir en un incremento próximo el import privado `_HEADINGS` por un nombre público del
  contrato de expediente; no requiere duplicar el mapa.
- Añadir una prueba explícita del retry tras avanzar el corpus y vigilar operaciones de escritura
  o metadatos de directorio, para fijar la decisión ya documentada de devolver `CONFLICT` sin
  staging incidental.

## Verificación realizada

- `py -3.14 -B -m unittest tests.test_workspace_persistence tests.test_manual_adapter
  tests.test_assimilation_workspace_cli -v`: **47 ejecutados; 46 OK y 1 omitido** por falta de
  permisos para crear symlinks.
- `py -3.14 -B -m unittest discover -s tests -v`: **192 ejecutados; 183 OK y 9 omitidos** por la
  misma limitación de symlinks.
- Python 3.11 no está instalado en esta sesión (`py -0p` solo enumera 3.14). Se toma como evidencia
  aportada la ejecución previa de **47/192 OK, 0 omitidos** en Python 3.11 y 3.14, pero no se pudo
  reproducir aquí el «0 omitidos».
- Reproducciones dirigidas, todas en temporales externos: aceptación de `\\?\` por la comprobación
  sin crear dentro del repo; junction de destino aceptada y sustituida; junction gestionada hacia
  fuera aceptada por `load_workspace`; carrera del destino → `IO`; fallos secundarios de limpieza
  → temporal y staging residuales. La comparación con distinta capitalización sí dio
  `UNSAFE_DESTINATION`.
- `rg` de nombres del legado: sin coincidencias. `git diff --name-only 42e724a -- reference`: sin
  salida. `git diff --check`: limpio. Rama y base coinciden con las indicadas.

## Verificación

Verificación de REV4A-01..04 sobre el mismo estado de trabajo sin commit, rama
`feature/incremento-4-rebanada-vertical` y base
`42e724a95157b704ac5b5033675a75f8bf50915e`.

- **REV4A-01 — Resuelto.** `_identity` unifica los prefijos de dispositivo, resolución física,
  nombres largos y capitalización; `_contains` compara contención sin confundir unidades. La
  detección por `S_ISLNK` o por el bit *name surrogate* del `st_reparse_tag` rechaza symlinks y
  junctions en destino, root, componentes gestionados, recorrido del expediente y retry. Los
  tests Windows y la ejecución directa confirmaron el rechazo de `\\?\`, variante de mayúsculas,
  junction de destino, junction interna hacia fuera y padre-junction que desemboca en el repo.
  Permitir otros reparse points es una decisión correcta para 4a: el bit *name surrogate* es el
  que identifica sustitución de ruta, mientras un placeholder de nube no crea por sí mismo un
  alias de contención. El riesgo anotado en loaders anteriores queda fuera de estos cuatro
  hallazgos y no se reabre aquí.
- **REV4A-02 — Resuelto.** La rama de fallo del rename inspecciona el destino creado por otro
  actor sin sobrescribirlo: contenido distinto produce `CONFLICT` y queda intacto; un árbol
  idéntico devuelve `created=False`. También se reclasifica como conflicto la reocupación de un
  destino que estaba vacío. Las dos carreras nuevas pasaron y no dejaron staging cuando la
  limpieza funcionó.
- **REV4A-03 — Resuelto.** `_fail` emite exactamente las claves `ok`, `code` y `message`; los
  tests comprueban forma y códigos 3, 4 y 5. La reproducción del error de estado confirmó un solo
  objeto JSON en stdout con el contrato esperado.
- **REV4A-04 — Resuelto.** La rama concurrente ya no retorna dentro del `try`: conserva el
  workspace idéntico y el `OSError` del replace, comprueba después el resultado de
  `_remove_staging` y solo devuelve `created=False` cuando la limpieza termina. Si queda residuo,
  lanza `WorkspaceError(code="IO")`, incluye una sola vez la ruta del staging y conserva aquel
  `OSError` en `__cause__`; el workspace instalado por el otro actor permanece íntegro y cargable.
  Un `CONFLICT` de `_existing` continúa por el manejador general, que limpia o informa el residuo
  una sola vez. La regresión combinada reprodujo ambas condiciones y pasó.

Comprobaciones de esta verificación:

- `py -3.14 -B -m unittest tests.test_workspace_persistence tests.test_manual_adapter
  tests.test_assimilation_workspace_cli -q`: **58 ejecutados; 57 OK y 1 omitido** porque este
  usuario no puede crear symlinks ordinarios. Las cinco pruebas de junction sí se ejecutaron y
  pasaron mediante `_winapi.CreateJunction`.
- `py -3.14 -B -m unittest discover -s tests -q`: **203 ejecutados; 194 OK y 9 omitidos** por la
  misma limitación histórica de symlinks; el resto pasó.
- Python 3.11 sigue sin estar instalado en esta sesión (`py -0p` solo enumera 3.14). Se toma como
  evidencia aportada la ejecución corregida de **203 OK, 0 omitidos** en Python 3.11 y 3.14, pero
  no se pudo reproducir aquí el «0 omitidos».
- Regresión dirigida
  `test_identical_race_with_failed_cleanup_is_reported`: **OK**; código `IO`, causa `OSError`,
  ruta del staging una sola vez y workspace concurrente intacto y cargable.

**Veredicto final: aprobado; REV4A-01, REV4A-02, REV4A-03 y REV4A-04 están resueltos y no quedan
pendientes de esta verificación.**
