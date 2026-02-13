"""Tests for the AI prompt builder module."""

from nochan.converter import onebot_to_internal
from nochan.prompt import build_prompt

BOT_ID = 1234567890


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
    parsed = onebot_to_internal(event, BOT_ID)
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
    parsed = onebot_to_internal(event, BOT_ID)
    prompt = build_prompt(parsed)
    assert "[群聊 开发群(222)" in prompt
    assert "用户 Alice(111)]" in prompt
    assert "帮忙" in prompt
