import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config.database import SessionLocal
from app.models.user import User

db = SessionLocal()
users = db.query(User).all()
print("--- USERS IN DATABASE ---")
for u in users:
    print(f"ID: {u.user_id} | Email: {u.email} | Name: {u.full_name} | Active: {u.is_active}")
db.close()
