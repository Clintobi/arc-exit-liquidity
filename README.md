# Exit Liquidity — Arc

Every Uniswap V4 swap on Circle's Arc chain since public mainnet launch, indexed from raw RPC, to answer one question per token: **what happened to the people who bought it?**

Arc routes all V4 swaps through a single PoolManager (`0x8366a39cc670b4001a1121b8f6a443a643e40951`) with the pool id as an indexed topic, so the chain's entire DEX history is one filtered log query. No API wrapper, no paid RPC, no indexer service.

## The metric

**Markout** — after a fill, where is the price 1, 5 and 30 minutes later. It measures whether you got picked off.

Buyers alone prove nothing. A token in freefall makes every buyer look bad, and that's a downtrend, not adverse selection. So sellers are the control: if both sides lose equally the token is simply falling; only a *gap* between the two sides means someone is systematically on the right side of the trade.

Early result on one pool, 5-minute horizon:

| side | fills | median markout |
|---|---|---|
| buyers | 3,717 | **−880.6 bp** |
| sellers | 1,778 | **+114.6 bp** |

Buyers down 8.8% while sellers are up 1.1%, over the same window. That is not a falling market.

The same method clears pools that are merely drifting — one showed buyers −14.3bp against sellers −11.1bp, which is symmetric and therefore uninformative. That discrimination is the point.

## Architecture

Live where it matters, precomputed where it's expensive:

- **Live** — the browser calls Arc's RPC *directly* for current price, liquidity, exit cost and recent flow. Arc's RPC sets permissive CORS, so nothing sits between the page and the chain. Open devtools and watch the calls.
- **Precomputed** — markouts and cohort stats run over millions of swaps, so they ship as static JSON refreshed on a schedule.
- **Cost** — $0. Static hosting plus a cron. No backend, no keys, no third-party data provider.

## Running it

```bash
python3 arc_index.py --workers 10     # backfill from mainnet launch, resumable
python3 aggregate.py                  # derive site/data/pools.json
```

The indexer records completed chunks in `data/done.json`, so it resumes rather than restarting. `.github/workflows/index.yml` runs the same two steps on a schedule, caching the raw log (too large for git) and committing only the derived JSON.

## Notes on method

- Block time is ~0.507s, measured, and markout horizons are converted to block offsets from it rather than fetching a timestamp per block.
- V4 emits `int128` amounts sign-extended across the full 32-byte word; decoding them as 128-bit silently produces garbage.
- Markouts use the pool's own `sqrtPriceX96` as the reference price, so token decimals cancel in the relative move.
- Pools with fewer than 40 swaps are not scored — a median over a handful of fills is noise.
- A markout always lags its horizon. A 30-minute number cannot exist for a fill five minutes old.
