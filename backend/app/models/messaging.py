"""
Internal staff messaging.

Three conversation kinds:
  * direct       — exactly two participants (user-to-user DM)
  * group        — ad-hoc multi-participant chat created by any staff
  * department   — auto-managed; participants mirror the department's members.
                   Admins manage Department membership; the participant list on
                   the linked conversation is kept in sync server-side so users
                   never see "you're not in this department but here are its
                   messages".

Read state is tracked per-participant via `last_read_at`. Unread count = number
of messages in the conversation with `created_at > last_read_at`. Cheaper than a
per-message read receipts table and matches the fidelity our UI shows.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
    UniqueConstraint, Index, Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class Department(Base):
    __tablename__ = "departments"

    department_id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    members = relationship(
        "DepartmentMember", back_populates="department", cascade="all, delete-orphan"
    )


class DepartmentMember(Base):
    __tablename__ = "department_members"

    department_id = Column(
        Integer,
        ForeignKey("departments.department_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    department = relationship("Department", back_populates="members")


class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id = Column(Integer, primary_key=True)
    # 'direct' | 'group' | 'department'
    kind = Column(String(20), nullable=False, index=True)
    # Group/department display name. Direct chats render the other user's name
    # and leave this null.
    title = Column(String(255), nullable=True)
    # Set when kind == 'department'. Lets us mirror membership server-side.
    department_id = Column(
        Integer,
        ForeignKey("departments.department_id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)

    department = relationship("Department")
    participants = relationship(
        "ConversationParticipant",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Updated when the user opens the conversation. Used to compute unread.
    last_read_at = Column(DateTime(timezone=True), nullable=True)

    conversation = relationship("Conversation", back_populates="participants")

    __table_args__ = (
        Index("ix_conv_participants_user", "user_id"),
    )


class Message(Base):
    __tablename__ = "messages"

    message_id = Column(Integer, primary_key=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )
