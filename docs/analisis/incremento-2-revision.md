# Revisión — incremento 2: manifiestos y loader de paquetes

## Alcance y veredicto

Revisado el estado de trabajo sin commit de `feature/incremento-2-paquetes-puertos`, con base
`17d83e1fa0849927f4d196caad1ae6e945d1be76`, contra los pasos 1–10 y los criterios de aceptación
del incremento 2 de `ANALISIS.md`, las notas de implementación y los requisitos generales
aplicables.

**Veredicto: requiere cambios.** El contrato v1, la resolución literal de dependencias y el orden
topológico están bien implementados; los manifiestos reales y las fixtures respetan el alcance y
no incorporan reglas, lore ni derivados. No obstante, el descubrimiento puede aceptar conjuntos
incompletos, la detección de categorías desconocidas no cubre todo lo exigido y los finales de
línea no están fijados, por lo que el hash de un mismo manifest versionado no es reproducible entre
checkouts.

## Defectos

### REV2-01 — Media — `core/runtime/packages.py:164-171`, `tests/test_package_loader.py:193-198,244-251`

**Problema y condición:** un hijo directo que sea directorio bajo `characters`, `worlds` o
`systems`, pero no contenga `manifest.json`, se ignora en silencio. En esa posición el directorio
es un candidato a paquete según la estructura definida; omitirlo convierte un manifest ausente o
mal nombrado en un conjunto aparentemente válido e incompleto. La decisión anotada de tratarlo
como un archivo auxiliar no está respaldada por el paso 5, que solo autoriza ignorar archivos
auxiliares, y contradice el fallo cerrado buscado. Además, una categoría conocida que sea un
symlink roto se equipara a categoría ausente porque se consulta `exists()` antes de `is_symlink()`.

**Evidencia:** una comprobación dirigida con `worlds/incomplete/` devolvió `()`; el test
`test_ignores_auxiliary_files_without_loading_payload` exige actualmente ese resultado. El caso de
symlink roto se desprende de las líneas 166–169; no pudo ejecutarse en este sandbox porque la
creación de symlinks devuelve `WinError 1314`.

**Criterio de resolución:** mantener aceptable una categoría realmente ausente o vacía, pero
enumerar sus hijos directos y rechazar con `PackageManifestError` todo candidato de directorio que
no tenga un `manifest.json` regular, así como symlinks de categoría o paquete, incluidos los rotos.
Seguir ignorando archivos auxiliares sueltos. Añadir tests para directorio sin manifest y para
symlinks de categoría/paquete cuando la plataforma los permita.

### REV2-02 — Media — `core/runtime/packages.py:158-161`, `tests/test_package_loader.py:237-242`

**Problema y condición:** la categoría desconocida solo se detecta si su manifest está exactamente
en `<raíz>/<categoría>/<paquete>/manifest.json`. Un manifest colocado directamente en la categoría
desconocida o más profundo queda fuera del patrón `*/*/manifest.json` y el conjunto se acepta. El
paso 5 exige rechazar una categoría desconocida que contenga manifests, no solo la variante que ya
tenga la profundidad esperada.

**Evidencia:** sendas comprobaciones dirigidas con `rules/manifest.json` y
`rules/nested/pkg/manifest.json` devolvieron `()` sin error. El test existente solo construye
`rules/r/manifest.json`, por lo que ambas regresiones pasan las 42 pruebas del incremento.

**Criterio de resolución:** cualquier categoría directa desconocida que contenga un archivo
llamado `manifest.json` en cualquier profundidad debe producir `PackageManifestError`, sin cargarlo
ni seguir symlinks. Añadir casos para manifest directo, a la profundidad normal y mal anidado.

### REV2-03 — Media — `.gitattributes` ausente; `packages/**/manifest.json`, `tests/fixtures/packages/**/manifest.json`, `tests/test_package_loader.py:62-82`

**Problema y condición:** el loader calcula correctamente el SHA-256 de los bytes de trabajo, pero
el repositorio no fija los finales de línea de los manifests. Con `core.autocrlf=true`, un checkout
de Windows puede materializar CRLF y otro checkout LF; ambos parten del mismo blob y producen
`SourceRef.sha256` distintos. Esto bloquea el criterio de hash reproducible entre máquinas.

**Evidencia:** los archivos sin versionar actuales tienen LF. Para
`packages/characters/nozomu/manifest.json`, esos bytes dan
`bd52e817c63aeba97f86c1ea07fbbfe2eec20cdddc39f7dfe03e8be05d9b73b6`; sustituyendo únicamente
LF por CRLF dan `ea718ba7e9a3fabc005eb0605524a83f533c98f9051b57a0996a246b6923b432`. El test calcula su valor
esperado leyendo el mismo checkout, de modo que no detecta esta diferencia.

**Criterio de resolución:** añadir en este incremento un `.gitattributes` raíz con este contenido
exacto y normalizar los manifests antes de incorporarlos:

```gitattributes
packages/**/manifest.json text eol=lf
tests/fixtures/packages/**/manifest.json text eol=lf
```

Actualizar la enumeración de rutas permitidas del incremento para incluir `.gitattributes` y
verificar con `git check-attr eol -- <manifest>` que el resultado sea `lf`. No debe aplazarse: el
primer commit de los manifests debe fijar ya su representación reproducible.

### REV2-04 — Baja — `core/runtime/packages.py:122-127`, `tests/test_package_loader.py:117-130`

**Problema y condición:** `json.loads` solo está envuelto para `JSONDecodeError` y
`PackageManifestError`. En versiones del intérprete cuyo decoder recursivo alcanza el límite con
un JSON profundamente anidado y menor de 65.536 bytes, escapa `RecursionError` en vez de la
`PackageManifestError` exigida para toda forma de manifest inválida.

**Evidencia:** reproducido en el Python 3.10 disponible con 1.000 arrays anidados (2.000 bytes):
`RecursionError`, sin causa envuelta. Python 3.14 ya devuelve `PackageManifestError` para la misma
entrada; Python 3.11 no está instalado en este sandbox, por lo que la reproducción directa en la
versión mínima queda pendiente. La lista de excepciones capturadas no cubre el caso en intérpretes
afectados.

**Criterio de resolución:** envolver `RecursionError` producido durante la decodificación como
`PackageManifestError`, conservándolo en `__cause__`, y añadir un test con anidamiento suficiente
pero por debajo del límite de bytes que pase tanto en 3.11 como en versiones posteriores.

### REV2-05 — Baja — `tests/test_package_loader.py:16-18,62-82,142-152`

**Problema y condición:** las pruebas de symlink y `locator` no protegen todo el contrato. Solo se
enlaza el archivo `manifest.json`, no el propio directorio de paquete ni una categoría; y el único
`locator` comprobado parte de `ROOT.resolve()`, por lo que una regresión que convierta siempre una
ruta relativa en absoluta seguiría pasando. Tampoco hay una comprobación del atributo de EOL que
detecte la regresión descrita en REV2-03.

**Evidencia:** `test_rejects_symlinked_manifest` mantiene regular `link_dir`; no existe caso con
`load_manifest(<symlink-al-directorio>)`. `test_source_ref_has_exact_hash_and_no_invented_dates`
usa una ruta absoluta. En esta ejecución el único test de symlink quedó omitido por falta de
privilegios, aunque las notas aportan evidencia de que sí se ejecutó en la corrida previa de
Python 3.11.

**Criterio de resolución:** añadir casos dirigidos para symlink de directorio de paquete y de
categoría —incluidos rotos cuando sea posible— y para una llamada con ruta relativa que conserve
un `locator` relativo en formato POSIX. Incorporar a la verificación del repositorio el
`git check-attr` indicado en REV2-03. Los tests pueden omitir únicamente la creación real de
symlinks cuando la plataforma no la autorice.

## Respuestas a las preguntas concretas

1. Sí. `parse_manifest` exige las seis claves exactas, usa `type(value) is int` para excluir
   `true`, valida enum, patrón ASCII de ID y textos, transforma `requires` en tupla sin mutar la
   entrada y rechaza autorreferencia y duplicados por tipo+ID. La misma validación aplicable se usa
   en dependencias. Las claves JSON duplicadas se rechazan durante la carga.
2. No en todos los casos: REV2-01 y REV2-02 describen aceptaciones silenciosas, y REV2-04 una
   violación del tipo de error público aunque la carga se interrumpa. Fuera de ellos, el loader
   comprueba archivo/directorio declarado, límite, UTF-8, JSON, ID/directorio,
   tipo/categoría, dependencia por tipo+ID+versión literal y ciclos. El algoritmo de Kahn con heap
   sí produce el orden pedido: dependencias antes que dependientes y, entre nodos disponibles,
   `(package_type.value, package_id, version)`.
3. Categoría ausente como vacía es compatible con categorías opcionales; rechazar BOM y constantes
   JSON no estándar es una interpretación conservadora válida de JSON/UTF-8 estricto; y conservar
   en `locator` la ruta recibida, con separadores POSIX, cumple el texto actual. En cambio, ignorar
   un subdirectorio directo sin manifest no es aceptable porque oculta un error de instalación
   (REV2-01). La decisión sobre `locator` debe quedar fijada por un caso relativo (REV2-05).
4. Sí, el riesgo CRLF bloquea el criterio de reproducibilidad entre checkouts. El `.gitattributes`
   exacto y su inclusión en este incremento se especifican en REV2-03.
5. Los tests actuales detectan bien las regresiones ordinarias del contrato v1, resolución,
   versión, ciclos y orden. No detectarían los layouts desconocidos de REV2-02, aceptan
   expresamente el caso de REV2-01, derivan el hash esperado del mismo checkout y no cubren todos
   los symlinks ni el `locator` relativo; tampoco cubren el error profundo de REV2-04.

## Sugerencias no bloqueantes

Ninguna.

## Verificación realizada

- `py -3.14 -B -m unittest tests.test_package_manifest tests.test_package_loader -v`: **42 tests,
  OK (1 omitido)** por falta de privilegios para crear el symlink.
- `py -3.14 -B -m unittest discover -s tests -v`: **79 tests, OK (1 omitido)**.
- Python 3.11 no está disponible ahora (`py -0p` solo enumera 3.14); se conserva como evidencia
  aportada la corrida previa de **42/79 OK** en 3.11, con el test de symlink ejecutado.
- Comprobaciones temporales de directorio sin manifest y categorías desconocidas directa y
  profundamente anidadas: aceptadas indebidamente, como detallan REV2-01 y REV2-02.
- Comprobación de JSON profundamente anidado: `RecursionError` en Python 3.10 y
  `PackageManifestError` en 3.14; pendiente confirmar directamente 3.11.
- Los seis manifests actuales contienen LF; la comparación LF/CRLF confirmó hashes diferentes.
- Búsqueda de nombres específicos en `core` y fixtures: sin coincidencias. Los manifests reales
  contienen solo las seis claves autorizadas y ningún payload.
- Rama y merge-base: correctos. `git diff --name-only 17d83e1 -- reference` no produjo salida;
  `git diff --check` fue limpio para archivos seguidos. Para los archivos sin versionar se toma la
  comprobación aportada con `git add -N` temporal.

## Verificación

Verificación de REV2-01..05 sobre el mismo estado de trabajo sin commit, rama
`feature/incremento-2-paquetes-puertos` y base `17d83e1`.

- **REV2-01 — Resuelto.** `load_package_set` enumera ahora los hijos directos de cada categoría:
  todo directorio se trata como paquete y pasa por `load_manifest`, por lo que un manifest ausente
  o no regular falla; solo los archivos sueltos se ignoran. Los symlinks directos de categoría o
  paquete se comprueban antes de consultar su destino, de modo que también se rechazan los rotos.
  Los tests distinguen categoría ausente/vacía, paquete incompleto y archivos auxiliares.
- **REV2-02 — Resuelto.** Los hijos desconocidos de la raíz se recorren con
  `os.walk(..., followlinks=False)` y cualquier `manifest.json`, tanto directo como anidado,
  provoca `PackageManifestError`; un directorio auxiliar sin manifests continúa ignorándose. Los
  tres niveles relevantes quedan cubiertos por tests y no se siguen enlaces durante la búsqueda.
- **REV2-03 — Resuelto.** `.gitattributes` contiene exactamente las dos reglas propuestas con
  `text eol=lf`; `git check-attr eol` devuelve `lf` para los tres manifests reales y las tres
  fixtures. El test adicional confirma que sus bytes de trabajo no contienen CR, por lo que
  `core.autocrlf` ya no cambia el SHA-256 entre checkouts conformes.
- **REV2-04 — Resuelto.** `load_manifest` convierte el `RecursionError` del decoder en
  `PackageManifestError` mediante `raise ... from exc`, preservando `__cause__`. El caso de 20.000
  niveles permanece por debajo de 65.536 bytes y pasa; la ejecución aportada en Python 3.11
  confirma que ejercita el `RecursionError` que motivó el hallazgo.
- **REV2-05 — Resuelto.** La suite añade casos para directorio de paquete y categoría enlazados,
  sus variantes rotas, manifest enlazado tanto por carga directa como por conjunto, ruta relativa
  y EOL. Los tests de symlink se omitieron en este sandbox por `WinError 1314`, pero su estructura
  contrasta las ramas corregidas y la ejecución aportada en Python 3.11 completó los 89 tests sin
  omisiones.

No se observaron regresiones relacionadas: orden topológico, dependencias, carga de fixtures y
paquetes reales, rechazo del conjunto inválido y contrato del incremento 1 siguen pasando.

Comprobaciones de esta verificación:

- `py -3.14 -B -m unittest tests.test_package_manifest tests.test_package_loader -v`: **52 tests,
  OK (5 omitidos por falta de privilegios para symlinks)**.
- `py -3.14 -B -m unittest discover -s tests -v`: **89 tests, OK (5 omitidos)**.
- Evidencia aportada en Python 3.11 y 3.14: **89 OK, 0 omitidos** en ambas; Python 3.11 no está
  instalado en este sandbox (`py -0p` solo enumera 3.14).
- `git check-attr eol` sobre los seis manifests: `lf`; búsqueda de nombres específicos en `core`
  y fixtures: sin coincidencias; `reference/`: sin cambios; `git diff --check`: limpio.
- Rama y merge-base verificados: `feature/incremento-2-paquetes-puertos` y
  `17d83e1fa0849927f4d196caad1ae6e945d1be76`.

**Veredicto final: aprobado; REV2-01, REV2-02, REV2-03, REV2-04 y REV2-05 están resueltos y no
quedan pendientes de esta revisión.**
