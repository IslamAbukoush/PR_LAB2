# Usage:
#   python rate_limit.py --url http://localhost:8000/test --rps 20 --duration 15

import argparse
import asyncio
import aiohttp
import time
from collections import Counter

async def fetch(session, url, timeout=5):
    try:
        async with session.get(url, timeout=timeout) as resp:
            await resp.read()              # fully read response
            return resp.status
    except Exception:
        return None  # treat network/timeout as "other error"

async def run(url, rps, duration):
    total_counter = Counter()
    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        for second in range(duration):
            # send rps requests concurrently for this 1-second window
            tasks = [asyncio.create_task(fetch(session, url)) for _ in range(rps)]
            # wait for all to complete (they may take longer than 1s)
            results = await asyncio.gather(*tasks)
            # count results for this second
            c = Counter()
            for st in results:
                if st is None:
                    c["errors"] += 1
                elif 200 <= st < 300:
                    c["success"] += 1
                elif st == 429:
                    c["denied"] += 1
                else:
                    c["other"] += 1
            # update totals
            total_counter.update(c)
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed:3d}s] R/s total={sum(c.values()):3d}  success={c['success']:3d}  denied={c['denied']:3d}  other={c['other']:3d}  errors={c['errors']:3d}")
        # final totals
        print("\n=== SUMMARY ===")
        total_sent = sum(total_counter.values())
        print(f"Duration: {duration}s  Target R/s: {rps}")
        print(f"Total requests sent: {total_sent}")
        print(f"Total successful (2xx): {total_counter['success']}")
        print(f"Total denied (429): {total_counter['denied']}")
        print(f"Total other (non-2xx/429): {total_counter['other']}")
        print(f"Total errors (network/timeouts): {total_counter['errors']}")

def parse_args():
    p = argparse.ArgumentParser(description="Very simple R/s tester")
    p.add_argument("--url", required=True, help="Target URL (e.g. http://localhost:8000/test)")
    p.add_argument("--rps", type=int, required=True, help="Requests per second (integer)")
    p.add_argument("--duration", type=int, default=10, help="Duration in seconds")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(run(args.url, args.rps, args.duration))
    except KeyboardInterrupt:
        print("Interrupted by user.")
