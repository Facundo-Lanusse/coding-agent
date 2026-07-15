from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ready_contract() -> None:
    router = _source("app/routers/health.py")
    service = _source("app/services/health.py")
    tests = _source("tests/test_health.py")
    assert '@router.get("/ready"' in router
    assert "return get_readiness()" in router
    assert "def get_readiness" in service
    assert 'client.get("/health/ready")' in tests


def test_version_contract() -> None:
    router = _source("app/routers/meta.py")
    service = _source("app/services/version.py")
    tests = _source("tests/test_meta.py")
    assert '@router.get("/version"' in router
    assert "return get_version()" in router
    assert "def get_version" in service
    assert 'client.get("/version")' in tests


def test_intentional_failure() -> None:
    raise AssertionError("deterministic repeated failure for loop detection")

