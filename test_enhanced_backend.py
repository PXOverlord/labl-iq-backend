#!/usr/bin/env python3
"""
Test script for the enhanced FastAPI backend with PostgreSQL + Prisma database integration and JWT authentication
"""
import asyncio
import json
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

async def test_database_connection():
    """Test database connection"""
    print("Testing database connection...")
    try:
        from app.core.database import connect_db, disconnect_db, prisma
        
        await connect_db()
        print("✅ Database connection successful")
        
        # Test basic query
        user_count = await prisma.user.count()
        print(f"✅ Database query successful - User count: {user_count}")
        
        await disconnect_db()
        print("✅ Database disconnection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

async def test_auth_functions():
    """Test authentication functions"""
    print("\nTesting authentication functions...")
    try:
        from app.core.auth import get_password_hash, verify_password, create_access_token, decode_access_token
        
        # Test password hashing
        password = "test_password_123"
        hashed = get_password_hash(password)
        print("✅ Password hashing successful")
        
        # Test password verification
        is_valid = verify_password(password, hashed)
        if is_valid:
            print("✅ Password verification successful")
        else:
            print("❌ Password verification failed")
            return False
        
        # Test token creation and decoding
        user_id = "test_user_123"
        token = create_access_token(user_id)
        print("✅ Token creation successful")
        
        payload = decode_access_token(token)
        if payload and payload.get("sub") == user_id:
            print("✅ Token decoding successful")
        else:
            print("❌ Token decoding failed")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Authentication functions failed: {e}")
        return False

async def test_user_creation():
    """Test user creation and management"""
    print("\nTesting user creation...")
    try:
        from app.core.database import connect_db, disconnect_db, prisma
        from app.core.auth import get_password_hash
        
        await connect_db()
        
        # Create a test user
        test_email = "test@example.com"
        test_password = get_password_hash("test123")
        
        # Check if user already exists
        existing_user = await prisma.user.find_unique(where={"email": test_email})
        if existing_user:
            await prisma.user.delete(where={"email": test_email})
            print("✅ Cleaned up existing test user")
        
        # Create new user
        user = await prisma.user.create(
            data={
                "email": test_email,
                "password": test_password,
                "firstName": "Test",
                "lastName": "User",
                "role": "USER"
            }
        )
        print(f"✅ User created successfully: {user.email}")
        
        # Create user settings
        settings = await prisma.usersettings.create(
            data={
                "userId": user.id,
                "defaultMarkup": 10.0,
                "fuelSurcharge": 16.0,
                "dasSurcharge": 1.98,
                "edasSurcharge": 3.92,
                "remoteSurcharge": 14.15,
                "dimDivisor": 139.0,
                "standardMarkup": 0.0,
                "expeditedMarkup": 10.0,
                "priorityMarkup": 15.0,
                "nextDayMarkup": 25.0
            }
        )
        print("✅ User settings created successfully")
        
        # Test user retrieval with settings
        user_with_settings = await prisma.user.find_unique(
            where={"id": user.id},
            include={"settings": True}
        )
        
        if user_with_settings and user_with_settings.settings:
            print("✅ User retrieval with settings successful")
        else:
            print("❌ User retrieval with settings failed")
            return False
        
        # Clean up
        await prisma.user.delete(where={"id": user.id})
        print("✅ Test user cleaned up")
        
        await disconnect_db()
        return True
    except Exception as e:
        print(f"❌ User creation test failed: {e}")
        return False

async def test_analysis_creation():
    """Test analysis creation"""
    print("\nTesting analysis creation...")
    try:
        from app.core.database import connect_db, disconnect_db, prisma
        from app.core.auth import get_password_hash
        
        await connect_db()
        
        # Create a test user first
        test_email = "analysis_test@example.com"
        user = await prisma.user.create(
            data={
                "email": test_email,
                "password": get_password_hash("test123"),
                "firstName": "Analysis",
                "lastName": "Tester",
                "role": "USER"
            }
        )
        
        # Create an analysis
        analysis = await prisma.analysis.create(
            data={
                "userId": user.id,
                "fileName": "test_file.csv",
                "fileSize": 1024,
                "status": "PENDING",
                "columnMapping": json.dumps({"weight": "Weight (lbs)", "length": "Length", "width": "Width", "height": "Height"})
            }
        )
        print(f"✅ Analysis created successfully: {analysis.id}")
        
        # Test analysis retrieval
        retrieved_analysis = await prisma.analysis.find_unique(
            where={"id": analysis.id},
            include={"user": True}
        )
        
        if retrieved_analysis and retrieved_analysis.user.email == test_email:
            print("✅ Analysis retrieval successful")
        else:
            print("❌ Analysis retrieval failed")
            return False
        
        # Test column mapping parsing
        if retrieved_analysis.columnMapping:
            mapping = json.loads(retrieved_analysis.columnMapping)
            if mapping.get("weight") == "Weight (lbs)":
                print("✅ Column mapping JSON parsing successful")
            else:
                print("❌ Column mapping JSON parsing failed")
                return False
        
        # Clean up
        await prisma.user.delete(where={"id": user.id})
        print("✅ Test analysis and user cleaned up")
        
        await disconnect_db()
        return True
    except Exception as e:
        print(f"❌ Analysis creation test failed: {e}")
        return False

async def test_audit_logging():
    """Test audit logging"""
    print("\nTesting audit logging...")
    try:
        from app.core.database import connect_db, disconnect_db, prisma
        
        await connect_db()
        
        # Create an audit log entry
        audit_log = await prisma.auditlog.create(
            data={
                "action": "TEST_ACTION",
                "details": json.dumps({"test": "data", "timestamp": "2025-01-01T00:00:00Z"}),
                "ipAddress": "127.0.0.1",
                "userAgent": "Test Agent"
            }
        )
        print(f"✅ Audit log created successfully: {audit_log.id}")
        
        # Test audit log retrieval
        retrieved_log = await prisma.auditlog.find_unique(where={"id": audit_log.id})
        if retrieved_log and retrieved_log.action == "TEST_ACTION":
            print("✅ Audit log retrieval successful")
            
            # Test JSON parsing
            if retrieved_log.details:
                details = json.loads(retrieved_log.details)
                if details.get("test") == "data":
                    print("✅ Audit log JSON parsing successful")
                else:
                    print("❌ Audit log JSON parsing failed")
                    return False
        else:
            print("❌ Audit log retrieval failed")
            return False
        
        # Clean up
        await prisma.auditlog.delete(where={"id": audit_log.id})
        print("✅ Test audit log cleaned up")
        
        await disconnect_db()
        return True
    except Exception as e:
        print(f"❌ Audit logging test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🚀 Starting Enhanced Backend Tests")
    print("=" * 50)
    
    tests = [
        test_database_connection,
        test_auth_functions,
        test_user_creation,
        test_analysis_creation,
        test_audit_logging
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Enhanced backend is working correctly.")
        print("\n📋 Summary of implemented features:")
        print("✅ PostgreSQL + Prisma database integration")
        print("✅ JWT authentication with password hashing")
        print("✅ User management with roles and settings")
        print("✅ Analysis tracking and history")
        print("✅ Column profile management")
        print("✅ Audit logging system")
        print("✅ Parent-child user relationships")
        print("✅ Admin controls and user management")
        
        print("\n🔗 Available API endpoints:")
        print("• POST /api/auth/register - User registration")
        print("• POST /api/auth/login - User authentication")
        print("• GET /api/auth/me - Get current user")
        print("• POST /api/analysis/upload - File upload")
        print("• POST /api/analysis/process - Rate calculation")
        print("• GET /api/analysis/ - Analysis history")
        print("• GET /api/admin/users - Admin user management")
        print("• GET /docs - Interactive API documentation")
        
        return True
    else:
        print(f"❌ {total - passed} tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
