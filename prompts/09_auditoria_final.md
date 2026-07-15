Realizá la Fase 09: auditoría final integral. No agregues features nuevas salvo
correcciones necesarias para requisitos incumplidos.

Leé completamente `docs/consigna_tp_final.pdf` y compará el repositorio final
requisito por requisito.

Auditoría obligatoria:

1. Confirmar que se reutilizaron conceptos del harness anterior.
2. Confirmar agente principal y cinco subagentes.
3. Confirmar permisos distintos.
4. Confirmar estado compartido mínimo obligatorio.
5. Confirmar memoria persistente entre sesiones.
6. Confirmar RAG con chunking, embeddings y almacenamiento vectorial.
7. Confirmar visualización/provenance de fuentes.
8. Confirmar RAG primero y web fallback.
9. Confirmar manejo de contexto y resúmenes.
10. Confirmar loop/no-progress detection.
11. Confirmar falta de evidencia y pedido de ayuda.
12. Confirmar validación de configuración antes de cada tool.
13. Confirmar políticas de lectura, escritura, comandos y aprobación.
14. Confirmar observabilidad requerida.
15. Confirmar caso de uso verificable.
16. Confirmar pruebas RAG, memoria y estrategia/detención.
17. Confirmar al menos una ejecución observable o declarar exactamente qué
    credenciales/acción humana falta.
18. Confirmar todos los entregables.
19. Buscar imports o dependencias de frameworks prohibidos.
20. Buscar secretos, paths absolutos del autor, outputs falsos y datos sensibles.

Ejecutar como mínimo:

- suite completa de tests;
- coverage;
- Ruff;
- mypy;
- build del paquete;
- instalación limpia en entorno temporal, si es viable;
- comandos CLI de ayuda;
- demos deterministas;
- inspección de artifacts;
- escaneo de secretos razonable.

Generar:

- `docs/final_audit.md`
- actualización final de `docs/requirements_matrix.md`
- actualización de `docs/delivery_checklist.md`

`docs/final_audit.md` debe separar:

- PASS;
- FAIL;
- PARTIAL;
- requiere acción humana.

No marcar PASS sin evidencia concreta: archivo, test, comando o artifact.

Al terminar, responder:

A. Estado general.
B. Tabla de requisitos.
C. Tests y comandos con exit codes.
D. Evidencias disponibles.
E. Acciones humanas pendientes, especialmente capturas Langfuse.
F. Riesgos residuales.
G. Lista exacta de archivos para entregar.
H. Confirmación de ausencia de secretos y frameworks prohibidos, o detalle del
   hallazgo.

Después, detenete.
