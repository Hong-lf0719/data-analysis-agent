# -*- coding: utf-8 -*-
"""数据分析 Agent · 测试看板（零依赖，仅用标准库）

一键运行 pytest 并在网页查看结果。
启动:  python test_dashboard.py   →   http://localhost:9871
"""
import os
import sys
import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 9871
PY = sys.executable

PAGE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>数据分析 Agent · 测试看板</title>
<style>
  body{font-family:-apple-system,Segoe UI,Roboto,"Microsoft YaHei",sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
  .bar{display:flex;align-items:center;gap:12px;padding:14px 20px;background:#171a21;border-bottom:1px solid #2a2f3a}
  h1{font-size:18px;margin:0}
  button{background:#2f81f7;color:#fff;border:0;border-radius:6px;padding:8px 16px;font-size:14px;cursor:pointer}
  button:disabled{opacity:.5;cursor:default}
  #status{font-size:13px;color:#9aa4b2}
  pre{margin:0;padding:16px 20px;white-space:pre-wrap;word-break:break-all;font-size:13px;line-height:1.55}
  .ok{color:#3fb950}.bad{color:#f85149}
</style>
</head>
<body>
  <div class="bar">
    <h1>📊 数据分析 Agent · 测试看板</h1>
    <button id="run">▶ 运行测试</button>
    <span id="status">就绪</span>
  </div>
  <pre id="out">点击「运行测试」开始（pytest tests/ -v）</pre>
<script>
const out=document.getElementById('out'),status=document.getElementById('status'),btn=document.getElementById('run');
btn.onclick=async()=>{
  btn.disabled=true;out.textContent='运行中…';status.textContent='pytest 执行中…';
  try{
    const r=await fetch('/run');const d=await r.json();
    const text=d.stdout+'\\n'+d.stderr;
    const passed=text.includes('passed') && !text.includes('failed') && d.code===0;
    out.textContent=text;
    status.innerHTML=passed?'<span class="ok">✓ 全部通过</span>':'<span class="bad">✗ 存在问题</span> · exit '+d.code;
  }catch(e){out.textContent='请求失败: '+e;status.textContent='错误';}
  btn.disabled=false;
};
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE)
        elif self.path.startswith("/run"):
            try:
                r = subprocess.run(
                    [PY, "-m", "pytest", "tests/", "-v"],
                    cwd=ROOT, capture_output=True, text=True, timeout=300,
                )
                payload = {"code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
            except Exception as e:  # noqa: BLE001
                payload = {"code": -1, "stdout": "", "stderr": str(e)}
            self._send(200, json.dumps(payload), "application/json; charset=utf-8")
        else:
            self._send(404, "not found")

    def log_message(self, *args):  # 静默日志
        pass


if __name__ == "__main__":
    print(f"Test dashboard → http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
