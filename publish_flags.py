#!/usr/bin/env python3
"""
Publish token flags from the local index to ArcFlagRegistry on Arc mainnet.

The index is keyed by POOL; the registry is keyed by TOKEN. A token can sit in
many pools with different fees and different traders, so this aggregates first
and only then decides a flag. Fees are the REALISED fee emitted on each swap,
not the pool's stated setting — a V4 hook can override the latter, and several
on Arc do.

Dry run by default. Nothing is sent without --broadcast.

    python3 publish_flags.py                          # plan only
    python3 publish_flags.py --plan-out flags.json    # plan to disk
    python3 publish_flags.py --broadcast --registry 0x... --private-key $PK
"""
import argparse, csv, json, os, subprocess, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SWAPS = os.path.join(HERE, "data", "swaps.csv")
TOKENS = os.path.join(HERE, "site", "data", "tokens.json")
CREATED = os.path.join(HERE, "data", "init_pools.txt")
RPC = "https://rpc.mainnet.arc.io"

# Flag bits — must match ArcFlagRegistry.sol
SYMBOL_COLLISION = 1 << 0
HIGH_FEE         = 1 << 1
SINGLE_TRADER    = 1 << 2
NEVER_TRADED     = 1 << 3
DYNAMIC_FEE      = 1 << 4

HIGH_FEE_THRESHOLD = 500_000      # hundredths of a bip = 50%
DYN_SENTINEL       = 8_388_608    # V4 "a hook sets the fee", not a rate
# Arc's block gas limit is 30M and a 150-token batch measures ~11.5M. 300 is
# 22.2M, which is too close to the ceiling to risk.
BATCH = 150

CANON_USDC = "0x3600000000000000000000000000000000000000"
NATIVE     = "0x0000000000000000000000000000000000000000"
QUOTES     = {CANON_USDC, NATIVE}


def quote_side(meta):
    if (meta.get("token0") or "").lower() in QUOTES: return 0
    if (meta.get("token1") or "").lower() in QUOTES: return 1
    return None


def traded_token(meta, qs):
    """The non-quote side: address, symbol."""
    if qs == 0:
        return (meta.get("token1") or "").lower(), meta.get("symbol1")
    return (meta.get("token0") or "").lower(), meta.get("symbol0")


def build_plan():
    tokens = json.load(open(TOKENS))
    created = {l.strip() for l in open(CREATED)} if os.path.exists(CREATED) else set()

    pools_of   = defaultdict(set)     # token -> pool ids
    traders_of = defaultdict(set)     # token -> distinct senders
    swaps_of   = defaultdict(int)
    dynamic_of = defaultdict(bool)
    symbol_of  = {}
    # Per POOL, because a fee is a property of a pool, not of a token. Taking a
    # token's max fee across all its pools flags ARGUS at 80% because somebody
    # spun up one scam pool containing it, which is both wrong and defamatory.
    pool_swaps = defaultdict(int)
    pool_maxfee = defaultdict(int)

    # Pool-level facts that need no swap history.
    for pid, meta in tokens.items():
        qs = quote_side(meta)
        if qs is None:
            continue
        addr, sym = traded_token(meta, qs)
        if not addr or addr in QUOTES:
            continue
        pools_of[addr].add(pid)
        symbol_of[addr] = sym
        if meta.get("fee") == DYN_SENTINEL:
            dynamic_of[pid] = True

    # Swap-level facts.
    csv.field_size_limit(10**7)
    with open(SWAPS, newline="") as f:
        for r in csv.DictReader(f):
            meta = tokens.get(r["pool"])
            if not meta:
                continue
            qs = quote_side(meta)
            if qs is None:
                continue
            addr, _ = traded_token(meta, qs)
            if not addr or addr in QUOTES:
                continue
            swaps_of[addr] += 1
            traders_of[addr].add(r["sender"])
            pool_swaps[r["pool"]] += 1
            try:
                fee = int(r["fee"])
            except (TypeError, ValueError):
                continue
            if fee != DYN_SENTINEL and fee > pool_maxfee[r["pool"]]:
                pool_maxfee[r["pool"]] = fee

    rows = []
    for addr, pids in pools_of.items():
        flags = 0
        sym = symbol_of.get(addr)
        # The fee that matters is the one on the venue you would actually route
        # to: the pool carrying most of this token's swaps.
        traded_pools = [(pool_swaps.get(q, 0), q) for q in pids]
        traded_pools.sort(reverse=True)
        main_pool = traded_pools[0][1] if traded_pools else None
        main_fee = pool_maxfee.get(main_pool, 0) if main_pool else 0
        # Claims the quote asset's symbol while living at another address.
        if sym == "USDC":
            flags |= SYMBOL_COLLISION
        if main_fee >= HIGH_FEE_THRESHOLD:
            flags |= HIGH_FEE
        if swaps_of[addr] == 0:
            # A pool exists and nothing ever settled in it. Only assert this
            # where the pool is one the census actually saw created.
            if not created or (pids & created):
                flags |= NEVER_TRADED
        elif len(traders_of[addr]) == 1:
            flags |= SINGLE_TRADER
        # Same rule as the fee: describe the venue people actually use, not
        # every pool that happens to contain this token.
        if main_pool and dynamic_of.get(main_pool):
            flags |= DYNAMIC_FEE

        if flags == 0:
            continue
        rows.append({
            "token": addr,
            "symbol": sym,
            "flags": flags,
            "pools": min(len(pids), 2**32 - 1),
            "traders": min(len(traders_of[addr]), 2**32 - 1),
            "maxFee": min(main_fee, 2**32 - 1),
            "swaps": swaps_of[addr],
        })

    # Most consequential first, so a partial run still publishes what matters.
    rows.sort(key=lambda r: (-r["swaps"], r["token"]))
    return rows


def summarise(rows):
    def n(bit): return sum(1 for r in rows if r["flags"] & bit)
    print(f"tokens to publish: {len(rows):,}")
    print(f"  symbol collision : {n(SYMBOL_COLLISION):>6,}")
    print(f"  high fee (>=50%) : {n(HIGH_FEE):>6,}")
    print(f"  single trader    : {n(SINGLE_TRADER):>6,}")
    print(f"  never traded     : {n(NEVER_TRADED):>6,}")
    print(f"  dynamic fee      : {n(DYNAMIC_FEE):>6,}")
    print(f"\nbatches of {BATCH}: {(len(rows) + BATCH - 1)//BATCH}")
    print("\nmost-traded flagged tokens:")
    for r in rows[:12]:
        bits = "".join(c for c, b in
                       zip("CFSNY", [SYMBOL_COLLISION, HIGH_FEE, SINGLE_TRADER,
                                     NEVER_TRADED, DYNAMIC_FEE]) if r["flags"] & b)
        print(f"  {str(r['symbol'])[:16]:>16} {r['token'][:12]}… "
              f"swaps {r['swaps']:>7,}  fee {r['maxFee']/1e4:>7.2f}%  [{bits}]")


def cast_send(registry, pk, sig, args, block_seen):
    cmd = ["cast", "send", registry, sig, *args, str(block_seen),
           "--rpc-url", RPC, "--private-key", pk]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:400])
    return out.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broadcast", action="store_true", help="actually send")
    ap.add_argument("--registry", help="deployed ArcFlagRegistry address")
    ap.add_argument("--private-key", dest="pk", help="publisher key")
    ap.add_argument("--block-seen", type=int, default=0,
                    help="Arc block the assessment holds through")
    ap.add_argument("--plan-out")
    ap.add_argument("--limit", type=int, help="publish only the first N (testing)")
    ap.add_argument("--only", default="collision,highfee",
                    help="comma-separated flags to publish: collision, highfee, "
                         "single, dead, dynamic, or 'all'. Defaults to the two "
                         "that are actual warnings; the never-traded set is half "
                         "the gas and mostly noise.")
    a = ap.parse_args()

    if not os.path.exists(TOKENS):
        sys.exit(f"missing {TOKENS}")
    rows = build_plan()

    if a.only.strip().lower() != "all":
        wanted = 0
        names = {"collision": SYMBOL_COLLISION, "highfee": HIGH_FEE,
                 "single": SINGLE_TRADER, "dead": NEVER_TRADED,
                 "dynamic": DYNAMIC_FEE}
        for nm in a.only.split(","):
            nm = nm.strip().lower()
            if nm not in names:
                sys.exit(f"unknown flag '{nm}' — pick from {', '.join(names)} or all")
            wanted |= names[nm]
        kept = []
        for r in rows:
            masked = r["flags"] & wanted
            if masked:
                # Publish only the selected bits, so a later round can add the
                # rest without this row implying anything it did not assert.
                kept.append({**r, "flags": masked})
        print(f"filter --only {a.only}: {len(kept):,} of {len(rows):,} tokens\n")
        rows = kept

    if a.limit:
        rows = rows[:a.limit]
    summarise(rows)

    if a.plan_out:
        json.dump(rows, open(a.plan_out, "w"), indent=1)
        print(f"\nplan written to {a.plan_out}")

    if not a.broadcast:
        print("\ndry run — nothing sent. add --broadcast --registry 0x… --private-key …")
        return
    if not (a.registry and a.pk):
        sys.exit("--broadcast needs --registry and --private-key")

    block_seen = a.block_seen
    if not block_seen:
        r = subprocess.run(["cast", "block-number", "--rpc-url", RPC],
                           capture_output=True, text=True)
        block_seen = int(r.stdout.strip())
    print(f"\nblockSeen = {block_seen:,}")

    print("opening epoch…")
    cast_send(a.registry, a.pk, "openEpoch(uint64)", [], block_seen)

    sig = "setFlagsBatch(address[],uint8[],uint32[],uint32[],uint32[],uint64)"
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        args = [
            "[" + ",".join(r["token"] for r in chunk) + "]",
            "[" + ",".join(str(r["flags"]) for r in chunk) + "]",
            "[" + ",".join(str(r["pools"]) for r in chunk) + "]",
            "[" + ",".join(str(r["traders"]) for r in chunk) + "]",
            "[" + ",".join(str(r["maxFee"]) for r in chunk) + "]",
        ]
        print(f"  batch {i//BATCH + 1}/{(len(rows)+BATCH-1)//BATCH} "
              f"({len(chunk)} tokens)…", flush=True)
        cast_send(a.registry, a.pk, sig, args, block_seen)

    print(f"\npublished {len(rows):,} tokens to {a.registry}")


if __name__ == "__main__":
    main()
