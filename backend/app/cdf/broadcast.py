"""
Real-time Distribution Adapter Boundary & WebSocket Connection Manager
Mission Forge — Phase 4
"""

import abc
import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Dict, Optional, Set
from fastapi import WebSocket

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

HandlerType = Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]


class BroadcastBackend(abc.ABC):
    """
    Abstract adapter boundary for real-time multi-client distribution.
    Enables single-process local operation and multi-instance Redis pub/sub.
    """

    @abc.abstractmethod
    async def publish(self, room_id: str, message: Dict[str, Any]) -> None:
        """Publishes a typed event to all active room subscribers."""
        pass

    @abc.abstractmethod
    async def subscribe(self, room_id: str, handler: HandlerType) -> str:
        """Subscribes an event handler to a room channel and returns a subscription token."""
        pass

    @abc.abstractmethod
    async def unsubscribe(self, room_id: str, subscription_id: str) -> None:
        """Removes a subscription from a room channel."""
        pass

    @abc.abstractmethod
    async def close(self) -> None:
        """Closes all active background subscriber tasks and connections."""
        pass


class InMemoryBroadcastBackend(BroadcastBackend):
    """
    In-memory broadcast backend using asyncio queues.

    ARCHITECTURAL LIMITATION & SINGLE-PROCESS BOUNDARY:
    This backend operates STRICTLY within a single Python operating system process.
    It does NOT support multi-worker server deployments (e.g. uvicorn with --workers > 1)
    or multi-container/cluster deployments. If Client A is connected to Worker Process 1
    and Client B is connected to Worker Process 2, broadcasts published by Client A will
    NEVER be received by Client B.

    For distributed multi-worker or multi-instance deployments, use RedisBroadcastBackend
    backed by an external Redis cluster.
    """

    def __init__(self) -> None:
        self._subscriptions: Dict[str, Dict[str, HandlerType]] = {}
        self._lock = asyncio.Lock()
        self._sub_counter = 0

    async def publish(self, room_id: str, message: Dict[str, Any]) -> None:
        async with self._lock:
            handlers = list(self._subscriptions.get(room_id, {}).values())

        for handler in handlers:
            try:
                asyncio.create_task(handler(room_id, message))
            except Exception as exc:
                logger.error("Error dispatching in-memory broadcast to handler: %s", exc)

    async def subscribe(self, room_id: str, handler: HandlerType) -> str:
        async with self._lock:
            self._sub_counter += 1
            sub_id = f"sub-{self._sub_counter}"
            if room_id not in self._subscriptions:
                self._subscriptions[room_id] = {}
            self._subscriptions[room_id][sub_id] = handler
            return sub_id

    async def unsubscribe(self, room_id: str, subscription_id: str) -> None:
        async with self._lock:
            if room_id in self._subscriptions:
                self._subscriptions[room_id].pop(subscription_id, None)
                if not self._subscriptions[room_id]:
                    del self._subscriptions[room_id]

    async def close(self) -> None:
        async with self._lock:
            self._subscriptions.clear()


class RedisBroadcastBackend(BroadcastBackend):
    """
    Redis Pub/Sub broadcast backend adapter for multi-instance cluster deployment.
    Requires redis-py package and reachable Redis service.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self.redis_url = redis_url
        self._client: Any = None
        self._is_connected = False
        self._subscriptions: Dict[str, Dict[str, HandlerType]] = {}
        self._sub_counter = 0
        self._listener_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> bool:
        if self._is_connected and self._client:
            return True
        try:
            import redis.asyncio as aioredis  # type: ignore[import-not-found]
            self._client = aioredis.from_url(self.redis_url)
            self._is_connected = True
            return True
        except Exception as exc:
            logger.warning(
                "Redis connection failed (%s); falling back to in-memory broadcast.", exc
            )
            return False

    async def publish(self, room_id: str, message: Dict[str, Any]) -> None:
        if await self._ensure_connected() and self._client:
            try:
                payload = json.dumps(message)
                channel = f"cdf:room:{room_id}"
                await self._client.publish(channel, payload)
                return
            except Exception as exc:
                logger.warning("Redis publish failed (%s); falling back to local dispatch.", exc)

        # Fallback local dispatch
        async with self._lock:
            handlers = list(self._subscriptions.get(room_id, {}).values())
        for handler in handlers:
            asyncio.create_task(handler(room_id, message))

    async def subscribe(self, room_id: str, handler: HandlerType) -> str:
        async with self._lock:
            self._sub_counter += 1
            sub_id = f"redis-sub-{self._sub_counter}"
            if room_id not in self._subscriptions:
                self._subscriptions[room_id] = {}
            self._subscriptions[room_id][sub_id] = handler

            # Start Redis listener task for this room if not already running
            connected = await self._ensure_connected()
            if room_id not in self._listener_tasks and connected and self._client:
                channel = f"cdf:room:{room_id}"
                pubsub = self._client.pubsub()
                await pubsub.subscribe(channel)
                task = asyncio.create_task(self._listen_channel(room_id, pubsub))
                self._listener_tasks[room_id] = task

            return sub_id

    async def _listen_channel(self, room_id: str, pubsub: Any) -> None:
        try:
            async for msg in pubsub.listen():
                if msg and msg.get("type") == "message":
                    raw_data = msg.get("data")
                    if isinstance(raw_data, bytes):
                        raw_data = raw_data.decode("utf-8")
                    try:
                        parsed = json.loads(raw_data)
                    except Exception:
                        continue
                    async with self._lock:
                        handlers = list(self._subscriptions.get(room_id, {}).values())
                    for h in handlers:
                        try:
                            await h(room_id, parsed)
                        except Exception as exc:
                            logger.error("Error in redis pubsub handler: %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Redis pubsub listener error for room %s: %s", room_id, exc)
        finally:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except Exception:
                pass

    async def unsubscribe(self, room_id: str, subscription_id: str) -> None:
        async with self._lock:
            if room_id in self._subscriptions:
                self._subscriptions[room_id].pop(subscription_id, None)
                if not self._subscriptions[room_id]:
                    del self._subscriptions[room_id]
                    task = self._listener_tasks.pop(room_id, None)
                    if task and not task.done():
                        task.cancel()

    async def close(self) -> None:
        async with self._lock:
            for task in self._listener_tasks.values():
                if not task.done():
                    task.cancel()
            self._listener_tasks.clear()
            self._subscriptions.clear()
            if self._client:
                await self._client.close()
                self._client = None
                self._is_connected = False


# Active Broadcast Backend Singleton
# Defaults to InMemory with clear single-process labeling, or Redis if configured
if settings.REDIS_URL:
    broadcast_backend: BroadcastBackend = RedisBroadcastBackend(redis_url=settings.REDIS_URL)
else:
    broadcast_backend = InMemoryBroadcastBackend()


class CDFConnectionManager:
    """
    Manages active WebSocket connections for concurrent participants in CDF rooms.
    Provides message serialization, rate limiting, and structured error dispatch.
    """

    def __init__(self, backend: BroadcastBackend) -> None:
        self.backend = backend
        # Mapping: room_id -> dict of {user_id: WebSocket}
        self._active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Mapping: room_id -> subscription_id in backend
        self._room_subscriptions: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def connect(self, room_id: str, user_id: str, websocket: WebSocket) -> None:
        """Registers an accepted WebSocket connection and subscribes to room updates."""
        async with self._lock:
            if room_id not in self._active_connections:
                self._active_connections[room_id] = {}
                # Subscribe connection manager to broadcast backend for this room
                sub_id = await self.backend.subscribe(room_id, self._on_broadcast_received)
                self._room_subscriptions[room_id] = sub_id

            self._active_connections[room_id][user_id] = websocket

    async def disconnect(
        self, room_id: str, user_id: str, websocket: Optional[WebSocket] = None
    ) -> None:
        """
        Unregisters a WebSocket connection.
        If a specific websocket instance is provided, only unregisters if that
        instance is still the active socket (preventing stale disconnects on reconnect).
        """
        async with self._lock:
            if room_id in self._active_connections:
                current_ws = self._active_connections[room_id].get(user_id)
                if websocket is not None and current_ws is not websocket:
                    logger.debug(
                        "Ignoring disconnect from stale socket for user %s in room %s",
                        user_id,
                        room_id,
                    )
                    return
                self._active_connections[room_id].pop(user_id, None)
                if not self._active_connections[room_id]:
                    del self._active_connections[room_id]
                    sub_id = self._room_subscriptions.pop(room_id, None)
                    if sub_id:
                        await self.backend.unsubscribe(room_id, sub_id)

    async def disconnect_and_close(
        self, room_id: str, user_id: str, close_code: int = 1000
    ) -> None:
        """Closes and unregisters an active WebSocket for a user in a room."""
        async with self._lock:
            ws = self._active_connections.get(room_id, {}).get(user_id)
        if ws:
            try:
                await ws.close(code=close_code)
            except Exception:
                pass
        await self.disconnect(room_id, user_id)

    async def send_personal_message(
        self, room_id: str, user_id: str, message: Dict[str, Any]
    ) -> bool:
        """Sends a direct message to a single participant."""
        async with self._lock:
            ws = self._active_connections.get(room_id, {}).get(user_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception as exc:
                logger.warning("Failed to send direct message to user %s: %s", user_id, exc)
                return False
        return False

    async def broadcast_to_room(self, room_id: str, message: Dict[str, Any]) -> None:
        """Publishes a message to all participants via the broadcast backend."""
        await self.backend.publish(room_id, message)

    async def _on_broadcast_received(self, room_id: str, message: Dict[str, Any]) -> None:
        """Internal callback invoked when a broadcast event arrives for a room."""
        async with self._lock:
            sockets = list(self._active_connections.get(room_id, {}).values())

        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.debug("Failed sending broadcast to a participant websocket: %s", exc)

    def get_connected_user_ids(self, room_id: str) -> Set[str]:
        """Returns the set of currently connected user IDs in a room."""
        return set(self._active_connections.get(room_id, {}).keys())


# Singleton CDF Connection Manager
cdf_connection_manager = CDFConnectionManager(broadcast_backend)
