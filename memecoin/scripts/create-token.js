// Step 1: create the SPL mint and mint the full supply to your own wallet.
//
// Mint authority and freeze authority are both set to your wallet for now
// so you can fix mistakes (wrong decimals, wrong supply) before launch.
// Run revoke-authorities.js right before you add liquidity - a mint with
// live authorities is the #1 thing scanners like RugCheck flag as risky.
import {
  createMint,
  getOrCreateAssociatedTokenAccount,
  mintTo,
} from "@solana/spl-token";
import { loadConnection, loadWallet, requireEnv, updateEnvFile } from "./lib.js";

async function main() {
  const connection = loadConnection();
  const payer = loadWallet();

  const decimals = Number(requireEnv("TOKEN_DECIMALS"));
  const supply = BigInt(requireEnv("TOKEN_SUPPLY"));

  const balance = await connection.getBalance(payer.publicKey);
  console.log(`Wallet: ${payer.publicKey.toBase58()}`);
  console.log(`Balance: ${balance / 1e9} SOL`);
  if (balance < 0.05 * 1e9) {
    console.warn(
      "!! Balance looks low. Mint creation + metadata typically costs a few " +
        "hundredths of a SOL in rent + fees. Fund the wallet before continuing " +
        "(devnet: `solana airdrop 2 --url devnet`).\n"
    );
  }

  console.log(`Creating mint (decimals=${decimals})...`);
  const mint = await createMint(
    connection,
    payer,
    payer.publicKey, // mint authority - revoke later
    payer.publicKey, // freeze authority - revoke later
    decimals
  );
  console.log(`Mint created: ${mint.toBase58()}`);

  const tokenAccount = await getOrCreateAssociatedTokenAccount(
    connection,
    payer,
    mint,
    payer.publicKey
  );

  const rawSupply = supply * 10n ** BigInt(decimals);
  console.log(`Minting ${supply} tokens (${rawSupply} base units)...`);
  await mintTo(connection, payer, mint, tokenAccount.address, payer, rawSupply);

  updateEnvFile({ TOKEN_MINT: mint.toBase58() });
  console.log("\nDone. TOKEN_MINT written to .env.");
  console.log("Next: npm run upload-metadata");
}

main().catch((err) => {
  console.error(`\ncreate-token failed: ${err.message}`);
  process.exit(1);
});
