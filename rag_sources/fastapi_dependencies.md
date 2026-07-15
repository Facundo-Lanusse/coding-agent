# FastAPI dependencies

Paráfrasis reproducible de la documentación oficial enlazada en el manifest.

## Declaración con Depends

Una dependencia de FastAPI es un callable. La operación declara que depende de
ese callable usando `Depends`; FastAPI lo ejecuta y entrega su resultado al
parámetro correspondiente. Para Python moderno, la documentación recomienda
conservar la anotación de tipo mediante `Annotated`.

```python
from typing import Annotated

from fastapi import Depends, FastAPI

app = FastAPI()


def common_parameters(limit: int = 20) -> dict[str, int]:
    return {"limit": limit}


@app.get("/items")
def list_items(params: Annotated[dict[str, int], Depends(common_parameters)]):
    return params
```

## Composición

Las dependencias pueden declarar subdependencias. FastAPI resuelve esa jerarquía
y reutiliza dentro de la misma request los resultados cacheados por defecto.
También integra las declaraciones de dependencias en el esquema OpenAPI.
