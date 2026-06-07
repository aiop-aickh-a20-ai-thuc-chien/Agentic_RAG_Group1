"""Bulk upload URLs to backend with parallel workers and retry on failure.

Usage:
    uv run --no-sync python scripts/bulk_upload.py --links _relink.txt --workers 5
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BACKEND = "http://localhost:8000"
UPLOAD_TIMEOUT = 180  # seconds per upload


def upload_url(url: str) -> tuple[str, bool, str]:
    """Returns (url, success, message)."""
    try:
        resp = requests.post(
            f"{BACKEND}/sources/url",
            json={"url": url},
            timeout=UPLOAD_TIMEOUT,
        )
        if resp.status_code == 200:
            doc_id = resp.json().get("document_id", "?")
            return url, True, doc_id
        else:
            return url, False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return url, False, str(e)[:120]


def run_batch(urls: list[str], workers: int, label: str) -> list[str]:
    """Upload a batch in parallel. Returns list of failed URLs."""
    failed: list[str] = []
    done = 0
    total = len(urls)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(upload_url, url): url for url in urls}
        for fut in as_completed(futures):
            url, ok, msg = fut.result()
            done += 1
            status = "OK" if ok else "FAIL"
            print(f"[{label}] [{done}/{total}] {status} | {url[:70]} | {msg}", flush=True)
            if not ok:
                failed.append(url)

    return failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--links", default="_relink.txt", help="File with URLs (one per line)")
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers")
    parser.add_argument("--retry-delay", type=int, default=10, help="Seconds before retry pass")
    args = parser.parse_args()

    urls = [
        line.strip()
        for line in Path(args.links).read_text(encoding="utf-8").splitlines()
        if line.strip() and line.strip().startswith("http")
    ]
    print(f"Total URLs: {len(urls)}, workers: {args.workers}", flush=True)

    # Pass 1
    print("\n=== PASS 1 ===", flush=True)
    failed = run_batch(urls, args.workers, "P1")
    print(f"\nPass 1 done — {len(urls) - len(failed)} OK, {len(failed)} failed", flush=True)

    # Retry failed
    if failed:
        print(f"\nWaiting {args.retry_delay}s before retry...", flush=True)
        time.sleep(args.retry_delay)
        print(f"\n=== PASS 2 (retry {len(failed)} URLs) ===", flush=True)
        still_failed = run_batch(failed, max(1, args.workers // 2), "P2")
        recovered = len(failed) - len(still_failed)
        print(
            f"\nPass 2 done — {recovered} recovered, {len(still_failed)} still failed",
            flush=True,
        )

        if still_failed:
            fail_path = Path("scripts/upload_failed.txt")
            fail_path.write_text("\n".join(still_failed), encoding="utf-8")
            print(f"\nStill failed ({len(still_failed)} URLs) saved to {fail_path}", flush=True)
            for u in still_failed:
                print(f"  FAILED: {u}", flush=True)
        else:
            print("\nAll URLs uploaded successfully!", flush=True)
    else:
        print("\nAll URLs uploaded successfully on first pass!", flush=True)


if __name__ == "__main__":
    main()
