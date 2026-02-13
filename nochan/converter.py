"""Message conversion between OneBot 11 format and AI plain text."""

from dataclasses import dataclass

# Help text template shown for /help and unknown commands
HELP_TEXT = (
    "nochan 指令列表：\n"
    "/new  - 创建新会话（清空 AI 上下文）\n"
    "/help - 显示本帮助信息\n"
    "直接发送文字即可与 AI 对话。"
)


@dataclass
class ParsedMessage:
    """Result of parsing an incoming OneBot message event."""

    # Unique chat identifier: "private:<user_id>" or "group:<group_id>"
    chat_id: str
    # Plain text extracted from message segments (@bot stripped, images→placeholders)
    text: str
    # Whether the bot was @-mentioned in this message (always False for private)
    is_at_bot: bool
    # Display name of the sender (group card preferred, fallback to nickname)
    sender_name: str
    # QQ number of the message sender
    sender_id: int
    # Group name from the event payload (None for private messages)
    group_name: str | None
    # "private" or "group"
    message_type: str


def parse_message_event(event: dict, bot_id: int) -> ParsedMessage:
    """
    Parse an OneBot 11 message event into a structured ParsedMessage.

    Args:
        event: The raw OneBot message event dict
        bot_id: The bot's own QQ ID (from self_id)
    """
    message_type: str = event.get("message_type", "")
    user_id: int = event.get("user_id", 0)
    group_id: int = event.get("group_id", 0)
    group_name: str | None = event.get("group_name")
    segments: list[dict] = event.get("message", [])
    sender: dict = event.get("sender", {})

    # Determine chat_id based on message type
    if message_type == "private":
        chat_id = f"private:{user_id}"
    else:
        chat_id = f"group:{group_id}"

    # Determine display name: prefer card (group nickname), fallback to nickname
    sender_name = sender.get("card") or sender.get("nickname", str(user_id))

    # Parse message segments into plain text and detect @bot
    text_parts: list[str] = []
    is_at_bot = False

    for seg in segments:
        seg_type = seg.get("type", "")
        seg_data = seg.get("data", {})

        if seg_type == "text":
            text_parts.append(seg_data.get("text", ""))

        elif seg_type == "at":
            # data.qq is a STRING in NapCatQQ, bot_id is int
            qq_str = str(seg_data.get("qq", ""))
            if qq_str == str(bot_id):
                is_at_bot = True
                # Skip @bot itself in the text output
            else:
                # Include other @mentions as text
                text_parts.append(f"@{qq_str}")

        elif seg_type == "image":
            text_parts.append("[图片]")

        elif seg_type == "face":
            text_parts.append("[表情]")
        # Other segment types (reply, etc.) are silently ignored

    text = "".join(text_parts).strip()

    return ParsedMessage(
        chat_id=chat_id,
        text=text,
        is_at_bot=is_at_bot,
        sender_name=sender_name,
        sender_id=user_id,
        group_name=group_name,
        message_type=message_type,
    )


def build_prompt(parsed: ParsedMessage) -> str:
    """
    Build the full prompt with context header for OpenCode.

    Prepends sender/group info so the AI knows who is talking.
    """
    if parsed.message_type == "private":
        header = f"[私聊，用户 {parsed.sender_name}({parsed.sender_id})]"
    else:
        header = (
            f"[群聊 {parsed.group_name}({parsed.chat_id.split(':')[1]})，"
            f"用户 {parsed.sender_name}({parsed.sender_id})]"
        )
    return f"{header}\n{parsed.text}"


def parse_command(text: str) -> str | None:
    """
    Parse user command from message text.

    Returns:
        "new" for /new, "help" for /help, "unknown" for other /commands,
        None for regular messages (not a command).
    """
    if not text.startswith("/"):
        return None

    # Extract command name (first word after /)
    cmd = text.split()[0][1:].lower() if text.split() else ""
    if cmd == "new":
        return "new"
    elif cmd == "help":
        return "help"
    else:
        return "unknown"


def to_onebot_message(text: str) -> list[dict]:
    """
    Convert AI response text to OneBot 11 message segment array.

    v1 simply wraps the text in a single text segment.
    """
    return [{"type": "text", "data": {"text": text}}]
