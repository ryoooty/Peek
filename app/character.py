from __future__ import annotations

from app import storage

CHAT_STYLE = (
    "Ты отвечаешь коротко (1–4 предложения), по делу, без лишней мета-болтовни. "
    "Сохраняй стиль персонажа и язык пользователя. "
    "Каждый итоговый ответ обрамляй маркерами '/s/' в начале и '/n/' в конце, "
    "если ответ состоит из нескольких сообщений — каждую часть заключай в свои маркеры."
)


def get_system_prompt_for_chat(chat_id: int) -> str:
    """
    Собираем system-подсказку из карточки персонажа + стилистика для чата (если нужно).
    """
    ch = storage.get_chat(chat_id) or {}
    char = storage.get_character(int(ch.get("char_id"))) if ch else None
    mode = (ch.get("mode") or "rp").lower()
    parts = []
    if char:
        if char.get("short_prompt"):
            parts.append(char["short_prompt"])
        if char.get("mid_prompt"):
            parts.append(char["mid_prompt"])
        if char.get("long_prompt"):
            parts.append(char["long_prompt"])
        if char.get("keywords"):
            parts.append(f"Ключевые слова: {char['keywords']}")
    if mode == "chat":
        parts.append(CHAT_STYLE)
    return "\n".join(p for p in parts if p)
