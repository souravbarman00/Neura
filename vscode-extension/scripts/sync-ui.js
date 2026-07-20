// Copy the Neura *extension* UI build (the lean chat+graph+checklist app) into media/
// so the extension can bundle/ship it. Override with NEURA_DIST=/path/to/frontend/dist-ext.
const fs = require("fs");
const path = require("path");

const dist =
  process.env.NEURA_DIST ||
  path.resolve(__dirname, "../../frontend/dist-ext"); // vscode-extension/scripts → repo/frontend
const media = path.resolve(__dirname, "../media");

const entry = fs.existsSync(path.join(dist, "ext.html"))
  ? "ext.html"
  : "index.html";
if (!fs.existsSync(path.join(dist, entry))) {
  console.error(
    `✗ Neura extension build not found at ${dist}\n` +
      `  Build it:  (cd frontend && npm run build:ext)   or set NEURA_DIST.`
  );
  process.exit(1);
}

// Wipe old assets but keep extension-owned icons.
for (const e of fs.readdirSync(media)) {
  if (e === "icon.svg" || e === "logo.png") continue;
  fs.rmSync(path.join(media, e), { recursive: true, force: true });
}
fs.cpSync(dist, media, { recursive: true });

// The webview host loads media/index.html — normalize the entry name.
if (entry === "ext.html") {
  fs.renameSync(path.join(media, "ext.html"), path.join(media, "index.html"));
}
console.log(`✓ synced extension UI  ${dist} → ${media}`);
