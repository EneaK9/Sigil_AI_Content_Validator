"""
Tests for health endpoint.
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from config import API_VERSION


@pytest.fixture
def client():
    """Create test client."""
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """Tests for GET /api/v1/health"""
    
    def test_health_returns_200(self, client):
        """Health endpoint returns 200 OK."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
    
    def test_health_returns_healthy_status(self, client):
        """Health endpoint returns healthy status."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_health_returns_version(self, client):
        """Health endpoint returns API version."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["version"] == API_VERSION
    
    def test_health_returns_timestamp(self, client):
        """Health endpoint returns timestamp."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert "timestamp" in data
        assert "T" in data["timestamp"]  # ISO format


class TestRootEndpoint:
    """Tests for GET /"""
    
    def test_root_returns_200(self, client):
        """Root endpoint returns 200 OK."""
        response = client.get("/")
        assert response.status_code == 200
    
    def test_root_returns_service_info(self, client):
        """Root endpoint returns service info."""
        response = client.get("/")
        data = response.json()
        assert data["service"] == "PolicyGuard API"
        assert data["version"] == API_VERSION
        assert "docs" in data
