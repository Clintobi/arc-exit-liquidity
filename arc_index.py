#!/usr/bin/env python3
"""
Index every Uniswap V4 swap on Arc since public mainnet launch.

Arc routes all V4 swaps through one PoolManager, with the pool id as an
indexed topic, so the whole chain's DEX activity is a single filtered log
query. The RPC caps eth_getLogs at 1,000 blocks and takes ~7s per call, so
1.27M blocks is ~2.5h sequential — this parallelises it across workers and
two endpoints, and is resumable.

    python3 arc_index.py --workers 10
    python3 arc_index.py --resume
"""
import argparse, csv, json, os, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

POOL_MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
SWAP = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"
RPCS = ["https://rpc.mainnet.arc.io", "https://arc.drpc.org"]
CHUNK = 1000
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "swaps.csv")
DONE = os.path.join(HERE, "data", "done.json")

_lock = threading.Lock()
_rr = [0]


def rpc(method, params, attempts=4):
    for i in range(attempts):
        with _lock:
            url = RPCS[_rr[0] % len(RPCS)]; _rr[0] += 1
        try:
            req = urllib.request.Request(
                url, data=json.dumps({"jsonrpc": "2.0", "id": 1,
                                      "method": method, "params": params}).encode(),
                headers={"content-type": "application/json", "User-Agent": "arc-exit-liquidity/1.0"})
            body = json.loads(urllib.request.urlopen(req, timeout=60).read())
            if "error" in body:
                raise RuntimeError(str(body["error"])[:80])
            return body.get("result")
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def signed(x, bits=256):
    """V4 emits int128 amounts sign-extended across the full 32-byte word."""
    return x - (1 << bits) if x >= (1 << (bits - 1)) else x


def get_swaps(a, b):
    return rpc("eth_getLogs", [{"fromBlock": hex(a), "toBlock": hex(b),
                                "address": POOL_MANAGER, "topics": [SWAP]}])


def fetch(start):
    logs = get_swaps(start, start + CHUNK - 1)
    if logs is None:
        # The primary refuses any query over 20,000 results, and the busiest
        # launch-week chunks exceed that; drpc refuses 1,000-block ranges on
        # its free plan. Both serve 100-block ranges. The chunk is still only
        # recorded done if every sub-range came back.
        parts = [get_swaps(s, s + 99) for s in range(start, start + CHUNK, 100)]
        if any(p is None for p in parts):
            return start, None
        logs = [l for p in parts for l in p]
    rows = []
    for l in logs:
        raw = l["data"][2:]
        w = [raw[i * 64:(i + 1) * 64] for i in range(6)]
        rows.append((
            int(l["blockNumber"], 16),
            l["topics"][1],                       # pool id
            "0x" + l["topics"][2][-40:],          # sender
            signed(int(w[0], 16)),                # amount0
            signed(int(w[1], 16)),                # amount1
            int(w[2], 16),                        # sqrtPriceX96
            int(w[3], 16),                        # liquidity
            signed(int(w[4], 16)),                # tick
            int(w[5], 16),                        # fee
        ))
    return start, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-block", type=int, default=21065860, help="Arc public mainnet launch")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    head = int(rpc("eth_blockNumber", []), 16)
    done = set(json.load(open(DONE))) if os.path.exists(DONE) else set()
    starts = [b for b in range(args.from_block, head, CHUNK) if b not in done]
    print(f"head {head:,} | {len(starts):,} chunks to fetch | {len(done):,} already done")

    new = open(OUT, "a", newline="")
    w = csv.writer(new)
    if os.path.getsize(OUT) == 0 if os.path.exists(OUT) else True:
        w.writerow(["block", "pool", "sender", "amount0", "amount1", "sqrtPriceX96", "liquidity", "tick", "fee"])

    t0, n_rows, n_done = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch, s): s for s in starts}
        for f in as_completed(futs):
            start, rows = f.result()
            if rows is None:
                continue
            with _lock:
                w.writerows(rows); new.flush()
                done.add(start); n_rows += len(rows); n_done += 1
                if n_done % 25 == 0:
                    json.dump(sorted(done), open(DONE, "w"))
                    el = time.time() - t0
                    rate = n_done / el
                    left = (len(starts) - n_done) / rate / 60 if rate else 0
                    print(f"  {n_done:>5,}/{len(starts):,} chunks  {n_rows:>9,} swaps  "
                          f"{rate*CHUNK:,.0f} blk/s  ~{left:.0f} min left")
    json.dump(sorted(done), open(DONE, "w"))
    new.close()
    print(f"\ndone — {n_rows:,} swaps written to {OUT}")


if __name__ == "__main__":
    main()
