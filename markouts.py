#!/usr/bin/env python3
"""
Does buying predict what happens next on Arc?

A markout is the price move after a fill. Measured on one side it proves
nothing: a token in freefall makes every buyer look picked off, and that is a
downtrend, not adverse selection. So sells are the control. Only a GAP between
what follows buys and what follows sells means direction carried information.

Both sides record the RAW subsequent move, deliberately not trader P&L.
Sign-flipping sells makes the two sides mechanical mirrors and collapses the
gap into a restatement of drift.

Three corrections over the first attempt, each of which silently broke it:

  1. Arc's V4 PoolManager uses SWAPPER-SIDE amounts. Negative means the trader
     paid that token in. Buying the traded token therefore means its amount is
     POSITIVE. Verified at 99.8% against own-swap price impact.
  2. USDC is token0 in ~86% of pools, so direction must resolve against the
     quote asset, never against token0.
  3. sqrtPriceX96 is token1 per token0, so the price must be inverted when the
     quote is token0 to express the traded token in dollars.

    python3 markouts.py
"""
import csv, json, os, statistics, sys
from bisect import bisect_left
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SWAPS = os.path.join(HERE, "data", "swaps.csv")
TOKENS = os.path.join(HERE, "site", "data", "tokens.json")
OUT = os.path.join(HERE, "site", "data", "markouts.json")

BLOCK_SECONDS = 0.507
HORIZONS = {"1m": 60, "5m": 300, "30m": 1800}
MIN_SIDE = 30            # fills per side before a median is worth printing
OUTLIER_BPS = 10_000     # a 100% move in minutes is a launch, not execution
STALE_MULT = 2.0         # reference must land within 2x the horizon

QUOTES = {"0x3600000000000000000000000000000000000000",
          "0x0000000000000000000000000000000000000000"}


def quote_is_token0(meta):
    t0 = (meta.get("token0") or "").lower()
    t1 = (meta.get("token1") or "").lower()
    if t0 in QUOTES: return True
    if t1 in QUOTES: return False
    return None


def load():
    pools = defaultdict(list)
    csv.field_size_limit(10**7)
    with open(SWAPS, newline="") as f:
        for r in csv.DictReader(f):
            try:
                b = int(r["block"]); a0 = int(r["amount0"])
                a1 = int(r["amount1"]); sq = int(r["sqrtPriceX96"])
            except (TypeError, ValueError):
                continue
            if sq > 0:
                pools[r["pool"]].append((b, a0, a1, sq))
    for v in pools.values():
        v.sort(key=lambda r: r[0])
    return pools


def analyse(events, q0):
    blocks = [e[0] for e in events]
    # Express the traded (non-quote) token in dollars.
    prices = [(1.0 / ((sq / 2**96) ** 2)) if q0 else ((sq / 2**96) ** 2)
              for _b, _a0, _a1, sq in events]

    out, stale = {}, 0
    for name, seconds in HORIZONS.items():
        ahead = int(seconds / BLOCK_SECONDS)
        limit = int(seconds * STALE_MULT / BLOCK_SECONDS)
        buy, sell = [], []
        for (b, a0, a1, _sq), p in zip(events, prices):
            i = bisect_left(blocks, b + ahead)
            if i >= len(blocks):
                continue
            if blocks[i] - b > limit:          # nothing traded near the horizon
                stale += 1
                continue
            later = prices[i]
            if later <= 0 or p <= 0:
                continue
            bps = (later - p) / p * 1e4
            if abs(bps) > OUTLIER_BPS:
                continue
            # SWAPPER-SIDE: receiving the traded token is the buy.
            bought = (a1 > 0) if q0 else (a0 > 0)
            (buy if bought else sell).append(bps)

        b_med = statistics.median(buy) if len(buy) >= MIN_SIDE else None
        s_med = statistics.median(sell) if len(sell) >= MIN_SIDE else None
        out[name] = {
            "buy": round(b_med, 1) if b_med is not None else None,
            "sell": round(s_med, 1) if s_med is not None else None,
            "n_buy": len(buy), "n_sell": len(sell),
            # positive => price fell more after buys than after sells
            "adverse": round(s_med - b_med, 1) if None not in (b_med, s_med) else None,
        }
    return out, stale


def main():
    if not os.path.exists(TOKENS):
        sys.exit("need site/data/tokens.json to resolve direction")
    tokens = json.load(open(TOKENS))
    pools = load()

    rows, skipped, stale_total = [], 0, 0
    for pid, evs in pools.items():
        meta = tokens.get(pid)
        if not meta:
            skipped += 1; continue
        q0 = quote_is_token0(meta)
        if q0 is None:
            skipped += 1; continue
        mk, stale = analyse(evs, q0)
        stale_total += stale
        if mk["5m"]["adverse"] is None:
            continue
        sym = (meta.get("symbol1") if q0 else meta.get("symbol0")) or "?"
        rows.append({"pool": pid[:10], "sym": sym[:18], "swaps": len(evs),
                     "markouts": mk, "adverse_5m": mk["5m"]["adverse"]})

    rows.sort(key=lambda r: -r["swaps"])
    adv = [r["adverse_5m"] for r in rows]
    adv_sorted = sorted(adv)

    json.dump({"pools_scored": len(rows), "stale_skipped": stale_total,
               "horizons": HORIZONS, "min_side": MIN_SIDE,
               "pools": rows[:800]},
              open(OUT, "w"), separators=(",", ":"))

    print(f"pools scored at 5m: {len(rows):,}   (skipped {skipped:,} without a quote leg)")
    print(f"observations dropped for a stale reference: {stale_total:,}")
    if not rows:
        return
    print(f"\nadverse gap (bps, + = buys precede worse moves than sells)")
    print(f"  median {statistics.median(adv):+.1f} | "
          f"p10 {adv_sorted[len(adv)//10]:+.1f} | p90 {adv_sorted[9*len(adv)//10]:+.1f}")
    print(f"  buyers worse in {sum(1 for a in adv if a>0)/len(adv)*100:.1f}% of pools")

    print(f"\n{'token':>16} {'swaps':>8} {'buy 5m':>9} {'sell 5m':>9} {'adverse':>9}")
    for r in rows[:15]:
        m = r["markouts"]["5m"]
        print(f"{r['sym']:>16} {r['swaps']:>8,} {m['buy']:>9} {m['sell']:>9} {r['adverse_5m']:>+9.1f}")


if __name__ == "__main__":
    main()
