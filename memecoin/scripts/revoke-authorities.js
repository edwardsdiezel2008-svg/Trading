// Step 4: permanently revoke mint authority and freeze authority.
//
// This is the single highest-leverage thing you can do for trust: it makes
// "no more tokens can ever be minted" and "no wallet can ever be frozen"
// verifiable on-chain by anyone, in seconds, on Solscan or RugCheck. Do
// this AFTER minting the full supply and attaching metadata, and right
// before you add liquidity - there's no undo once it's done.
import readline from "node:readline/promises";
import { AuthorityType, setAuthority } from "@solana/spl-token";
import { PublicKey } from "@solana/web3.js";
import { loadConnection, loadWallet, requireEnv } from "./lib.js";

async function confirm(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const answer = await rl.question(question);
  rl.close();
  return answer.trim().toLowerCase() === "yes";
}

async function main() {
  const connection = loadConnection();
  const payer = loadWallet();
  const mint = new PublicKey(requireEnv("TOKEN_MINT"));

  console.log(`Mint: ${mint.toBase58()}`);
  console.log(
    "This will PERMANENTLY revoke mint authority and freeze authority. " +
      "There is no way to reverse this - double check the mint address and " +
      "that you're on the intended network (RPC_URL) before continuing.\n"
  );
  const ok = await confirm('Type "yes" to proceed: ');
  if (!ok) {
    console.log("Aborted - nothing was changed.");
    return;
  }

  console.log("Revoking mint authority...");
  await setAuthority(connection, payer, mint, payer, AuthorityType.MintTokens, null);

  console.log("Revoking freeze authority...");
  await setAuthority(connection, payer, mint, payer, AuthorityType.FreezeAccount, null);

  console.log("\nBoth authorities revoked. Verify with: npm run verify");
}

main().catch((err) => {
  console.error(`\nrevoke-authorities failed: ${err.message}`);
  process.exit(1);
});
