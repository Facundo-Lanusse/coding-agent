Implementá únicamente la Fase 02: tools, registry y políticas de seguridad.

Releé `AGENTS.md`, la consigna, el plan y el código existente. Informá primero
los archivos que modificarás.

Implementá una interfaz común para tools con:

- nombre;
- descripción;
- schema JSON de parámetros;
- función de ejecución;
- metadatos de permisos;
- resultado estructurado;
- error estructurado.

Implementá o migrá:

- `read_file`
- `write_file`
- `list_files`
- `run_command`
- `search_files`
- `repository_status`
- `web_search`

Implementá un `ToolRegistry`. Como extra opcional de la consigna, agregá
descubrimiento/registro extensible sin acoplar el núcleo a cada tool.

Implementá `PolicyEngine` y validación de `agent.config.yaml` ANTES de cada tool
call.

Seguridad obligatoria:

- containment de paths mediante `Path.resolve()` y `relative_to`, no mediante
  comparación textual con `startswith`;
- bloqueo de traversal;
- bloqueo de symlinks que salgan del workspace;
- glob patterns de lectura y escritura;
- denegación de secretos;
- escritura atómica;
- límite de tamaño de lectura y output;
- timeout;
- working directory fijo;
- no usar `shell=True` para comandos arbitrarios;
- parseo seguro de argumentos;
- comandos denegados;
- comandos que requieren aprobación;
- registro de la decisión de política;
- parámetros sensibles redacted en logs.

Definí resultados como mínimo:

- `allowed`;
- `denied`;
- `requires_approval`;
- `executed`;
- `failed`.

Permisos recomendados por rol, aunque los roles se conectarán en la fase 03:

- Explorer: lectura, listado, búsqueda, status y comandos seguros de inspección.
- Researcher: RAG/memoria/web, sin escritura productiva.
- Implementer: lectura y escritura controlada, sin comandos riesgosos.
- Tester: lectura y checks permitidos.
- Reviewer: lectura, diff y status, sin escritura productiva.

Tests obligatorios:

- path normal permitido;
- `../` bloqueado;
- path con prefijo similar pero fuera del workspace bloqueado;
- symlink externo bloqueado;
- `.env`, PEM y secrets bloqueados;
- `.github/**` bloqueado para escritura;
- comando prohibido bloqueado;
- comando sujeto a aprobación no ejecutado sin approval;
- timeout;
- output truncado;
- escritura atómica;
- configuración inválida rechazada;
- prueba que demuestra que la política se evalúa antes de la tool.

Ejecutá tests, Ruff y mypy. No avances a agentes. Actualizá la matriz de
requisitos y detenete.
