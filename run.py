# -*- coding: utf-8 -*-
"""启动脚本：自动检测端口 → 显示进度 → 自动打开浏览器"""
import socket
import subprocess
import sys
import os
import time
import threading
import webbrowser

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def find_free_port(start=8501, end=8510):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return None


# ── 1. 检测端口 ──
print("🔍 检测可用端口...", end=" ", flush=True)
port = find_free_port()
if port is None:
    print("\n❌ 8501-8509 均被占用，请关闭其他 Streamlit 后重试")
    sys.exit(1)
print(f"✅ {port}")

# ── 2. 启动 ──
spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
stop_spin = False


def spin():
    i = 0
    while not stop_spin:
        sys.stdout.write(f"\r{spinner[i % len(spinner)]} 正在启动 Streamlit...")
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1


t = threading.Thread(target=spin, daemon=True)
t.start()

url = f"http://localhost:{port}"
proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "app.py",
     "--server.port", str(port),
     "--server.headless", "true"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

# ── 等待就绪 ──
ready = False
for _ in range(60):  # 最多等 30 秒
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        ready = True
        break
    except (socket.timeout, ConnectionRefusedError, OSError):
        time.sleep(0.5)

stop_spin = True
t.join(timeout=0.5)

if ready:
    print(f"\r✅ 启动成功！正在打开浏览器...")
    time.sleep(0.5)
    webbrowser.open(url)
    print(f"⚔️  星见 · 数据分析  →  {url}")
    print("   按 Ctrl+C 停止")
    proc.wait()
else:
    print(f"\r❌ 启动超时，请手动访问 {url}")
    proc.terminate()
    sys.exit(1)
