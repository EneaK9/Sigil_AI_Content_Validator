"""
Tests for jobs endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import get_job_store


@pytest.fixture
def client():
    """Create test client."""
    with TestClient(app) as c:
        yield c


class TestJobsEndpoint:
    """Tests for GET /api/v1/jobs/{job_id}"""
    
    def test_get_nonexistent_job_returns_404(self, client):
        """Getting a nonexistent job returns 404."""
        response = client.get("/api/v1/jobs/nonexistent-id")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_get_existing_job_returns_status(self, client):
        """Getting an existing job returns its status."""
        # First create a batch job
        response = client.post("/api/v1/check/batch", json={
            "posts": [
                {"url": "https://facebook.com/post/1", "message": "Test"}
            ]
        })
        job_id = response.json()["job_id"]
        
        # Then get the job
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "progress" in data
        assert data["progress"]["total"] == 1
    
    def test_job_response_structure(self, client):
        """Job response has correct structure."""
        # Create a batch job
        response = client.post("/api/v1/check/batch", json={
            "posts": [
                {"url": "https://facebook.com/post/1", "message": "Test 1"},
                {"url": "https://facebook.com/post/2", "message": "Test 2"}
            ]
        })
        job_id = response.json()["job_id"]
        
        # Get job and verify structure
        response = client.get(f"/api/v1/jobs/{job_id}")
        data = response.json()
        
        assert "job_id" in data
        assert "status" in data
        assert "progress" in data
        assert "completed" in data["progress"]
        assert "total" in data["progress"]
        assert "failed" in data["progress"]
        assert "verdicts" in data
        assert "errors" in data
        assert "created_at" in data


class TestDeleteJobEndpoint:
    """Tests for DELETE /api/v1/jobs/{job_id}"""
    
    def test_delete_nonexistent_job_returns_404(self, client):
        """Deleting a nonexistent job returns 404."""
        response = client.delete("/api/v1/jobs/nonexistent-id")
        assert response.status_code == 404
    
    def test_delete_existing_job_succeeds(self, client):
        """Deleting an existing job succeeds."""
        # Create a batch job
        response = client.post("/api/v1/check/batch", json={
            "posts": [
                {"url": "https://facebook.com/post/1", "message": "Test"}
            ]
        })
        job_id = response.json()["job_id"]
        
        # Delete the job
        response = client.delete(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()
        
        # Verify it's gone
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 404


class TestJobStoreIntegration:
    """Integration tests for job store functionality."""
    
    def test_multiple_jobs_tracked_independently(self, client):
        """Multiple jobs are tracked independently."""
        # Create two jobs
        response1 = client.post("/api/v1/check/batch", json={
            "posts": [{"url": "https://facebook.com/post/1", "message": "Test 1"}]
        })
        job_id1 = response1.json()["job_id"]
        
        response2 = client.post("/api/v1/check/batch", json={
            "posts": [
                {"url": "https://facebook.com/post/2", "message": "Test 2"},
                {"url": "https://facebook.com/post/3", "message": "Test 3"}
            ]
        })
        job_id2 = response2.json()["job_id"]
        
        # Verify they have different IDs
        assert job_id1 != job_id2
        
        # Verify they have correct totals
        response1 = client.get(f"/api/v1/jobs/{job_id1}")
        response2 = client.get(f"/api/v1/jobs/{job_id2}")
        
        assert response1.json()["progress"]["total"] == 1
        assert response2.json()["progress"]["total"] == 2
