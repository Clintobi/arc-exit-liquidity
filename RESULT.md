# RESULT — Task 1 (pool → token map) + Task 2 (full index + aggregate)

Run on the Grok Bot box, 2026-09-23. Every number below comes from `data/swaps.csv` (indexed here from raw RPC), `site/data/pools.json` (unchanged `aggregate.py`) or `site/data/tokens.json`. Anything computed outside `aggregate.py` is marked **diagnostic**.

> **Read section 4 before you publish anything.** The swap amounts' sign convention is the opposite of what `aggregate.py` assumes, and I checked that against the data. The "buyers picked off, sellers as control" reading of `adverse_gap_5m_bps` doesn't hold on this data. I did **not** change the methodology or `pools.json`. I'm reporting it so you can decide.

---

## 1. Coverage

| | |
|---|---|
| Swaps indexed | **7,538,644** |
| Distinct pools with ≥1 swap | **64,416** |
| Pools scored (≥40 swaps) | **11,398** |
| Block range | **21,065,860 → 22,357,859**: 1,292 contiguous 1,000-block chunks, every one fetched complete (checked: `done.json` has no gaps) |
| Head at finish | 22,357,904 (the last chunk ends 45 blocks below it; GitHub Actions carries it forward) |
| Pools found via Initialize | **204,073** (185,873 distinct tokens read), scanned contiguously from block 20,379,860 to 22,361,191 |
| Pools published in `tokens.json` | **11,345 of the 11,398 scored pools** (9,229 tokens). The full 204k map stays in `data/init.json` + `data/token_meta.json`; at 79 MB it's too big to commit or load |
| Scored pools still unnamed | **53** (88,161 swaps, 1.2% of the total; the largest ranks #42). See 4.6 |
| Tokens with no readable `symbol()` | 28 (stored as `null`) |

`tokens.json` has the requested shape per pool id: `token0, token1, symbol0, symbol1, decimals0, decimals1, fee, tickSpacing, created_block`, plus `name0, name1, hooks`. Native `0x000…0` is written as `USDC` with **18** decimals. I checked that on-chain: `eth_getBalance(PoolManager)` equals 10¹² × `balanceOf(PoolManager)` on the 6-decimal ERC-20 at `0x3600…0000`.

Topic0 for Initialize = `0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438`. I computed it with keccak and cross-checked with the same tool, which reproduces the repo's Swap topic exactly.

## 2. Top 15 pools by swap count (from `pools.json`, as-is)

Labels, signs and gap are exactly as `aggregate.py` produces them: price = token1 per token0, "buy" = `amount0<0 && amount1>0`, gap = sell − buy. **Section 4.1 explains what these columns actually measure.**

| # | pool | token0 / token1 | fee | swaps | buys | sells | 5m buy bp (n) | 5m sell bp (n) | gap bp |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `0xd86a9e58…` | USDC / DUKE | 10000 | 85,253 | 48,084 | 37,169 | −290.1 (48,084) | −177.2 (37,167) | 112.9 |
| 2 | `0xd77a1efb…` | USDC / Minara | 0 | 80,888 | 46,311 | 34,577 | −147.3 (46,304) | −88.1 (34,576) | 59.2 |
| 3 | `0xb3f441e8…` | USDC / ARGUS | 9850 | 65,492 | 34,989 | 30,503 | −9.0 (34,988) | 6.1 (30,494) | 15.1 |
| 4 | `0x551bc970…` | TROLL / USDC | 10000 | 57,452 | 1,047 | 56,405 | 0.0 (1,047) | 0.0 (56,330) | 0.0 |
| 5 | `0x3664e344…` | PI / USDC | 10000 | 56,163 | 24,970 | 31,193 | −4.8 (24,969) | 49.9 (31,193) | 54.7 |
| 6 | `0x1857b4a0…` | USDC / MI | 0 | 53,580 | 28,689 | 24,891 | −119.0 (28,685) | 12.9 (24,889) | 131.9 |
| 7 | `0x2318d64a…` | USDC / ARCADE | 100 | 52,844 | 31,646 | 21,198 | 3.3 (31,646) | 17.9 (21,197) | 14.6 |
| 8 | `0x54d5fe8e…` | USDC / "USDC" (UpSideDownCat, fake) | 10000 | 50,814 | 28,790 | 22,024 | −146.0 (28,789) | −25.8 (22,021) | 120.2 |
| 9 | `0xf5a91352…` | USDC / "USDC" (FatCatBatRatWifHat, fake) | 10000 | 43,800 | 24,714 | 19,086 | −218.7 (24,714) | −41.4 (19,085) | 177.3 |
| 10 | `0x68266e6f…` | creo / USDC | 0 | 43,176 | 19,372 | 23,804 | 78.0 (19,371) | 219.6 (23,803) | 141.6 |
| 11 | `0xcd85a7c2…` | USDC / PANCHU | 10000 | 39,308 | 22,118 | 17,190 | −217.2 (22,117) | −100.0 (17,188) | 117.2 |
| 12 | `0xffc14015…` | cirBTC / ARGUS | 2500 | 38,943 | 20,096 | 18,847 | 13.3 (20,081) | −15.2 (18,834) | −28.5 |
| 13 | `0xc362f08b…` | USDC / AI | 10000 | 32,839 | 19,387 | 13,452 | −72.4 (19,383) | 1.0 (13,449) | 73.4 |
| 14 | `0x971d66fc…` | USDC / DUKE | 10000 | 32,405 | 16,942 | 15,463 | 12.2 (16,941) | 36.0 (15,462) | 23.8 |
| 15 | `0xd9133187…` | USDC / FAZE | 0 | 30,892 | 15,766 | 15,126 | −7.8 (15,766) | −0.7 (15,125) | 7.1 |

"USDC" here is ERC-20 USDC `0x3600…0000` unless marked fake. #8 and #9 are meme tokens whose `symbol()` returns `USDC`.

## 3. Gap distribution (scored pools, `adverse_gap_5m_bps` from `pools.json`)

| bucket | pools |
|---|---|
| gap > +100 bp (the pipeline's "buyers materially worse") | **3,039** (= `pools_adverse`) |
| symmetric, \|gap\| ≤ 100 bp | **1,392** |
| … of which tightly symmetric, \|gap\| ≤ 25 bp | 554 |
| gap < −100 bp | **4,291** |
| gap not computable (<5 fills on a side at 5m) | 2,676 |
| **total scored** | **11,398** |

"Symmetric" is my threshold: \|gap\| ≤ 100bp, mirroring the pipeline's 100bp cut. More pools fall below −100 than above +100.

## 4. What looks wrong or suspicious

### 4.1 The sign convention is inverted, so the headline reading is backwards (serious)

`aggregate.py` treats `amount0 < 0` as "the pool pays out token0", which is the Uniswap **V3** pool-side convention. On Arc's V4 PoolManager the amounts are **swapper-side** (negative = the trader paid that token in). I checked it on the data rather than from docs. Across 1,284,859 consecutive-swap price changes in the top 40 pools, `amount0 < 0` coincided with token0's price **falling** 667,722 times out of 667,722, and `amount0 > 0` with it rising 617,137 of 617,137. No exceptions.

What follows, with no change to the code:

- The `buy` label (`amount0<0 && amount1>0`) is really "trader **paid token0, received token1**". In the 9,668 of 11,398 scored pools where token0 is USDC (native 4,623, ERC-20 5,045), that happens to be buying the meme token. The label is right by accident, and the code comment is wrong.
- The markout price is token1-per-token0. In those same USDC-token0 pools, that's the **inverse** of the token's USD price. So `buy = −290bp` on DUKE means DUKE's USDC price **rose** about 3% in the 5 minutes after buys.
- Working through both orientations, `adverse_gap_5m_bps` ≈ (token price move after buys) − (token price move after sells). A positive gap means **price rose more after buys than after sells**. Buyers came out *better* than that reading claims, not worse. `pools_adverse = 3,039` counts pools where buy flow was followed by relatively higher prices.
- Also, even under the code's intended convention, comparing raw price moves across sides isn't a like-for-like control. A seller gains when price *falls*, so "sellers +114.6bp" in HANDOVER.md means the price rose after sells and **sellers lost**. It does not mean "sellers up 1.1%".

**Diagnostic** (same method: post-fill reference, first swap at or after +592 blocks, median). The only change is that it's oriented on the non-USDC token (buy = trader received it, price = its USDC price):

| # | token | `buy` in pools.json means | token buyers: n, 5m bp | token sellers: n, 5m bp | sellers − buyers |
|---|---|---|---|---|---|
| 1 | DUKE | buying DUKE | 48,084, **+298.7** | 37,167, +180.4 | −118.3 |
| 2 | Minara | buying Minara | 46,304, +149.5 | 34,576, +88.9 | −60.6 |
| 3 | ARGUS | buying ARGUS | 34,988, +9.0 | 30,494, −6.1 | −15.1 |
| 4 | TROLL | *selling* TROLL | 56,330, 0.0 | 1,047, 0.0 | 0.0 |
| 5 | PI | *selling* PI | 31,193, +49.9 | 24,969, −4.8 | −54.7 |
| 6 | MI | buying MI | 28,685, +120.4 | 24,889, −12.9 | −133.3 |
| 7 | ARCADE | buying ARCADE | 31,646, −3.3 | 21,197, −17.8 | −14.5 |
| 8 | "USDC" (UpSideDownCat) | buying it | 28,789, +148.1 | 22,021, +25.9 | −122.2 |
| 9 | "USDC" (FatCatBatRatWifHat) | buying it | 24,714, +223.6 | 19,085, +41.5 | −182.1 |
| 10 | creo | *selling* creo | 23,803, +219.6 | 19,371, +78.0 | −141.6 |
| 11 | PANCHU | buying PANCHU | 22,117, +222.1 | 17,188, +101.0 | −121.1 |
| 12 | cirBTC/ARGUS | no USDC leg, skipped | | | |
| 13 | AI | buying AI | 19,383, +72.9 | 13,449, −1.0 | −73.9 |
| 14 | DUKE (2nd pool) | buying DUKE | 16,941, −12.2 | 15,462, −35.9 | −23.7 |
| 15 | FAZE | buying FAZE | 15,766, +7.8 | 15,125, +0.7 | −7.1 |

In the busiest pools, the token's price **went up** after buys, by more than it did after sells. That is the opposite of "buyers picked off". The discrimination the handover relies on (one pool clearly split, another symmetric) still exists, but the direction and meaning of the split need re-deriving before anything ships. Suggested fix, for you to approve: read the side from `amount1 > 0` (or `amount0 < 0`) with a correct comment, orient price on the non-USDC token, and compare *trader P&L* (buyer: +move, seller: −move) rather than raw moves.

### 4.2 The handover's headline pool doesn't reproduce

No scored pool on the full dataset has 3,717 buy fills or 1,778 sell fills at 5m, and none shows −880.6bp. Those numbers came from a partial index. Don't quote them.

### 4.3 The indexer could never finish: 20,000-result cap (fixed)

The primary RPC refuses any `eth_getLogs` returning more than 20,000 logs (`query exceeds max results 20000`). 55 chunks in the launch-week window (blocks 21.12M–21.21M) exceed that. `rpc()` swallows the error, the chunk is never marked done, and every rerun skips it. The drpc backup can't help: its free plan rejects 1,000-block ranges with a misleading "ranges over 10000 blocks" error, though it accepts 100. **GitHub Actions has the same problem and would never have reached a complete index.** Fix in `arc_index.py`: `fetch()` retries a failed chunk as ten 100-block sub-ranges, and the chunk is recorded done only if all ten return. The resume logic is untouched.

### 4.4 Resume logic: two data-integrity bugs, flagged and not changed

1. **Tip chunk marked done half-read.** `range(from_block, head, CHUNK)` includes the chunk containing `head` and marks it done after fetching only up to `head`. The rest of that chunk is never fetched. Each run near the tip loses up to 999 blocks. The GH Action runs every 30 minutes, so it loses a slice every run. Here it cost 447 swaps across 17 chunks, which I re-fetched with a one-off repair. Suggested one-line fix: only schedule chunks with `start + CHUNK - 1 <= head`.
2. **Duplicates after an interrupted run.** `done.json` is flushed every 25 chunks, but rows are flushed immediately. A killed run (or an Actions timeout) re-fetches up to 24 chunks that were already written. It happened here once, when I stopped a pass: 2,990 duplicate rows. I dropped them and re-fetched that chunk. About 108 further exact-duplicate rows remain, scattered across chunks that were fetched exactly once. They look like real bot swaps that return to the same price inside a block, so I kept them.

### 4.5 Data quirks that will distort a dashboard

- **1,055 tokens return `symbol() = "USDC"` and aren't USDC**, including pools #8 and #9 above. Show `name` and address, and flag symbol collisions with `0x3600…` and native.
- **TROLL (#4) is one bot.** Sender `0x4fca4a51…` made 56,241 of the pool's 57,452 swaps, and both markout medians are exactly 0.0. It's the fourth-busiest pool, but it isn't a market.
- **Extreme tails.** Top gaps in `pools.json` reach 1,343,826,464bp on 56-swap pools, where price moves by orders of magnitude (rugs or pulled liquidity). Sorting by gap surfaces only these. Clip or require more fills.
- **Stale reference price.** `price_at` takes the first swap at or after +5m with no cap. For 7.9% of 5m markout fills (537,807 of 6,816,652), that swap is more than 5 minutes late. For 1.7% (117,663) it's more than 60 minutes late.
- **Fees.** 2,005 pools initialize with fee 931,000 (93.1%) and 1,571 with 890,090 (89%), which looks like honeypots. 1,414 use the dynamic-fee flag (8,388,608). There are 165,724 distinct hook contracts, roughly one per launchpad pool.
- 203k+ pools were initialized, but only 64,416 ever swapped.

### 4.6 Pools created before the "launch" block

The PoolManager was deployed at block **1,948,056**, and USDC has sat in it since before block 5,000,000. Blocks 21,065,860 onward aren't the start of V4 activity. The first swap in the window lands on block 21,065,860 itself, so many pools were created earlier. Scanning back to block 20,379,860 found **883** pools created before the launch block, 122 of them scored (including #9, created at 20,837,016). The remaining 53 unnamed scored pools were created earlier still. Scanning back to deployment is ~18.4M more blocks, about 5–6 h under the primary RPC's rate limit (drpc can't serve these ranges). The scan is resumable and newest-first: `python3 arc_tokens.py --workers 4 --from-block 1947860`. Don't raise the worker count. At 16 workers the RPC returns 429 and the scan stalls.

### 4.7 Other

- **The Action could never commit its output.** `.gitignore` had `data/`, which also matches `site/data/`. So `git add site/data` in the workflow fails ("paths are ignored"), the step errors, and nothing gets committed. That's consistent with `origin/main` having no `data: refresh` commit. Fixed by anchoring it to `/data/`. I couldn't view the Action's run logs: no `gh` auth on this box, and the public API was rate-limited.
- The markout reference is the swap's own post-trade `sqrtPriceX96`, so the fill's own price impact is excluded. **Diagnostic:** measuring from the pre-fill price instead widens every top-15 gap, by 9.5bp (FAZE) up to 181.3bp (the second DUKE pool: 23.8 → 205.1). The reference choice matters as much as some of the gaps.

## What changed in the repo

- `arc_tokens.py` (new): Initialize scan to pool map, then batched `symbol/name/decimals`. Resumable caches live in `data/` (gitignored). It seeds from the committed `tokens.json` on a cold runner.
- `arc_index.py`: 100-block sub-range fallback in `fetch()` (4.3). Resume logic unchanged.
- `.github/workflows/index.yml`: runs `arc_tokens.py` after `aggregate.py`, with `continue-on-error`.
- `.gitignore`: `data/` changed to `/data/`, so `site/data/` can be committed (4.7).
- `site/data/tokens.json`, `site/data/pools.json`: regenerated from the full index.
- `aggregate.py`: **unchanged**.
