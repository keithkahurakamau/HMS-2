import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config.database import DefaultSessionLocal
from app.models.user import User, Role
from app.core.security import get_password_hash

def reset_admin():
    db = DefaultSessionLocal()
    
    # Ensure Admin role exists
    admin_role = db.query(Role).filter(Role.name == "Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin", description="Super Administrator")
        db.add(admin_role)
        db.commit()
        db.refresh(admin_role)
        
    admin_email = "admin@mayoclinic.com"
    user = db.query(User).filter(User.email == admin_email).first()
    
    hashed_pw = get_password_hash("admin123")
    
    if user:
        user.hashed_password = hashed_pw
        user.role_id = admin_role.role_id
        user.is_active = True
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        print(f"Password reset for {admin_email}. New password is: admin123")
    else:
        new_user = User(
            email=admin_email,
            full_name="System Admin",
            hashed_password=hashed_pw,
            role_id=admin_role.role_id,
            is_active=True
        )
        db.add(new_user)
        db.commit()
        print(f"User created: {admin_email} / admin123")
        
    db.close()

if __name__ == "__main__":
    reset_admin()
