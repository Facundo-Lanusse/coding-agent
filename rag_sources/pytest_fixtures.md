# pytest fixtures

Paráfrasis reproducible de la documentación estable enlazada en el manifest.

## Contexto explícito para tests

Una fixture proporciona contexto confiable y repetible para un test. Se define
con `@pytest.fixture` y se solicita declarando su nombre como argumento del test
o de otra fixture.

```python
import pytest


@pytest.fixture
def sample_items() -> list[str]:
    return ["one", "two"]


def test_items(sample_items: list[str]) -> None:
    assert len(sample_items) == 2
```

## Alcance y limpieza

Las fixtures pueden tener alcance de función, clase, módulo, paquete o sesión.
Una fixture con `yield` puede ejecutar la limpieza después del test. Las
dependencias explícitas entre fixtures permiten que pytest determine el orden de
preparación.
