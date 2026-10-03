# Product

## Register

product

## Users
People about to buy a token on Circle's Arc chain (chain 5042), usually from a link, a group chat or a DEX list. They have a contract address and a few seconds before they act, and they often check on their phone. They want to know one thing: is this token what it says it is, or is there something about it I'd regret not knowing?

Secondary users:
- Arc/Circle grant reviewers, who walk through the same flow to judge the build.
- Wallet and DEX developers, who want to read the same answer from the on-chain registry in one contract call.

## Product Purpose
Arc Token Check gives a plain, evidence-backed answer about any Arc token before you trade it. The answers come from ArcFlagRegistry on Arc mainnet (`0x27B0AA7E1824d4561c02363bf1c3Ac47e4548221`). That registry is built from a full index of every Uniswap V4 swap on Arc: 4.6M swaps across 200,163 pools.

The facts it surfaces:
- the token's symbol reads USDC, but its address isn't USDC (on a chain where USDC is the gas token)
- the pool's realised fee is 50% or more
- only one wallet has ever traded it
- a pool exists but has never traded
- the fee is hook-controlled, so no fixed rate can be quoted

Success means a trader pastes an address and understands the verdict, and why, in under five seconds. A reviewer sees a real, working tool on mainnet. A developer can copy the one-line contract call.

The app has two surfaces:
1. **Check (home):** paste an address and get a verdict with its evidence.
2. **Findings:** what the chain-wide index found, plus how the registry works and how to integrate it.

## Brand Personality
Calm, exact, trustworthy. The voice is a lab report written by someone who respects you:
- Plain verdicts.
- Numbers that back them up.
- No hype, no fear-selling.
- Flags are stated as facts, not accusations ("symbol collides with USDC at a different address", never "SCAM").
- When the tool doesn't know, it says so.

References:
- **Apple Health lab results:** one plain result up top, evidence underneath, calm color that separates normal from out-of-range without alarm.
- **Stripe Radar and Stripe docs:** quiet confidence in risk language, exact numbers, developer docs that just work.

## Anti-references
- **Crypto casino:** neon, gradients, rockets, degen meme energy.
- **Generic SaaS template:** hero + three feature cards + big stat numbers.
- **Scary red alarm site:** everything flashing red, fear-selling.
- **The current terminal look:** SCREAMING_SNAKE_CASE headings, a hacker aesthetic, dashboard-as-costume.

## Design Principles
1. **Verdict first, evidence always.** The answer leads; every claim links to the number or transaction that supports it.
2. **Facts, not accusations.** Wording and color describe what's observable and never pass judgment on the people behind a token.
3. **Calm under risk.** A flagged token is shown clearly but without alarm. Severity comes from hierarchy and plain words, not red everywhere.
4. **Honest about limits.** Show the block the data holds through, who publishes the flags, and what isn't covered.
5. **One job per screen.** Check is for checking. Findings is for reading. Nothing competes with the address field on home.

## Accessibility & Inclusion
- WCAG 2.2 AA throughout.
- Mobile-first: most checks happen on a phone.
- Every flag state is distinguishable without color: icon plus words.
- Full keyboard use, including paste-and-check with Enter.
- `prefers-reduced-motion` respected.
- Readable at 200% zoom.
