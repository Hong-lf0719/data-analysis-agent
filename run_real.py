import os, shutil, datetime
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from agent import analyze

SRC = "data/real/global_tech_market_2026.csv"
print(f"[driver] starting analyze on {SRC}", flush=True)
res = analyze(SRC)
report = res.get("final_report", "")
print(f"[driver] analyze done. report_len={len(report)} chars, charts={len(res.get('chart_files', []))}", flush=True)

# 落盘为带日期的报告，避免覆盖旧的 analysis_report.md
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
dst = f"outputs/real_report_global_tech_{stamp}.md"
os.makedirs("outputs", exist_ok=True)
with open(dst, "w", encoding="utf-8") as f:
    f.write(report)
# 同时保留最新版到根
shutil.copyfile(dst, "analysis_report.md")
print(f"[driver] report written -> {dst}", flush=True)
print("=== REPORT HEAD ===", flush=True)
print(report[:1500], flush=True)
