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
