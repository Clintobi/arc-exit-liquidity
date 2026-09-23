#!/usr/bin/env python3
"""
Turn the raw swap log into the small JSON the dashboard actually loads.

The raw index is hundreds of MB and grows; the dashboard needs a few hundred
KB. Everything expensive to compute over millions of swaps is precomputed
here. Everything that must be live (current price, liquidity, exit cost) is
read by the browser straight from Arc's RPC instead, so it never goes stale.

    python3 aggregate.py            # writes site/data/*.json
"""
import csv, json, os, statistics, sys
from bisect import bisect_left
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SWAPS = os.path.join(HERE, "data", "swaps.csv")
OUTDIR = os.path.join(HERE, "site", "data")

BLOCK_SECONDS = 0.507          # measured on Arc mainnet
HORIZONS = {"1m": 60, "5m": 300, "30m": 1800}
MIN_SWAPS = 40                 # below this a median markout is noise


def load():
    """Swaps grouped by pool, ascending by block."""
    pools = defaultdict(list)
    csv.field_size_limit(10**7)
    with open(SWAPS, newline="") as f:
        for row in csv.DictReader(f):
            try:
                pools[row["pool"]].append((
                    int(row["block"]),
                    int(row["amount0"]),
                    int(row["amount1"]),
                    int(row["sqrtPriceX96"]),
                    row["sender"],
                ))
            except (ValueError, KeyError):
                continue          # a torn final line mid-write is not fatal
    for v in pools.values():
        v.sort(key=lambda r: r[0])
    return pools


def price_of(sqrt_x96):
    """token1 per token0, raw units. Decimals cancel in a relative markout."""
    return (sqrt_x96 / 2**96) ** 2


def markouts(events):
    """Median post-fill price move, split by side.

    Buyers alone mean nothing: a token in freefall makes every buyer look
    picked off. Sellers are the control — if both sides lose equally the
    token is simply falling and direction carries no information. Only a
    gap between the two is adverse selection.
    """
    blocks = [e[0] for e in events]
    prices = [price_of(e[3]) for e in events]

    def price_at(block):
        i = bisect_left(blocks, block)
        return prices[i] if i < len(prices) else None

    out = {}
    for name, seconds in HORIZONS.items():
        ahead = int(seconds / BLOCK_SECONDS)
        buy, sell = [], []
        for (b, a0, a1, _sq, _s), p in zip(events, prices):
            later = price_at(b + ahead)
            if not later or p <= 0:
                continue
            bps = (later - p) / p * 1e4
            # pool pays out token0 (a0<0) and takes token1 (a1>0) => buying token0
            (buy if (a0 < 0 and a1 > 0) else sell).append(bps)
        out[name] = {
            "buy": round(statistics.median(buy), 1) if len(buy) >= 5 else None,
            "sell": round(statistics.median(sell), 1) if len(sell) >= 5 else None,
            "n_buy": len(buy),
            "n_sell": len(sell),
        }
    return out


def main():
    if not os.path.exists(SWAPS):
        sys.exit(f"no swap data at {SWAPS} — run arc_index.py first")
    os.makedirs(OUTDIR, exist_ok=True)

    pools = load()
    print(f"loaded {sum(len(v) for v in pools.values()):,} swaps across {len(pools):,} pools")

    rows = []
    for pid, evs in pools.items():
        if len(evs) < MIN_SWAPS:
            continue
        mk = markouts(evs)
        buys = sum(1 for _b, a0, a1, _s, _sd in evs if a0 < 0 and a1 > 0)
        traders = len({e[4] for e in evs})
        five = mk["5m"]
        # The headline number: how much worse buyers do than sellers.
        gap = (round(five["sell"] - five["buy"], 1)
               if five["buy"] is not None and five["sell"] is not None else None)
        rows.append({
            "pool": pid,
            "swaps": len(evs),
            "buys": buys,
            "sells": len(evs) - buys,
            "traders": traders,
            "first_block": evs[0][0],
            "last_block": evs[-1][0],
            "markouts": mk,
            "adverse_gap_5m_bps": gap,
        })

    rows.sort(key=lambda r: -r["swaps"])
    toxic = [r for r in rows if (r["adverse_gap_5m_bps"] or 0) > 100]
    json.dump({
        "generated_block": max(r["last_block"] for r in rows) if rows else 0,
        "pools_total": len(pools),
        "pools_scored": len(rows),
        "pools_adverse": len(toxic),
        "swaps_total": sum(len(v) for v in pools.values()),
        "block_seconds": BLOCK_SECONDS,
        "pools": rows,
    }, open(os.path.join(OUTDIR, "pools.json"), "w"), separators=(",", ":"))

    print(f"scored {len(rows):,} pools with >= {MIN_SWAPS} swaps")
    print(f"{len(toxic):,} show buyers losing >100bp more than sellers at 5m")
    for r in sorted(rows, key=lambda r: -(r["adverse_gap_5m_bps"] or 0))[:10]:
        m = r["markouts"]["5m"]
        print(f"  {r['pool'][:14]}..  buys {r['buys']:>6,} sells {r['sells']:>6,}  "
              f"buy {str(m['buy']):>9} sell {str(m['sell']):>9}  gap {r['adverse_gap_5m_bps']}")


if __name__ == "__main__":
    main()
