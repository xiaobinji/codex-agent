#!/usr/bin/env python3
"""
Codex notify hook — Codex 完成 turn 时：
1. 给用户发 Telegram 通知（看到 Codex 干了什么）
2. 唤醒 OpenClaw agent（去检查输出）

配置：通过环境变量或修改下方默认值
  CODEX_AGENT_CHAT_ID   — Chat ID (Telegram/Discord/WhatsApp etc.)
  CODEX_AGENT_NAME      — OpenClaw agent 名称（默认 main）
"""

import json
import os
import subprocess
import sys
from datetime import datetime

LOG_FILE = "/tmp/codex_notify_log.txt"

# 从环境变量读取，fallback 到默认值（方便部署时不改代码）
CHAT_ID = os.environ.get("CODEX_AGENT_CHAT_ID", "YOUR_CHAT_ID")
CHANNEL = os.environ.get("CODEX_AGENT_CHANNEL", "telegram")
ACCOUNT = os.environ.get("CODEX_AGENT_ACCOUNT", "")
AGENT_NAME = os.environ.get("CODEX_AGENT_NAME", "main")


def log(msg: str):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass  # 日志写入失败不应影响主流程


def redact(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "<redacted>"
    return f"{value[:5]}...{value[-4:]}"


def resolve_account() -> str:
    if ACCOUNT:
        return ACCOUNT

    # Feishu open_id values are app-scoped. If the target came from a prior
    # inbound session, prefer the OpenClaw account whose allow-list contains it.
    if CHANNEL != "feishu" or not CHAT_ID or CHAT_ID == "YOUR_CHAT_ID":
        return ""

    credentials_dir = os.path.expanduser("~/.openclaw/credentials")
    prefix = "feishu-"
    suffix = "-allowFrom.json"
    try:
        for filename in os.listdir(credentials_dir):
            if not filename.startswith(prefix) or not filename.endswith(suffix):
                continue
            path = os.path.join(credentials_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    if CHAT_ID in f.read():
                        return filename[len(prefix):-len(suffix)]
            except OSError:
                continue
    except OSError:
        pass

    return ""


def notify_user(msg: str) -> bool:
    """发送 Telegram 通知，返回是否成功启动进程"""
    account = resolve_account()
    cmd = [
        "openclaw", "message", "send",
        "--channel", CHANNEL,
        "--target", CHAT_ID,
        "--message", msg,
    ]
    if account:
        cmd[3:3] = ["--account", account]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # 等待最多 10 秒，检查是否成功
        try:
            stdout, stderr = proc.communicate(timeout=10)
            if proc.returncode != 0:
                out = stdout.decode(errors="replace")[:1000]
                err = stderr.decode(errors="replace")[:2000]
                log(
                    "channel notify failed "
                    f"(exit {proc.returncode}, channel={CHANNEL}, "
                    f"account={account or 'default'}, target={redact(CHAT_ID)}): "
                    f"stdout={out} stderr={err}"
                )
                return False
        except subprocess.TimeoutExpired:
            log("channel notify timeout (10s), process still running")
        log(f"channel notify sent (channel={CHANNEL}, account={account or 'default'}, target={redact(CHAT_ID)})")
        return True
    except Exception as e:
        log(f"channel notify error: {e}")
        return False


def wake_agent(msg: str) -> bool:
    """唤醒 OpenClaw agent，返回是否成功启动进程"""
    account = resolve_account()
    cmd = [
        "openclaw", "agent",
        "--agent", AGENT_NAME,
        "--message", msg,
        "--deliver",
        "--channel", CHANNEL,
        "--timeout", "120",
    ]
    if account:
        cmd.extend(["--reply-account", account])
    if CHAT_ID and CHAT_ID != "YOUR_CHAT_ID":
        cmd.extend(["--reply-to", CHAT_ID])

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(f"agent wake fired (pid {proc.pid}, channel={CHANNEL}, account={account or 'default'}, target={redact(CHAT_ID)})")
        return True
    except Exception as e:
        log(f"agent wake error: {e}")
        return False


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    try:
        notification = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        log(f"JSON parse error: {e}")
        return 1

    if notification.get("type") != "agent-turn-complete":
        return 0

    summary = notification.get("last-assistant-message", "Turn Complete!")
    cwd = notification.get("cwd", "unknown")
    thread_id = notification.get("thread-id", "unknown")

    log(f"Codex turn complete: thread={thread_id}, cwd={cwd}")
    log(
        f"Notify config: channel={CHANNEL}, account={resolve_account() or 'default'}, "
        f"target={redact(CHAT_ID)}, agent={AGENT_NAME}"
    )
    log(f"Summary: {summary[:200]}")

    # ⚠️ 注意：summary 可能包含代码片段、路径、密钥等敏感信息
    # 发送到 Telegram 前用户应评估风险（私人仓库/私聊通常可接受）
    msg = (
        f"🔔 Codex 任务回复\n"
        f"📁 {cwd}\n"
        f"💬 {summary}"
    )

    # 1. 给用户发 Telegram 通知
    tg_ok = notify_user(msg)

    # 2. 唤醒 agent（fire-and-forget）
    agent_msg = (
        f"[Codex Hook] 任务完成，请检查输出并汇报。\n"
        f"cwd: {cwd}\n"
        f"thread: {thread_id}\n"
        f"summary: {summary}"
    )
    agent_ok = wake_agent(agent_msg)

    if not tg_ok and not agent_ok:
        log("⚠️ Both channel notify and agent wake failed!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
