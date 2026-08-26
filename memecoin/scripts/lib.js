import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";
import { Connection, Keypair } from "@solana/web3.js";

const here = path.dirname(fileURLToPath(import.meta.url));
export const MEMECOIN_ROOT = path.resolve(here, "..");

dotenv.config({ path: path.join(MEMECOIN_ROOT, ".env") });

export function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing ${name} in memecoin/.env. Copy .env.example to .env and fill it in first.`
    );
  }
  return value;
}

export function loadConnection() {
  const url = process.env.RPC_URL || "https://api.devnet.solana.com";
  if (url.includes("mainnet")) {
    console.warn(
      "!! RPC_URL points at mainnet - transactions below will spend REAL funds. " +
        "Ctrl+C now if that's not intended.\n"
    );
  }
  return new Connection(url, "confirmed");
}

export function loadWallet() {
  const keypairPath = path.resolve(
    MEMECOIN_ROOT,
    process.env.WALLET_KEYPAIR_PATH || "./wallet.json"
  );
  if (!fs.existsSync(keypairPath)) {
    throw new Error(
      `No wallet keypair at ${keypairPath}. Generate one yourself first, e.g.:\n` +
        `  solana-keygen new --outfile ${keypairPath}\n` +
        "This script never generates or funds a wallet for you."
    );
  }
  const secret = JSON.parse(fs.readFileSync(keypairPath, "utf8"));
  return Keypair.fromSecretKey(Uint8Array.from(secret));
}

// Reads/writes the flat KEY=value lines in memecoin/.env without disturbing
// comments, so scripts can hand values (TOKEN_MINT, METADATA_URI) forward
// to the next step in the pipeline.
export function updateEnvFile(updates) {
  const envPath = path.join(MEMECOIN_ROOT, ".env");
  let lines = fs.existsSync(envPath)
    ? fs.readFileSync(envPath, "utf8").split("\n")
    : [];
  for (const [key, value] of Object.entries(updates)) {
    const idx = lines.findIndex((l) => l.startsWith(`${key}=`));
    const line = `${key}=${value}`;
    if (idx >= 0) lines[idx] = line;
    else lines.push(line);
  }
  fs.writeFileSync(envPath, lines.join("\n"));
}
