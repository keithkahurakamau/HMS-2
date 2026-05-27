"""
ConnectionManager — WebSocket fan-out for real-time notifications.

Two backends:
  • In-process dict (default, for local dev / single worker).
  • Redis pub/sub (recommended for any production deployment with >1 worker
    or multiple replicas behind a load balancer).

When `settings.REDIS_URL` is configured, every send call publishes to a Redis
channel keyed by the addressable target (`hms:user:{id}` or `hms:role:{name}`).
A long-running listener task in each worker subscribes to those channels and
forwards messages to every locally-attached WebSocket. This means a message
sent from worker-A reaches a user whose socket happens to be on worker-B.

If Redis is not configured, the manager logs a warning at boot and falls back
to in-process delivery — fine for development, broken for multi-worker prod.
"""
import asyncio
import json
import logging
from typing import Dict, List, Optional, Set

from fastapi import WebSocket, status
from jose import jwt, JWTError

from app.config.settings import settings

logger = logging.getLogger(__name__)


USER_CHANNEL_PREFIX = "hms:user:"
ROLE_CHANNEL_PREFIX = "hms:role:"
# Generic, arbitrary-keyed topic channel. Used for tenant-scoped payment
# feeds (topic == "payment:{tenant_db}") so a hospital's payment events only
# ever reach that hospital's own staff — never broadcast by role across tenants.
TOPIC_CHANNEL_PREFIX = "hms:topic:"


class ConnectionManager:
    def __init__(self):
        # Local connection registry. Stored per worker; the Redis layer is what
        # makes broadcasts cross-worker.
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # user_id -> role lookup, populated on connect, used for role broadcasts.
        self.user_roles: Dict[int, str] = {}

        # Arbitrary-topic registry (e.g. tenant-scoped payment feeds).
        self.topic_connections: Dict[str, List[WebSocket]] = {}

        self._redis = None  # type: ignore[assignment]
        self._pubsub = None
        self._listener_task: Optional[asyncio.Task] = None
        self._subscribed_user_ids: Set[int] = set()
        self._subscribed_roles: Set[str] = set()
        self._subscribed_topics: Set[str] = set()
        self._lock = asyncio.Lock()
        # The main event loop, captured at startup so synchronous code (e.g. a
        # webhook BackgroundTask running in a threadpool) can publish safely.
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self) -> None:
        """Capture the running loop at app startup for thread-safe publishing."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    # ----- lifecycle -------------------------------------------------
    async def init_redis(self) -> None:
        """Lazily connect to Redis. Safe to call repeatedly; idempotent."""
        if self._redis is not None or not settings.REDIS_URL:
            return
        try:
            import redis.asyncio as redis_async  # type: ignore
            self._redis = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            self._listener_task = asyncio.create_task(self._listen_forever())
            logger.info("WebSocket Redis pub/sub backend initialized: %s", settings.REDIS_URL)
        except ImportError:
            logger.warning("REDIS_URL is set but the 'redis' package is not installed; falling back to in-process broadcast.")
            self._redis = None
        except Exception as exc:
            logger.error("Could not connect to Redis at %s — falling back to in-process broadcast. Cause: %s", settings.REDIS_URL, exc)
            self._redis = None

    async def shutdown(self) -> None:
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._pubsub:
            try:
                await self._pubsub.aclose()
            except Exception:
                pass
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass

    # ----- connect/disconnect ---------------------------------------
    async def connect(self, websocket: WebSocket, user_id: int, role: Optional[str] = None) -> bool:
        token = websocket.cookies.get("access_token")
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False

        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.ALGORITHM],
                options={"verify_aud": False},  # AUTH-002 rollover
            )
            if payload.get("user_id") != user_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return False
        except JWTError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False

        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)
        if role:
            self.user_roles[user_id] = role

        # Make sure Redis is initialized in this worker; subscribe lazily.
        await self.init_redis()
        if self._redis is not None:
            await self._ensure_subscribed_user(user_id)
            if role:
                await self._ensure_subscribed_role(role)
        return True

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                self.user_roles.pop(user_id, None)
                # Note: we deliberately do NOT unsubscribe the channel even when
                # the last connection closes. Re-subscription is cheap and
                # avoids race conditions with reconnecting clients.

    # ----- tenant-scoped topic connect ------------------------------
    async def connect_payment(self, websocket: WebSocket, tenant_db: str) -> bool:
        """Authenticated subscribe to a tenant's payment feed.

        Verifies the access_token cookie AND that its ``tenant_id`` claim
        matches the requested tenant — so a user from hospital B can never
        attach to hospital A's payment channel.
        """
        token = websocket.cookies.get("access_token")
        if not token or not tenant_db:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.ALGORITHM],
                options={"verify_aud": False},
            )
        except JWTError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False
        if payload.get("tenant_id") != tenant_db:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False

        await websocket.accept()
        topic = f"payment:{tenant_db}"
        self.topic_connections.setdefault(topic, []).append(websocket)

        await self.init_redis()
        if self._redis is not None:
            await self._ensure_subscribed_topic(topic)
        return True

    def disconnect_topic(self, websocket: WebSocket, topic: str) -> None:
        if topic in self.topic_connections:
            try:
                self.topic_connections[topic].remove(websocket)
            except ValueError:
                pass
            if not self.topic_connections[topic]:
                del self.topic_connections[topic]

    # ----- public sender API ----------------------------------------
    async def send_personal_message(self, message: dict, user_id: int) -> None:
        """Deliver to a specific user across all workers."""
        if self._redis is not None:
            await self._redis.publish(f"{USER_CHANNEL_PREFIX}{user_id}", json.dumps(message))
        else:
            await self._dispatch_local_user(user_id, message)

    async def broadcast_to_role(self, message: dict, role: str) -> None:
        """Deliver to every user with the given role across all workers."""
        if self._redis is not None:
            await self._redis.publish(f"{ROLE_CHANNEL_PREFIX}{role}", json.dumps(message))
        else:
            await self._dispatch_local_role(role, message)

    async def publish_topic(self, topic: str, message: dict) -> None:
        """Deliver to every subscriber of an arbitrary topic across all workers."""
        if not settings.REDIS_URL:
            await self._dispatch_local_topic(topic, message)
            return
        # Ensure this worker has a Redis client even if no socket has connected
        # here yet (the publisher may be a different worker than the listener).
        await self.init_redis()
        if self._redis is not None:
            await self._redis.publish(f"{TOPIC_CHANNEL_PREFIX}{topic}", json.dumps(message))
        else:
            await self._dispatch_local_topic(topic, message)

    def publish_topic_threadsafe(self, topic: str, message: dict) -> None:
        """Publish from synchronous code (e.g. a webhook BackgroundTask running
        in a threadpool) by scheduling the coroutine on the captured loop."""
        if self._loop is None:
            logger.warning("publish_topic_threadsafe called before loop bind; dropping %s", topic)
            return
        try:
            asyncio.run_coroutine_threadsafe(self.publish_topic(topic, message), self._loop)
        except Exception:  # noqa: BLE001 — never let a notification break settlement
            logger.exception("Failed to schedule WS publish for topic %s", topic)

    # ----- internal: local dispatch ---------------------------------
    async def _dispatch_local_user(self, user_id: int, message: dict) -> None:
        connections = list(self.active_connections.get(user_id, []))
        for ws in connections:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.disconnect(ws, user_id)

    async def _dispatch_local_role(self, role: str, message: dict) -> None:
        for uid, user_role in list(self.user_roles.items()):
            if user_role == role:
                await self._dispatch_local_user(uid, message)

    async def _dispatch_local_topic(self, topic: str, message: dict) -> None:
        for ws in list(self.topic_connections.get(topic, [])):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.disconnect_topic(ws, topic)

    # ----- internal: subscription bookkeeping -----------------------
    async def _ensure_subscribed_user(self, user_id: int) -> None:
        async with self._lock:
            if user_id in self._subscribed_user_ids or self._pubsub is None:
                return
            await self._pubsub.subscribe(f"{USER_CHANNEL_PREFIX}{user_id}")
            self._subscribed_user_ids.add(user_id)

    async def _ensure_subscribed_role(self, role: str) -> None:
        async with self._lock:
            if role in self._subscribed_roles or self._pubsub is None:
                return
            await self._pubsub.subscribe(f"{ROLE_CHANNEL_PREFIX}{role}")
            self._subscribed_roles.add(role)

    async def _ensure_subscribed_topic(self, topic: str) -> None:
        async with self._lock:
            if topic in self._subscribed_topics or self._pubsub is None:
                return
            await self._pubsub.subscribe(f"{TOPIC_CHANNEL_PREFIX}{topic}")
            self._subscribed_topics.add(topic)

    async def _listen_forever(self) -> None:
        """Long-running task that reads pub/sub messages and dispatches locally."""
        if self._pubsub is None:
            return
        try:
            async for raw in self._pubsub.listen():
                if not raw or raw.get("type") != "message":
                    continue
                channel = raw.get("channel")
                data = raw.get("data")
                try:
                    payload = json.loads(data) if isinstance(data, str) else data
                except Exception:
                    continue

                if channel and channel.startswith(USER_CHANNEL_PREFIX):
                    try:
                        user_id = int(channel[len(USER_CHANNEL_PREFIX):])
                    except ValueError:
                        continue
                    await self._dispatch_local_user(user_id, payload)
                elif channel and channel.startswith(ROLE_CHANNEL_PREFIX):
                    role = channel[len(ROLE_CHANNEL_PREFIX):]
                    await self._dispatch_local_role(role, payload)
                elif channel and channel.startswith(TOPIC_CHANNEL_PREFIX):
                    topic = channel[len(TOPIC_CHANNEL_PREFIX):]
                    await self._dispatch_local_topic(topic, payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("WebSocket Redis listener crashed: %s", exc)


manager = ConnectionManager()
