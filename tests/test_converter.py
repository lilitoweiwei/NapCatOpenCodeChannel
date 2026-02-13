"""Tests for the message converter module."""

from nochan.converter import (
    build_prompt,
    parse_command,
    parse_message_event,
    to_onebot_message,
)

BOT_ID = 1234567890


# --- parse_message_event tests ---


def test_parse_private_text_message() -> None:
    """Test parsing a simple private text message."""
    event = {
        "self_id": BOT_ID,
        "user_id": 111222,
        "message_type": "private",
        "sender": {"user_id": 111222, "nickname": "Alice", "card": ""},
        "message": [{"type": "text", "data": {"text": "hello"}}],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    assert parsed.chat_id == "private:111222"
    assert parsed.text == "hello"
    assert parsed.sender_name == "Alice"
    assert parsed.sender_id == 111222
    assert parsed.message_type == "private"
    assert parsed.group_name is None
    assert parsed.is_at_bot is False


def test_parse_group_message_with_at_bot() -> None:
    """Test parsing a group message where the bot is @-mentioned."""
    event = {
        "self_id": BOT_ID,
        "user_id": 333444,
        "message_type": "group",
        "group_id": 999888,
        "group_name": "测试群",
        "sender": {"user_id": 333444, "nickname": "Bob", "card": "Bob群名片"},
        "message": [
            {"type": "at", "data": {"qq": str(BOT_ID)}},
            {"type": "text", "data": {"text": " 你好"}},
        ],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    assert parsed.chat_id == "group:999888"
    assert parsed.text == "你好"
    assert parsed.is_at_bot is True
    assert parsed.group_name == "测试群"
    # Should prefer card over nickname
    assert parsed.sender_name == "Bob群名片"


def test_parse_group_message_without_at_bot() -> None:
    """Test that group messages without @bot have is_at_bot=False."""
    event = {
        "self_id": BOT_ID,
        "user_id": 333444,
        "message_type": "group",
        "group_id": 999888,
        "group_name": "测试群",
        "sender": {"user_id": 333444, "nickname": "Bob", "card": ""},
        "message": [{"type": "text", "data": {"text": "普通消息"}}],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    assert parsed.is_at_bot is False
    assert parsed.text == "普通消息"


def test_parse_mixed_segments() -> None:
    """Test parsing a message with mixed segment types."""
    event = {
        "self_id": BOT_ID,
        "user_id": 111,
        "message_type": "private",
        "sender": {"user_id": 111, "nickname": "User", "card": ""},
        "message": [
            {"type": "text", "data": {"text": "看这个"}},
            {"type": "image", "data": {"url": "http://example.com/img.jpg"}},
            {"type": "text", "data": {"text": "好看吗"}},
            {"type": "face", "data": {"id": "1"}},
        ],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    assert parsed.text == "看这个[图片]好看吗[表情]"


def test_parse_at_other_user() -> None:
    """Test that @-mentioning a non-bot user is included as text."""
    event = {
        "self_id": BOT_ID,
        "user_id": 111,
        "message_type": "group",
        "group_id": 222,
        "group_name": "G",
        "sender": {"user_id": 111, "nickname": "U", "card": ""},
        "message": [
            {"type": "at", "data": {"qq": "999"}},
            {"type": "text", "data": {"text": " 你看看"}},
        ],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    assert parsed.is_at_bot is False
    assert "@999" in parsed.text


def test_sender_name_prefers_card() -> None:
    """Test that card (group nickname) is preferred over nickname."""
    event = {
        "self_id": BOT_ID,
        "user_id": 111,
        "message_type": "group",
        "group_id": 222,
        "group_name": "G",
        "sender": {"user_id": 111, "nickname": "RealName", "card": "CardName"},
        "message": [{"type": "text", "data": {"text": "hi"}}],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    assert parsed.sender_name == "CardName"


def test_sender_name_fallback_to_nickname() -> None:
    """Test fallback to nickname when card is empty."""
    event = {
        "self_id": BOT_ID,
        "user_id": 111,
        "message_type": "group",
        "group_id": 222,
        "group_name": "G",
        "sender": {"user_id": 111, "nickname": "RealName", "card": ""},
        "message": [{"type": "text", "data": {"text": "hi"}}],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    assert parsed.sender_name == "RealName"


# --- build_prompt tests ---


def test_build_prompt_private() -> None:
    """Test prompt building for private messages."""
    event = {
        "self_id": BOT_ID,
        "user_id": 111,
        "message_type": "private",
        "sender": {"user_id": 111, "nickname": "Alice", "card": ""},
        "message": [{"type": "text", "data": {"text": "写个函数"}}],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    prompt = build_prompt(parsed)
    assert "[私聊，用户 Alice(111)]" in prompt
    assert "写个函数" in prompt


def test_build_prompt_group() -> None:
    """Test prompt building for group messages."""
    event = {
        "self_id": BOT_ID,
        "user_id": 111,
        "message_type": "group",
        "group_id": 222,
        "group_name": "开发群",
        "sender": {"user_id": 111, "nickname": "Alice", "card": ""},
        "message": [
            {"type": "at", "data": {"qq": str(BOT_ID)}},
            {"type": "text", "data": {"text": " 帮忙"}},
        ],
        "post_type": "message",
    }
    parsed = parse_message_event(event, BOT_ID)
    prompt = build_prompt(parsed)
    assert "[群聊 开发群(222)" in prompt
    assert "用户 Alice(111)]" in prompt
    assert "帮忙" in prompt


# --- parse_command tests ---


def test_parse_command_new() -> None:
    assert parse_command("/new") == "new"
    assert parse_command("/NEW") == "new"
    assert parse_command("/new extra args") == "new"


def test_parse_command_help() -> None:
    assert parse_command("/help") == "help"


def test_parse_command_unknown() -> None:
    assert parse_command("/foo") == "unknown"
    assert parse_command("/") == "unknown"


def test_parse_command_not_command() -> None:
    assert parse_command("hello") is None
    assert parse_command("not a /command") is None
    assert parse_command("") is None


# --- to_onebot_message tests ---


def test_to_onebot_message() -> None:
    result = to_onebot_message("Hello world")
    assert result == [{"type": "text", "data": {"text": "Hello world"}}]
