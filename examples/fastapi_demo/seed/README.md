# Inventory API

Small FastAPI service used by the advanced coding-agent demos.

```bash
python -m uvicorn app.main:app --reload
python -m pytest -q
```

Architecture:

- `app/routers`: HTTP declaration only;
- `app/services`: business decisions and response construction;
- `app/schemas`: Pydantic response models;
- `app/core`: application configuration.

Convention: routers must delegate to a service and must not build response
payloads directly. This is intentionally easy to miss during a superficial
repository scan.

