import asyncio
import os
import sys

# Ensure root directory is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import db
from app.utils.admin_auth import get_password_hash

async def seed_admin():
    existing_admin = await db.admins.find_one({"username": "admin"})
    if existing_admin:
        print("[INFO] Admin user 'admin' already exists in database.")
        return

    hashed_pw = get_password_hash("admin123")
    admin_doc = {
        "username": "admin",
        "password": hashed_pw,
        "full_name": "System Administrator",
        "email": "admin@example.com",
        "phone_number": "0000000000",
        "address": "Admin Office",
        "role_name": "superadmin"
    }

    await db.admins.insert_one(admin_doc)
    print("[SUCCESS] Superadmin user created successfully:")
    print("  Username: admin")
    print("  Password: admin123")
    print("  Role: superadmin")

if __name__ == "__main__":
    asyncio.run(seed_admin())
