# Handover — Exit Liquidity (Arc dashboard)

Repo: **https://github.com/Clintobi/arc-exit-liquidity** (public)

## Context

Clinton is applying to Schema Research (@schemacap) for an On-chain Data Researcher role. **Applications close Friday 25 September 2026.** The hiring manager is Mike Rychko (@mikhryc0x), who recently praised a live AMM execution dashboard and separately spent two days hand-pulling Arc data.

This project is the audition piece: a live dashboard for Circle's Arc chain, built on a metric he named himself (markouts).

## What is already done

- `arc_index.py` — parallel, resumable backfill of every Uniswap V4 swap on Arc since public mainnet launch (block 21065860). Arc routes all V4 swaps through one PoolManager `0x8366a39cc670b4001a1121b8f6a443a643e40951` with the pool id as an indexed topic, so the whole chain's DEX history is one filtered log query.
- `aggregate.py` — derives `site/data/pools.json`: per-pool markouts at 1/5/30 minutes, split buyer vs seller.
- `.github/workflows/index.yml` — runs both on GitHub's machines every 30 minutes, caches the raw log, commits only the derived JSON. Already triggered and running.

## The finding (verified, do not overstate beyond this)

Markout = after a fill, where the price sits 1/5/30 minutes later.

Buyers alone prove nothing — a token in freefall makes every buyer look picked off, and that is a downtrend, not adverse selection. **Sellers are the control.** Only a gap between the two sides is meaningful.

One pool, 5-minute horizon: buyers −880.6bp across 3,717 fills, sellers **+114.6bp** across 1,778. Buyers down 8.8% while sellers are up 1.1%. Another pool showed −14.3 vs −11.1, which is symmetric and therefore uninformative — the method correctly clears it. That discrimination is the whole credibility of the piece.

## What remains

1. **Map pool ids to token names.** Everything is currently a 32-byte hash. Pool ids are `keccak(PoolKey)`; the practical route is decoding the `Initialize` event from the PoolManager, which carries currency0/currency1 per pool id, then reading `symbol()`/`decimals()` off each token. Nobody shares a dashboard of hashes.
2. **Build the front end** in `site/`. Static, no framework required. Three hero visuals:
   - **Markout divergence** — buyer line falling, seller line rising, diverging over 30 minutes. This is the hero; it is a picture of being picked off.
   - **Token survival** — of tokens launched each day, how many still have real liquidity 1/3/7 days later. A cohort decay curve. Answers "is there a meme season" in one image.
   - **Volume vs liquidity** — log-log scatter; points far off the diagonal are wash, not markets.
   Plus a per-token table (real liquidity, exit cost at $100/$1k/$10k, buyer markout, buy/sell imbalance) as the layer that keeps people returning.
3. **Live layer.** Arc's RPC sets permissive CORS (verified), so the browser calls `https://rpc.mainnet.arc.io` **directly** for current price, liquidity and recent flow — no backend, no keys, nothing between the page and the chain. Batch JSON-RPC calls; refresh the open token fast and the full table slowly.
4. **Deploy** static to Vercel. Total cost $0.

## Hard constraints

- **Do not drop the seller control.** Reporting buyer markouts alone is the difference between a finding and a scare headline.
- **Do not claim every Arc token is toxic.** Some pools are clean; some are merely drifting. The tool's value is telling them apart.
- **Markouts lag their horizon by definition.** A 30-minute number cannot exist for a fill five minutes old. Say so rather than faking freshness.
- **No invented numbers.** Everything must come from the indexed data.
- Known decoding trap: V4 emits `int128` amounts **sign-extended across the full 32-byte word**. Decoding at 128 bits silently produces garbage.
- Block time is ~0.507s, measured; horizons convert to block offsets from it.

## Tone

This ships publicly and gets linked in an application. Plain, precise, no hype. The numbers carry it.
