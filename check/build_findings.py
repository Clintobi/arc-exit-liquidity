#!/usr/bin/env python3
"""
Build check/data/findings.json for the Findings page.

Every row comes from ArcFlagRegistry on Arc mainnet (the source of truth the
checker reads), joined with volume and swap counts from the local index in
site/data/arc.json. Run after each publishing round:

    python3 check/build_findings.py
"""
import json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RPC = "https://rpc.mainnet.arc.io"
REGISTRY = "0x27B0AA7E1824d4561c02363bf1c3Ac47e4548221"
SEL_COUNT = "0x5d214e01"      # flaggedCount()
SEL_AT = "0x97bb7775"         # flaggedAt(uint256,uint256)
SEL_RECORD = "0x617fba04"     # getRecord(address)
SEL_EPOCH = "0x900cf0cf"      # epoch()
PAGE = 50


def rpc(method, params):
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"content-type": "application/json", "user-agent": "arc-token-check/1.0"},
    )
    out = json.load(urllib.request.urlopen(req, timeout=30))
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["result"]


def call(data, to=REGISTRY):
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])


def words(hexstr):
    h = hexstr[2:]
    return [h[i:i + 64] for i in range(0, len(h), 64)]


def u256(n):
    return format(n, "064x")


def read_symbol(addr):
    """symbol() as string or bytes32; None if the call fails."""
    try:
        h = call("0x95d89b41", to=addr)[2:]
    except Exception:
        return None
    if len(h) >= 192:
        n = int(h[64:128], 16)
        raw = bytes.fromhex(h[128:128 + 2 * n])
    else:
        raw = bytes.fromhex(h[:64]).rstrip(b"\x00")
    return raw.decode("utf-8", "replace").strip() or None


def main():
    count = int(call(SEL_COUNT), 16)
    epoch = int(call(SEL_EPOCH), 16)
    head = int(rpc("eth_blockNumber", []), 16)

    addrs = []
    for start in range(0, count, PAGE):
        w = words(call(SEL_AT + u256(start) + u256(min(PAGE, count - start))))
        n = int(w[1], 16)
        addrs += ["0x" + x[24:] for x in w[2:2 + n]]

    index = json.load(open(os.path.join(ROOT, "site", "data", "arc.json")))
    by_addr = {}
    for row in index["tokens"] + index["flagged"]:
        a = row["addr"].lower()
        # keep the row with the most volume if a token appears twice
        if a not in by_addr or row.get("v", 0) > by_addr[a].get("v", 0):
            by_addr[a] = row

    tokens = []
    block_seen = 0
    for a in addrs:
        w = words(call(SEL_RECORD + a[2:].rjust(64, "0")))
        flags, pools, traders, max_fee, seen, ep = (int(x, 16) for x in w[:6])
        block_seen = max(block_seen, seen)
        meta = by_addr.get(a.lower(), {})
        tokens.append({
            "address": a,
            "symbol": meta.get("sym"),
            "flags": flags,
            "pools": pools,
            "wallets": traders,
            "maxFee": max_fee,          # hundredths of a bip; 1_000_000 = 100%
            "volume": round(meta.get("v", 0), 2),   # USDC, both legs of a round trip
            "swaps": meta.get("sw", 0),
            "blockSeen": seen,
            "epoch": ep,
        })

    for t in tokens:
        if not t["symbol"]:
            t["symbol"] = read_symbol(t["address"])

    tokens.sort(key=lambda t: t["volume"], reverse=True)
    seen_ts = int(rpc("eth_getBlockByNumber", [hex(block_seen), False])["timestamp"], 16)
    out = {
        "registry": REGISTRY,
        "count": count,
        "epoch": epoch,
        "blockSeen": block_seen,
        "blockSeenTime": seen_ts,
        "builtAtBlock": head,
        "chain": {
            "poolsCreated": index["funnel"][0]["n"],
            "poolsTraded": index["funnel"][1]["n"],
            "pools100Wallets": index["funnel"][-1]["n"],
            "swaps": index["swaps_total"],
            "dexUsdcNet": round(index["usdc_dex_net"]),
            "usdcTransferredWeek1": index["arc_usdc_transferred_wk1"],
            "usdcCirculating": index["arc_usdc_circulating"],
            "impostorPools": index["flags"]["impostor"],
            "highFeePools": index["flags"]["high_fee"],
            "soloPools": index["flags"]["solo"],
            "dynamicFeePools": index["flags"]["dynamic"],
            "blockFrom": index["block_from"],
            "blockTo": index["block_to"],
        },
        "tokens": tokens,
    }
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    with open(os.path.join(HERE, "data", "findings.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"{count} records, epoch {epoch}, data through block {block_seen:,}, head {head:,}")


if __name__ == "__main__":
    main()
