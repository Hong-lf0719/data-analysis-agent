import os, shutil, datetime
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from agent import analyze

SRC = "data/real/college_sleep_and_gpa.csv"
print(f"[driver] starting analyze on {SRC}", flush=True)
res = analyze(SRC)
report = res.get("final_report", "")
print(f"[driver] analyze done. report_len={len(report)} chars, charts={len(res.get('chart_files', []))}", flush=True)

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
dst = f"outputs/real_report_sleep_gpa_{stamp}.md"
os.makedirs("outputs", exist_ok=True)
with open(dst, "w", encoding="utf-8") as f:
    f.write(report)
shutil.copyfile(dst, "analysis_report_sleep.md")
print(f"[driver] report written -> {dst}", flush=True)
print("=== REPORT HEAD ===", flush=True)
print(report[:1500], flush=True)
