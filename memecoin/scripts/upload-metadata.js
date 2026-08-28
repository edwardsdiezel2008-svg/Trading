// Step 2: build the off-chain metadata JSON (the standard Metaplex token
// metadata shape) from config/tokenomics.json and write it locally.
//
// This script does NOT pin the file anywhere - pinning services require
// their own account/API key, and picking one for you would just be another
// thing to trust blindly. Pin metadata.json yourself (nft.storage, Pinata,
// or `irys upload` all work), then paste the resulting URI into .env as
// METADATA_URI and continue to attach-metadata.js.
import fs from "node:fs";
import path from "node:path";
import { MEMECOIN_ROOT } from "./lib.js";

function loadTokenomics() {
  const configured = path.join(MEMECOIN_ROOT, "config", "tokenomics.json");
  const example = path.join(MEMECOIN_ROOT, "config", "tokenomics.example.json");
  const file = fs.existsSync(configured) ? configured : example;
  if (file === example) {
    console.warn(
      "!! No config/tokenomics.json found - using tokenomics.example.json. " +
        "Copy it to tokenomics.json and fill in your real values first.\n"
    );
  }
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function main() {
  const t = loadTokenomics();

  const metadata = {
    name: t.name,
    symbol: t.symbol,
    description: t.description,
    image: t.image,
    external_url: t.external_url,
    properties: {
      files: [{ uri: t.image, type: "image/png" }],
      category: "image",
    },
    extensions: t.socials || {},
  };

  const missing = ["name", "symbol", "description", "image"].filter(
    (k) => !metadata[k] || String(metadata[k]).startsWith("https://your-")
  );
  if (missing.length) {
    console.warn(
      `!! These fields still look like placeholders: ${missing.join(", ")}. ` +
        "Edit config/tokenomics.json before pinning.\n"
    );
  }

  const outPath = path.join(MEMECOIN_ROOT, "metadata.json");
  fs.writeFileSync(outPath, JSON.stringify(metadata, null, 2));
  console.log(`Wrote ${outPath}\n`);
  console.log(JSON.stringify(metadata, null, 2));
  console.log(
    "\nNext: pin this file to permanent storage (nft.storage, Pinata, Irys, " +
      "Arweave, IPFS - anything returning a stable https:// or ipfs:// URI), " +
      "then set METADATA_URI in .env to that URI.\n" +
      "After that: npm run attach-metadata"
  );
}

main();
