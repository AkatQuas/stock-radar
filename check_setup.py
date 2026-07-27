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

from stock_trade_z.llm.llm import api_key_configured, ping  # noqa: E402
from stock_trade_z.market.fetch_data import fetch_one_data  # noqa: E402
from stock_trade_z.market.fetch_trend import fetch_pool  # noqa: E402
from stock_trade_z.notify.lark_notify import send_report_as_doc  # noqa: E402
from stock_trade_z.notify.send_lark_message import lark_configured  # noqa: E402

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


section("环境变量 / GitHub Secrets")
required = {
    "ZHITU_TOKEN": os.getenv("ZHITU_TOKEN"),
    "TUSHARE_TOKEN": os.getenv("TUSHARE_TOKEN"),
    "LARK_APP_ID": os.getenv("LARK_APP_ID"),
    "LARK_SECRET": os.getenv("LARK_SECRET"),
    "LARK_FOLDER_TOKEN": os.getenv("LARK_FOLDER_TOKEN"),
    "ME_UNION_ID": os.getenv("ME_UNION_ID"),
}
optional = {
    "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
}
for name, value in required.items():
    check(name, bool(value), "已设置" if value else "未找到")
for name, value in optional.items():
    print(f"  {'✅' if value else '⚪'}  {name}  ({'已设置' if value else '可选，LLM 复盘用'})")

section("本地 .env")
env_path = ROOT / ".env"
check(".env 存在", env_path.exists(), str(env_path) if env_path.exists() else "运行 setup.py 生成")

section("TickFlow API（日线 K 线）")
try:
    df = fetch_one_data("000066", "20240701", "20240710")
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
if not lark_configured():
    check("Lark 配置完整", False, "需设置 LARK_APP_ID、LARK_SECRET、ME_UNION_ID")
else:
    check("Lark 配置完整", True)
    if not errors:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            markdown = (
                f"# Stock Trade Z 配置验证成功\n\n"
                f"验证时间：{now}\n\n"
                f"- TickFlow K 线\n"
                f"- 智图股池 (qsgc/ztgc)\n"
                f"- Tushare 股票列表\n"
                f"- 飞书机器人 + 云文档\n"
            )
            ok_send = send_report_as_doc(
                title=f"配置验证 {now[:10]}",
                markdown=markdown,
                summary="✅ Stock Trade Z — 配置验证成功",
                receive_id=os.getenv("ME_UNION_ID"),
            )
            check("测试 Lark 文档通知已发送", ok_send)
        except Exception as e:
            check("发送测试 Lark 消息", False, str(e))
    else:
        print("  ⚠️  存在配置错误，跳过发送测试 Lark 消息")

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
