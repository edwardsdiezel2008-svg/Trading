// Step 5: read the mint back from chain and print a summary you can share
// (or paste into your announcement) that anyone can independently verify -
// don't just claim "authorities revoked, LP locked", show the addresses
// and let people check them on Solscan/RugCheck themselves.
import fs from "node:fs";
import path from "node:path";
import { getMint } from "@solana/spl-token";
import { PublicKey } from "@solana/web3.js";
import { createUmi } from "@metaplex-foundation/umi-bundle-defaults";
import { mplTokenMetadata, safeFetchMetadata, findMetadataPda } from "@metaplex-foundation/mpl-token-metadata";
import { publicKey } from "@metaplex-foundation/umi";
import { loadConnection, requireEnv, MEMECOIN_ROOT } from "./lib.js";

async function main() {
  const connection = loadConnection();
  const rpcUrl = process.env.RPC_URL || "https://api.devnet.solana.com";
  const mintAddress = requireEnv("TOKEN_MINT");
  const mintPk = new PublicKey(mintAddress);

  const mintInfo = await getMint(connection, mintPk);

  const umi = createUmi(rpcUrl).use(mplTokenMetadata());
  const metadataPda = findMetadataPda(umi, { mint: publicKey(mintAddress) });
  const metadata = await safeFetchMetadata(umi, metadataPda);

  const cluster = rpcUrl.includes("devnet")
    ? "devnet"
    : rpcUrl.includes("testnet")
    ? "testnet"
    : "mainnet-beta";
  const explorerSuffix = cluster === "mainnet-beta" ? "" : `?cluster=${cluster}`;

  const summary = {
    mint: mintAddress,
    explorer: `https://solscan.io/token/${mintAddress}${explorerSuffix}`,
    decimals: mintInfo.decimals,
    supply: (mintInfo.supply / 10n ** BigInt(mintInfo.decimals)).toString(),
    mintAuthorityRevoked: mintInfo.mintAuthority === null,
    freezeAuthorityRevoked: mintInfo.freezeAuthority === null,
    metadataAttached: metadata !== null,
    name: metadata?.name?.replace(/\0/g, "").trim() ?? null,
    symbol: metadata?.symbol?.replace(/\0/g, "").trim() ?? null,
    metadataUri: metadata?.uri?.replace(/\0/g, "").trim() ?? null,
    checkedAt: new Date().toISOString(),
  };

  console.log(JSON.stringify(summary, null, 2));

  if (!summary.mintAuthorityRevoked || !summary.freezeAuthorityRevoked) {
    console.warn(
      "\n!! Authorities are NOT fully revoked yet. Run `npm run revoke-authorities` " +
        "before adding liquidity or announcing publicly."
    );
  }
  if (!summary.metadataAttached) {
    console.warn("\n!! No on-chain metadata found. Run `npm run attach-metadata` first.");
  }

  fs.writeFileSync(
    path.join(MEMECOIN_ROOT, "launch-summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log("\nWrote launch-summary.json");
}

main().catch((err) => {
  console.error(`\nverify failed: ${err.message}`);
  process.exit(1);
});
