# Desarrollo local

## Camino recomendado

El flujo cotidiano usa Python 3.11 y un entorno virtual local. Docker es una
alternativa reproducible para onboarding, demos y CI; no es obligatorio para
editar o ejecutar tests.

```bash
make bootstrap
make check
```

`make bootstrap` crea `.venv` si falta e instala exactamente el proyecto y el
extra `dev` declarados en `pyproject.toml`. No carga `.env` ni llama proveedores.

Targets útiles:

```text
make test         suite offline
make coverage     suite y coverage branch
make lint         Ruff
make typecheck    mypy estricto
make check        test + lint + typecheck
make build        wheel y sdist
make config       validación YAML sin red
make rag-ingest   ingesta determinista local
make demo         escenarios A/B/C deterministas
```

## Docker y Compose

El `Dockerfile` tiene etapas separadas:

- `builder`: construye el wheel;
- `runtime`: instala sólo dependencias runtime, incluye config/corpus/fixture y
  ejecuta como usuario no-root;
- `development`: agrega el extra `dev` y el código/test suite editable.

Para evitar problemas de permisos en bind mounts Linux, completá `LOCAL_UID` y
`LOCAL_GID` en tu `.env` con el resultado de `id -u` e `id -g`. En Docker
Desktop normalmente los defaults funcionan.

```bash
cp .env.example .env
docker compose build agent
docker compose run --rm agent --help
docker compose run --rm agent config validate --config agent.config.yaml
docker compose --profile dev run --rm dev python -m pytest -q
```

Las demos necesitan `pytest`, por lo que se ejecutan con la etapa de desarrollo:

```bash
docker compose --profile dev run --rm dev \
  coding-agent demo all \
  --runtime-root tmp/demo-runtime \
  --output-root docs/evidence/runs
```

Compose pasa únicamente variables explícitas. `.dockerignore` impide copiar
`.env`, entornos, caches, DBs y outputs locales al contexto de build. Los
contenedores usan filesystem raíz read-only, `/tmp` efímero, sin capabilities y
con `no-new-privileges`; sólo los mounts declarados son escribibles.

La imagen slim no instala Git como paquete del sistema. Esto mantiene el cambio
sin dependencias nuevas, pero las tools `repository_status`/`git diff` dentro
del contenedor requieren aprobar e incorporar `git`; el flujo local usa el Git
del host y no tiene esa limitación.

## Antes de abrir un PR

1. Ejecutar `make check`.
2. Ejecutar `make coverage` si se tocó lógica.
3. Actualizar documentación/evidencias sólo con resultados realmente obtenidos.
4. Confirmar que no se agregaron `.env`, claves, bases SQLite ni artifacts
   temporales.
5. No regenerar `docs/evidence/runs/` salvo que el cambio afecte la demo.

No hay workflow bajo `.github/`: la propia policy del TP bloquea escritura en
esa ruta y su incorporación requiere una decisión explícita del responsable.
El repositorio fue inicializado sobre `main`, pero deliberadamente no se hizo
`git add` ni commit.
