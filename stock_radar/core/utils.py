import random
import time
from pathlib import Path

from tqdm import tqdm

from stock_radar.core.constant import CD_SECS
from stock_radar.core.logger import get_logger

BAN_PATTERNS = (
    "访问频繁",
    "请稍后",
    "超过频率",
    "频率超限",
    "频繁访问",
    "too many requests",
    "429",
    "forbidden",
    "403",
    "max retries exceeded",
)


def random_sleep_50_to_150ms():
    sleep_seconds = random.uniform(50 / 1000.0, 150 / 1000.0)
    time.sleep(sleep_seconds)


def looks_like_ip_ban(exc: Exception) -> bool:
    msg = (str(exc) or "").lower()
    return any(pat in msg for pat in BAN_PATTERNS)


def sleep_progress(total_seconds: int, update_interval: float = 0.05, desc="Sleeping"):
    total_steps = int(total_seconds / update_interval)
    with tqdm(
        total=total_steps,
        desc=desc,
        unit="s",
        smoothing=0.9,
        mininterval=0.01,
        maxinterval=update_interval,
        bar_format="{desc}: {bar:50} [{elapsed}]",
    ) as pbar:
        for _ in range(total_steps):
            time.sleep(update_interval)
            pbar.update(1)


def cool_sleep(base_seconds=CD_SECS) -> None:

    jitter = random.uniform(0.9, 1.2)
    sleep_s = max(1, int(base_seconds * jitter))
    get_logger("fetch").warning("疑似被限流/封禁，进入冷却期 %d 秒...", sleep_s)
    time.sleep(sleep_s)


def ensure_folder(folder: str):
    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    return dest
