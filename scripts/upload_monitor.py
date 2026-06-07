"""Monitor bulk_upload.py progress from its output file."""
import sys
import io
import time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import re
from pathlib import Path

OUTPUT_FILE = r"C:\Users\ACER\AppData\Local\Temp\claude\c--Users-ACER-Downloads-Agentic-RAG-Group1\7cd79017-8e13-48b3-b435-9e096254977c\tasks\b9si1lm5l.output"
TOTAL = 323


def read_progress(path: str) -> tuple[int, int, int, list[str], bool]:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return 0, 0, 0, [], False

    done = ok = fail = 0
    failed_urls = []
    for line in lines:
        m = re.search(r"\[P\d\] \[(\d+)/\d+\] (OK|FAIL)", line)
        if m:
            done = int(m.group(1))
            if m.group(2) == "OK":
                ok += 1
            else:
                fail += 1
                url_m = re.search(r"FAIL \| (https?://\S+) \|", line)
                if url_m:
                    failed_urls.append(url_m.group(1))

    joined = "\n".join(lines)
    finished = "All URLs uploaded" in joined or "still failed" in joined
    return done, ok, fail, failed_urls, finished


def bar(done: int, total: int, width: int = 40) -> str:
    pct = done / total if total else 0
    filled = int(width * pct)
    return f"[{'#'*filled}{'-'*(width-filled)}] {done}/{total} ({pct*100:.1f}%)"


print(f"Monitoring upload progress... (Ctrl+C to stop)")
try:
    while True:
        result = read_progress(OUTPUT_FILE)
        done, ok, fail, failed_urls, finished = result
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.write(bar(done, TOTAL) + f"  OK={ok} FAIL={fail}")
        sys.stdout.flush()
        if finished:
            print(f"\n\nDone! OK={ok} FAIL={fail}")
            if failed_urls:
                print("Failed URLs:")
                for u in failed_urls:
                    print(f"  {u}")
            break
        time.sleep(2)
except KeyboardInterrupt:
    print(f"\nStopped. Current: {done}/{TOTAL}")
