# Tools y políticas de seguridad

## Principio de ejecución

Tener una tool asignada no autoriza una acción. Toda invocación productiva pasa
por `AuthorizedToolGateway` en este orden:

1. cargar y validar nuevamente `agent.config.yaml`;
2. comprobar registro de tool y rol;
3. validar parámetros contra el schema Pydantic;
4. resolver path/comando y evaluar `PolicyEngine`;
5. registrar una `PolicyDecision` con argumentos redactados;
6. pedir aprobación si corresponde;
7. ejecutar y limitar el resultado sólo si quedó permitido.

Un error en cualquier precondición produce `ToolResult` estructurado y cero
efectos. Los outcomes de policy son `allowed`, `denied` y
`requires_approval`; los estados de tool incluyen `executed`, `failed`,
`denied`, `requires_approval` y `rejected`.

## Interfaz y registry

Cada tool expone nombre, descripción, schema JSON, modelo de parámetros,
función de ejecución y `ToolPermissions` con tipo de permiso, roles, argumento
de path/comando, campos sensibles y si muta el workspace.

El registry por defecto contiene:

- `read_file`, `write_file`, `list_files`, `search_files`;
- `run_command`, `repository_status`, `web_search`.

`ToolRegistry.discover()` permite entry points opt-in del grupo
`coding_agent.tools`; no se ejecuta automáticamente al importar el paquete.

## Paths y filesystem

`WorkspaceGuard` resuelve paths con `Path.resolve()` y comprueba containment
mediante `relative_to()`. Esto bloquea:

- `../` y paths absolutos fuera del workspace;
- directorios con prefijo textual similar pero externos;
- symlinks cuyo destino sale del workspace;
- `.env`, `.env.*`, PEM, claves y `secrets/**`;
- cualquier glob de lectura/escritura configurado.

La configuración raíz deniega además `.git/**` para leer/escribir,
`.github/**` y `**/*.lock` para escribir. La defensa de secretos es interna y
no depende sólo del YAML.

`read_file` limita bytes y rangos; list/search limitan entradas y filtran paths
no legibles. `write_file` crea un temporal en el mismo directorio, hace
`fsync` y `os.replace`; nunca expone un archivo parcialmente escrito.

## Comandos

`run_command` recibe una lista `argv`, usa `subprocess.run` con `shell=False`,
cwd fijo en el workspace, entorno reducido, timeout y captura de salida. El
gateway trunca el output conforme a `execution.max_output_chars` y conserva
exit code y flag de truncado.

Además de reglas YAML, la policy bloquea shells/intérpretes arbitrarios,
procesos privilegiados, `git push`, hard reset, `rm -rf`, `find -exec`,
preprocesadores de `rg` y helpers externos de Git. Cada rol tiene allowlist de
prefijos. Por defecto Implementer y Researcher no ejecutan comandos; Tester
puede ejecutar checks declarados y Explorer comandos de inspección.

Acciones como `pip install`, `python -m pip install`, `uv add`, `poetry add` y
`git commit` requieren aprobación. Una acción prohibida sigue prohibida aunque
el usuario apruebe otra acción.

## Aprobaciones

El puerto `ApprovalProvider` permite fake en tests y UI interactiva en CLI. La
decisión se vincula al fingerprint de tool/argumentos/config. Sin proveedor o
ante rechazo, la acción no se ejecuta.

La máquina de estados también soporta aprobación pausada mediante
`WAITING_APPROVAL` y `resume`. Son capas diferentes: el gateway resuelve una
tool puntual; el orquestador preserva una pausa de tarea. La demo C verifica
decisiones `requires_approval`, pero deliberadamente no las concede.

## Redacción y logs

`PolicyDecision.arguments` pasa por redacción central de claves sensibles y de
valores de argv asociados a opciones secretas. Tracing aplica además
`Sanitizer`, límites de payload y captura de contenido configurable. La regla de
operación sigue siendo no entregar un secreto al sistema: redacción es defensa
en profundidad, no autorización para leerlo.

## Evidencia y pruebas

Los tests cubren path normal, traversal, prefijo externo, symlink externo,
secretos, `.github/**`, escritura atómica, configuración inválida, orden de
policy, comando prohibido, aprobación, timeout y truncado. El escenario C
registra los outcomes en
[`evidence/runs/scenario-c-safety/events.json`](evidence/runs/scenario-c-safety/events.json).

Limitaciones:

- `web_search` sólo tiene un proveedor no disponible por defecto y fakes;
- la policy reduce riesgo, no crea un sandbox de sistema operativo;
- Git fue inicializado al preparar la publicación, pero aún no existe un commit
  baseline; el primer diff completo deberá validarse después del commit humano;
- los artifacts sanitizan workspace e intérprete con marcadores portables; la
  policy sigue sin equivaler a un sandbox de sistema operativo.
