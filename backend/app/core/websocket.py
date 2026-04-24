from fastapi import WebSocket, WebSocketDisconnect, status
from jose import jwt, JWTError
from typing import Dict, List
import json

from app.config.settings import settings

class ConnectionManager:
    def __init__(self):
        # Maps user_id to their active WebSocket connections (a user might have multiple tabs open)
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        # 1. Extract the HttpOnly cookie
        token = websocket.cookies.get("access_token")
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False

        # 2. Cryptographically verify the token
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            token_user_id = payload.get("user_id")
            if token_user_id != user_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return False
        except JWTError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False

        # 3. Accept the secure connection
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        return True

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        """Sends a real-time JSON message to a specific staff member."""
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_text(json.dumps(message))

    async def broadcast_to_role(self, message: dict, role: str):
        """Broadcasts a message (like a new lab order) to all users with a specific role."""
        # In a full implementation, you would look up active users by role.
        # For the MVP, we can broadcast to everyone if needed, or maintain a role map.
        pass

manager = ConnectionManager()