"""AI prompt construction — builds context-enriched prompts for OpenCode."""

from nochan.converter import ParsedMessage


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
