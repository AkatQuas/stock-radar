#!/usr/bin/env python3
"""
Stock Radar — 交互式配置向导
运行方式：uv run python setup.py
完成后写入本地 .env，并将 GitHub Secrets 同步到远程仓库。
"""

import getpass
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def green(s):
    return f"\033[32m{s}\033[0m"


def yellow(s):
    return f"\033[33m{s}\033[0m"


def red(s):
    return f"\033[31m{s}\033[0m"


def bold(s):
    return f"\033[1m{s}\033[0m"


def dim(s):
    return f"\033[2m{s}\033[0m"


def ok(msg):
    print(f"  {green('✓')}  {msg}")


def warn(msg):
    print(f"  {yellow('!')}  {msg}")


def fail(msg):
    print(f"  {red('✗')}  {msg}")


def section(title):
    print(f"\n{bold('── ' + title + ' ' + '─' * max(0, 48 - len(title)))}")


def ask(prompt, default=None, secret=False):
    hint = f" [{dim(default)}]" if default else ""
    full_prompt = f"  {prompt}{hint}: "
    while True:
        val = (getpass.getpass(full_prompt) if secret else input(full_prompt)).strip()
        if val:
            return val
        if default is not None:
            return default
        print(f"  {red('请输入内容')}")


def ask_optional(prompt, secret=False):
    hint = f" [{dim('留空跳过')}]"
    full_prompt = f"  {prompt}{hint}: "
    return (getpass.getpass(full_prompt) if secret else input(full_prompt)).strip()


def collect_langfuse_config() -> dict[str, str]:
    section("Langfuse 追踪（可选）")
    print(dim("  在 https://langfuse.com/cloud 创建项目并获取 API Keys"))
    print(dim("  留空跳过；需同时填写 PUBLIC_KEY 和 SECRET_KEY 才会启用"))

    public_key = ask_optional("LANGFUSE_PUBLIC_KEY")
    secret_key = ask_optional("LANGFUSE_SECRET_KEY", secret=True) if public_key else ""
    if not public_key and not secret_key:
        return {}
    if not (public_key and secret_key):
        warn("Langfuse 需要同时设置 PUBLIC_KEY 和 SECRET_KEY，已跳过")
        return {}

    base_url = ask("LANGFUSE_BASE_URL", default="https://cloud.langfuse.com")
    config = {
        "LANGFUSE_PUBLIC_KEY": public_key,
        "LANGFUSE_SECRET_KEY": secret_key,
        "LANGFUSE_BASE_URL": base_url,
    }
    ok("Langfuse 追踪已配置")
    return config


def ask_choice(prompt, choices):
    print(f"\n  {prompt}")
    for i, (label, desc) in enumerate(choices, 1):
        print(f"    {bold(str(i))}.  {label}  {dim(desc)}")
    while True:
        raw = input(f"  选择 [1-{len(choices)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][0]
        print(f"  {red('请输入有效编号')}")


def run(cmd: list[str], capture=True):
    return subprocess.run(cmd, capture_output=capture, text=True, cwd=ROOT)


def get_repo_slug():
    r = run(["git", "remote", "get-url", "origin"])
    url = r.stdout.strip()
    m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def set_secret(repo: str, name: str, value: str) -> bool:
    r = run(["gh", "secret", "set", name, "--repo", repo, "--body", value])
    return r.returncode == 0


def update_env_file(updates: dict[str, str]) -> None:
    if ENV_PATH.exists():
        content = ENV_PATH.read_text(encoding="utf-8")
    elif ENV_EXAMPLE.exists():
        content = ENV_EXAMPLE.read_text(encoding="utf-8")
    else:
        content = ""

    for key, value in updates.items():
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + f"\n{replacement}\n"

    ENV_PATH.write_text(content, encoding="utf-8")


def main():
    print()
    print(bold("  🚀  Stock Radar 配置向导"))
    print(dim("  ─────────────────────────────────────────────"))
    print(dim("  回答以下问题，向导将写入 .env 并同步 GitHub Secrets。"))
    print(dim("  密码输入时不显示字符，直接回车接受 [默认值]。"))

    section("环境检查")

    if run(["git", "rev-parse", "--is-inside-work-tree"]).returncode != 0:
        fail("请在 stock_radar 仓库目录内运行此脚本")
        sys.exit(1)
    ok("Git 仓库")

    repo = get_repo_slug()
    if not repo:
        fail("无法解析 GitHub 仓库地址，请确认 origin remote 已设置")
        sys.exit(1)
    ok(f"仓库：{repo}")

    if run(["gh", "--version"]).returncode != 0:
        fail("未检测到 GitHub CLI")
        print()
        print(f"  请先安装 gh：{bold('https://cli.github.com')}")
        print(f"  macOS:   {dim('brew install gh')}")
        print()
        sys.exit(1)

    if run(["gh", "auth", "status"]).returncode != 0:
        fail("GitHub CLI 未登录")
        print()
        print(f"  请运行：{bold('gh auth login')}，按提示完成授权后重新运行此向导。")
        print()
        sys.exit(1)
    ok("GitHub CLI 已认证")

    section("DeepSeek API")
    print(dim("  申请 API Key：https://platform.deepseek.com/api_keys"))
    api_key = ask("粘贴你的 DEEPSEEK_API_KEY", secret=True)

    section("智图 API（股池 qsgc/ztgc）")
    print(dim("  申请 Token：https://www.zhituapi.com/get-free-cert.html"))
    zhitu_token = ask("粘贴你的 ZHITU_TOKEN", secret=True)

    section("Tushare API（股票列表）")
    print(dim("  申请 Token：https://tushare.pro/weborder/#/user/info"))
    tushare_token = ask("粘贴你的 TUSHARE_TOKEN", secret=True)

    section("Lark 配置")
    print(dim("  在飞书开放平台创建应用：https://open.feishu.cn/app"))
    print(
        dim(
            "  需开通 im:message | docx:document | docx:document.block:convert 权限，ME_UNION_ID 为接收人的 union_id"
        )
    )
    lark_app_id = ask("LARK_APP_ID")
    lark_secret = ask("LARK_SECRET", secret=True)
    lark_folder_token = ask("LARK_FOLDER_TOKEN")
    me_union_id = ask("ME_UNION_ID（接收人 union_id）")

    langfuse_config = collect_langfuse_config()

    section("写入本地 .env")
    update_env_file(
        {
            "DEEPSEEK_API_KEY": api_key,
            "ZHITU_TOKEN": zhitu_token,
            "TUSHARE_TOKEN": tushare_token,
            "LARK_APP_ID": lark_app_id,
            "LARK_SECRET": lark_secret,
            "ME_UNION_ID": me_union_id,
            "LARK_FOLDER_TOKEN": lark_folder_token,
            **langfuse_config,
        }
    )
    ok(f"已更新 {ENV_PATH.name}")

    section("写入 GitHub Secrets")
    secrets = {
        "DEEPSEEK_API_KEY": api_key,
        "ZHITU_TOKEN": zhitu_token,
        "TUSHARE_TOKEN": tushare_token,
        "LARK_APP_ID": lark_app_id,
        "LARK_SECRET": lark_secret,
        "LARK_FOLDER_TOKEN": lark_folder_token,
        "ME_UNION_ID": me_union_id,
        **langfuse_config,
    }
    all_ok = True
    for name, value in secrets.items():
        if set_secret(repo, name, value):
            ok(name)
        else:
            fail(f"{name}  （写入失败，请检查 gh 权限）")
            all_ok = False

    if not all_ok:
        warn("部分 Secret 写入失败，可手动在 Settings → Secrets → Actions 中补充")

    section("完成")
    run_check = ask_choice(
        "是否立即运行本地配置检查并发送 Lark 测试消息？",
        [("yes", "推荐"), ("no", "稍后手动运行")],
    )

    if run_check == "yes":
        section("运行 check_setup.py")
        r = run(["uv", "run", "python", "check_setup.py"], capture=False)
        if r.returncode != 0:
            warn("检查未全部通过，请根据上方输出修复后重试：uv run python check_setup.py")
            sys.exit(r.returncode)

    print(f"""
  {green("✓")}  配置完成！

  下一步（可选）：

    1. 在 GitHub Actions 手动触发验证：
       {bold("Actions → ✅ Check Setup → Run workflow")}

    2. 本地再次检查：
       {bold("uv run python check_setup.py")}

    3. 手动跑一轮选股 / 风控（含 Lark 推送）：
       {bold("uv run stock-select --data-dir ./data --send-lark")}
       {bold("uv run stock-detect-risk --data-dir ./data --send-lark")}
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {yellow('已取消')}\n")
        sys.exit(0)
