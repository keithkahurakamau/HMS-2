"""Support tickets.

Two surfaces:
  - ``/api/support/...``                        — for tenant Admins to raise and
                                                 follow up tickets to the
                                                 MediFleet platform team.
  - ``/api/public/superadmin/tickets/...``      — for platform superadmins to
                                                 triage, respond, and close.

Tickets live in the master DB so the platform team can see them in one inbox.
Tenant-side endpoints authenticate via the usual tenant cookie + RBAC, then
write to the master DB through ``MasterSessionLocal``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config.database import MasterSessionLocal, get_db, get_master_db
from app.core.dependencies import RequirePermission, get_current_user, require_superadmin
from app.models.master import Tenant
from app.models.support import SupportTicket, SupportMessage

logger = logging.getLogger(__name__)


CATEGORIES = {"Billing", "Bug", "Feature", "Account", "Onboarding", "Other"}
PRIORITIES = {"Low", "Normal", "High", "Urgent"}
STATUSES = {"Open", "In Progress", "Waiting on Customer", "Resolved", "Closed"}
TERMINAL_STATUSES = {"Resolved", "Closed"}


def _get_master() -> Session:
    """Yields a master-DB session, used by tenant-side handlers that need to
    write to ``hms_master`` without going through the FastAPI dependency
    (we still want the tenant-DB session for auth)."""
    return MasterSessionLocal()


def _serialize_ticket(t: SupportTicket, *, include_messages: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ticket_id": t.ticket_id,
        "tenant_id": t.tenant_id,
        "tenant_name": t.tenant_name,
        "submitter_email": t.submitter_email,
        "submitter_name": t.submitter_name,
        "subject": t.subject,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "assigned_to_admin_id": t.assigned_to_admin_id,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "first_response_at": t.first_response_at.isoformat() if t.first_response_at else None,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
    }
    if include_messages:
        out["messages"] = [
            {
                "message_id": m.message_id,
                "author_kind": m.author_kind,
                "author_name": m.author_name,
                "body": m.body,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in t.messages
        ]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Tenant-side router
# ─────────────────────────────────────────────────────────────────────────────
tenant_router = APIRouter(prefix="/api/support", tags=["Support (tenant)"])


class TicketCreate(BaseModel):
    subject: str = Field(min_length=4, max_length=200)
    body: str = Field(min_length=10)
    category: str = "Other"
    priority: str = "Normal"

    @field_validator("category")
    @classmethod
    def cat_in_set(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
        return v

    @field_validator("priority")
    @classmethod
    def prio_in_set(cls, v):
        if v not in PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(PRIORITIES)}")
        return v


class TicketReply(BaseModel):
    body: str = Field(min_length=1)


@tenant_router.get("/", dependencies=[Depends(RequirePermission("support:manage"))])
def list_my_tenant_tickets(
    request: Request,
    status: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
    tenant_db: Session = Depends(get_db),  # noqa: ARG001 — auth side-effect only
):
    """List tickets raised by *this tenant*. Read-only — every staff member
    with support:manage sees the same tenant inbox so handover is painless."""
    tenant_db_name = request.headers.get("X-Tenant-ID")
    master = _get_master()
    try:
        tenant = master.query(Tenant).filter(Tenant.db_name == tenant_db_name).first()
        if not tenant:
            raise HTTPException(status_code=400, detail="Unknown tenant.")
        q = master.query(SupportTicket).filter(SupportTicket.tenant_id == tenant.tenant_id)
        if status:
            q = q.filter(SupportTicket.status == status)
        rows = q.order_by(SupportTicket.created_at.desc()).all()
        return [_serialize_ticket(t) for t in rows]
    finally:
        master.close()


@tenant_router.get("/{ticket_id}", dependencies=[Depends(RequirePermission("support:manage"))])
def get_tenant_ticket(
    ticket_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    tenant_db: Session = Depends(get_db),  # noqa: ARG001 — auth
):
    tenant_db_name = request.headers.get("X-Tenant-ID")
    master = _get_master()
    try:
        tenant = master.query(Tenant).filter(Tenant.db_name == tenant_db_name).first()
        ticket = master.query(SupportTicket).filter(
            SupportTicket.ticket_id == ticket_id,
            SupportTicket.tenant_id == tenant.tenant_id,
        ).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return _serialize_ticket(ticket, include_messages=True)
    finally:
        master.close()


@tenant_router.post("/", dependencies=[Depends(RequirePermission("support:manage"))])
def create_tenant_ticket(
    payload: TicketCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    tenant_db: Session = Depends(get_db),  # noqa: ARG001 — auth
):
    tenant_db_name = request.headers.get("X-Tenant-ID")
    master = _get_master()
    try:
        tenant = master.query(Tenant).filter(Tenant.db_name == tenant_db_name).first()
        if not tenant:
            raise HTTPException(status_code=400, detail="Unknown tenant.")
        ticket = SupportTicket(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.name,
            submitter_email=current_user["email"],
            submitter_name=current_user["full_name"],
            submitter_user_id=current_user["user_id"],
            subject=payload.subject.strip(),
            category=payload.category,
            priority=payload.priority,
            status="Open",
        )
        master.add(ticket)
        master.flush()
        master.add(SupportMessage(
            ticket_id=ticket.ticket_id,
            author_kind="staff",
            author_name=current_user["full_name"],
            author_id=current_user["user_id"],
            body=payload.body.strip(),
        ))
        master.commit()
        master.refresh(ticket)
        return _serialize_ticket(ticket, include_messages=True)
    finally:
        master.close()


@tenant_router.post("/{ticket_id}/reply", dependencies=[Depends(RequirePermission("support:manage"))])
def reply_to_tenant_ticket(
    ticket_id: int,
    payload: TicketReply,
    request: Request,
    current_user: dict = Depends(get_current_user),
    tenant_db: Session = Depends(get_db),  # noqa: ARG001
):
    tenant_db_name = request.headers.get("X-Tenant-ID")
    master = _get_master()
    try:
        tenant = master.query(Tenant).filter(Tenant.db_name == tenant_db_name).first()
        ticket = master.query(SupportTicket).filter(
            SupportTicket.ticket_id == ticket_id,
            SupportTicket.tenant_id == tenant.tenant_id,
        ).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        if ticket.status in TERMINAL_STATUSES:
            raise HTTPException(status_code=400, detail=f"Ticket is {ticket.status}; reopen it to add messages.")
        master.add(SupportMessage(
            ticket_id=ticket.ticket_id,
            author_kind="staff",
            author_name=current_user["full_name"],
            author_id=current_user["user_id"],
            body=payload.body.strip(),
        ))
        # Staff reply usually means "still need help" — flip status from
        # Waiting-on-Customer back to In Progress so it surfaces in the
        # superadmin queue.
        if ticket.status == "Waiting on Customer":
            ticket.status = "In Progress"
        master.commit()
        master.refresh(ticket)
        return _serialize_ticket(ticket, include_messages=True)
    finally:
        master.close()


@tenant_router.post("/{ticket_id}/close", dependencies=[Depends(RequirePermission("support:manage"))])
def close_tenant_ticket(
    ticket_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    tenant_db: Session = Depends(get_db),  # noqa: ARG001
):
    """Tenants can close their own ticket once they're satisfied."""
    tenant_db_name = request.headers.get("X-Tenant-ID")
    master = _get_master()
    try:
        tenant = master.query(Tenant).filter(Tenant.db_name == tenant_db_name).first()
        ticket = master.query(SupportTicket).filter(
            SupportTicket.ticket_id == ticket_id,
            SupportTicket.tenant_id == tenant.tenant_id,
        ).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        if ticket.status == "Closed":
            return _serialize_ticket(ticket, include_messages=True)
        ticket.status = "Closed"
        ticket.resolved_at = ticket.resolved_at or datetime.now()
        master.add(SupportMessage(
            ticket_id=ticket.ticket_id,
            author_kind="staff",
            author_name=current_user["full_name"],
            author_id=current_user["user_id"],
            body="(Closed by tenant.)",
        ))
        master.commit()
        master.refresh(ticket)
        return _serialize_ticket(ticket, include_messages=True)
    finally:
        master.close()


# ─────────────────────────────────────────────────────────────────────────────
# Superadmin-side router (mounted under /api/public/superadmin to ride the same
# auth guard the cross-tenant patient browser uses).
# ─────────────────────────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/api/public/superadmin/tickets", tags=["Support (platform)"])


class AdminReply(BaseModel):
    body: str = Field(min_length=1)


class AdminStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_in_set(cls, v):
        if v not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        return v


class AdminAssign(BaseModel):
    admin_id: Optional[int] = None


@admin_router.get("/summary", dependencies=[Depends(require_superadmin)])
def admin_summary(master_db: Session = Depends(get_master_db)):
    """Per-status counters for the inbox header."""
    from sqlalchemy import func as sqlfunc
    rows = (master_db.query(SupportTicket.status, sqlfunc.count(SupportTicket.ticket_id))
            .group_by(SupportTicket.status).all())
    out = {s: 0 for s in STATUSES}
    for status, count in rows:
        out[status] = int(count)
    out["total"] = sum(out.values())
    return out


@admin_router.get("/", dependencies=[Depends(require_superadmin)])
def admin_list(
    status: Optional[str] = Query(default=None),
    tenant_id: Optional[int] = Query(default=None),
    category: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    master_db: Session = Depends(get_master_db),
):
    q = master_db.query(SupportTicket)
    if status:
        q = q.filter(SupportTicket.status == status)
    if tenant_id:
        q = q.filter(SupportTicket.tenant_id == tenant_id)
    if category:
        q = q.filter(SupportTicket.category == category)
    if priority:
        q = q.filter(SupportTicket.priority == priority)
    if search:
        needle = f"%{search}%"
        q = q.filter(SupportTicket.subject.ilike(needle))

    return [_serialize_ticket(t) for t in q.order_by(SupportTicket.created_at.desc()).all()]


@admin_router.get("/{ticket_id}", dependencies=[Depends(require_superadmin)])
def admin_detail(ticket_id: int, master_db: Session = Depends(get_master_db)):
    t = master_db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return _serialize_ticket(t, include_messages=True)


@admin_router.post("/{ticket_id}/reply", dependencies=[Depends(require_superadmin)])
def admin_reply(
    ticket_id: int,
    payload: AdminReply,
    master_db: Session = Depends(get_master_db),
    superadmin: dict = Depends(require_superadmin),
):
    t = master_db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if t.status == "Closed":
        raise HTTPException(status_code=400, detail="Ticket is Closed; reopen it to add messages.")

    master_db.add(SupportMessage(
        ticket_id=t.ticket_id,
        author_kind="platform",
        author_name=superadmin["full_name"],
        author_id=superadmin["admin_id"],
        body=payload.body.strip(),
    ))
    # First response auto-flips Open → In Progress and records first_response_at.
    if t.status == "Open":
        t.status = "In Progress"
    if t.first_response_at is None:
        t.first_response_at = datetime.now()
    master_db.commit()
    master_db.refresh(t)
    return _serialize_ticket(t, include_messages=True)


@admin_router.patch("/{ticket_id}/status", dependencies=[Depends(require_superadmin)])
def admin_set_status(
    ticket_id: int,
    payload: AdminStatusUpdate,
    master_db: Session = Depends(get_master_db),
):
    t = master_db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    t.status = payload.status
    if payload.status in TERMINAL_STATUSES and t.resolved_at is None:
        t.resolved_at = datetime.now()
    if payload.status not in TERMINAL_STATUSES and t.resolved_at is not None:
        # Reopened — clear the resolved-at marker so SLA math stays honest.
        t.resolved_at = None
    master_db.commit()
    master_db.refresh(t)
    return _serialize_ticket(t)


@admin_router.patch("/{ticket_id}/assign", dependencies=[Depends(require_superadmin)])
def admin_assign(
    ticket_id: int,
    payload: AdminAssign,
    master_db: Session = Depends(get_master_db),
):
    t = master_db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    t.assigned_to_admin_id = payload.admin_id
    master_db.commit()
    master_db.refresh(t)
    return _serialize_ticket(t)
