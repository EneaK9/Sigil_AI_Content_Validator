"""
Tests for services layer.
"""
import pytest
import time
from unittest.mock import patch, MagicMock

from services.checker import CheckerService
from services.job_store import JobStore, Job
from services.batch_processor import BatchProcessor
from core.models import PostData


class TestCheckerService:
    """Tests for CheckerService."""
    
    def test_policy_caching(self):
        """Policies are cached after first load."""
        checker = CheckerService()
        
        with patch("services.checker.load_policies") as mock_load:
            mock_load.return_value = "Policy text"
            
            # First call loads
            result1 = checker.get_policies("facebook")
            assert mock_load.call_count == 1
            
            # Second call uses cache
            result2 = checker.get_policies("facebook")
            assert mock_load.call_count == 1  # Still 1
            
            assert result1 == result2 == "Policy text"
    
    def test_different_platforms_cached_separately(self):
        """Different platforms are cached separately."""
        checker = CheckerService()
        
        with patch("services.checker.load_policies") as mock_load:
            mock_load.side_effect = lambda p: f"Policy for {p}"
            
            fb = checker.get_policies("facebook")
            ig = checker.get_policies("instagram")
            
            assert fb == "Policy for facebook"
            assert ig == "Policy for instagram"
            assert mock_load.call_count == 2
    
    def test_warm_cache(self):
        """warm_cache preloads multiple platforms."""
        checker = CheckerService()
        
        with patch("services.checker.load_policies") as mock_load:
            mock_load.return_value = "Policy"
            
            checker.warm_cache({"facebook", "instagram", "reddit"})
            
            assert mock_load.call_count == 3
    
    def test_clear_cache(self):
        """clear_cache removes all cached policies."""
        checker = CheckerService()
        
        with patch("services.checker.load_policies") as mock_load:
            mock_load.return_value = "Policy"
            
            checker.get_policies("facebook")
            assert mock_load.call_count == 1
            
            checker.clear_cache()
            
            checker.get_policies("facebook")
            assert mock_load.call_count == 2  # Reloaded


class TestJobStore:
    """Tests for JobStore."""
    
    def test_create_job_returns_uuid(self):
        """create_job returns a UUID."""
        store = JobStore()
        job_id = store.create_job(total=10)
        
        assert job_id is not None
        assert len(job_id) == 36  # UUID format
    
    def test_get_job_returns_job(self):
        """get_job returns the job object."""
        store = JobStore()
        job_id = store.create_job(total=5)
        
        job = store.get_job(job_id)
        
        assert job is not None
        assert job.id == job_id
        assert job.total == 5
        assert job.status == "pending"
    
    def test_get_nonexistent_job_returns_none(self):
        """get_job returns None for nonexistent job."""
        store = JobStore()
        
        job = store.get_job("nonexistent")
        
        assert job is None
    
    def test_set_status_updates_status(self):
        """set_status updates job status."""
        store = JobStore()
        job_id = store.create_job(total=1)
        
        store.set_status(job_id, "processing")
        
        job = store.get_job(job_id)
        assert job.status == "processing"
    
    def test_completed_status_sets_completed_at(self):
        """Setting status to completed sets completed_at."""
        store = JobStore()
        job_id = store.create_job(total=1)
        
        store.set_status(job_id, "completed")
        
        job = store.get_job(job_id)
        assert job.completed_at is not None
    
    def test_add_verdict_increments_completed(self):
        """add_verdict increments completed count."""
        store = JobStore()
        job_id = store.create_job(total=3)
        
        store.add_verdict(job_id, {"verdict": "PASS"})
        store.add_verdict(job_id, {"verdict": "FAIL"})
        
        job = store.get_job(job_id)
        assert job.completed == 2
        assert len(job.verdicts) == 2
    
    def test_add_error_increments_failed(self):
        """add_error increments failed count."""
        store = JobStore()
        job_id = store.create_job(total=3)
        
        store.add_error(job_id, {"error": "Failed"})
        
        job = store.get_job(job_id)
        assert job.failed == 1
        assert job.completed == 1  # Also increments completed
        assert len(job.errors) == 1
    
    def test_delete_job_removes_job(self):
        """delete_job removes the job."""
        store = JobStore()
        job_id = store.create_job(total=1)
        
        result = store.delete_job(job_id)
        
        assert result is True
        assert store.get_job(job_id) is None
    
    def test_delete_nonexistent_returns_false(self):
        """delete_job returns False for nonexistent job."""
        store = JobStore()
        
        result = store.delete_job("nonexistent")
        
        assert result is False
    
    def test_job_to_dict(self):
        """Job.to_dict returns correct structure."""
        store = JobStore()
        job_id = store.create_job(total=2)
        store.add_verdict(job_id, {"verdict": "PASS"})
        
        job = store.get_job(job_id)
        data = job.to_dict()
        
        assert data["job_id"] == job_id
        assert data["status"] == "pending"
        assert data["progress"]["completed"] == 1
        assert data["progress"]["total"] == 2
        assert len(data["verdicts"]) == 1


class TestBatchProcessor:
    """Tests for BatchProcessor."""
    
    def test_convert_input_to_post_data(self):
        """_convert_input_to_post_data creates correct PostData."""
        checker = MagicMock()
        store = MagicMock()
        processor = BatchProcessor(checker, store, max_concurrent=5)
        
        post_input = {
            "url": "https://facebook.com/post/1",
            "message": "Hello world",
            "author_name": "Test User",
            "image_uri": "https://example.com/image.jpg",
            "video": "https://example.com/video.mp4",
            "video_transcript": "Hello everyone",
        }
        
        post, transcript = processor._convert_input_to_post_data(post_input)
        
        assert post.url == "https://facebook.com/post/1"
        assert post.platform == "facebook"
        assert post.text == "Hello world"
        assert post.author == "Test User"
        assert post.image_urls == ["https://example.com/image.jpg"]
        assert post.video_urls == ["https://example.com/video.mp4"]
        assert transcript == "Hello everyone"
    
    def test_empty_transcript_becomes_none(self):
        """Empty video_transcript becomes None."""
        checker = MagicMock()
        store = MagicMock()
        processor = BatchProcessor(checker, store, max_concurrent=5)
        
        post_input = {
            "url": "https://facebook.com/post/1",
            "message": "Test",
            "video_transcript": "   ",  # Whitespace only
        }
        
        post, transcript = processor._convert_input_to_post_data(post_input)
        
        assert transcript is None
    
    def test_process_single_returns_verdict(self):
        """_process_single returns verdict on success."""
        checker = MagicMock()
        checker.check_post.return_value = {"verdict": "PASS"}
        store = MagicMock()
        processor = BatchProcessor(checker, store, max_concurrent=5)
        
        post_input = {
            "url": "https://facebook.com/post/1",
            "message": "Test",
        }
        
        index, verdict, error = processor._process_single(post_input, 0)
        
        assert index == 0
        assert verdict == {"verdict": "PASS"}
        assert error is None
    
    def test_process_single_returns_error_on_failure(self):
        """_process_single returns error on failure."""
        checker = MagicMock()
        checker.check_post.side_effect = Exception("API Error")
        store = MagicMock()
        processor = BatchProcessor(checker, store, max_concurrent=5)
        
        post_input = {
            "url": "https://facebook.com/post/1",
            "message": "Test",
        }
        
        index, verdict, error = processor._process_single(post_input, 0)
        
        assert index == 0
        assert verdict is None
        assert error is not None
        assert "API Error" in error["error"]
