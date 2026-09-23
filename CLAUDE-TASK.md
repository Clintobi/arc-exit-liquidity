# Claude Code task — Arc Exit Liquidity (blocking dashboard)

Repo: /Users/mac/Projects/arc-exit-liquidity (origin https://github.com/Clintobi/arc-exit-liquidity)
Read HANDOVER.md and README.md first.

You own TASK 1 + TASK 2 below. When finished, write the full report to RESULT.md in this repo root and push tokens.json + pools.json to main.

## TASK 1 — MAP POOL IDS TO TOKENS (priority)

Everything is currently a 32-byte pool id hash. Dashboard unusable until pool ids resolve to token symbols.

Arc Uniswap V4 PoolManager: `0x8366a39cc670b4001a1121b8f6a443a643e40951`

Every pool announces once via Initialize:
`Initialize(bytes32 indexed id, address indexed currency0, address indexed currency1, uint24 fee, int24 tickSpacing, address hooks, uint160 sqrtPriceX96, int24 tick)`

Compute topic0 = keccak of that signature. getLogs over PoolManager from block 21065860 (Arc public mainnet launch) to head. Pool id = topic1, currency0 = topic2, currency1 = topic3.

For each distinct token address, eth_call symbol(), name(), decimals(). Some tokens return bytes32 not string for symbol — handle both or skip gracefully. Native/zero address 0x000…0 = native USDC gas token on Arc.

Write `site/data/tokens.json` as:
```json
{ "<poolId>": { "token0": "0x..", "token1": "0x..", "symbol0": "..", "symbol1": "..", "decimals0": 6, "decimals1": 18, "fee": 10000, "tickSpacing": 200, "created_block": 21077123 } }
```

## TASK 2 — FINISH THE INDEX AND AGGREGATE

```bash
python3 arc_index.py --workers 12    # resumable via data/done.json; local swaps.csv already large
python3 aggregate.py                 # writes site/data/pools.json
```

Confirm it reaches current head. Report swap total.

## RPC / decoding notes (will bite you)

- RPC: https://rpc.mainnet.arc.io (backup https://arc.drpc.org)
- Returns 403 without User-Agent. Set one.
- eth_getLogs capped at 1000 blocks/request. Larger → "requested range too large".
- ~7s/request single-threaded → parallelise ~12 workers + both endpoints. Full history ~1.27M blocks.
- V4 int128 amounts are SIGN-EXTENDED across the FULL 32-BYTE WORD. Convert at 256 bits, not 128.
- Block time ~0.507s measured. Convert horizons to block offsets from that.
- Arc RPC has permissive CORS — do NOT add a proxy/backend.

## Hard constraints

- Do NOT change markout methodology. Buyers vs SELLERS as control. Keep seller numbers in every report.
- Do NOT invent or estimate any number.
- Do NOT delete or rewrite arc_index.py resume logic.
- Commit and push `site/data/tokens.json` and `site/data/pools.json` to main.

## Report back in RESULT.md

1. Total swaps indexed, number of distinct pools, block range covered.
2. Top 15 pools by swap count, with token symbols, showing: buys, sells, 5m buyer markout, 5m seller markout, and the gap.
3. How many pools have 5m gap over 100bp (buyers materially worse than sellers), and how many are symmetric.
4. Anything that looks wrong or suspicious — say so plainly.

If RESULT.md is missing seller markouts, the task is incomplete.
