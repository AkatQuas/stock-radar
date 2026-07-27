CD_SECS = 600
COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]


class RateLimitError(RuntimeError):
    """表示命中限流/封禁，需要长时间冷却后重试。"""
