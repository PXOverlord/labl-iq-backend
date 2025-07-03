
#!/usr/bin/env python3
"""
Seed script to create initial admin user
Run this after database migration in production
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the app directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.database import connect_db, disconnect_db
from app.core.security import get_password_hash
from prisma import Prisma

async def create_admin_user():
    """Create initial admin user"""
    
    # Connect to database
    await connect_db()
    
    try:
        # Check if admin user already exists
        admin_email = os.getenv("ADMIN_EMAIL", "admin@labliq.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")  # Change this!
        
        db = Prisma()
        await db.connect()
        
        existing_admin = await db.user.find_first(
            where={"email": admin_email}
        )
        
        if existing_admin:
            print(f"Admin user {admin_email} already exists")
            return
        
        # Create admin user
        hashed_password = get_password_hash(admin_password)
        
        admin_user = await db.user.create(
            data={
                "email": admin_email,
                "password": hashed_password,
                "firstName": "Admin",
                "lastName": "User",
                "role": "ADMIN",
                "isActive": True
            }
        )
        
        # Create default settings for admin
        await db.usersettings.create(
            data={
                "userId": admin_user.id,
                "originZip": "10001",
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
        
        print(f"✅ Admin user created successfully!")
        print(f"Email: {admin_email}")
        print(f"Password: {admin_password}")
        print("⚠️  IMPORTANT: Change the admin password after first login!")
        
        await db.disconnect()
        
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        raise
    finally:
        await disconnect_db()

if __name__ == "__main__":
    asyncio.run(create_admin_user())
