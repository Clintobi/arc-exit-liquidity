#!/usr/bin/env python3
"""
Turn the raw swap log into the small JSON the dashboard loads.

Direction is defined relative to the QUOTE asset, not token0. This matters:
USDC is token0 in ~86% of Arc pools, so labelling a "buy" as buying token0
inverts buyer and seller across most of the chain. An earlier version did
exactly that and produced a scrambled distribution with a negative median.

    python3 aggregate.py
"""
import csv, json, os, statistics, sys
from bisect import bisect_left
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SWAPS = os.path.join(HERE, "data", "swaps.csv")
OUTDIR = os.path.join(HERE, "site", "data")
TOKENS = os.path.join(OUTDIR, "tokens.json")

BLOCK_SECONDS = 0.507
HORIZONS = {"1m": 60, "5m": 300, "30m": 1800}
MIN_SWAPS = 40
MIN_SIDE = 15            # fills per side before a median means anything
OUTLIER_BPS = 10_000     # a 100% move in minutes is a launch, not execution

CANON_USDC = "0x3600000000000000000000000000000000000000"
NATIVE = "0x0000000000000000000000000000000000000000"
QUOTES = {CANON_USDC, NATIVE}


def num(v, cast=int, default=None):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


def load_swaps():
    pools = defaultdict(list)
    csv.field_size_limit(10**7)
    with open(SWAPS, newline="") as f:
        for row in csv.DictReader(f):
            b = num(row.get("block")); a0 = num(row.get("amount0"))
            a1 = num(row.get("amount1")); sq = num(row.get("sqrtPriceX96"))
            if None in (b, a0, a1, sq) or sq <= 0:
                continue                       # torn final line mid-write
            pools[row["pool"]].append((b, a0, a1, sq))
    for v in pools.values():
        v.sort(key=lambda r: r[0])
    return pools


def classify(meta):
    """Which side is the quote asset, and is the pool priced in real USDC?

    Returns (quote_is_token0, impostor) or None when neither side is a quote.
    """
    if not meta:
        return None
    t0 = (meta.get("token0") or "").lower()
    t1 = (meta.get("token1") or "").lower()
    s0, s1 = meta.get("symbol0"), meta.get("symbol1")
    if t0 in QUOTES:
        return True, (s1 == "USDC" and t1 not in QUOTES)
    if t1 in QUOTES:
        return False, (s0 == "USDC" and t0 not in QUOTES)
    # Neither side is a real quote asset. If something here calls itself USDC
    # it is an impostor, and the pool is not priced in dollars either way.
    if "USDC" in (s0, s1):
        return None
    return None


def analyse(events, quote_is_token0):
    """Median post-fill move in the traded token, signed from the buyer's view.

    sqrtPriceX96 gives token1 per token0. The asset being speculated on is the
    non-quote side, so when the quote is token0 the price must be inverted to
    express the traded token in dollars.
    """
    blocks = [e[0] for e in events]
    prices = []
    for _b, _a0, _a1, sq in events:
        p = (sq / 2**96) ** 2
        prices.append(1.0 / p if (quote_is_token0 and p > 0) else p)

    def price_at(block):
        i = bisect_left(blocks, block)
        return prices[i] if i < len(prices) else None

    out, dropped = {}, 0
    for name, seconds in HORIZONS.items():
        ahead = int(seconds / BLOCK_SECONDS)
        buy, sell = [], []
        for (b, a0, a1, _sq), p in zip(events, prices):
            later = price_at(b + ahead)
            if not later or p <= 0:
                continue
            bps = (later - p) / p * 1e4
            if abs(bps) > OUTLIER_BPS:
                dropped += 1
                continue
            # Acquiring the traded (non-quote) token is the "buy", whichever
            # index it sits at. The pool pays out what the trader receives.
            bought_traded = (a1 < 0) if quote_is_token0 else (a0 < 0)
            # Both sides record the RAW subsequent price move, not trader P&L.
            # The question is whether direction predicts what happens next: if
            # buys are followed by the same moves as sells, direction carries
            # no information and the token is simply drifting. Sign-flipping
            # sells to make P&L would make the two sides mechanical mirrors of
            # each other and turn the gap into a restatement of the drift.
            (buy if bought_traded else sell).append(bps)
        out[name] = {
            "buy": round(statistics.median(buy), 1) if len(buy) >= MIN_SIDE else None,
            "sell": round(statistics.median(sell), 1) if len(sell) >= MIN_SIDE else None,
            "n_buy": len(buy), "n_sell": len(sell),
        }
    return out, dropped


def main():
    if not os.path.exists(SWAPS):
        sys.exit(f"no swap data at {SWAPS} — run arc_index.py first")
    tokens = json.load(open(TOKENS)) if os.path.exists(TOKENS) else {}
    if not tokens:
        sys.exit(f"no token map at {TOKENS} — direction cannot be resolved without it")

    pools = load_swaps()
    print(f"loaded {sum(len(v) for v in pools.values()):,} swaps / {len(pools):,} pools")

    rows, skipped_noquote, impostors, total_dropped = [], 0, 0, 0
    for pid, evs in pools.items():
        if len(evs) < MIN_SWAPS:
            continue
        cls = classify(tokens.get(pid))
        if cls is None:
            skipped_noquote += 1
            continue
        quote_is_token0, impostor = cls
        impostors += bool(impostor)
        mk, dropped = analyse(evs, quote_is_token0)
        total_dropped += dropped

        five = mk["5m"]
        # Positive gap = buys are followed by worse price action than sells,
        # over the same window. That asymmetry is the adverse selection.
        gap = (round(five["sell"] - five["buy"], 1)
               if five["buy"] is not None and five["sell"] is not None else None)
        meta = tokens.get(pid, {})
        traded = (meta.get("symbol1") if quote_is_token0 else meta.get("symbol0")) or "?"
        rows.append({
            "pool": pid, "token": traded, "impostor_usdc": impostor,
            "swaps": len(evs), "buys": five["n_buy"], "sells": five["n_sell"],
            "first_block": evs[0][0], "last_block": evs[-1][0],
            "markouts": mk, "adverse_gap_5m_bps": gap,
        })

    scored = [r for r in rows if r["adverse_gap_5m_bps"] is not None]
    adverse = [r for r in scored if r["adverse_gap_5m_bps"] > 100]
    rows.sort(key=lambda r: -r["swaps"])

    os.makedirs(OUTDIR, exist_ok=True)
    json.dump({
        "generated_block": max((r["last_block"] for r in rows), default=0),
        "swaps_total": sum(len(v) for v in pools.values()),
        "pools_total": len(pools),
        "pools_scored": len(scored),
        "pools_adverse": len(adverse),
        "pools_skipped_no_quote": skipped_noquote,
        "impostor_usdc_pools": impostors,
        "outlier_fills_dropped": total_dropped,
        "block_seconds": BLOCK_SECONDS,
        "outlier_bps": OUTLIER_BPS,
        "pools": rows,
    }, open(os.path.join(OUTDIR, "pools.json"), "w"), separators=(",", ":"))

    gaps = sorted(r["adverse_gap_5m_bps"] for r in scored)
    print(f"scored {len(scored):,} pools | {len(adverse):,} adverse (>100bp)")
    print(f"skipped {skipped_noquote:,} with no quote asset | {impostors:,} impostor-USDC pools")
    print(f"dropped {total_dropped:,} fills beyond +/-{OUTLIER_BPS}bp as launch artefacts")
    if gaps:
        print(f"gap median {statistics.median(gaps):+.1f}bp | "
              f"p90 {gaps[9*len(gaps)//10]:+.1f} | "
              f"buyers worse in {sum(1 for g in gaps if g>0)/len(gaps)*100:.1f}% of pools")
        print("\ntop adverse pools (min 500 swaps):")
        for r in sorted([x for x in scored if x["swaps"] >= 500],
                        key=lambda r: -r["adverse_gap_5m_bps"])[:12]:
            m = r["markouts"]["5m"]
            print(f"  {r['token'][:14]:>14} {r['swaps']:>7,} swaps  "
                  f"buy {m['buy']:>8} sell {m['sell']:>8}  gap {r['adverse_gap_5m_bps']:>8,.0f}")


if __name__ == "__main__":
    main()
