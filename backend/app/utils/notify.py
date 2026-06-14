"""
Single helper for emitting persistent + real-time notifications together.

Server code calls `notify(...)` instead of touching the WebSocket layer or the
DB directly. The helper writes a Notification row and (best-effort) publishes
a WebSocket message so the bell + toast update live without a refresh.
"""
import asyncio
import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.core.websocket import manager

logger = logging.getLogger(__name__)


def users_with_permission(db: Session, codename: str, *, exclude_roles: tuple = ()) -> list[int]:
    """Active user_ids whose *effective* permissions include `codename`.

    Effective = (role.permissions ∪ explicit grants) − explicit revokes —
    the same rule get_current_user applies, expressed as set queries so a
    fan-out doesn't load every user's permission graph.

    `exclude_roles` drops named roles from the audience. The main use is
    ("Admin",) on high-frequency operational events: Admin holds every
    permission, and a bell that rings for every queue entry and dispense
    across the hospital is a bell that gets ignored.
    """
    from app.models.user import Permission, Role, User, UserPermissionOverride, role_permissions

    perm = db.query(Permission).filter(Permission.codename == codename).first()
    if not perm:
        logger.warning("notify: unknown permission codename %r — nobody notified", codename)
        return []

    role_holder_q = (
        db.query(User.user_id)
        .join(Role, User.role_id == Role.role_id)
        .join(role_permissions, role_permissions.c.role_id == Role.role_id)
        .filter(role_permissions.c.permission_id == perm.permission_id,
                User.is_active == True)  # noqa: E712
    )
    if exclude_roles:
        role_holder_q = role_holder_q.filter(~Role.name.in_(exclude_roles))
    role_holders = role_holder_q.all()
    granted = (
        db.query(UserPermissionOverride.user_id)
        .join(User, User.user_id == UserPermissionOverride.user_id)
        .filter(UserPermissionOverride.permission_id == perm.permission_id,
                UserPermissionOverride.granted == True,  # noqa: E712
                User.is_active == True)  # noqa: E712
        .all()
    )
    revoked = {
        uid for (uid,) in db.query(UserPermissionOverride.user_id)
        .filter(UserPermissionOverride.permission_id == perm.permission_id,
                UserPermissionOverride.granted == False)  # noqa: E712
        .all()
    }
    holders = {uid for (uid,) in role_holders} | {uid for (uid,) in granted}
    return sorted(holders - revoked)


def notify(
    db: Session,
    *,
    user_id: int,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    category: str = "info",
    flush: bool = True,
) -> Notification:
    """
    Persists a notification and pushes a real-time fan-out message.

    The caller commits the surrounding transaction. If `flush=True` (default)
    the row is flushed so the notification_id is available on the returned
    object.
    """
    n = Notification(
        user_id=user_id,
        category=category,
        title=title,
        body=body,
        link=link,
    )
    db.add(n)
    if flush:
        db.flush()

    payload = {
        "type": "notification",
        "notification_id": n.notification_id,
        "category": category,
        "title": title,
        "body": body,
        "link": link,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }

    # Real-time fan-out is best-effort — never block the write path.
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(manager.send_personal_message(payload, user_id))
            else:
                loop.run_until_complete(manager.send_personal_message(payload, user_id))
        except RuntimeError:
            asyncio.run(manager.send_personal_message(payload, user_id))
    except Exception as exc:
        logger.warning("notify(): WebSocket fan-out failed for user %s: %s", user_id, exc)

    return n


def notify_users(
    db: Session,
    user_ids: Iterable[int],
    *,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    category: str = "info",
    exclude_user_id: Optional[int] = None,
) -> int:
    """Notify several users at once. Returns how many were notified.

    `exclude_user_id` skips the actor — the doctor who routed a prescription
    doesn't need to be told a prescription was routed.
    """
    sent = 0
    for uid in user_ids:
        if exclude_user_id is not None and uid == exclude_user_id:
            continue
        notify(db, user_id=uid, title=title, body=body, link=link, category=category)
        sent += 1
    return sent


def notify_permission(
    db: Session,
    codename: str,
    *,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    category: str = "info",
    exclude_user_id: Optional[int] = None,
    exclude_roles: tuple = ("Admin",),
) -> int:
    """Notify every active user who effectively holds `codename`.

    Permission-keyed (not role-keyed) so custom roles a tenant creates get
    the right notifications automatically — same philosophy as route guards.
    Admin is excluded by default (they hold every permission; pass
    exclude_roles=() for events admins genuinely need).
    Best-effort: a failure here must never sink the caller's transaction.
    """
    try:
        return notify_users(
            db, users_with_permission(db, codename, exclude_roles=exclude_roles),
            title=title, body=body, link=link, category=category,
            exclude_user_id=exclude_user_id,
        )
    except Exception as exc:  # noqa: BLE001 — notifications are never fatal
        logger.warning("notify_permission(%s) failed: %s", codename, exc)
        return 0


def notify_role(
    db: Session,
    role_name: str,
    *,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    category: str = "info",
    exclude_user_id: Optional[int] = None,
) -> int:
    """Notify every active user holding a named role.

    For audiences a permission can't express — e.g. lab orders should reach
    Lab Technicians, but doctors also hold laboratory:manage (for catalogue
    edits) and must not be paged for every order they themselves place.
    """
    from app.models.user import Role, User

    try:
        ids = [
            uid for (uid,) in db.query(User.user_id)
            .join(Role, User.role_id == Role.role_id)
            .filter(Role.name == role_name, User.is_active == True)  # noqa: E712
            .all()
        ]
        return notify_users(
            db, ids, title=title, body=body, link=link, category=category,
            exclude_user_id=exclude_user_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("notify_role(%s) failed: %s", role_name, exc)
        return 0
