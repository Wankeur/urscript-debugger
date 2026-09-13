// Copies the Python DAP server files into extension/server/ so they get bundled into
// the packaged .vsix (vsce only packages files under the extension/ folder). Run before
// compiling/packaging/testing — see package.json scripts.
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "server");
const DEST = path.join(__dirname, "..", "server");
const FILES = ["dap_server.py", "instrument.py"];

fs.mkdirSync(DEST, { recursive: true });
for (const file of FILES) {
  fs.copyFileSync(path.join(SRC, file), path.join(DEST, file));
}
console.log(`Copied ${FILES.join(", ")} into ${DEST}`);
