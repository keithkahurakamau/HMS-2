from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.websocket import manager

router = APIRouter(tags=["Realtime WebSockets"])

@router.websocket("/ws/notifications/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    # Attempt to securely connect and validate JWT via HttpOnly cookie
    is_connected = await manager.connect(websocket, user_id)
    if not is_connected:
        return # Connection was rejected by the manager

    try:
        while True:
            # Keep the connection alive. We mostly SEND messages to clients, 
            # but we must listen to keep the socket open.
            data = await websocket.receive_text()
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)