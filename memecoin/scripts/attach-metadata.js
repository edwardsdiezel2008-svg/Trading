// Step 3: attach on-chain metadata (name/symbol/URI) to the mint created in
// create-token.js, so wallets and DEXes show a name and logo instead of a
// bare address. Requires METADATA_URI (from upload-metadata.js + pinning
// it yourself) and TOKEN_MINT (from create-token.js) in .env.
import { createUmi } from "@metaplex-foundation/umi-bundle-defaults";
import { mplTokenMetadata, createFungible } from "@metaplex-foundation/mpl-token-metadata";
import { keypairIdentity, percentAmount, publicKey } from "@metaplex-foundation/umi";
import { loadWallet, requireEnv } from "./lib.js";

async function main() {
  const rpcUrl = process.env.RPC_URL || "https://api.devnet.solana.com";
  const mintAddress = requireEnv("TOKEN_MINT");
  const metadataUri = requireEnv("METADATA_URI");
  const name = requireEnv("TOKEN_NAME");
  const symbol = requireEnv("TOKEN_SYMBOL");

  const umi = createUmi(rpcUrl).use(mplTokenMetadata());
  const walletKeypair = loadWallet();
  const umiKeypair = umi.eddsa.createKeypairFromSecretKey(walletKeypair.secretKey);
  umi.use(keypairIdentity(umiKeypair));

  console.log(`Attaching metadata to mint ${mintAddress}...`);
  console.log(`  name: ${name}`);
  console.log(`  symbol: ${symbol}`);
  console.log(`  uri: ${metadataUri}`);

  const tx = createFungible(umi, {
    mint: publicKey(mintAddress),
    authority: umi.identity,
    name,
    symbol,
    uri: metadataUri,
    sellerFeeBasisPoints: percentAmount(0),
    isMutable: true, // leave true until launch is finalized, then lock via update-authority transfer if desired
  });

  const { signature } = await tx.sendAndConfirm(umi);
  console.log(`\nMetadata attached. Signature: ${Buffer.from(signature).toString("base64")}`);
  console.log("Next: npm run revoke-authorities (do this right before adding liquidity)");
}

main().catch((err) => {
  console.error(`\nattach-metadata failed: ${err.message}`);
  process.exit(1);
});
