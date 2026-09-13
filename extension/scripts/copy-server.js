// Copies files from the repo root into extension/ so they get bundled into the
// packaged .vsix — vsce only packages files under the extension/ folder (its package
// root), so anything living at the repo root (server code, README, LICENSE) needs a
// copy here or the Marketplace/runtime won't see it. Run before compiling/packaging/
// testing — see package.json scripts.
const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.join(__dirname, "..", "..");
const EXT_ROOT = path.join(__dirname, "..");

const SERVER_SRC = path.join(REPO_ROOT, "server");
const SERVER_DEST = path.join(EXT_ROOT, "server");
const SERVER_FILES = ["dap_server.py", "instrument.py"];

fs.mkdirSync(SERVER_DEST, { recursive: true });
for (const file of SERVER_FILES) {
  fs.copyFileSync(path.join(SERVER_SRC, file), path.join(SERVER_DEST, file));
}
console.log(`Copied ${SERVER_FILES.join(", ")} into ${SERVER_DEST}`);

for (const file of ["README.md", "LICENSE"]) {
  fs.copyFileSync(path.join(REPO_ROOT, file), path.join(EXT_ROOT, file));
}
console.log("Copied README.md and LICENSE into extension/");
