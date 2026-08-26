# Memecoin launch toolkit (Solana)

Scripted, auditable pipeline for launching an SPL memecoin on Solana,
plus the non-code checklist that actually determines whether it earns
any trust or traction.

**Read `docs/RISK_DISCLOSURE.md` first.** The short version: most
memecoins fail, nothing here changes that, and you should only fund this
with money you can afford to lose completely.

**This toolkit never holds your wallet, keys, or funds.** Every script
reads a keypair file you generate and fund yourself, and only submits
transactions your own wallet signs. There is no step where you hand
anything to an external service on your behalf.

## Why this exists

"Success" for a memecoin has two separable parts:

1. **Avoidable failure** - live mint/freeze authorities, an unlocked LP,
   hidden allocations. These are pure downside with no upside, and
   they're exactly what automated scanners (RugCheck, Solsniffer) and
   experienced traders check for in the first ten seconds. This part is
   scriptable and this toolkit does it.
2. **Actual demand** - people finding out the token exists, trusting it,
   and wanting in. This is marketing and community work. No script does
   this for you; see `docs/MARKETING_PLAN.md` for the legitimate version
   of it.

Doing (1) well doesn't guarantee (2). But skipping (1) guarantees you
never get a fair shot at (2), because anyone who checks will bail
immediately.

## Two ways to actually launch

- **pump.fun** - bundles minting + bonding curve + eventual LP lock into
  one flow, the default path for most new Solana memecoins today. See
  `docs/LP_GUIDE.md` Path A. You still don't need to run any of these
  scripts if you go this route.
- **Manual mint + Raydium** - full control over supply/timing, uses the
  scripts below. See `docs/LP_GUIDE.md` Path B.

The rest of this README covers the manual path.

## Setup

```bash
cd memecoin
npm install
cp .env.example .env
cp config/tokenomics.example.json config/tokenomics.json
```

Edit both `.env` and `config/tokenomics.json` with your real values.
`RPC_URL` defaults to devnet - **run the entire pipeline on devnet first**
and confirm it behaves as expected before touching mainnet.

You need your own wallet. This toolkit doesn't create or fund one:

```bash
solana-keygen new --outfile wallet.json   # if you have the Solana CLI installed
# or generate one any other way and drop the secret-key JSON array at
# the path WALLET_KEYPAIR_PATH points to in .env
solana airdrop 2 --url devnet             # devnet only - free test SOL
```

## Pipeline

Each step is one `npm run` command, in order:

| Step | Command | What it does |
|---|---|---|
| 1 | `npm run create-token` | Creates the SPL mint, mints the full supply to your wallet |
| 2 | `npm run upload-metadata` | Builds `metadata.json` from `config/tokenomics.json` (you pin it yourself - see script output) |
| 3 | `npm run attach-metadata` | Attaches on-chain name/symbol/logo to the mint (needs `METADATA_URI` set after pinning) |
| - | add liquidity | Manual, through Raydium's UI - see `docs/LP_GUIDE.md` |
| 4 | `npm run revoke-authorities` | **Permanently** revokes mint + freeze authority - asks for a typed confirmation first |
| 5 | `npm run verify` | Reads the mint back from chain, prints a shareable, independently-checkable summary, writes `launch-summary.json` |

Full walkthrough and the order-of-operations tradeoffs (revoke before or
after adding LP) are in `docs/LAUNCH_CHECKLIST.md`.

## Docs

- `docs/RISK_DISCLOSURE.md` - read first
- `docs/LAUNCH_CHECKLIST.md` - the full deploy sequence and what to
  publish
- `docs/LP_GUIDE.md` - pump.fun vs. manual Raydium, and how to lock/burn
  liquidity
- `docs/MARKETING_PLAN.md` - the non-code work that actually drives
  demand, and the tactics this toolkit deliberately won't help with

## Site

`site/index.html` is a static landing page template - fill in the
placeholders (mint address, socials, DEX link) once the token exists.
No build step; deploy it however you deploy the rest of this repo's
pages (see `../.github/workflows/`).

## What's deliberately not automated

- **Wallet creation/funding** - you control the keys and the money at
  every step, full stop.
- **Metadata pinning** - picking a pinning service is a trust decision;
  making it for you would just move the trust problem, not solve it.
- **Liquidity add/lock** - the highest-stakes, least-reversible step.
  Done by hand through Raydium's own UI so you see exactly what you're
  signing.
- **Marketing** - see `docs/MARKETING_PLAN.md` for why, and what
  legitimate marketing looks like instead.
