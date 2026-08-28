# Liquidity: two paths

Adding and locking liquidity is deliberately **not scripted** in this
toolkit. It's the step where mistakes are hardest to undo and most
scripts/bots that "help" with LP creation are exactly the kind of thing
you should be suspicious of. Do it by hand, through the DEX's own UI,
with your own wallet.

## Path A: pump.fun (simplest, most common for new Solana memecoins)

pump.fun bundles token creation + a bonding curve + eventual LP creation
into one flow, and is the default path most new Solana memecoins take:

1. Go to pump.fun, connect your wallet, create the token (name, symbol,
   image, description - the same fields as `config/tokenomics.json`).
2. Trading starts immediately on their bonding curve - no separate LP
   step from you.
3. Once the bonding curve hits their market-cap threshold, it
   auto-migrates to Raydium and the LP is auto-locked/burned by their
   contract. Mint authority is revoked by their contract automatically
   too.

Tradeoffs vs the manual path below: less control over initial
supply/parameters, pump.fun takes a fee, and you're trusting their
contract's lock/burn behavior instead of doing it yourself and pointing
people at the transaction. It's simpler and it's what most traders
expect to see, which cuts both ways - familiar, but also more crowded.

If you go this route, you don't need `create-token.js` /
`attach-metadata.js` / `revoke-authorities.js` at all - pump.fun replaces
that whole pipeline. `config/tokenomics.json` is still useful as your
source of truth for the fields you'll type into their form.

## Path B: manual mint (this toolkit) + Raydium LP

Use this if you want full control over supply, decimals, and the exact
moment authorities are revoked (per `LAUNCH_CHECKLIST.md`).

1. Run through `create-token.js` -> `upload-metadata.js` (+ pin it
   yourself) -> `attach-metadata.js` as documented in the main README.
2. Go to raydium.io, connect the same wallet, use their "Create Pool"
   flow, pick your mint and SOL (or USDC) as the pair, and set the
   initial price by choosing how much of each side to deposit. This
   deposit is real money leaving your wallet into the pool - the ratio
   you choose sets the starting price.
3. Raydium will mint you an LP token representing your share of the
   pool. **This is the part that makes a token ruggable even with mint
   authority revoked** - whoever holds the LP token can withdraw the
   underlying liquidity at any time.
4. Lock or burn that LP token:
   - **Burn** (send to an unrecoverable address / use Raydium's burn UI
     if offered): liquidity is permanently locked forever, simplest,
     fully credible, but you can never withdraw your own capital back
     even to responsibly wind the project down.
   - **Time-lock** (a locker service such as Streamflow or a Raydium-
     integrated locker): liquidity is inaccessible until a public unlock
     date, which you should set far enough out to matter (months, not
     days) and disclose alongside the launch. Less final than burning,
     still requires trusting the locker contract itself.
5. Run `npm run revoke-authorities`, then `npm run verify`, and publish
   both the LP lock/burn transaction and the `launch-summary.json`
   output together per `LAUNCH_CHECKLIST.md`.

## Either path

Do a small test with an amount you're fully comfortable losing before
committing your full liquidity budget - confirm the pool trades, the
price looks right, and (Path B) the LP lock/burn transaction actually
went through and is verifiable on Solscan before telling anyone the
token exists.
