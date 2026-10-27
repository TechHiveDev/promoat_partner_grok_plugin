# Promoat for Claude Code

Make realistic AI videos of yourself, with your own face and voice, from Claude Code. This plugin connects Claude to your Promoat account through the Promoat Partner API. It calls `https://promoat-platform-plugins.vercel.app/mcp` with your own Promoat API key. That server proxies to the live API at `https://platform.promoat.ai`. It does not charge, reserve, or refund on its own.

## What's in this plugin

- `.claude-plugin/plugin.json` — manifest. It asks for your Promoat API key when you install the plugin and stores it as a sensitive setting.
- `.claude-plugin/marketplace.json` — makes this repository a one-plugin marketplace, so it can be installed straight from GitHub.
- `.mcp.json` — points Claude Code at the Promoat MCP server with `Authorization: Bearer ${user_config.promoat_key}`, filled from the key you entered at install.
- `skills/promoat-partner-api/SKILL.md` — the Promoat Partner API operating manual. Golden path, hard rules, every endpoint, price, and error code.

This plugin ships no custom code. Every tool call goes through the MCP server, which accepts a `pmat_...` bearer key.

## Install in Claude Code

1. Get a `pmat_...` key from https://platform.promoat.ai. Do not put the key in chat, and do not commit it.
2. Run:

```text
/plugin marketplace add TechHiveDev/promoat_partner_grok_plugin@claude-directory
/plugin install promoat@promoat
```

The first line adds this repository as a marketplace (named `promoat`); the second installs the `promoat` plugin from it. Claude Code asks for your Promoat API key during install. Requires Claude Code 2.1.275 or later.

For one session from a local checkout:

```bash
claude --plugin-dir .
```

Note: opening Claude Code *inside* this repository also loads `.mcp.json` as a project server, which duplicates the plugin's server. When testing the installed plugin, start Claude Code from another folder.

## Check it works

```bash
claude plugin validate --strict .
```

Inside Claude Code, `/mcp` should show `promoat` connected with 25 tools. If you see a 401 or the server is missing, the saved Promoat API key is wrong or missing; reconfigure the plugin.

### Golden-path smoke test

Ask Claude, in order: `get_balance` → `estimate_video` (do not spend yet) → confirm the quote → `create_video` → poll `get_job` until `completed` or `failed`.

## Also works with Grok Build

Grok Build reads the Claude Code plugin format, but it does not use the install-time key prompt above. Use the `main` branch of this repository for Grok Build. It reads the key from an environment variable instead.

1. Save your key as the `PROMOAT_KEY` environment variable, then fully close and reopen your terminal.
   - Windows (PowerShell): `[Environment]::SetEnvironmentVariable("PROMOAT_KEY", "pmat_...", "User")`
   - macOS / Linux: add `export PROMOAT_KEY="pmat_..."` to `~/.zshrc` or `~/.bashrc`.
2. Clone the `main` branch and install it from the checkout:

```bash
git clone --branch main https://github.com/TechHiveDev/promoat_partner_grok_plugin.git
cd promoat_partner_grok_plugin
grok plugin install . --trust
```

`--trust` is required for a local path. Check it with `grok inspect`: it should list the `promoat` MCP server and the `promoat-partner-api` skill, with `promoat` `[ready]` in Grok's MCP Servers panel.

## Privacy

Promoat's privacy policy: https://www.promoat.ai/privacy-policy

## License

Proprietary. © 2026 Promoat. All rights reserved.

You may install and use this plugin in Claude Code or Grok Build with your own Promoat account and API key. You may not copy, modify, republish, sublicense, or sell the plugin files. See [LICENSE](LICENSE) for the full terms. Use of the Promoat platform and Partner API follows Promoat's own terms at https://platform.promoat.ai.
