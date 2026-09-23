#!/usr/bin/env python3
"""Independently count pools created on Arc, to check the census headline.

Counts Initialize events from the V4 PoolManager over the same block window
the swap index covers, so "created" and "traded" are measured on identical
ground. Anything created before the window is deliberately excluded rather
than silently mixed in.
"""
import json, os, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

PM = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
INIT = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
RPCS = ["https://rpc.mainnet.arc.io", "https://arc.drpc.org"]
CHUNK = 1000
FROM, TO = 21_065_860, 22_357_859     # same window as the swap index
OUT = "data/init_pools.txt"

_l = threading.Lock(); _rr = [0]

def rpc(params, attempts=4):
    for i in range(attempts):
        with _l:
            url = RPCS[_rr[0] % len(RPCS)]; _rr[0] += 1
        try:
            req = urllib.request.Request(url, data=json.dumps(
                {"jsonrpc":"2.0","id":1,"method":"eth_getLogs","params":[params]}).encode(),
                headers={"content-type":"application/json","User-Agent":"arc-census/1.0"})
            b = json.loads(urllib.request.urlopen(req, timeout=60).read())
            if "error" in b: raise RuntimeError(str(b["error"])[:60])
            return b.get("result")
        except Exception as e:
            # 429 needs real backoff, not a retry storm
            time.sleep((6 if "rate limit" in str(e).lower() else 1.2) * (i + 1))
    return None

def fetch(start):
    end = min(start+CHUNK-1, TO)
    logs = rpc({"fromBlock":hex(start),"toBlock":hex(end),"address":PM,"topics":[INIT]})
    if logs is None:                      # split on the 20k-result cap
        out=[]
        for s in range(start, end+1, 100):
            sub = rpc({"fromBlock":hex(s),"toBlock":hex(min(s+99,end)),"address":PM,"topics":[INIT]})
            if sub is None: return start, None
            out += sub
        logs = out
    return start, [l["topics"][1] for l in logs]

if __name__ == "__main__":
    starts = list(range(FROM, TO+1, CHUNK))
    seen, failed, done = set(), [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch, s): s for s in starts}
        for f in as_completed(futs):
            s, ids = f.result()
            if ids is None: failed.append(s); continue
            with _l:
                seen.update(ids); done += 1
                if done % 25 == 0:
                    el = time.time()-t0
                    print(f"  {done:,}/{len(starts):,} chunks  {len(seen):,} pools  "
                          f"~{(len(starts)-done)/(done/el)/60:.0f} min left", flush=True)
    os.makedirs("data", exist_ok=True)
    open(OUT,"w").write("\n".join(sorted(seen)))
    print(f"\nchunks {len(starts):,} | failed {len(failed)}")
    print(f"POOLS CREATED in {FROM:,}-{TO:,}: {len(seen):,}")
