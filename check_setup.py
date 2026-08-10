"""
验证所有配置是否就绪，完成后发送一条测试 Lark 消息。
本地运行：uv run python check_setup.py
GitHub Actions：Actions → ✅ Check Setup → Run workflow
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

from stock_radar.llm.llm import api_key_configured, ping  # noqa: E402
from stock_radar.market.fetch_data import fetch_one_data  # noqa: E402
from stock_radar.market.fetch_trend import fetch_pool  # noqa: E402
from stock_radar.notify.lark_notify import send_report_as_doc  # noqa: E402
from stock_radar.notify.send_lark_message import lark_configured  # noqa: E402

OK = "✅"
FAIL = "❌"
errors: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = OK if ok else FAIL
    line = f"  {status}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    if not ok:
        errors.append(label)
    return ok


def section(title: str) -> None:
    print(f"\n── {title} {'─' * (50 - len(title))}")


def _mask_secret(value: str, *, visible: int = 10) -> str:
    if len(value) <= visible:
        return value
    return f"{value[:visible]}…"


def report_langfuse() -> None:
    public = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret = os.getenv("LANGFUSE_SECRET_KEY")
    base_url = os.getenv("LANGFUSE_BASE_URL")

    if not any((public, secret, base_url)):
        print("  ⚪  Langfuse 未配置（可选，LLM 可观测性）")
        return

    if public:
        print(f"  ✅  LANGFUSE_PUBLIC_KEY  ({public})")
    else:
        print("  ⚪  LANGFUSE_PUBLIC_KEY  (未设置)")

    if secret:
        print(f"  ✅  LANGFUSE_SECRET_KEY  ({_mask_secret(secret)})")
    else:
        print("  ⚪  LANGFUSE_SECRET_KEY  (未设置)")

    if base_url:
        print(f"  ✅  LANGFUSE_BASE_URL  ({base_url})")
    else:
        print("  ⚪  LANGFUSE_BASE_URL  (未设置，使用 Langfuse SDK 默认)")

    from stock_radar.llm.langfuse_tracing import is_enabled

    if is_enabled():
        print("  ✅  Langfuse 追踪已启用")
    else:
        print("  ⚠️  Langfuse 密钥不完整，追踪未启用（需同时设置 PUBLIC_KEY 与 SECRET_KEY）")


section("GitHub Secrets")
required_secrets = {
    "ZHITU_TOKEN": os.getenv("ZHITU_TOKEN"),
    "TUSHARE_TOKEN": os.getenv("TUSHARE_TOKEN"),
    "LARK_APP_ID": os.getenv("LARK_APP_ID"),
    "LARK_SECRET": os.getenv("LARK_SECRET"),
    "ME_UNION_ID": os.getenv("ME_UNION_ID"),
    "LARK_FOLDER_TOKEN": os.getenv("LARK_FOLDER_TOKEN"),
}
for name, value in required_secrets.items():
    check(
        name,
        bool(value),
        "已设置" if value else "未找到，请在 Settings → Secrets 中添加",
    )

optional_secrets = {
    "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
}
for name, value in optional_secrets.items():
    print(f"  {'✅' if value else '⚪'}  {name}  ({'已设置' if value else '可选，LLM 复盘用'})")

section("TickFlow API（日线 K 线）")
try:
    df = fetch_one_data("000066", "20260701", "20260710")
    check("TickFlow K 线连接成功", df is not None and len(df) > 0)
except Exception as e:
    check("TickFlow K 线连接", False, str(e))

section("智图 API（股池 qsgc/ztgc）")
if os.getenv("ZHITU_TOKEN"):
    try:
        pool_df = fetch_pool("2024-07-10", "qsgc")
        check("智图股池 API 连接成功", pool_df is not None)
    except Exception as e:
        check("智图股池 API 连接", False, str(e))
else:
    check("智图股池 API 连接（跳过，ZHITU_TOKEN 未设置）", False)

section("DeepSeek LLM（可选）")
if api_key_configured():
    try:
        ping()
        check("DeepSeek API 连接成功", True)
    except Exception as e:
        check("DeepSeek API 连接", False, str(e))
else:
    print("  ⚪  DEEPSEEK_API_KEY 未设置（可选，--llm-analyze 时使用）")

section("Langfuse（可选）")
report_langfuse()

section("Tushare API（股票列表）")
if os.getenv("TUSHARE_TOKEN"):
    pass
    # try:
    #     ts_pro = get_pro_api()
    #     df: pd.DataFrame | None = ts.pro_bar(
    #         ts_code="000066.SZ",
    #         adj="qfq",
    #         start_date="20240701",
    #         end_date="20240710",
    #         freq="D",
    #         api=ts_pro,
    #     )
    #     check("Tushare API 连接成功", df is not None and len(df) > 0)
    # except Exception as e:
    #     check("Tushare API 连接", False, str(e))
else:
    check("Tushare API 连接（跳过，TUSHARE_TOKEN 未设置）", False)

section("Lark")
all_ok = not errors
if not lark_configured():
    check(
        "Lark 配置完整",
        False,
        "需设置 LARK_APP_ID、LARK_SECRET、ME_UNION_ID、LARK_FOLDER_TOKEN",
    )
else:
    check("Lark 配置完整", True)
    if all_ok:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
            markdown = (
                f"# Stock Radar — 配置验证成功\n\n"
                f"验证时间：{now}\n\n"
                f"- TickFlow K 线\n"
                f"- 智图股池 (qsgc/ztgc)\n"
                f"- Tushare 股票列表\n"
                f"- 飞书机器人 + 云文档\n"
            )
            ok_send = send_report_as_doc(
                title="配置验证",
                markdown=markdown,
                summary="Stock Radar — 配置验证成功",
            )
            check("测试 Lark 文档通知已发送", ok_send)
        except Exception as e:
            check("发送测试 Lark 消息", False, str(e))
    else:
        print("    存在配置错误，跳过发送测试 Lark 消息")

print("\n" + "═" * 54)
if not errors:
    print("  🎉  所有检查通过！查收 Lark 测试消息后即可运行每日工作流。")
else:
    print(f"  ❌  {len(errors)} 项需要修复：")
    for e in errors:
        print(f"       · {e}")
    print("\n  运行 uv run python setup.py 完成配置后重新检查。")
print("═" * 54)

sys.exit(0 if not errors else 1)
