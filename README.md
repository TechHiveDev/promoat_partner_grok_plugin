# Promoat for Grok Build / Claude Code

A Claude Code–format plugin for the Promoat Partner API. Grok Build reads Claude Code's plugin format directly, so this one package works on both. It calls `https://promoat-platform-plugins.vercel.app/mcp` with your own `PROMOAT_KEY`. That server proxies to the live API at `https://platform.promoat.ai`. It does not charge, reserve, or refund on its own.

The plugin files sit at the repository root.

## What's in this plugin

- `.claude-plugin/plugin.json` — manifest. Declares a `userConfig.PROMOAT_KEY` field (sensitive, required) so the host CLI prompts for and stores the key.
- `.mcp.json` — points the host at the shared MCP server (`https://promoat-platform-plugins.vercel.app/mcp`) with `Authorization: Bearer ${user_config.PROMOAT_KEY}`.
- `skills/promoat-partner-api/SKILL.md` — the Promoat Partner API operating manual. Golden path, hard rules, every endpoint, price, and error code.

This plugin ships no custom code. Every tool call goes through the shared MCP server at `/mcp`, which accepts a `pmat_...` bearer key.

## Install

On first load, the host prompts for `PROMOAT_KEY`. Paste a `pmat_...` key there. Do not put the key in chat, and do not commit it.

### Claude Code

```bash
claude plugin marketplace add TechHiveDev/promoat_partner_grok-claude
claude plugin install promoat
```

For one session from a local checkout:

```bash
claude --plugin-dir .
```

### Grok Build

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

`grok inspect` should list the `promoat` MCP server as connected and the `promoat-partner-api` skill as available. Inside Claude Code, `/mcp` should show `promoat` connected.

### Golden-path smoke test

Ask the agent, in order: `get_balance` → `estimate_video` (do not spend yet) → confirm the quote → `create_video` → poll `get_job` until `completed` or `failed`.
