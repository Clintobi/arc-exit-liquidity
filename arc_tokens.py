#!/usr/bin/env python3
"""
Map every Arc Uniswap V4 pool id to its two tokens.

Pool ids are keccak(PoolKey), so they can't be reversed. Every pool announces
itself exactly once through the PoolManager's Initialize event, which carries
currency0/currency1 as indexed topics — one filtered log query recovers the
whole map. Each distinct token is then asked for symbol()/name()/decimals().

Arc has hundreds of thousands of pools (most are launchpad tokens paired with
USDC), so both stages are resumable: the Initialize scan is cached per chunk in
data/init.json and token metadata in data/token_meta.json.

    python3 arc_tokens.py            # after aggregate.py; writes site/data/tokens.json
"""
import argparse, json, os, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from arc_index import POOL_MANAGER, CHUNK, RPCS, rpc, signed

# keccak("Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)")
INITIALIZE = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
NATIVE = "0x0000000000000000000000000000000000000000"
HERE = os.path.dirname(os.path.abspath(__file__))
INIT = os.path.join(HERE, "data", "init.json")
META = os.path.join(HERE, "data", "token_meta.json")
OUT = os.path.join(HERE, "site", "data", "tokens.json")
POOLS = os.path.join(HERE, "site", "data", "pools.json")

SIG_SYMBOL, SIG_NAME, SIG_DECIMALS = "0x95d89b41", "0x06fdde03", "0x313ce567"
BATCH_TOKENS = 3            # 3 tokens x 3 calls: drpc 500s on batches over ~10

_lock = threading.Lock()


def fetch(start, end):
    """Initialize logs for one chunk. Retries hard: a gap here would silently
    leave pools unnamed, so failing loudly is better.

    The drpc backup rejects 1,000-block ranges on its free plan but accepts
    100, so a chunk the primary won't serve is retried as sub-ranges."""
    q = lambda a, b: rpc("eth_getLogs", [{"fromBlock": hex(a), "toBlock": hex(b),
                                          "address": POOL_MANAGER, "topics": [INITIALIZE]}])
    for attempt in range(8):
        logs = q(start, end)
        if logs is not None:
            return start, logs
        parts = [q(s, min(s + 99, end)) for s in range(start, end + 1, 100)]
        if all(p is not None for p in parts):
            return start, [l for p in parts for l in p]
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"chunk {start} failed after retries")


def decode_text(res):
    """symbol()/name() come back as an ABI string, or as bytes32 on some
    older-style tokens. Handle both; return None if neither parses."""
    if not res or res == "0x":
        return None
    try:
        raw = bytes.fromhex(res[2:])
    except ValueError:
        return None
    try:
        if len(raw) >= 64:
            off = int.from_bytes(raw[:32], "big")
            n = int.from_bytes(raw[off:off + 32], "big")
            if off + 32 + n <= len(raw):
                return raw[off + 32:off + 32 + n].decode("utf-8").strip("\x00").strip() or None
    except (UnicodeDecodeError, ValueError, OverflowError):
        pass
    if len(raw) == 32:
        try:
            return raw.rstrip(b"\x00").decode("utf-8").strip() or None
        except UnicodeDecodeError:
            return None
    return None


def batch_call(addrs, attempts=8):
    """symbol/name/decimals for a few tokens in one JSON-RPC batch. A revert
    (no such method) is a per-call error and is recorded as None; only a
    transport failure or rate limit is retried."""
    calls = [{"jsonrpc": "2.0", "id": i * 3 + j, "method": "eth_call",
              "params": [{"to": a, "data": sig}, "latest"]}
             for i, a in enumerate(addrs) for j, sig in enumerate((SIG_SYMBOL, SIG_NAME, SIG_DECIMALS))]
    for k in range(attempts):
        url = RPCS[(k + 1) % len(RPCS)]           # drpc first: primary is busy with getLogs
        try:
            req = urllib.request.Request(url, data=json.dumps(calls).encode(),
                                         headers={"content-type": "application/json",
                                                  "User-Agent": "arc-exit-liquidity/1.0"})
            body = json.loads(urllib.request.urlopen(req, timeout=60).read())
            by_id = {r["id"]: r for r in body}
            if len(by_id) != len(calls) or any(
                    "rate limit" in str(r.get("error", "")).lower() or r.get("error", {}).get("code") in (-32005, 429)
                    for r in body):
                raise RuntimeError("rate limited")
            out = {}
            for i, a in enumerate(addrs):
                s, n, d = (by_id[i * 3 + j].get("result") for j in range(3))
                try:
                    dec = int(d, 16) if d and d != "0x" else None
                    dec = dec if dec is not None and dec <= 255 else None
                except ValueError:
                    dec = None
                out[a] = {"symbol": decode_text(s), "name": decode_text(n), "decimals": dec}
            return out
        except Exception:
            time.sleep(1.5 * (k + 1))
    return None


def published():
    """The committed tokens.json doubles as a seed when the local cache is
    missing (a fresh CI runner), so pools created before the scan window
    aren't lost and their tokens aren't re-read."""
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def scan(from_block, workers):
    if os.path.exists(INIT):
        init = json.load(open(INIT))
    else:
        init = {"chunks": {}, "pools": {pid: {k: t[k] for k in (
            "token0", "token1", "fee", "tickSpacing", "hooks", "created_block")}
            for pid, t in published().items()}}
    head = int(rpc("eth_blockNumber", []), 16)
    # Only whole chunks below head are cached, so a tip chunk is never
    # recorded half-read.
    todo = [(s, min(s + CHUNK - 1, head)) for s in range(from_block, head + 1, CHUNK)
            if str(s) not in init["chunks"]]
    print(f"Initialize scan to {head:,}: {len(todo):,} chunks to fetch, {len(init['chunks']):,} cached")
    t0, n = time.time(), 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        # newest first: a partial backward scan then covers the blocks nearest
        # to where the uncached pools are most likely to have been created
        for f in as_completed([ex.submit(fetch, s, e) for s, e in reversed(todo)]):
            start, logs = f.result()
            with _lock:
                for l in logs:
                    w = [l["data"][2 + k * 64:2 + (k + 1) * 64] for k in range(5)]
                    init["pools"][l["topics"][1]] = {
                        "token0": "0x" + l["topics"][2][-40:],
                        "token1": "0x" + l["topics"][3][-40:],
                        "fee": int(w[0], 16),
                        "tickSpacing": signed(int(w[1], 16)),
                        "hooks": "0x" + w[2][-40:],
                        "created_block": int(l["blockNumber"], 16),
                    }
                if start + CHUNK - 1 <= head:
                    init["chunks"][str(start)] = 1
                n += 1
                if n % 50 == 0:
                    json.dump(init, open(INIT, "w"))
                    print(f"  {n:,}/{len(todo):,} chunks  {len(init['pools']):,} pools  {time.time()-t0:.0f}s")
    json.dump(init, open(INIT, "w"))
    return init["pools"], head


def metadata(addrs, workers):
    if os.path.exists(META):
        meta = json.load(open(META))
    else:
        meta = {}
        for t in published().values():
            for i in "01":
                meta[t["token" + i]] = {"symbol": t["symbol" + i], "name": t["name" + i],
                                        "decimals": t["decimals" + i]}
    meta[NATIVE] = {"symbol": "USDC", "name": "USDC (native)", "decimals": 18}
    # Arc gas token is native USDC. Native balances are 18-decimal (checked:
    # eth_getBalance == 1e12 x balanceOf on the 6-decimal ERC-20 at 0x3600..00).
    todo = [a for a in addrs if a not in meta]
    groups = [todo[i:i + BATCH_TOKENS] for i in range(0, len(todo), BATCH_TOKENS)]
    print(f"token metadata: {len(todo):,} to read, {len(meta):,} cached")
    t0, n, failed = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(batch_call, g) for g in groups]):
            res = f.result()
            with _lock:
                n += 1
                if res is None:
                    failed += 1
                else:
                    meta.update(res)
                if n % 2000 == 0:
                    json.dump(meta, open(META, "w"))
                    print(f"  {n:,}/{len(groups):,} batches  {failed} failed  {time.time()-t0:.0f}s")
    json.dump(meta, open(META, "w"))
    if failed:
        print(f"WARNING: {failed} batches failed — rerun to fill them in")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-block", type=int, default=21065860, help="Arc public mainnet launch")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(INIT), exist_ok=True)

    pools, head = scan(args.from_block, args.workers)
    print(f"{len(pools):,} pools initialized")
    # Most pools never trade. The dashboard only shows pools aggregate.py
    # scored, so only those are published (the full map stays in data/init.json).
    scored = ([r["pool"] for r in json.load(open(POOLS))["pools"]]
              if os.path.exists(POOLS) else list(pools))
    unmapped = [pid for pid in scored if pid not in pools]
    pools = {pid: pools[pid] for pid in scored if pid in pools}
    addrs = sorted({p[k] for p in pools.values() for k in ("token0", "token1")})
    meta = metadata(addrs, args.workers)

    blank = {"symbol": None, "name": None, "decimals": None}
    out = {}
    for pid, p in sorted(pools.items(), key=lambda kv: kv[1]["created_block"]):
        m0, m1 = meta.get(p["token0"], blank), meta.get(p["token1"], blank)
        out[pid] = {
            "token0": p["token0"], "token1": p["token1"],
            "symbol0": m0["symbol"], "symbol1": m1["symbol"],
            "name0": m0["name"], "name1": m1["name"],
            "decimals0": m0["decimals"], "decimals1": m1["decimals"],
            "fee": p["fee"], "tickSpacing": p["tickSpacing"], "hooks": p["hooks"],
            "created_block": p["created_block"],
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), separators=(",", ":"))

    missing = [a for a in addrs if a not in meta]
    unnamed = [a for a in addrs if a in meta and meta[a]["symbol"] is None]
    print(f"wrote {len(out):,} pools / {len(addrs):,} tokens to {OUT} (scanned to block {head:,})")
    print(f"{len(unnamed):,} tokens with no readable symbol, {len(missing):,} not yet read")
    print(f"{len(unmapped):,} scored pools have no Initialize in the scanned range")


if __name__ == "__main__":
    main()
