"""
Internal staff messaging.

Three conversation kinds are supported:
  * direct       — exactly two participants. Idempotent: opening a DM twice
                   returns the same conversation row.
  * group        — created by any staff member with messaging:write.
  * department   — auto-mirrored from Department membership. The participant
                   list lives in lockstep with `department_members`; this is
                   maintained in the department admin endpoints below, not by
                   end users.

Live updates piggy-back on the existing /ws/notifications/{user_id} WebSocket.
We push events of the form `{"type": "message:new", ...}` to every participant
the moment a message lands, so the client UI does not have to poll.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.core.websocket import manager as ws_manager
from app.models.user import User, Role
from app.models.messaging import (
    Conversation, ConversationParticipant, Message,
    Department, DepartmentMember,
)
from app.schemas.messaging import (
    CreateDirectConversationRequest,
    CreateGroupConversationRequest,
    SendMessageRequest,
    CreateDepartmentRequest,
    UpdateDepartmentRequest,
    SetDepartmentMembersRequest,
)


router = APIRouter(prefix="/api/messaging", tags=["Messaging"])


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _serialize_message(m: Message) -> dict:
    return {
        "message_id": m.message_id,
        "conversation_id": m.conversation_id,
        "sender_id": m.sender_id,
        "body": m.body,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_user_brief(u: User) -> dict:
    return {
        "user_id": u.user_id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role.name if u.role else None,
    }


def _participant_user_ids(db: Session, conversation_id: int) -> List[int]:
    rows = (
        db.query(ConversationParticipant.user_id)
        .filter(ConversationParticipant.conversation_id == conversation_id)
        .all()
    )
    return [r[0] for r in rows]


async def _broadcast(payload: dict, user_ids: List[int]) -> None:
    """Best-effort fan-out — failures must not break the write path."""
    for uid in user_ids:
        try:
            await ws_manager.send_personal_message(payload, uid)
        except Exception:
            # Logged inside the manager; swallow here so one bad socket
            # doesn't poison the rest of the broadcast.
            pass


def _ensure_participant(db: Session, conversation_id: int, user_id: int) -> ConversationParticipant:
    p = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
        .first()
    )
    if not p:
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation.")
    return p


def _serialize_conversation(db: Session, conv: Conversation, viewer_id: int) -> dict:
    """Render a conversation with the viewer's unread count + display name."""
    participants = (
        db.query(ConversationParticipant, User)
        .join(User, User.user_id == ConversationParticipant.user_id)
        .filter(ConversationParticipant.conversation_id == conv.conversation_id)
        .all()
    )

    members = []
    viewer_last_read: Optional[datetime] = None
    for p, u in participants:
        members.append({
            "user_id": u.user_id,
            "full_name": u.full_name,
            "role": u.role.name if u.role else None,
        })
        if u.user_id == viewer_id:
            viewer_last_read = p.last_read_at

    # Display name: department/group titles, or the "other person" for DMs.
    title = conv.title
    if conv.kind == "direct":
        other = next((m for m in members if m["user_id"] != viewer_id), None)
        title = other["full_name"] if other else "Direct message"
    elif conv.kind == "department" and conv.department:
        title = conv.department.name

    # Unread count = messages newer than viewer_last_read (or all if never read).
    q = db.query(func.count(Message.message_id)).filter(
        Message.conversation_id == conv.conversation_id,
        # Don't count your own outbound messages as unread.
        Message.sender_id != viewer_id,
    )
    if viewer_last_read is not None:
        q = q.filter(Message.created_at > viewer_last_read)
    unread = q.scalar() or 0

    last_message = (
        db.query(Message)
        .filter(Message.conversation_id == conv.conversation_id)
        .order_by(Message.created_at.desc())
        .first()
    )

    return {
        "conversation_id": conv.conversation_id,
        "kind": conv.kind,
        "title": title,
        "department_id": conv.department_id,
        "members": members,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
        "last_message": _serialize_message(last_message) if last_message else None,
        "unread_count": int(unread),
    }


# ------------------------------------------------------------------
# staff directory (for the DM picker)
# ------------------------------------------------------------------

@router.get("/staff", dependencies=[Depends(RequirePermission("messaging:read"))])
def list_staff(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    q: Optional[str] = Query(None, description="Search by name or email"),
    limit: int = Query(50, le=200),
):
    query = (
        db.query(User)
        .join(Role, Role.role_id == User.role_id, isouter=True)
        .filter(User.is_active.is_(True))
        .filter(User.user_id != current_user["user_id"])
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))
    users = query.order_by(User.full_name).limit(limit).all()
    return [_serialize_user_brief(u) for u in users]


# ------------------------------------------------------------------
# conversations
# ------------------------------------------------------------------

@router.get("/conversations", dependencies=[Depends(RequirePermission("messaging:read"))])
def list_my_conversations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = current_user["user_id"]
    convs = (
        db.query(Conversation)
        .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.conversation_id)
        .filter(ConversationParticipant.user_id == me)
        .order_by(
            Conversation.last_message_at.desc().nullslast(),
            Conversation.created_at.desc(),
        )
        .all()
    )
    return [_serialize_conversation(db, c, me) for c in convs]


@router.post("/conversations/direct", dependencies=[Depends(RequirePermission("messaging:write"))])
def create_or_get_direct(
    payload: CreateDirectConversationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = current_user["user_id"]
    other_id = payload.user_id
    if other_id == me:
        raise HTTPException(status_code=400, detail="You cannot DM yourself.")

    other = db.query(User).filter(User.user_id == other_id, User.is_active.is_(True)).first()
    if not other:
        raise HTTPException(status_code=404, detail="User not found or inactive.")

    # Look for an existing direct conversation between exactly these two users.
    # We do this by finding all direct conversations the current user is in,
    # then checking which of them has the other user as a co-participant.
    my_direct_ids = {
        cid for (cid,) in
        db.query(ConversationParticipant.conversation_id)
        .join(Conversation, Conversation.conversation_id == ConversationParticipant.conversation_id)
        .filter(
            ConversationParticipant.user_id == me,
            Conversation.kind == "direct",
        )
        .all()
    }
    if my_direct_ids:
        existing = (
            db.query(Conversation.conversation_id)
            .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.conversation_id)
            .filter(
                Conversation.conversation_id.in_(my_direct_ids),
                ConversationParticipant.user_id == other_id,
            )
            .first()
        )
        if existing:
            conv = db.query(Conversation).filter(Conversation.conversation_id == existing[0]).first()
            return _serialize_conversation(db, conv, me)

    conv = Conversation(kind="direct", title=None, created_by=me)
    db.add(conv)
    db.flush()
    db.add(ConversationParticipant(conversation_id=conv.conversation_id, user_id=me))
    db.add(ConversationParticipant(conversation_id=conv.conversation_id, user_id=other_id))
    db.commit()
    db.refresh(conv)
    return _serialize_conversation(db, conv, me)


@router.post("/conversations/group", dependencies=[Depends(RequirePermission("messaging:write"))])
def create_group(
    payload: CreateGroupConversationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = current_user["user_id"]
    member_ids = set(payload.user_ids) | {me}
    member_ids.discard(None)
    if len(member_ids) < 2:
        raise HTTPException(status_code=400, detail="A group needs at least one other participant.")

    valid_users = (
        db.query(User.user_id)
        .filter(User.user_id.in_(member_ids), User.is_active.is_(True))
        .all()
    )
    valid_ids = {row[0] for row in valid_users}
    if len(valid_ids) != len(member_ids):
        raise HTTPException(status_code=400, detail="One or more selected users are invalid.")

    conv = Conversation(kind="group", title=payload.title.strip(), created_by=me)
    db.add(conv)
    db.flush()
    for uid in valid_ids:
        db.add(ConversationParticipant(conversation_id=conv.conversation_id, user_id=uid))
    db.commit()
    db.refresh(conv)
    return _serialize_conversation(db, conv, me)


@router.get("/conversations/{conversation_id}/messages", dependencies=[Depends(RequirePermission("messaging:read"))])
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(100, le=500),
    before_id: Optional[int] = Query(None, description="Cursor: return messages with message_id < this"),
):
    me = current_user["user_id"]
    _ensure_participant(db, conversation_id, me)

    q = db.query(Message).filter(Message.conversation_id == conversation_id)
    if before_id:
        q = q.filter(Message.message_id < before_id)
    rows = q.order_by(Message.message_id.desc()).limit(limit).all()
    rows.reverse()
    return [_serialize_message(m) for m in rows]


@router.post("/conversations/{conversation_id}/messages", dependencies=[Depends(RequirePermission("messaging:write"))])
async def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = current_user["user_id"]
    _ensure_participant(db, conversation_id, me)

    conv = db.query(Conversation).filter(Conversation.conversation_id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    msg = Message(
        conversation_id=conversation_id,
        sender_id=me,
        body=payload.body.strip(),
    )
    db.add(msg)
    conv.last_message_at = datetime.now(timezone.utc)
    db.flush()
    db.commit()
    db.refresh(msg)

    # Mark sender as having read up through their own message — they obviously
    # don't need an unread indicator on what they just typed.
    sender_participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me,
        )
        .first()
    )
    if sender_participant:
        sender_participant.last_read_at = msg.created_at
        db.commit()

    payload_out = {
        "type": "message:new",
        "conversation_id": conversation_id,
        "message": _serialize_message(msg),
    }
    await _broadcast(payload_out, _participant_user_ids(db, conversation_id))
    return _serialize_message(msg)


@router.post("/conversations/{conversation_id}/read", dependencies=[Depends(RequirePermission("messaging:read"))])
async def mark_conversation_read(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    me = current_user["user_id"]
    p = _ensure_participant(db, conversation_id, me)
    p.last_read_at = datetime.now(timezone.utc)
    db.commit()

    # Tell other participants that this user is now caught up. Useful for
    # rendering "seen" indicators in the UI.
    payload = {
        "type": "message:read",
        "conversation_id": conversation_id,
        "user_id": me,
        "read_at": p.last_read_at.isoformat(),
    }
    await _broadcast(payload, _participant_user_ids(db, conversation_id))
    return {"ok": True, "read_at": p.last_read_at.isoformat()}


# ------------------------------------------------------------------
# departments (admin-managed, but readable by anyone with messaging:read)
# ------------------------------------------------------------------

def _serialize_department(db: Session, dept: Department) -> dict:
    members = (
        db.query(User)
        .join(DepartmentMember, DepartmentMember.user_id == User.user_id)
        .filter(DepartmentMember.department_id == dept.department_id)
        .order_by(User.full_name)
        .all()
    )
    return {
        "department_id": dept.department_id,
        "name": dept.name,
        "description": dept.description,
        "is_active": dept.is_active,
        "member_count": len(members),
        "members": [_serialize_user_brief(u) for u in members],
        "created_at": dept.created_at.isoformat() if dept.created_at else None,
    }


def _sync_department_conversation(db: Session, dept: Department) -> Conversation:
    """Ensure a department conversation exists and its participants mirror members."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.department_id == dept.department_id)
        .first()
    )
    if not conv:
        conv = Conversation(
            kind="department",
            title=dept.name,
            department_id=dept.department_id,
            created_by=dept.created_by,
        )
        db.add(conv)
        db.flush()
    else:
        # Keep the title in sync with the department name in case it was renamed.
        conv.title = dept.name

    member_ids = {
        m.user_id for m in
        db.query(DepartmentMember).filter(DepartmentMember.department_id == dept.department_id).all()
    }

    existing_participants = {
        p.user_id: p for p in
        db.query(ConversationParticipant)
        .filter(ConversationParticipant.conversation_id == conv.conversation_id)
        .all()
    }

    # Remove participants who are no longer department members.
    for uid, p in existing_participants.items():
        if uid not in member_ids:
            db.delete(p)

    # Add new members.
    for uid in member_ids:
        if uid not in existing_participants:
            db.add(ConversationParticipant(conversation_id=conv.conversation_id, user_id=uid))

    db.flush()
    return conv


@router.get("/departments", dependencies=[Depends(RequirePermission("messaging:read"))])
def list_departments(db: Session = Depends(get_db)):
    depts = db.query(Department).order_by(Department.name).all()
    return [_serialize_department(db, d) for d in depts]


@router.post("/departments", dependencies=[Depends(RequirePermission("departments:manage"))])
def create_department(
    payload: CreateDepartmentRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    name = payload.name.strip()
    existing = db.query(Department).filter(func.lower(Department.name) == name.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="A department with this name already exists.")

    dept = Department(
        name=name,
        description=(payload.description or None),
        created_by=current_user["user_id"],
    )
    db.add(dept)
    db.flush()

    if payload.member_ids:
        valid = {
            row[0] for row in
            db.query(User.user_id).filter(
                User.user_id.in_(payload.member_ids), User.is_active.is_(True)
            ).all()
        }
        for uid in valid:
            db.add(DepartmentMember(department_id=dept.department_id, user_id=uid))
        db.flush()

    _sync_department_conversation(db, dept)
    db.commit()
    db.refresh(dept)
    return _serialize_department(db, dept)


@router.patch("/departments/{department_id}", dependencies=[Depends(RequirePermission("departments:manage"))])
def update_department(
    department_id: int,
    payload: UpdateDepartmentRequest,
    db: Session = Depends(get_db),
):
    dept = db.query(Department).filter(Department.department_id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    if payload.name is not None:
        new_name = payload.name.strip()
        clash = (
            db.query(Department)
            .filter(func.lower(Department.name) == new_name.lower(), Department.department_id != department_id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=409, detail="Another department already uses that name.")
        dept.name = new_name
    if payload.description is not None:
        dept.description = payload.description or None
    if payload.is_active is not None:
        dept.is_active = payload.is_active

    _sync_department_conversation(db, dept)
    db.commit()
    db.refresh(dept)
    return _serialize_department(db, dept)


@router.put("/departments/{department_id}/members", dependencies=[Depends(RequirePermission("departments:manage"))])
async def set_department_members(
    department_id: int,
    payload: SetDepartmentMembersRequest,
    db: Session = Depends(get_db),
):
    dept = db.query(Department).filter(Department.department_id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    target_ids = set(payload.member_ids)
    if target_ids:
        valid = {
            row[0] for row in
            db.query(User.user_id).filter(
                User.user_id.in_(target_ids), User.is_active.is_(True)
            ).all()
        }
        if len(valid) != len(target_ids):
            raise HTTPException(status_code=400, detail="One or more user_ids are invalid.")
        target_ids = valid

    existing = {
        m.user_id for m in
        db.query(DepartmentMember).filter(DepartmentMember.department_id == department_id).all()
    }

    to_remove = existing - target_ids
    to_add = target_ids - existing

    if to_remove:
        (
            db.query(DepartmentMember)
            .filter(
                DepartmentMember.department_id == department_id,
                DepartmentMember.user_id.in_(to_remove),
            )
            .delete(synchronize_session=False)
        )
    for uid in to_add:
        db.add(DepartmentMember(department_id=department_id, user_id=uid))
    db.flush()

    conv = _sync_department_conversation(db, dept)
    db.commit()

    # Tell newly-added users they have a new conversation; tell removed users
    # to drop it from their UI.
    if to_add:
        await _broadcast(
            {"type": "conversation:joined", "conversation_id": conv.conversation_id},
            list(to_add),
        )
    if to_remove:
        await _broadcast(
            {"type": "conversation:left", "conversation_id": conv.conversation_id},
            list(to_remove),
        )

    db.refresh(dept)
    return _serialize_department(db, dept)


@router.delete("/departments/{department_id}", dependencies=[Depends(RequirePermission("departments:manage"))])
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
):
    dept = db.query(Department).filter(Department.department_id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
    db.delete(dept)  # CASCADE removes members + conversation
    db.commit()
    return {"deleted": True}
