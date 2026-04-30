"""Tests básicos para verificar que la aplicación levanta correctamente."""

from fastapi.testclient import TestClient

from app.main import app

# raise_server_exceptions=True (por defecto) permite que los errores del servidor
# se propaguen correctamente en los tests. Las respuestas 422 de Pydantic son
# respuestas HTTP normales y no levantan excepciones del servidor.
client = TestClient(app)


def test_health_returns_200():
    """El endpoint /health debe retornar HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok():
    """El endpoint /health debe retornar {"status": "ok"}."""
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_docs():
    """El endpoint / debe redirigir a /docs."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (301, 302, 307, 308)
    assert "/docs" in response.headers.get("location", "")


def test_clave_catastral_sin_body_retorna_422():
    """POST /api/clave-catastral sin body debe retornar 422 (validación Pydantic)."""
    response = client.post("/api/clave-catastral", json={})
    assert response.status_code == 422


def test_clave_catastral_direccion_muy_corta_retorna_422():
    """POST /api/clave-catastral con dirección muy corta debe retornar 422."""
    response = client.post("/api/clave-catastral", json={"direccion": "AB"})
    assert response.status_code == 422
