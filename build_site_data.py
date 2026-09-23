#!/usr/bin/env python3
"""
Compact the raw index into what the page loads.

pools.json and tokens.json are ~4MB each — fine on disk, wasteful over the
wire. This emits one small file: the census funnel, plus the tokens that
actually cleared a liquidity bar, plus the flagged pools.

    python3 build_site_data.py
"""
import csv, json, os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SWAPS = os.path.join(HERE, "data", "swaps.csv")
CREATED = os.path.join(HERE, "data", "init_pools.txt")
TOKENS = os.path.join(HERE, "site", "data", "tokens.json")
OUT = os.path.join(HERE, "site", "data", "arc.json")

DYN = 8_388_608                      # V4 dynamic-fee sentinel, not a rate
HIGH_FEE = 500_000                   # 50% in hundredths of a bip
QUOTES = {"0x3600000000000000000000000000000000000000",
          "0x0000000000000000000000000000000000000000"}


def quote_side(m):
    if (m.get("token0") or "").lower() in QUOTES: return 0
    if (m.get("token1") or "").lower() in QUOTES: return 1
    return None


def main():
    created = {l.strip() for l in open(CREATED) if l.strip()}
    tokens = json.load(open(TOKENS))

    swaps, wallets, first, last = Counter(), defaultdict(set), {}, {}
    vol = defaultdict(float)
    csv.field_size_limit(10**7)
    with open(SWAPS, newline="") as f:
        for r in csv.DictReader(f):
            p = r["pool"]
            try:
                b = int(r["block"]); a0 = int(r["amount0"]); a1 = int(r["amount1"])
            except (ValueError, TypeError):
                continue
            swaps[p] += 1
            wallets[p].add(r["sender"])
            first[p] = min(first.get(p, b), b); last[p] = max(last.get(p, b), b)
            m = tokens.get(p)
            if m:
                qs = quote_side(m)
                if qs is not None:
                    amt = a0 if qs == 0 else a1
                    dec = m.get("decimals0") if qs == 0 else m.get("decimals1")
                    vol[p] += abs(amt) / (10 ** (dec if isinstance(dec, int) else 6))

    traded = set(swaps)
    # The funnel. Each step is a weaker and weaker definition of "a market",
    # and the point is how fast it collapses.
    funnel = [
        {"label": "created",            "n": len(created)},
        {"label": "traded at least once","n": len(traded)},
        {"label": "traded more than once","n": sum(1 for p in traded if swaps[p] > 1)},
        {"label": "2+ distinct wallets", "n": sum(1 for p in traded if len(wallets[p]) >= 2)},
        {"label": "10+ distinct wallets","n": sum(1 for p in traded if len(wallets[p]) >= 10)},
        {"label": "100+ distinct wallets","n": sum(1 for p in traded if len(wallets[p]) >= 100)},
    ]

    rows = []
    for p in traded:
        m = tokens.get(p)
        if not m:
            continue
        qs = quote_side(m)
        if qs is None:
            continue
        sym = (m.get("symbol1") if qs == 0 else m.get("symbol0")) or "?"
        addr = (m.get("token1") if qs == 0 else m.get("token0")) or ""
        fee = m.get("fee")
        rows.append({
            "p": p[:10], "sym": sym[:18], "addr": addr,
            "sw": swaps[p], "w": len(wallets[p]), "v": round(vol[p], 2),
            "fee": fee, "dyn": fee == DYN,
            "hf": bool(fee is not None and fee != DYN and fee >= HIGH_FEE),
            "imp": bool(sym == "USDC" and addr.lower() not in QUOTES),
            "solo": len(wallets[p]) == 1,
            "fb": first[p], "lb": last[p],
        })

    rows.sort(key=lambda r: -r["v"])
    flags = {
        "high_fee":  sum(1 for r in rows if r["hf"]),
        "impostor":  sum(1 for r in rows if r["imp"]),
        "solo":      sum(1 for r in rows if r["solo"]),
        "dynamic":   sum(1 for r in rows if r["dyn"]),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({
        "funnel": funnel,
        "flags": flags,
        "swaps_total": sum(swaps.values()),
        "block_from": min(first.values()) if first else 0,
        "block_to": max(last.values()) if last else 0,
        "tokens": rows[:1500],              # the page only ever renders the top
        "flagged": [r for r in rows if r["hf"] or r["imp"]][:400],
    }, open(OUT, "w"), separators=(",", ":"))

    print(f"wrote {OUT}  ({os.path.getsize(OUT)/1e6:.2f} MB)")
    for s in funnel:
        print(f"  {s['label']:>22}: {s['n']:>8,}")
    print(f"  flags: {flags}")


if __name__ == "__main__":
    main()
