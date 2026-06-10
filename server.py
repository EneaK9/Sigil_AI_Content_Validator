#!/usr/bin/env python3
"""
PolicyGuard API Server entry point.

Usage:
    # Development (auto-reload)
    python server.py
    
    # Production (multiple workers)
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
"""
import uvicorn

from config import API_HOST, API_PORT


def main():
    """Run the API server in development mode."""
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
