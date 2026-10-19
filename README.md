# Promoat for Grok Build / Claude Code

A Claude Code–format plugin for the Promoat Partner API. Grok Build reads Claude Code's plugin format directly, so this one package works on both. It calls `https://promoat-platform-plugins.vercel.app/mcp` with your own `PROMOAT_KEY`. That server proxies to the live API at `https://platform.promoat.ai`. It does not charge, reserve, or refund on its own.

The plugin files sit at the repository root.

## What's in this plugin

- `.claude-plugin/marketplace.json` — makes this repository a one-plugin marketplace, so it can be installed straight from GitHub.
- `.claude-plugin/plugin.json` — manifest.
- `.mcp.json` — points the host at the shared MCP server (`https://promoat-platform-plugins.vercel.app/mcp`) with `Authorization: Bearer ${PROMOAT_KEY}`. Both Claude Code and Grok Build fill `${PROMOAT_KEY}` from the environment, so the same file works in both.
- `skills/promoat-partner-api/SKILL.md` — the Promoat Partner API operating manual. Golden path, hard rules, every endpoint, price, and error code.

This plugin ships no custom code. Every tool call goes through the shared MCP server at `/mcp`, which accepts a `pmat_...` bearer key.

## Install

### 1. Set your key (once)

Get a `pmat_...` key from https://platform.promoat.ai, then save it as the `PROMOAT_KEY` environment variable. Do not put the key in chat, and do not commit it.

Windows (PowerShell):

```powershell
[Environment]::SetEnvironmentVariable("PROMOAT_KEY", "pmat_...", "User")
```

macOS / Linux (add to `~/.zshrc` or `~/.bashrc`):

```bash
export PROMOAT_KEY="pmat_..."
```

Then fully close and reopen your terminal (and VS Code / Cursor, if you start the CLI from there) so new sessions see the variable. Check it with `echo $env:PROMOAT_KEY` (PowerShell) or `echo $PROMOAT_KEY` (bash/zsh).

### 2. Install the plugin

#### Claude Code

```text
/plugin marketplace add TechHiveDev/promoat_partner_grok_plugin
/plugin install promoat@promoat
```

The first line adds this repository as a marketplace (named `promoat`); the second installs the `promoat` plugin from it. Requires Claude Code 2.1.275 or later.

For one session from a local checkout:

```bash
claude --plugin-dir .
```

Note: opening Claude Code *inside* this repository also loads `.mcp.json` as a project server. That works too now, but it duplicates the plugin's server; when testing the installed plugin, start Claude Code from another folder.

#### Grok Build

From a local checkout:

```bash
grok plugin install . --trust
```

`--trust` is required for a local path. Installing from the xAI marketplace, after this repo is listed, does not use that flag.

## Check before you publish

```bash
claude plugin validate --strict .
grok plugin validate .
grok plugin install . --trust
grok inspect
```

`grok inspect` should list the `promoat` MCP server and the `promoat-partner-api` skill; in Grok's MCP Servers panel `promoat` should be `[ready]` with 25 tools. Inside Claude Code, `/mcp` should show `promoat` connected with 25 tools. If either shows a 401 or the server is missing, `PROMOAT_KEY` isn't set in the environment the CLI was started from.

### Golden-path smoke test

Ask the agent, in order: `get_balance` → `estimate_video` (do not spend yet) → confirm the quote → `create_video` → poll `get_job` until `completed` or `failed`.

## License

Proprietary. © 2026 Promoat. All rights reserved.

You may install and use this plugin in Grok Build or Claude Code with your own Promoat account and API key. You may not copy, modify, republish, sublicense, or sell the plugin files. See [LICENSE](LICENSE) for the full terms. Use of the Promoat platform and Partner API follows Promoat's own terms at https://platform.promoat.ai.
