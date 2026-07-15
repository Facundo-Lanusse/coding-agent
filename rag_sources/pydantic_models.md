# Pydantic models

Paráfrasis reproducible de la documentación oficial enlazada en el manifest.

## Validación

Un modelo hereda de `BaseModel` y declara campos mediante anotaciones. Pydantic
valida los datos de entrada y construye una instancia que respeta los tipos y
restricciones declarados.

```python
from pydantic import BaseModel, Field


class User(BaseModel):
    name: str
    age: int = Field(ge=0)
```

## Serialización y configuración

`model_dump()` produce datos Python y `model_dump_json()` produce JSON. La
configuración del modelo permite, entre otras políticas, rechazar campos extra o
hacer instancias inmutables. Una inferencia del agente no debe confundirse con
un hecho validado solo porque fue expresada mediante un modelo.
