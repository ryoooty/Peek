from __future__ import annotations
from typing import Tuple
from app.config import settings

def get_out_price_per_1k(model: str) -> float:
    pr = settings.pricing
    if model in ("deepseek-reasoner", "deepseek_reasoner"):
        return pr.deepseek_reasoner.out
    return pr.deepseek_chat.out

def calc_user_price_rub(model: str, prompt_tokens: int, completion_tokens: int) -> Tuple[float, float, float]:
    """
    Возвращает (стоимость_инпут, стоимость_аутпут, итого) в ₽.
    Консервативно считаем input как cache-miss.
    """
    pr = settings.pricing
    m = pr.deepseek_reasoner if model in ("deepseek-reasoner", "deepseek_reasoner") else pr.deepseek_chat
    in_k  = prompt_tokens / 1000.0
    out_k = completion_tokens / 1000.0
    price_in  = in_k  * m.in_miss
    price_out = out_k * m.out
    total = round(price_in + price_out, 4)
    return round(price_in, 4), round(price_out, 4), total
