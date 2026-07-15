Implementá únicamente la Fase 06: observabilidad completa con Langfuse.

Crear una abstracción de tracing con:

- implementación Langfuse;
- implementación no-op;
- sanitización centralizada;
- context manager seguro;
- funcionamiento correcto aunque Langfuse no esté configurado.

Crear una traza principal por tarea y spans/generations para:

- carga y validación de configuración;
- carga de memoria;
- cada subagente;
- cada llamada LLM;
- cada tool call;
- política y aprobación;
- RAG retrieval;
- web fallback;
- replanificación;
- loop/no-progress detection;
- tests/checks;
- revisión;
- persistencia de memoria;
- resultado final.

Registrar como mínimo, cuando esté disponible:

- task_id;
- project_id;
- session_id;
- agent;
- modelo;
- prompt/instructions sanitizados;
- input/output sanitizados;
- tool y parámetros sanitizados;
- documentos recuperados;
- fuentes;
- búsquedas web;
- iteración;
- error;
- latencia;
- tokens de entrada y salida;
- costo reportado o estimado;
- archivos modificados;
- resultado final.

Requisitos de seguridad:

- nunca enviar API keys;
- redactar valores de env y patrones sensibles;
- limitar tamaño de payload;
- poder desactivar captura de contenido completo;
- no romper la tarea si falla observabilidad.

Tests obligatorios:

- no-op registra sin fallar;
- Langfuse adapter recibe eventos esperados mediante fake client;
- secretos redacted;
- error de tracing no rompe el agente;
- jerarquía de trace/spans correcta;
- tool, RAG, web, loop y result quedan registrados;
- tokens, latencia y costo quedan en metadata cuando existen.

Crear una prueba de integración marcada para ejecutarse solamente cuando las
variables Langfuse estén presentes. Crear también una guía para encontrar la
traza y tomar las capturas requeridas.

Ejecutá tests, Ruff y mypy. Actualizá documentación y matriz. No fabriques
capturas. Detenete.
