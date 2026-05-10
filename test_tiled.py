"""
Quick responsiveness test — polls image endpoints in a loop.
Draw in Krita while this runs; compare stutter between the two modes.

Usage:
    python test_tiled.py              # compare both
    python test_tiled.py sync         # only sync (blocking)
    python test_tiled.py tiled        # only tiled (sleep 0 between chunks)
"""
import sys
import json
import time
import urllib.request

HOST = "http://localhost:1976"


def post(code: str, param: dict) -> dict:
    body = json.dumps({"code": code, "param": param}).encode()
    req = urllib.request.Request(HOST, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def bench(route: str, param: dict, label: str, n: int = 20):
    print(f"\n{'='*50}")
    print(f"  {label}  (x{n})")
    print(f"{'='*50}")
    times = []
    for i in range(n):
        t0 = time.perf_counter()
        r = post(route, param)
        elapsed = (time.perf_counter() - t0) * 1000
        ok = r.get("ok")
        status = "OK" if ok else f"FAIL: {r.get('msg','')}"
        tile_count = len(r.get("data", {}).get("tiles", [])) if ok else 0
        print(f"  [{i+1:2d}]  {elapsed:7.0f}ms  {status}" + (f"  ({tile_count} tiles)" if tile_count else ""))
        times.append(elapsed)
        time.sleep(0.1)

    avg = sum(times) / len(times)
    print(f"  --- avg {avg:.0f}ms | min {min(times):.0f}ms | max {max(times):.0f}ms")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"

    if mode in ("sync", "both"):
        bench("document/image", {"withImage": True}, "SYNC  (full image, no sleep — blocks Qt)", n=10)

    if mode in ("tiled", "both"):
        bench("document/image-tiled", {"tileSize": 256},
              "TILED (256px tiles, sleep(0) between — Qt stays responsive)")

    print("\nDone.")


if __name__ == "__main__":
    main()
