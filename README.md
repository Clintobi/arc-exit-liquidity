# Arc is two chains

**Live: [arc-exit-liquidity.vercel.app](https://arc-exit-liquidity.vercel.app)**

Circle launched Arc on 16 September 2026 and the coverage was unanimous. Coindesk: *"traders immediately turned it into a memecoin casino."* Forbes: *"Circle built Arc for BlackRock, memecoins are moving in first."* Fortune, KuCoin and the rest ran the same story — the institutional chain had been taken over on day one.

The arithmetic does not support it.

| | |
|---|---|
| USDC in circulation, week one (Circle) | 624,000,000 |
| USDC transferred, week one (Circle) | $6,800,000,000 |
| Of that, through DEX pools (this repo) | **~$176M — under 3%** |
| Uniswap V4 pools created (this repo) | **200,163** |
| Pools that ever traded | 48,495 |
| Pools with 100+ distinct wallets | **34** |

Arc turned its entire float eleven times in seven days. That is what a settlement rail looks like. The memecoin layer everyone wrote about was a low single-digit share of the chain's activity, and of the 200,163 pools it produced, thirty-four ever saw a hundred distinct wallets.

It was not a takeover. It was a rounding error on a payments network.

That also settles an open question. The obvious thing to ask was whether Circle would ever bless memecoins on its own chain — Robinhood faced the same situation and resolved it in two weeks by saying memes were fine, while Circle said nothing with Visa and DTCC among its validators. **Circle never had to decide.** The layer resolved itself into irrelevance without a policy statement.

## How it was measured

Arc routes every Uniswap V4 swap through a single PoolManager at `0x8366a39cc670b4001a1121b8f6a443a643e40951`, with the pool id as an indexed topic. That makes the chain's entire DEX history one filtered log query. Pools are counted from `Initialize` events on the same contract over the same block window, so *created* and *traded* are measured on identical ground.

No API wrapper, no paid RPC, no indexing service. The block height on the live page is the browser calling `rpc.mainnet.arc.io` directly — Arc sets permissive CORS, so nothing sits between the page and the chain. Open devtools and watch it.

```bash
python3 arc_index.py --workers 4        # backfill swaps, resumable
python3 verify_census.py                # count pools created, independently
python3 build_site_data.py              # compact to site/data/arc.json
```

## What else is in the data

**155 pools trade a token whose symbol reads USDC but whose contract is not USDC** — on a chain where USDC is the gas token. Two of them are among the largest tokens on Arc by volume, at $7.68M and $6.04M. One contract, `0x8e98a62a…a8f9d9`, runs seven separate pools totalling roughly $7.5M.

**121 pools charge a fixed swap fee of 50% or more.** Every one realised that fee on real swaps with no hook overriding it — verified by comparing the pool's stated fee against the fee emitted on each `Swap` event. Total routed through them is only about $20,000, so this is a real mechanism at trivial scale.

**1,637 pools have been touched by exactly one wallet.** TROLL, the fourth-busiest pool on the chain by swap count, is a single sender: 56,241 of its 57,452 swaps.

## Stated limits

- The scan covers blocks 21,065,860 → 22,357,859. Pools created before Arc's public launch are excluded; the PoolManager itself was deployed far earlier, at block 1,948,056.
- 13 of 1,292 chunks failed on rate limits, so ~1% of the window is unscanned and the created count is a floor.
- Swap-derived counts come from a 4.6M-swap index; the complete index is 7.5M, so traded counts are floors too. This makes the DEX share of transfers a floor as well — call it 3–5% rather than exactly 2.6%.
- "Transferred" is Circle's published ERC-20 transfer figure; ours is DEX swap notional. Different measures, so the ratio is directional. The gap is 20–40×, which no reasonable adjustment closes.
- Volume sums the USDC leg of each swap absolutely, counting both sides of a round trip. The headline figure halves it; the per-token table does not.

## Things that were wrong and got fixed

Recorded because the corrections matter more than the result.

**The swap sign convention is swapper-side, not pool-side.** On Arc's V4 PoolManager a negative amount means the *trader paid that token in*. An earlier version assumed the Uniswap V3 pool-side convention, which inverted buyer and seller. Verified at 99.8% by pairing each swap's own price impact against its sign, restricted to swaps alone in their block so ordering is unambiguous without a log index.

**USDC is token0 in 86% of Arc pools**, so defining direction against token0 rather than against the quote asset scrambles most of the chain.

**The indexer could never finish.** The RPC rejects any `eth_getLogs` returning more than 20,000 logs; 55 chunks in launch week exceed that, the error was swallowed, and every rerun skipped them. Fixed with a 100-block sub-range fallback.

**An early markout finding does not reproduce, and the metric itself does not work here.** A partial 20,000-block sample appeared to show buyers systematically picked off. On the full index those numbers do not exist. Re-derived against the corrected sign convention the result reversed — buys preceded *better* moves than sells, median gap −51bp across 2,289 pools, with buyers worse in only 44% of them.

That reversal is also not reportable, and the reason is the useful part. A markout is only evidence of adverse selection if order flow is roughly independent. On Arc it is nowhere close: across 3.7M consecutive swap pairs, a buy is followed by another buy **84.0%** of the time against **39.4%** after a sell — a 44.5 percentage-point clustering lift. In an AMM that mechanically lifts the price after any buy, whether or not the buyer knew anything.

So the price rise after buys is the next buys arriving, not information. Markouts cannot separate momentum from adverse selection on this flow, in either direction, and no amount of horizon tuning fixes it. `markouts.py` and `flow_clustering.py` reproduce both halves. Nothing is reported from them.

**Fee `8388608` is not a 838% fee**, it is V4's dynamic-fee sentinel meaning a hook sets the rate per swap. Those pools are marked `DYN` rather than given a number.

## Sources

Circle's week-one figures are from [@arc](https://x.com/arc), 23 September 2026. Everything else is derived from Arc mainnet (chain 5042) via `rpc.mainnet.arc.io`, indexed in this repo.
