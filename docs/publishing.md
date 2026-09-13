# Publishing to the VS Code Marketplace

Three things require your personal account — I can't do them for you.

## 1. Create a Marketplace "publisher"

1. Go to https://marketplace.visualstudio.com/manage (sign in with a Microsoft account).
2. "Create publisher" — pick an ID (e.g. your name or your future company's name). That's the ID you give me for the `publisher` field in `package.json`.

Note: if it asks for a domain to verify your identity, that's **optional** — it's only for the "Verified" badge, and Microsoft requires 6 months of history anyway before you'd even qualify. Skip it for now.

## 2. Create an access token (PAT)

1. Go to https://dev.azure.com, sign in with the same Microsoft account (create an Azure DevOps organization first if prompted — any name works, it's just a required container).
2. User icon (top right) → "Personal access tokens" → "New Token".
3. Organization: "All accessible organizations". Scopes: "Custom defined" → find "Marketplace" → check "Manage".
4. Copy the generated token (it won't be shown again).

**Never paste this token into the chat.** In practice, in this environment, sharing secrets via `~/.bashrc` exports turned out to be unreliable — the assistant's shell doesn't always pick up profile exports the way you'd expect, and troubleshooting it (grepping the file to check) can itself leak the value into the conversation by accident. **The safer, actually-reliable approach: run the publish command yourself, in your own terminal**, so the token never has to leave your machine or pass through the chat at all (see step 4).

## 3. Create the remote Git repository

1. Create an **empty** repository on GitHub (or GitLab/other) — don't check "Initialize with README".
2. Give me the URL (e.g. `https://github.com/your-account/urscript-debugger.git`), I'll push the code to it and update `repository` in `package.json`.

## 4. Publish

Once the three steps above are done:

```bash
cd extension
npx @vscode/vsce publish -p <your-token>
```

Run this **yourself**, in your own terminal — that's the cleanest way given the environment-sharing caveat above. I'll have already prepared and verified everything else (compiled, packaged, tested) beforehand, so this final command is the only thing you need to run.

## After the first publish

- Each new version: change `version` in `package.json` (semver), then run `vsce publish` again (or `vsce publish patch`/`minor`/`major` to bump it automatically).
- The extension's Marketplace page becomes: `https://marketplace.visualstudio.com/items?itemName=<publisher>.urscript-debugger`.
