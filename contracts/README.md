# ArcFlagRegistry

On-chain record of observable facts about tokens traded on Arc, readable by any
wallet or DEX in a single call.

Arc has ~200k Uniswap V4 pools and a few ways to lose money that are knowable
*before* you trade: a token whose symbol reads USDC while its address is not
USDC, a pool whose fee makes selling pointless, a pool only its deployer has
ever touched. Those facts sit in chain history and nothing surfaces them at the
moment anyone would act on them. This puts them somewhere composable.

Detection comes from the full-chain index in the parent repo — 4.6M swaps,
200,163 pools — so a token is assessed whether or not its owner ever shows up.

## Flags

| flag | meaning |
|---|---|
| `SYMBOL_COLLISION` | reports a symbol colliding with a canonical asset at a different address |
| `HIGH_FEE` | seen in a pool whose **realised** fee is >= 50% |
| `SINGLE_TRADER` | every swap in its pools came from one sender |
| `NEVER_TRADED` | a pool exists, no swap ever settled |
| `DYNAMIC_FEE` | fee is hook-controlled per swap, so no fixed rate can be quoted |

Each record carries the supporting numbers — pools, distinct traders, highest
realised fee, the block it holds through, and a publication epoch — so a reader
can check a claim instead of trusting it.

## Three deliberate choices

**Flags are facts, not verdicts.** `SYMBOL_COLLISION` says a symbol collides and
an address differs. It does not say "scam". Consumers decide.

**Clearing is as cheap as publishing.** A detector that cannot be corrected is a
liability, and mislabelling someone's token is real harm.

**Honest about centralisation.** Publishers are an allowlist starting as one
address. `setPublisher` is the seam for changing that, not a claim that it
already has been.

## Costs, measured

Against live Arc gas (20.1 gwei-equivalent, paid in USDC):

| action | gas | USDC |
|---|---|---|
| deploy | 1,111,896 | $0.022 |
| first publish, 155 tokens | 11,503,155 | $0.231 |
| republish, 155 tokens | 1,170,474 | $0.024 |

First write is ~74,000 gas per token and a republish ~7,550 — cold versus warm
storage. Arc's block gas limit is 30,000,000, so batches are chunked at 150
(~11.5M); 300 in one call is 22.2M and too close to the ceiling to be safe.

## Deploy

Arc pays gas in USDC, so the deployer needs a USDC balance on Arc. $5 covers
deployment and a long run of republishing.

```bash
forge test                       # 16 tests
forge script script/Deploy.s.sol:Deploy --rpc-url arc          # dry run
forge script script/Deploy.s.sol:Deploy --rpc-url arc --broadcast --private-key $PK
```
