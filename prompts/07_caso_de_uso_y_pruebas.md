Implementá únicamente la Fase 07: caso de uso concreto, repositorio FastAPI de
demostración y pruebas end-to-end reproducibles.

## Repositorio demo

Crear `examples/fastapi_demo/` como un repositorio/proyecto pequeño pero realista
con:

- aplicación FastAPI;
- routers;
- services;
- models/schemas;
- tests;
- pyproject o requirements;
- comandos claros;
- una arquitectura que el Explorer pueda descubrir;
- al menos una convención no obvia guardable en memoria.

Crear un mecanismo seguro para resetear la fixture al estado inicial antes de
cada demo.

## Escenario A — RAG

Tarea:

```text
Analizá este repositorio FastAPI y agregá un endpoint GET /health/ready.
Antes de implementar, consultá el RAG. Mostrá las fuentes utilizadas, agregá
tests y revisá el diff.
```

Debe demostrar:

- Explorer;
- Researcher;
- RAG;
- sources;
- Implementer;
- Tester;
- Reviewer;
- estado compartido;
- trazabilidad.

## Escenario B — memoria entre sesiones

Sesión 1:

```text
Analizá el proyecto y guardá su arquitectura, convenciones, comandos de test y
archivos principales.
```

Sesión 2, usando un nuevo contexto conversacional:

```text
Agregá un endpoint GET /version siguiendo las convenciones previamente
detectadas. Recuperá primero la memoria del proyecto.
```

Debe demostrar que la memoria persiste fuera del historial.

## Escenario C — detenerse/cambiar estrategia/seguridad

Preparar una situación reproducible que incluya:

- un check que falla siempre con la misma huella, para detectar repetición; y/o
- un pedido de modificar `.github/**`, instalar dependencias y hacer commit.

El agente debe:

- no repetir indefinidamente el mismo comando;
- replanificar o detenerse;
- bloquear escritura prohibida;
- solicitar aprobación para instalar/commit;
- explicar política activada y evidencia faltante.

## Evidencia

Crear scripts o comandos CLI para ejecutar cada escenario y guardar:

- task state JSON;
- resumen Markdown;
- fuentes;
- archivos modificados;
- diff;
- comandos y exit codes;
- memoria recuperada;
- eventos de loop/política;
- trace id de Langfuse;
- resultado final.

Guardar outputs bajo `docs/evidence/runs/`, sin secretos y sin inventar
resultados.

Tests obligatorios:

- reset de fixture;
- escenario A con providers fake;
- escenario B en dos procesos/instancias;
- escenario C sin loop infinito;
- artifacts tienen schema válido;
- no se modifica nada fuera del workspace;
- el Reviewer detecta cambios fuera del pedido.

Después de los tests deterministas, si las claves están configuradas, ejecutá
una demo real pequeña y registrá su trace id. Si faltan claves, informá los
comandos exactos pendientes sin simular la ejecución.

Ejecutá tests, Ruff y mypy. Actualizá documentación y detenete.
