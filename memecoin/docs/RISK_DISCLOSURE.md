# Risk disclosure - read this before spending real money

This is not investment, legal, or tax advice. Nothing in this directory
guarantees a token will gain value, attract holders, or trade at all.

## The base rate

The large majority of memecoins launched go to zero. Most get little to no
trading volume beyond the launch. Even ones that pump early often collapse
within days. Treat any money put into liquidity, marketing, or the token
itself as money you are fully prepared to lose - because on the base rate,
that is the most likely outcome, not a tail risk.

## What good execution can and can't do

Revoked mint/freeze authorities, locked liquidity, and honest tokenomics
(covered in `LAUNCH_CHECKLIST.md`) remove the *avoidable* failure modes -
the ones where the deployer can rug by design. They do not create demand.
Nothing in this toolkit can manufacture organic holders, trading volume, or
media attention. That depends on factors outside code: timing, luck, an
actual community forming, and sustained, honest promotion.

## Legal and regulatory exposure

- Token launches can implicate securities law depending on your
  jurisdiction, how the token is marketed, and whether purchasers are led
  to expect profit from your efforts. "Memecoin, no utility, pure joke"
  positioning is the common way projects try to stay outside that
  framework, but positioning is not a legal opinion - talk to a lawyer if
  you intend to raise a meaningful amount of money or market aggressively.
- Misleading claims (fake partnerships, fabricated audits, fake team
  credentials, promised returns) can constitute fraud in most
  jurisdictions regardless of "it's just a memecoin."
- Wash trading, fake volume bots, and coordinated pump-and-dump
  organizing are illegal market manipulation in many jurisdictions, not
  just against exchange ToS. Nothing here helps with any of that, and it
  won't.

## What this toolkit will not help with

- Fake or purchased social proof (bought followers, fake engagement, bot
  armies).
- Deceptive claims in metadata, the landing page, or marketing copy.
- Anything designed to make an exit scam ("rug") look like a legitimate
  failure - concealing an unlocked LP, hidden minting, or misleading
  supply allocation.

If you want a project to be durable, the honest version of every step
here (real revoked authorities, real locked liquidity, accurate
tokenomics) is also the version most likely to earn trust - they're not
in tension.

## Only proceed with mainnet spending once

- You've read `LAUNCH_CHECKLIST.md` and can honestly check every box.
- You've validated the entire pipeline on devnet first (default `RPC_URL`
  in `.env.example`) and confirmed it behaves as expected.
- The wallet funding this is money you can afford to lose completely.
