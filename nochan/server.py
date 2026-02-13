"""WebSocket server for receiving OneBot 11 events from NapCatQQ."""

import asyncio
import json
import logging
import uuid

import websockets
from websockets.server import ServerConnection

from nochan.converter import (
    HELP_TEXT,
    build_prompt,
    parse_command,
    parse_message_event,
    to_onebot_message,
)
from nochan.opencode import SubprocessOpenCodeBackend
from nochan.session import SessionManager

logger = logging.getLogger("nochan.server")


class NochanServer:
    """WebSocket server that bridges NapCatQQ and OpenCode."""

    def __init__(
        self,
        host: str,
        port: int,
        session_manager: SessionManager,
        opencode_backend: SubprocessOpenCodeBackend,
    ) -> None:
        # WebSocket bind address and port
        self._host = host
        self._port = port
        # Session manager for chat-to-opencode session mapping
        self._session_manager = session_manager
        # OpenCode backend for sending prompts and receiving AI responses
        self._opencode_backend = opencode_backend

        # Currently active WebSocket connection from NapCatQQ (only one expected)
        self._connection: ServerConnection | None = None
        # Bot's own QQ ID, extracted from self_id in the first received event
        self._bot_id: int | None = None
        # In-flight API calls awaiting response, keyed by echo ID
        self._pending: dict[str, asyncio.Future[dict]] = {}

    async def start(self) -> None:
        """Start the WebSocket server and run forever."""
        logger.info(
            "Starting nochan server on ws://%s:%d", self._host, self._port
        )
        # Use None for host to bind all interfaces (IPv4 + IPv6)
        host = None if self._host == "0.0.0.0" else self._host
        async with websockets.serve(self._handler, host, self._port):
            logger.info("Server ready, waiting for NapCatQQ connection...")
            await asyncio.Future()  # run forever

    async def _handler(self, websocket: ServerConnection) -> None:
        """Handle a WebSocket connection from NapCatQQ."""
        remote = websocket.remote_address
        logger.info("NapCatQQ connected from %s", remote)
        self._connection = websocket

        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON message received: %s", str(raw_message)[:200])
                    continue

                # Check if this is an API response (has echo field matching a pending request)
                if "echo" in data and data["echo"] in self._pending:
                    echo = data["echo"]
                    self._pending[echo].set_result(data)
                    del self._pending[echo]
                    continue

                # Dispatch by event type
                await self._dispatch_event(data)

        except websockets.ConnectionClosed as e:
            logger.warning("Connection closed: code=%s reason=%s", e.code, e.reason)
        finally:
            self._connection = None
            logger.info("Connection handler exited")

    async def _dispatch_event(self, event: dict) -> None:
        """Route an incoming OneBot event to the appropriate handler."""
        post_type = event.get("post_type", "")

        # Extract bot ID from any event's self_id
        if self._bot_id is None and "self_id" in event:
            self._bot_id = event["self_id"]
            logger.info("Bot QQ ID: %d", self._bot_id)

        if post_type == "meta_event":
            meta_type = event.get("meta_event_type", "")
            if meta_type == "lifecycle":
                logger.info("Lifecycle event: sub_type=%s", event.get("sub_type"))
            elif meta_type == "heartbeat":
                logger.debug("Heartbeat received")
            else:
                logger.debug("Unhandled meta event: %s", meta_type)

        elif post_type == "message":
            # Log every incoming message at DEBUG for full traceability
            msg_type = event.get("message_type", "?")
            user_id = event.get("user_id", "?")
            raw_msg = event.get("raw_message", "")[:150]
            logger.debug(
                "Raw message event: type=%s user=%s raw=%s",
                msg_type, user_id, raw_msg,
            )
            # Handle message events in a separate task to not block the event loop
            asyncio.create_task(self._handle_message(event))

        elif post_type == "notice":
            logger.debug(
                "Unhandled notice event: type=%s data=%s",
                event.get("notice_type", "?"),
                {k: v for k, v in event.items() if k not in ("post_type",)},
            )

        elif post_type == "request":
            logger.debug(
                "Unhandled request event: type=%s data=%s",
                event.get("request_type", "?"),
                {k: v for k, v in event.items() if k not in ("post_type",)},
            )

        else:
            logger.debug("Unknown post_type: %s keys=%s", post_type, list(event.keys()))

    async def _handle_message(self, event: dict) -> None:
        """Process an incoming message event through the full pipeline."""
        try:
            if self._bot_id is None:
                logger.warning("Received message before bot_id was set, ignoring")
                return

            # Step 1: Parse the message event
            parsed = parse_message_event(event, self._bot_id)

            # Step 2: Group messages require @bot
            if parsed.message_type == "group" and not parsed.is_at_bot:
                logger.debug(
                    "Ignored group message (no @bot): group=%s user=%s text=%s",
                    parsed.chat_id, parsed.sender_name, parsed.text[:100],
                )
                return

            logger.info(
                "Processing message from %s (%s): %s",
                parsed.sender_name, parsed.chat_id, parsed.text[:100],
            )

            # Step 3: Check for commands
            command = parse_command(parsed.text)
            if command is not None:
                logger.info("Command received: /%s from %s", command, parsed.chat_id)
                await self._handle_command(command, parsed, event)
                return

            # Step 4: Get or create session
            session = await self._session_manager.get_active_session(parsed.chat_id)
            if session is None:
                session = await self._session_manager.create_session(parsed.chat_id)

            # Step 5: Build prompt with context
            prompt = build_prompt(parsed)

            # Step 6: Check queue and send queuing notice if needed
            if self._opencode_backend.is_queue_full():
                await self._reply_text(event, "AI 正在忙，你的请求已排队，请稍候...")

            # Step 7: Call OpenCode
            response = await self._opencode_backend.send_message(
                session.opencode_session_id, prompt
            )

            # Step 8: Update session with OpenCode session ID if new
            if session.opencode_session_id is None and response.session_id:
                await self._session_manager.update_opencode_session_id(
                    session.id, response.session_id
                )

            # Step 9-10: Convert and send reply
            if response.success and response.content:
                logger.info(
                    "Sending AI reply to %s (%d chars)",
                    parsed.chat_id, len(response.content),
                )
                await self._reply_text(event, response.content)
            elif response.success and not response.content:
                logger.warning("OpenCode returned empty content for %s", parsed.chat_id)
                await self._reply_text(event, "AI 未返回有效回复")
            else:
                logger.error(
                    "OpenCode failed for %s: %s", parsed.chat_id, response.error,
                )
                await self._reply_text(event, "AI 处理出错，请稍后重试")

        except Exception as e:
            logger.error("Error handling message: %s", e, exc_info=True)
            try:
                await self._reply_text(event, "处理消息时发生内部错误")
            except Exception:
                pass

    async def _handle_command(
        self, command: str, parsed: "ParsedMessage", event: dict
    ) -> None:
        """Handle a user command (/new, /help, etc.)."""
        if command == "new":
            # Archive current session and create a new one
            await self._session_manager.archive_active_session(parsed.chat_id)
            await self._session_manager.create_session(parsed.chat_id)
            await self._reply_text(event, "已创建新会话，AI 上下文已清空。")
            logger.info("New session created for %s", parsed.chat_id)

        elif command == "help" or command == "unknown":
            await self._reply_text(event, HELP_TEXT)

    async def _reply_text(self, event: dict, text: str) -> None:
        """Send a text reply back to the source of the message event."""
        message_type = event.get("message_type", "")
        segments = to_onebot_message(text)

        # Log the reply text at DEBUG (may be long)
        logger.debug("Reply text (%d chars): %s", len(text), text[:300])

        if message_type == "private":
            resp = await self.send_api("send_private_msg", {
                "user_id": event["user_id"],
                "message": segments,
            })
            if resp and resp.get("retcode") != 0:
                logger.warning("send_private_msg failed: %s", resp)
        elif message_type == "group":
            resp = await self.send_api("send_group_msg", {
                "group_id": event["group_id"],
                "message": segments,
            })
            if resp and resp.get("retcode") != 0:
                logger.warning("send_group_msg failed: %s", resp)

    async def send_api(
        self, action: str, params: dict | None = None
    ) -> dict | None:
        """
        Send an OneBot 11 API request via WebSocket and wait for response.

        Returns the response dict, or None if no connection or timeout.
        """
        if self._connection is None:
            logger.warning("Cannot send API %s: no active connection", action)
            return None

        echo = str(uuid.uuid4())[:8]
        request = {
            "action": action,
            "params": params or {},
            "echo": echo,
        }

        # Create future for response
        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending[echo] = future

        try:
            logger.debug("API request: action=%s echo=%s", action, echo)
            await self._connection.send(json.dumps(request))
            # Wait for response with 10s timeout
            response = await asyncio.wait_for(future, timeout=10.0)
            logger.debug(
                "API response: action=%s status=%s retcode=%s",
                action, response.get("status"), response.get("retcode"),
            )
            return response
        except asyncio.TimeoutError:
            logger.warning("API call %s timed out", action)
            self._pending.pop(echo, None)
            return None
        except websockets.ConnectionClosed:
            logger.warning("Connection closed while waiting for API %s", action)
            self._pending.pop(echo, None)
            return None
