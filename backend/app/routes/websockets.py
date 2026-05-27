from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from app.core.websocket import manager

router = APIRouter(tags=["Realtime WebSockets"])


@router.websocket("/ws/notifications/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    role: Optional[str] = Query(None, description="Connecting user's role for role-channel subscriptions"),
):
    """
    Authenticated WebSocket endpoint for real-time notifications.

    The optional `?role=` query parameter lets the client opt into role-channel
    broadcasts (e.g. all Lab Technicians get notified of a new STAT order). The
    role is validated by the server: it must match the user's actual role
    cached during connect, otherwise role broadcasts won't reach them.
    """
    is_connected = await manager.connect(websocket, user_id, role=role)
    if not is_connected:
        return

    try:
        while True:
            # We mostly send messages to clients. The receive loop keeps the
            # socket open and lets us pick up disconnects promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)


@router.websocket("/ws/payments/{tenant_db}")
async def payments_websocket(websocket: WebSocket, tenant_db: str):
    """Tenant-scoped live payment feed for the cashier / pharmacy checkout.

    Authenticated by the access_token cookie; the token's tenant must match
    ``tenant_db`` so a hospital only ever receives its own payment events.
    The webhook publishes ``payment_update`` frames here the instant a receipt
    settles, turning the checkout spinner into a success/failure state without
    waiting for the next poll.
    """
    is_connected = await manager.connect_payment(websocket, tenant_db)
    if not is_connected:
        return
    topic = f"payment:{tenant_db}"
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_topic(websocket, topic)
