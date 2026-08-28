# Launch checklist

These are the concrete, externally-verifiable factors that correlate with
a memecoin being trusted enough to get a fair look, versus being
auto-flagged as a likely rug by scanners (RugCheck, Solsniffer) and
skipped by anyone who checks. Security/trust removes downside; it doesn't
create upside (see `RISK_DISCLOSURE.md`) - both matter.

## Before you deploy anything

- [ ] `config/tokenomics.json` filled in with real, accurate values (copy
      from `tokenomics.example.json`)
- [ ] Supply allocation decided and, if anything other than 100% to LP,
      publicly disclosed *before* launch, not after
- [ ] Logo image and description hosted somewhere permanent (not a
      random personal server that can go offline)
- [ ] Ran the full pipeline on **devnet** first (`RPC_URL` defaults to
      devnet in `.env.example`) and confirmed each step behaves as
      expected with `npm run verify`

## Deploy sequence (mainnet)

1. [ ] `npm run create-token` - mint created, full supply minted to your
       wallet
2. [ ] `npm run upload-metadata` - builds `metadata.json`
3. [ ] Pin `metadata.json` to permanent storage yourself, set
       `METADATA_URI` in `.env`
4. [ ] `npm run attach-metadata` - name/symbol/logo now show in wallets
5. [ ] Add liquidity (see `LP_GUIDE.md`) - do this **before** revoking
       authorities if you want the option to adjust supply first, or
       after if you want to prove authorities were dead before any LP
       existed (stronger trust signal, no flexibility to fix mistakes)
6. [ ] `npm run revoke-authorities` - permanent, no undo
7. [ ] Lock or burn the LP token (see `LP_GUIDE.md`) - a token with
       revoked authorities but an unlocked LP is still fully ruggable via
       liquidity withdrawal
8. [ ] `npm run verify` - produces `launch-summary.json` with everything
       below, independently checkable

## What to publish alongside the launch

Publish these together so people don't have to trust your word for any
of it - all of it is checkable on Solscan/RugCheck from the mint address
alone:

- [ ] Mint address
- [ ] `mintAuthorityRevoked: true`
- [ ] `freezeAuthorityRevoked: true`
- [ ] LP lock/burn transaction link (see `LP_GUIDE.md`)
- [ ] Supply allocation (from `tokenomics.json`)
- [ ] Contract/mint was NOT used for a pre-sale to insiders (or, if it
      was, the exact terms - amount, price, vesting)

## Red flags to avoid triggering yourself

These are the exact patterns automated scanners and experienced traders
look for. Don't do these:

- Minting extra supply after the "final" announcement (impossible once
  you've revoked mint authority - which is the point)
- Leaving freeze authority live (lets the deployer freeze any holder's
  wallet)
- An LP that isn't locked or burned (deployer can pull it any time)
- A team/marketing allocation that isn't disclosed
- Metadata pointing at a URI you don't control long-term (free image
  hosts that expire, personal servers)
