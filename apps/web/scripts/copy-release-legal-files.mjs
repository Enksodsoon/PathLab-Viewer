// SPDX-License-Identifier: Apache-2.0

import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const repositoryRoot = resolve(webRoot, "../..");
const outputRoot = resolve(webRoot, "dist");

await mkdir(outputRoot, { recursive: true });
await Promise.all(
  ["LICENSE", "NOTICE"].map((name) =>
    copyFile(resolve(repositoryRoot, name), resolve(outputRoot, name)),
  ),
);
