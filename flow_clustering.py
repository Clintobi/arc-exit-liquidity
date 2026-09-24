#!/usr/bin/env python3
"""
Is a markout on an Arc pool measuring information, or just the next trade?

A markout asks what the price did after a fill. On an order book that is a
reasonable proxy for whether the trade was informed. On an AMM it is only
meaningful if order flow is roughly independent — because if buys arrive in
runs, the price after a buy rises for the mechanical reason that more buys
arrived, regardless of whether anyone knew anything.

This measures that directly: given a swap, how likely is the next swap in the
same pool to be a buy?

    python3 flow_clustering.py
"""
import csv, json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SWAPS = os.path.join(HERE, "data", "swaps.csv")
TOKENS = os.path.join(HERE, "site", "data", "tokens.json")
MIN_SWAPS = 200

QUOTES = {"0x3600000000000000000000000000000000000000",
          "0x0000000000000000000000000000000000000000"}


def quote_is_token0(meta):
    t0 = (meta.get("token0") or "").lower()
    t1 = (meta.get("token1") or "").lower()
    if t0 in QUOTES: return True
    if t1 in QUOTES: return False
    return None


def main():
    if not os.path.exists(TOKENS):
        sys.exit("need site/data/tokens.json")
    tokens = json.load(open(TOKENS))

    pools = defaultdict(list)
    csv.field_size_limit(10**7)
    with open(SWAPS, newline="") as f:
        for r in csv.DictReader(f):
            meta = tokens.get(r["pool"])
            if not meta:
                continue
            q0 = quote_is_token0(meta)
            if q0 is None:
                continue
            try:
                b = int(r["block"]); a0 = int(r["amount0"]); a1 = int(r["amount1"])
            except (TypeError, ValueError):
                continue
            # swapper-side signs: receiving the traded token is the buy
            pools[r["pool"]].append((b, (a1 > 0) if q0 else (a0 > 0)))

    bb = bs = sb = ss = 0
    for evs in pools.values():
        if len(evs) < MIN_SWAPS:
            continue
        evs.sort(key=lambda e: e[0])
        for (_b1, x), (_b2, y) in zip(evs, evs[1:]):
            if x and y: bb += 1
            elif x: bs += 1
            elif y: sb += 1
            else: ss += 1

    total = bb + bs + sb + ss
    buys, sells = bb + bs, sb + ss
    if not total:
        sys.exit("no pools met the swap threshold")

    p_bb = bb / buys * 100
    p_sb = sb / sells * 100
    print(f"consecutive swap pairs: {total:,}   (pools with >= {MIN_SWAPS} swaps)\n")
    print(f"  P(next is buy | this was buy ) = {p_bb:5.1f}%")
    print(f"  P(next is buy | this was sell) = {p_sb:5.1f}%")
    print(f"  unconditional P(buy)           = {(bb+sb)/total*100:5.1f}%")
    print(f"\n  clustering lift = {p_bb - p_sb:+.1f} percentage points")
    print("\nA lift of this size means the price move after a buy is dominated by the"
          "\nbuys that follow it. A markout computed over this flow measures momentum,"
          "\nnot adverse selection, and cannot separate the two.")


if __name__ == "__main__":
    main()
