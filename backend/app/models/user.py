from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base

# Many-to-Many association table for Roles and Permissions
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.permission_id", ondelete="CASCADE"), primary_key=True)
)

class Permission(Base):
    __tablename__ = "permissions"
    permission_id = Column(Integer, primary_key=True)
    codename = Column(String(100), unique=True, index=True, nullable=False) # e.g., 'patients:write'
    description = Column(String(255))

class Role(Base):
    __tablename__ = "roles"
    role_id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, index=True, nullable=False) # e.g., 'ADMIN', 'DOCTOR'
    description = Column(String(255))
    permissions = relationship("Permission", secondary=role_permissions)

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # RBAC & Identity
    role_id = Column(Integer, ForeignKey("roles.role_id"), index=True, nullable=False)
    role = relationship("Role")
    
    # Clinical Identity (Replaces the old Doctor table)
    specialization = Column(String(100), nullable=True)
    license_number = Column(String(100), unique=True, index=True, nullable=True)
    
    # Security & Lockout
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserPermissionOverride(Base):
    """Per-user permission overrides layered on top of role permissions.

    A row with `granted=True` means: explicitly grant this permission to the
    user, even if their role does not have it. `granted=False` means:
    explicitly revoke this permission, even if their role has it.

    Effective permissions = (role.permissions ∪ grants) − revokes.
    """
    __tablename__ = "user_permission_overrides"

    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id = Column(
        Integer,
        ForeignKey("permissions.permission_id", ondelete="CASCADE"),
        primary_key=True,
    )
    granted = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())