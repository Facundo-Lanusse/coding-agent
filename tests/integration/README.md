# Integration tests

La suite predeterminada permanece offline y sin credenciales. La integración
opt-in con Langfuse requiere sus claves en el entorno y se ejecuta con:

```bash
.venv/bin/python -m pytest -m langfuse_integration -q
```

Sin credenciales, pytest informa un `skip` explícito.
