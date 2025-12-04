#!/usr/bin/env python3
"""
Labl IQ Rate Analyzer API - Hybrid Backend
Simple startup script for the API server
"""

import uvicorn

if __name__ == "__main__":
    print("Starting Labl IQ Rate Analyzer API...")
    print("API Documentation: http://localhost:8000/docs")
    print("Health Check: http://localhost:8000/health")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 