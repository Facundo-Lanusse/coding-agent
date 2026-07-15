from fastapi.testclient import TestClient


def test_service_info(client: TestClient) -> None:
    response = client.get("/info")

    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"

