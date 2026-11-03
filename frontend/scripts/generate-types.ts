/**
 * Generate TypeScript types from the backend OpenAPI schema.
 * Usage: npx tsx scripts/generate-types.ts
 * Requires: backend/openapi.json (run `cd backend && python scripts/export_openapi.py` first)
 */

import { execSync } from "child_process";
import fs from "fs";
import path from "path";

const OPENAPI_PATH = path.resolve(__dirname, "../../backend/openapi.json");
const OUTPUT_PATH = path.resolve(__dirname, "../src/types/api.generated.ts");

if (!fs.existsSync(OPENAPI_PATH)) {
  console.error(`OpenAPI schema not found at ${OPENAPI_PATH}`);
  console.error("Run: cd backend && python scripts/export_openapi.py");
  process.exit(1);
}

console.log("Generating TypeScript types from OpenAPI schema...");
execSync(
  `npx openapi-typescript "${OPENAPI_PATH}" --output "${OUTPUT_PATH}"`,
  { stdio: "inherit" },
);
console.log(`Types written to ${OUTPUT_PATH}`);
