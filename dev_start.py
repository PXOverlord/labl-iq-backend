#!/usr/bin/env python3
"""
Labl IQ Development Startup Script

This script provides a comprehensive development environment setup with:
1. Environment validation
2. Database connection testing
3. Performance testing
4. Server startup with proper configuration

Date: August 7, 2025
"""

import os
import sys
import asyncio
import time
import uvicorn
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

def setup_environment():
    """Setup development environment."""
    print("🚀 Setting up LABL IQ Development Environment...")
    
    # Check if we're in the right directory
    current_dir = Path.cwd()
    expected_files = ['app', 'requirements.txt', 'run.py']
    
    for file in expected_files:
        if not (current_dir / file).exists():
            print(f"❌ Error: {file} not found. Are you in the correct directory?")
            print(f"Current directory: {current_dir}")
            return False
    
    print(f"✅ Working directory: {current_dir}")
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 11):
        print(f"❌ Error: Python 3.11+ required, found {python_version.major}.{python_version.minor}")
        return False
    
    print(f"✅ Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # Setup environment variables
    env_file = current_dir / '.env'
    env_local_file = current_dir / 'env.local.example'
    
    if not env_file.exists() and env_local_file.exists():
        print("📝 Creating .env file from template...")
        import shutil
        shutil.copy(env_local_file, env_file)
        print("✅ Created .env file")
    
    return True

async def test_database_connection():
    """Test database connection."""
    print("\n🔍 Testing Database Connection...")
    
    try:
        from app.core.database import connect_db, get_db_status
        
        await connect_db()
        status = await get_db_status()
        
        if status['connected']:
            print("✅ Database connected successfully")
            print(f"   Stats: {status.get('stats', 'N/A')}")
        else:
            print("⚠️  Database connection failed, but continuing...")
            print(f"   Error: {status.get('error', 'Unknown error')}")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Database test failed: {e}")
        print("   Continuing without database...")
        return False

def test_calculation_engine():
    """Test calculation engine performance."""
    print("\n🧮 Testing Calculation Engine...")
    
    try:
        from app.services.calc_engine import AmazonRateCalculator
        
        start_time = time.time()
        calculator = AmazonRateCalculator()
        load_time = time.time() - start_time
        
        print(f"✅ Calculation engine loaded in {load_time:.2f} seconds")
        
        # Test zone lookup
        test_cases = [
            ("46307", "90210"),  # Common US ZIPs
            ("10001", "33101"),  # Another pair
            ("46307", "M5V3A8"), # US to Canada
        ]
        
        for origin, dest in test_cases:
            zone = calculator.get_zone(origin, dest)
            print(f"   Zone lookup {origin} → {dest}: Zone {zone}")
        
        return True
        
    except Exception as e:
        print(f"❌ Calculation engine test failed: {e}")
        return False

def test_optimized_engine():
    """Test optimized calculation engine."""
    print("\n⚡ Testing Optimized Calculation Engine...")
    
    try:
        from app.services.calc_engine_optimized import OptimizedAmazonRateCalculator
        
        start_time = time.time()
        calculator = OptimizedAmazonRateCalculator()
        load_time = time.time() - start_time
        
        print(f"✅ Optimized engine loaded in {load_time:.2f} seconds")
        
        # Test optimized zone lookup
        test_cases = [
            ("46307", "90210"),
            ("10001", "33101"),
            ("46307", "M5V3A8"),
        ]
        
        for origin, dest in test_cases:
            zone = calculator.get_zone_optimized(origin, dest)
            print(f"   Optimized lookup {origin} → {dest}: Zone {zone}")
        
        # Get performance stats
        stats = calculator.get_performance_stats()
        print(f"   Cache hit rate: {stats['cache_hit_rate']:.2%}")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Optimized engine test failed: {e}")
        return False

def start_server():
    """Start the development server."""
    print("\n🌐 Starting Development Server...")
    
    try:
        # Configure uvicorn for development
        config = uvicorn.Config(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            reload_dirs=["app"],
            log_level="info",
            access_log=True
        )
        
        server = uvicorn.Server(config)
        
        print("✅ Server configuration loaded")
        print("🌐 Starting server on http://localhost:8000")
        print("📚 API Documentation: http://localhost:8000/docs")
        print("💚 Health Check: http://localhost:8000/health")
        print("\nPress Ctrl+C to stop the server")
        
        server.run()
        
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return False

async def main():
    """Main development startup function."""
    print("=" * 60)
    print("🚀 LABL IQ - Development Environment Startup")
    print("=" * 60)
    
    # Setup environment
    if not setup_environment():
        print("❌ Environment setup failed")
        return
    
    # Test database connection
    await test_database_connection()
    
    # Test calculation engines
    test_calculation_engine()
    test_optimized_engine()
    
    # Start server
    start_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Development server stopped")
    except Exception as e:
        print(f"\n❌ Startup failed: {e}")
        sys.exit(1)
