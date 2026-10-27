---
name: promoat-partner-api
description: Operate the Promoat Partner API end to end through the Promoat MCP tools — make AI presenter (UGC-style) vertical videos from a script or recording, create presenter characters from selfies or a description, pick a free studio voice or clone one, synthesize speech, generate first-frame stills, and edit finished videos (redo a scene, rewrite lines, replace the sound) — always quoting credits before spending, with idempotent retries and active job polling. Use whenever the user wants a Promoat / AI presenter / AI spokesperson / talking-head / UGC ad / "video of me" / multi-scene marketing video, mentions their Promoat key, credits, balance, top-up, job or workflow status, or any /api/partner/v1 endpoint.
version: 1.2.2
---

# Promoat Partner API — agent operating manual

The **Promoat Partner API** turns a script (or a recording) into a finished vertical 9:16 marketing video fronted by an AI presenter. This file is the agent's source of truth: golden path, rules, decision table, every tool, price, limit and error. When the live API disagrees with this file, trust the API response and tell the user.

**You work through the Promoat MCP tools** (`get_balance`, `estimate_video`, `create_video`, `get_job`, …). The plugin connects them with the user's own key, read from the `PROMOAT_KEY` environment variable. **If the Promoat tools are not in your tool list, stop**: tell the user the Promoat MCP server isn't connected and how to fix it ([Key handling](#hard-rules), rule 1). Don't switch to raw HTTP on your own, and never go looking for a key.

## Quick facts

| Fact | Value |
|---|---|
| How to call | The Promoat MCP tools. Each tool returns the API's JSON unchanged; a failed call returns the error JSON (`error_code`, `message`) as a tool error |
| Auth | Handled by the plugin: the MCP server is called with `Authorization: Bearer ${PROMOAT_KEY}` from the user's environment. Never ask for the key (see [Key handling](#hard-rules)) |
| Async | Videos and edits return a `workflow_id`; **poll** with `get_job` every ~20 s until `completed` or `failed`. No webhooks |
| Output | Always vertical 9:16; default resolution **768P** |
| Inputs | Every image / audio input is a **public https URL**. The tools cannot upload local files |
| Money | 1 credit = $0.01 of usage. Quotes are a hard ceiling: you are charged min(actual, reserved) |
| Live API · docs · dashboard | `https://platform.promoat.ai` · `/docs` · `/partner` (sign in `/sign-in`, new account `/sign-up`) |

## Tools

Argument names follow each tool's schema. Two differ from the API's field names: job and edit tools take **`workflowId`** (camelCase), and get / delete / regenerate / reclone tools take **`id`**. Everything else uses the API's snake_case body fields shown in the playbooks.

| Tool | Key arguments | API | Cost |
|---|---|---|---|
| `get_balance` | `from?`, `to?` (ISO) | `GET /usage/summary` | free |
| `create_character` | `name` + `selfie_image_urls` or `description` | `POST /characters` | free |
| `list_characters` · `get_character` · `delete_character` | — · `id` · `id` | `GET/DELETE /characters…` | free |
| `regenerate_character` | `id`, `edit_instructions?` | `POST /characters/{id}/regenerate` | 4 |
| `list_voice_presets` | — | `GET /voices/presets` | free |
| `clone_voice` | `name` + `studio_voice`/`language`/`gender` **or** `sample_urls` | `POST /voices` | studio 0 · first clone 0, then 30 |
| `list_voices` · `delete_voice` | — · `id` | `GET/DELETE /voices…` | free |
| `reclone_voice` | `id`, `sample_urls` | `POST /voices/{id}/reclone` | 30, or 0 if expired |
| `synthesize_speech` | `voice_id`, `text` | `POST /tts` | max(10, ceil(chars/1,000) × 10) |
| `create_first_frame` | `character_id`, `kind`, `scene_description` | `POST /images/first-frame` | 4 |
| `plan_scenes` | `video_type`, `script` | `POST /videos/scene-plan` | free |
| `estimate_video` | the exact video body | `POST /videos/estimate` | free |
| `create_video` | same body + `expected_credits` + `idempotency_key` | `POST /videos` | the quote, reserved up front |
| `get_job` | `workflowId` | `GET /jobs/{workflow_id}/status` | free |
| `get_scenes` | `workflowId` | `GET /videos/{workflow_id}/scenes` | free |
| `fix_scene` · `edit_script` · `fix_sound` | `workflowId` + edit body + `dry_run` / `expected_credits` + `idempotency_key` | `POST /videos/{workflow_id}/…` | quote; sound swap free |
| `list_jobs` | `limit?`, `offset?` | `GET /usage/jobs` | free |
| `list_assets` · `get_asset` | `kind?`, `limit?`, `offset?` · `id` | `GET /assets…` | free |
| `create_checkout_session` | — | `POST /billing/checkout-session` | **don't use** — see rule 8 |

`idempotency_key` is sent as the `Idempotency-Key` header. Use it rather than the body field `client_request_id` (which must be a real UUID).

## Golden path

**Make a video**
1. **Key check** — `get_balance` (free). `401` → the key in `PROMOAT_KEY` is wrong; stop and tell the user to fix it (rule 1). Note `credits_balance`.
2. **Character** — reuse an existing `character_id` (`list_characters`) or create one (`create_character`, free). Show `sheet_image_url` and get the user's OK on the look.
3. **Voice** — reuse a `voice_id` (`list_voices`), add a free studio voice, or clone the user's voice (first clone free, then 30). Skip if the user supplies their own audio (`audio_url`) or wants a silent video.
4. **Script & format** — agree the script and pick the mode with the [decision table](#choosing-the-request). Optional: `plan_scenes` (free) to preview the scenes.
5. **Estimate** — `estimate_video` with the exact body you will send (free). Read `credits_required`, `sufficient_credits`, `lines`, `warnings`.
6. **Confirm the price with the user** — write a visible chat reply with the estimate: "This will cost N credits (balance B). Go?" and **end your turn**. Wait for a yes unless the user pre-approved a budget that covers N. Never call `create_video` before an `estimate_video` result has been shown to the user in the chat; `sufficient_credits: true` only means the balance is enough, it is not approval. If `sufficient_credits` is false, stop and send them to top up.
7. **Queue** — `create_video`, same body + `"expected_credits": N` + a fresh `idempotency_key` ([how to make one](#idempotency)). Write down `workflow_id` and the key.
8. **Poll actively** — tell the user the expected time (talking head ~10 min, scenes ~25 min), then call `get_job` every ~20 s yourself until `completed` or `failed` ([polling](#polling)).
9. **Deliver** — hand over `video_url` (and `poster_url`), `credits_consumed`, and any warnings. On `failed`, act on `error_code` ([job failures](#job-failure-codes)).

**Edit a finished video** (each edit makes a NEW video; the source stays as the undo)
1. `get_scenes` — show the user the numbered scenes and their lines.
2. Pick the edit: one scene looks wrong → `fix_scene`; change words → `edit_script`; new voice-over / recording → `fix_sound`.
3. Call it with `"dry_run": true` (no key needed, nothing charged) → show `credits_quoted` (and the fix-sound `plan`) → get a yes.
4. Call it again with the same body without `dry_run`, plus `"expected_credits": N` and a fresh `idempotency_key` → poll the new `workflow_id` → deliver.

## Hard rules

**Key handling**
1. The key comes from the user's `PROMOAT_KEY` environment variable, and the MCP tools already send it. **Never** ask the user to paste the key into chat, and never print it. Two failure cases:
   - **The Promoat tools are missing, or a tool answers `401`** → the key isn't set or is wrong where the app was started. Tell the user: "The Promoat server isn't connected — set `PROMOAT_KEY` to your `pmat_…` key (Windows: `[Environment]::SetEnvironmentVariable("PROMOAT_KEY", "pmat_…", "User")`; macOS/Linux: add `export PROMOAT_KEY="pmat_…"` to your shell profile), then fully restart the app and try again." Then stop until they have.
   - **Never go looking for a key.** Don't read credential stores, config folders, `.env` files, shell history, or other apps' settings (for example `~/.claude/`, `~/.grok/`, `.credentials.json`) to find one, and never use a key you come across there.
2. If the user pastes a key into chat anyway, don't repeat it, and recommend they get it replaced: there is no self-serve rotation for current keys, so they ask Promoat support (the dashboard's **Replace with new encrypted key** button exists only for older keys stored without an encrypted copy).
3. Never print, log, or write a key into files, scripts or docs; redact it to `pmat_…` in anything you show.

**Spend safety**
4. Never call a paid tool without telling the user the price first, in a visible chat reply. Every `create_video` must be preceded by an `estimate_video` for the same body whose price the user has seen. Videos: `estimate_video`. Edits: `dry_run: true`. Fixed prices (first frame 4, regenerate 4, TTS, clone 0 or 30) come from the [price list](#pricing). Instant tools have no `expected_credits` guard: check `credits_charged` in the answer.
5. Always send `expected_credits` = the price the user approved. If the server would charge more, it refuses with `409 QUOTE_MISMATCH` and charges nothing. A paid `fix_sound` **requires** it (missing = treated as 0 → 409).
6. Never loop on `402` or `409`. `402 INSUFFICIENT_CREDITS`: report `credits_required` vs `credits_balance` and send the user to top up (rule 8). `409`: read the code, re-quote or fix, and ask the user again.
7. Never re-queue a video while the original is still `queued`/`running` — that pays twice.
8. To top up, send the user to the dashboard: `https://platform.promoat.ai/partner` → **Buy credits**. Don't call `create_checkout_session` — it is the dashboard's own checkout step and is not tied to the caller's account.

**Inputs**
9. Every selfie, voice sample, scene photo, frame and recording must be a **public https URL**. You cannot upload files through the tools. If the user points at a local file ("the selfies on my desktop"), say so and ask for a public https link to each file (any host that serves the raw file works). Never invent or guess URLs.

**Retries and idempotency**
10. Send an `idempotency_key` on every `create_video` and every paid edit (edits require it). Make a new key per intended job ([how](#idempotency)) and write it down with the job.
11. Timeout, connection error, or `503 TRY_AGAIN` → call the tool again with the **identical** arguments and the **same** key: you get the original job (`"duplicate": true`) and nothing is charged twice. On `create_video` the body is re-validated and re-priced **before** the duplicate lookup, so a retry can instead get `409 QUOTE_MISMATCH` (the price rose: re-confirm, resend with the new `expected_credits` under the same key) or `404`/`422` (a referenced character, voice or recording is gone). Edits answer the duplicate first. Without a key, never blind-retry `create_video` — check `list_jobs` with `limit: 5` first.
12. A key is bound to its first job forever, even a failed one: a duplicate answer whose `status` is `failed` means "refunded, start over" — use a **new** key for the new attempt.
13. Read tools (`get_*`, `list_*`) are always safe to retry.

**Bookkeeping**
14. Record every id the API returns (`character_id`, `voice_id`, `workflow_id`, `asset_id`/`frame_id`) and every idempotency key. Recover lost ids with `list_characters`, `list_voices`, `list_jobs`, `list_assets`.
15. Always tell the user about `warnings` — the request ran, but not exactly as written.

**Polling**
16. After `create_video` or any paid edit, poll **actively**: call `get_job`, wait ~20 s, call it again, and keep going on your own until `status` is `completed` or `failed`. Don't wait for the user to ask "is it done?", and don't replace the loop with one long wait followed by a single check. Report `phase` / `progress` when it changes, not on every call. Poll with the `get_job` tool itself, never with a shell command, script or code runner (`sleep`, `curl`, Python, …): those make the user approve or click Run for every pause. Never ask the user to run, click or approve anything to keep polling.
17. **Never end your turn while a job is `queued` or `running`.** You cannot act after your turn ends, so a message like "I'll check about once a minute" or "I'll send the link when it's done" followed by stopping is a broken promise — the user is left waiting. Keep calling `get_job` in the same turn until `completed` or `failed`, then deliver. Check every ~20 s, not "once a minute". Stop early only if the user explicitly tells you to; then give them the `workflow_id` and say they can ask you to check it.

**Talking to the user**
18. Never mention this skill, "the guide", "the plugin's instructions", these rules, or any internal reference to the user. Speak only about their request and their Promoat account.
19. The price is whatever `estimate_video` (or an edit's `dry_run`) returns. Show that number as the price. Never compare it with the tables in this file, never say a quote "doesn't match" anything, and never explain prices using this file's numbers — the live price includes deployment pricing that this file does not show.

## Choosing the request

| The user wants… | Send | Price impact (768P) |
|---|---|---|
| One presenter talking to camera (promo, announcement, explainer, CTA) | `mode: "talking_head"` | 8 cr/s + first frame 4 + transcription |
| The presenter acting it out across shots (tour, demo, day-in-the-life) | `mode: "scenes"` (reference mode, default) | 8 cr/s + realistic photo 4 + photo/voice allowance + transcription |
| Scenes, cheapest, no photos needed | `mode: "scenes"`, `video_mode: "text"` | 4 cr/s, no photo line; scene photos and frames are ignored |
| A silent clip (music added later) | `mode: "scenes"`, `voice_mode: "none"`, `target_seconds` 5–60 (a JSON number) | No TTS, no transcription; seconds = `target_seconds` |
| Presenter speaks a script in a chosen voice | `voice_id` + `script` | + TTS (10 per started 1,000 chars); priced at estimated length +10% (+35% non-Latin), settled at the real length — often a refund |
| User has their own recording | `audio_url` (public https, 1–59.5 s) | Priced at the probed length; no TTS line |
| Captions burned in | `use_dynamic_captions: true` (talking head only) | +10 |
| Product / place / prop shots in the video | `scene_photos: [{url, role, caption}]` (≤3) | Talking head: used in the generated first frame, free. Scenes reference mode: allowance ≈ +0 / +0 / +6 / +10 for 0/1/2/3 photos on a 15 s video (grows with voiced clip length) |
| Lock the opening look before paying for the render | `create_first_frame` (4) → `first_frame_asset_id` | Drops the video's 4-credit frame line (net 0, but the look is approved first) |
| Their own opening still | `first_frame_url` (https, single subject) | −4 |
| Cheaper / sharper | `resolution`: `480P` / `768P` / `1080P` | 5 / 8 / 16 cr/s (text mode 2.5 / 4 / 8) |

Rules of thumb: `talking_head` is the safe default for a single message; `scenes` when movement or real product shots matter. Scene `role`: `product` (the thing sold), `setting` (the place), `prop` (an object handled). `caption` (≤200 chars) says what it is. No voice and no recording → only a silent `scenes` video is possible.

## First-run setup

1. **Account** — `https://platform.promoat.ai/sign-up` (full name, organization, email, password ≥8 characters, confirm password), then the dashboard `/partner`.
2. **Buy credits** — dashboard → **Buy credits** → Stripe checkout. Default is the **$19.99 pack**: **1,499 credits** for accounts created on/after 8 July 2026 20:40 UTC (current tier, 750 credits per $10), **1,738** for older accounts (earlier tier, $1.15 per 100 credits). A custom amount is available (multiples of 100 credits). Credits land within seconds; receipts appear in the dashboard's payments list.
3. **API key** — with `/sign-up`, the first top-up creates the key; it is shown after checkout and can be revealed and copied from the dashboard's API key panel (signed in). The homepage sign-up creates the key straight away; 25 starter credits are added on the key's first call.
4. **Store it** — as the `PROMOAT_KEY` environment variable (rule 1 has the commands), then fully restart Claude Code / Grok so the plugin picks it up. Not in chat, not in code.
5. **Verify** — `get_balance` → `{ "credits_balance": …, … }`. `401` (or the Promoat tools are missing) = `PROMOAT_KEY` is unset, wrong or truncated; fix it and restart the app.

For scale: a 15 s talking head at 768P from your own audio is 125 credits; a 15 s scenes video with 2 photos is 131.

## Writing the script (idea → approved script)

When the user brings an idea, not a script, do the creative work before any paid call:
1. Get the brief in one pass (skip what they already said): goal (sell / explain / announce / story), product or offer, audience, platform, length, language, tone, the one action viewers should take.
2. Offer three genuinely different hooks (direct benefit, curiosity gap, relatable problem), each sayable in the first 2–3 seconds. Let them pick or combine.
3. Recommend the format from the decision table in one sentence; let them override.
4. Write spoken language for the target length: ~35 words ≈ 15 s, 55–65 ≈ 25 s, 90–100 ≈ 40 s, and stay under ~120 words (~100 for Arabic and other non-Latin scripts) — the hard cap is 59.5 s of speech. Hook → one idea → one CTA.
5. For scenes, write concrete actions the same presenter can perform; follow the identity rules in P7. Use the user's real product/place photos as `scene_photos` (public https links — rule 9).
6. Optional: `plan_scenes` and show the scene lines; send approved lines back as `scene_lines`.
7. Show the full script + format for approval, then run the golden path from step 5.

Never claim facts were researched unless you actually checked a source. For medical, legal, financial or current-events claims, verify or ask the user for approved copy.

## Playbooks

Input URLs (selfies, samples, scene photos, frames, audio) must be **public https** URLs; private, link-local or metadata hosts are refused. All ids are scoped to the key's account — another account's id answers the same `404` as a missing one.

### P1 — Character (free)

```jsonc
// create_character — from 1–3 selfies (reproduces the person)
{ "name": "Omar",
  "selfie_image_urls": ["https://cdn.example.com/omar-1.jpg", "https://cdn.example.com/omar-2.jpg"],
  "edit_instructions": "professional attire, studio lighting" }

// create_character — from a description (invents a person)
{ "name": "Ava", "description": "a friendly presenter in her early 30s, warm smile",
  "reference_image_urls": ["https://cdn.example.com/mood.jpg"], "recast_attempt": 1 }

// → { character_id, name, mode: "photos"|"description", sheet_image_url, character_sheet_text, asset_id,
//     presenter_gender: "female"|"male"|"unknown",
//     head_covering: "none"|"hijab"|"niqab"|"headscarf"|"turban"|"kippah"|"unknown",
//     credits_charged: 0, warnings? }
```
- `name` required (≤120). Exactly one of `selfie_image_urls` (https; first 3 used) or `description` (≤2,000). `edit_instructions` ≤500 (longer is cut). `reference_image_urls` (≤3, description mode only) are style inspiration, never an identity. Disliked face → re-run with `recast_attempt` 1, 2, … for a different person.
- An https selfie/reference that cannot be loaded is skipped with a `FIELD_IGNORED` warning; if no selfie loads → `422`. Non-https URLs are dropped silently, and a selfie list with no https URL at all → `400`. Each video re-detects the head covering from the character image, so it is kept.
- **Regenerate the sheet** (same person, same `character_id`, **4 credits**): `regenerate_character` `{ "id": "CHARACTER_ID", "edit_instructions"?: "navy blazer" }` (≤500, else 400) → `{ character_id, sheet_image_url, asset_id, credits_charged }`; it falls back to the current sheet when the original photos can't be read; `422` only when neither can.
- Manage: `list_characters` (newest 100), `get_character` `{ "id" }`, `delete_character` `{ "id" }` → `{ "deleted": true }` (confirm which one with the user first).

> `sheet_image_url` is a multi-pose reference sheet. Show it to the user, but never pass it as `first_frame_url` — the video would animate the grid. Pass `character_id`; to control the opening look use P4.

### P2 — Voice

```jsonc
// list_voice_presets → { "voices": [ { "studio_voice": "Brian", "gender": "male", "languages": "multilingual" }, … ] }

// clone_voice — studio voice (free, multilingual)
{ "name": "Spanish narrator", "language": "spanish", "gender": "female", "studio_voice": "Sarah" }
// → { voice_id: "sv_…", name, kind: "library", language, credits_charged: 0, studio_voice, gender }

// clone_voice — clone a real voice (first clone per account free, later 30)
{ "name": "Ava voice", "sample_urls": ["https://cdn.example.com/ava-1.mp3"], "preview_language": "en" }
// → { voice_id: "pv_…", name, kind: "cloned", credits_charged, preview_url, warnings }
```
- Studio: send `language` and/or `studio_voice` (not `sample_urls`). Never send `language` with `sample_urls`: that is `400 "Provide exactly one voice source"`; for a clone in another language use `preview_language`. Male Brian, Daniel, George, Chris; female Sarah, Laura, Alice, Jessica. Without `studio_voice` one is picked from `gender` (default `female`). Unknown name → `400 INVALID_STUDIO_VOICE`. Cap 10 library voices.
- Clone: `name` ≤80; 1–25 public https `sample_urls` of clean speech (25 s+ total is best; only the first 25 URLs are used, non-https ones are dropped). The **first** clone per account is free, once ever (deleting it does not reset that); later clones 30. Tell the user "free if it is your first clone, otherwise 30": there is no `expected_credits` guard, and a second clone sent at the same time is charged 30 — read `credits_charged`. Under ~25 s of usable speech → warning `LOW_SAMPLE_AUDIO` (offer a re-clone). Play `preview_url` to the user. Cap 3 cloned voices.
- Clone errors: `400` + `sample_errors: [{index, reason}]` (no sample could be fetched), `400 INVALID_SAMPLES`, `422 NO_SPEECH` (refunded), `502 CLONE_UNAVAILABLE` (retry later, refunded), `409 VOICE_LIMIT_REACHED` (+`max_voices`; delete one), `409 FREE_CLONE_ATTEMPTS_EXHAUSTED` (free clone failed 20 times — fix the samples, ask Promoat support; don't retry).
- **Re-clone** (better samples, or revive an expired clone): `reclone_voice` `{ "id": "pv_…", "sample_urls": [...], "preview_language"?: "en" }` → `{ voice_id: "pv_NEW…", previous_voice_id, name, kind, credits_charged, preview_url, warnings }`. New id — the old one is removed; update your notes. 30 credits, or **0** if the old voice had expired. Studio voice → `400 NOT_A_CLONED_VOICE`.
- Manage: `list_voices` (newest 100: `voice_id, name, kind, language, created_at`), `delete_voice` `{ "id" }` → `{ "deleted": true }` (frees a slot; confirm which one with the user first).

### P3 — Text-to-speech (standalone audio)

```jsonc
// synthesize_speech
{ "voice_id": "VOICE_ID", "text": "Welcome back! Here is what is new this week.", "language": "en",
  "voice_settings": { "stability": 0.5, "similarity_boost": 0.75, "style": 0.3, "speed": 1.1 } }
// → { audio_url, duration_sec, asset_id, credits_charged, characters }
```
`text` ≤5,000 chars. `language` (name or ISO code; wins over the older `language_code`). Settings clamped: `speed` 0.7–1.2, others 0–1. **Price max(10, ceil(chars / 1,000) × 10)**. Unknown voice → `404`; expired/removed voice → `409 VOICE_UNAVAILABLE` with `voice_state` (re-clone, P2). For videos you do not need this: pass `voice_id` + `script` to `create_video`. A TTS asset can be reused as a fix-sound take (`tts_asset_id`).

### P4 — First-frame still (4 credits)

```jsonc
// create_first_frame
{ "character_id": "CHARACTER_ID", "kind": "talking_head",
  "scene_description": "behind the counter of a bright coffee shop, morning light" }
// → { image_url, asset_id, frame_id, kind, credits_charged: 4, warnings? }
```
- `kind`: `talking_head` (default) or `moving_scene` (the realistic photo a scenes video starts from).
- One of `scene_description` (≤2,000), `scene_prompt` (≤400) or `script` (≤4,000, context only) is required. `scene_photos` (≤3) are used for `talking_head` frames only. `language` optional.
- Pass `frame_id` to `estimate_video` / `create_video` as `first_frame_asset_id`: the look is locked and the video drops its own 4-credit frame line. The kind must match the video mode, else `400 FIRST_FRAME_KIND_MISMATCH`.
- Failure (refunded): `500` with `error_code` `FIRST_FRAME_NOT_VERTICAL` (retry), `CHARACTER_IMAGE_UNAVAILABLE` (regenerate the character), `PROVIDER_*` or `INTERNAL`.

### P5 — Talking-head video

```jsonc
// 1. estimate_video — the exact body you will queue
{ "mode": "talking_head",
  "character_id": "CHARACTER_ID",
  "voice_id": "VOICE_ID",
  "script": "Hi! Three quick updates from the shop this week. First, we extended our opening hours.",
  "video_idea": "standing in a bright modern kitchen, smiling at the camera",
  "resolution": "768P",
  "use_dynamic_captions": true,
  "captions_position": "bottom" }
// → { mode, credits_required, credits_balance, sufficient_credits, estimated_seconds, billed_seconds,
//     resolution, job_type, price_table_version, lines: [{kind, credits, …}], clips, breakdown, warnings }

// 2. Only after the user approves credits_required (say 151):
// create_video — the same body plus:
{ …, "expected_credits": 151, "idempotency_key": "promoat-20261019-1507-shop-updates-k3x9qa" }
// → { workflow_id: "partner_h3t_…", status: "queued", credits_reserved, credits_quoted, job_type,
//     resolution, price_table_version, warnings, duplicate: false }
```
- `character_id` required on `create_video` (the estimate prices without it and does not check ids, so `404` or `FIRST_FRAME_KIND_MISMATCH` for a bad `first_frame_asset_id` can first appear on `create_video`).
- Audio: exactly one of `voice_id` + `script` (≤4,000 chars, spoken verbatim) or `audio_url` (P6). Speech must be 1–59.5 s (`AUDIO_TOO_SHORT` / `AUDIO_TOO_LONG`); 1–5 s bills as 5.
- `video_idea` (≤2,000) is required unless a frame is given (`first_frame_asset_id` = a `talking_head` frame from P4, or `first_frame_url`; not both). `scene_prompt` (≤400) and `scene_photos` also shape the generated frame.
- `resolution`: `480P`, `768P` (default), `1080P` (any case); `720p` is served as 768P with `RESOLUTION_MAPPED`; anything else `400 INVALID_RESOLUTION`. `video_mode` / `voice_mode: "none"` are refused on talking heads.
- `voice_settings` (as P3), `language` (name or ISO code), `scene_lines` (from P8; 1–15 strings ≤600 chars). `topic` / `audience` are accepted (cut at 500) but have **no effect** (warning `FIELD_IGNORED`): put the brief in `video_idea` / `scene_prompt`, and don't promise the user they steer the video.
- Captions: `use_dynamic_captions: true` (+10) burns word-by-word captions on a solid band; `captions_position` `bottom` (default) | `center` | `top`; `captions_language` optional hint (`"en"`, `"ar"`). Pick a frame that leaves that area clear.
- `expected_credits`: whole number ≥0; a higher server quote → `409 QUOTE_MISMATCH` (+`credits_quoted`), nothing charged.
- Accepted but ignored (warning `FIELD_IGNORED`): `fast`, `narration_mode`, `lipsync`, `audio_duration`, `first_frame_title`, `topic`, `audience`; also a non-https `first_frame_url` / `audio_url` (a non-https `audio_url` with no other audio source is `400 INVALID_BODY` — fix the URL). Every talking head is lip-synced automatically, in windows of 5–14.5 s cut at natural pauses.

### P6 — From the user's own recording

Replace `voice_id` + `script` with `"audio_url": "https://cdn.example.com/narration.mp3"` (talking head or scenes). The length is probed server-side (`estimate_video` and `create_video`); a private or unsafe host is `400 INVALID_URL`, and `422 INVALID_URL` means it could not be read as audio. Same 1–59.5 s rule. Recording-voiced videos cannot use `edit-script` later (only fix-scene / fix-sound).

### P7 — Scenes video (the presenter acts the script out)

> **Identity rules for `video_idea` / `scene_prompt`** — state the presenter's gender and lock to one person: `one female barista, the same woman throughout; no other people; do not restyle or recast the presenter`. Describe the presenter *doing* things ("pours", "holds up the bag"), not a scene full of people.

```jsonc
// estimate_video → confirm → create_video with expected_credits + idempotency_key  (workflow_id partner_h3v_…)
{ "mode": "scenes",
  "character_id": "CHARACTER_ID",
  "voice_id": "VOICE_ID",
  "script": "Ever wondered how we roast our beans? Come on, I will show you. This is where every batch starts.",
  "scene_lines": ["Ever wondered how we roast our beans?", "Come on, I will show you.", "This is where every batch starts."],
  "video_idea": "one female barista, the same woman throughout, touring a small roastery. Single presenter only.",
  "scene_prompt": "warm industrial roastery, morning light, sacks of green coffee",
  "video_mode": "reference",
  "resolution": "768P",
  "scene_photos": [
    { "url": "https://cdn.example.com/retail-bag.jpg", "role": "product", "caption": "our 250g retail bag" },
    { "url": "https://cdn.example.com/storefront.jpg", "role": "setting", "caption": "the shop exterior" }
  ],
  "language": "english" }
```
- `mode`: `scenes` (alias `moving_scene`). Audio: `voice_id` + `script`, or `audio_url`, or none with `voice_mode: "none"`.
- `video_mode`: `reference` (default; the presenter's realistic photo + up to 3 scene photos; voiced clips are spoken on camera) or `text` (half price; scene photos and frames are ignored with `FIELD_IGNORED`).
- `voice_mode: "none"` (silent): `target_seconds` 5–60 required, as a JSON **number** (`"15"` → `400 INVALID_DURATION`); the brief is `script`, else `scene_lines`, else `video_idea` (one is required, `INVALID_SCRIPT`); `audio_url` is refused (`400 INVALID_BODY`), `voice_id` ignored (`FIELD_IGNORED`).
- `scene_photos`: `[{ url, role?: "setting"|"product"|"prop", caption? ≤200 }]`. First 3 unique URLs are used (`SCENE_PHOTOS_TRUNCATED`); more than 12 items or a malformed item → `400 INVALID_SCENE_PHOTOS`. A photo that cannot be fetched at render time is dropped, the charge is re-quoted without it (never above the reservation), and the job carries `SCENE_PHOTO_DROPPED` in `list_jobs` → `metadata.warnings`.
- `first_frame_asset_id`: a `moving_scene` frame (P4) — a talking-head frame → `400 FIRST_FRAME_KIND_MISMATCH`. Or `first_frame_url`. Either drops the 4-credit photo line; otherwise the job makes the photo.
- `scene_prompt` (≤400), `scene_lines`, `language`, `voice_settings`, `resolution` as in P5. `use_dynamic_captions` has no effect on scenes (no warning).

### P8 — Scene plan (free, instant)

```jsonc
// plan_scenes
{ "video_type": "scenes", "script": "Ever wondered how we roast our beans? ..." }
// → { "scenes": [ { "index": 0, "line": "…", "seconds": 4.2 }, … ], "max_words_per_scene": 33 }
```
`video_type`: `talking_head` | `scenes` | `moving_scene` | `normal_video` (the last two are aliases of `scenes`). `script` 1–4,000 chars. Optional `audio_duration_seconds` (≤60.5; required and 5–60 with `voice_mode: "none"`), `voice_mode`. `max_words_per_scene` is 32 for talking heads, 33 for scenes. Errors: `400 INVALID_BODY | INVALID_SCRIPT | INVALID_DURATION | INVALID_VOICE_MODE`.

### P9 — Edits

All three (`fix_scene`, `edit_script`, `fix_sound`) take `workflowId` = the source video; the source must be a `completed` video whose status `result.editable` is `true` (an edit's output can be edited again). fix-scene and edit-script refuse body fields beyond those listed (`400 INVALID_BODY`); **`fix_sound` silently ignores unknown fields**, so check the spelling of `expected_credits` / `dry_run` (a typo there reads as missing → `409 QUOTE_MISMATCH`). `idempotency_key` (or body `client_request_id`, a UUID) is **required** unless `dry_run: true` (`400 IDEMPOTENCY_KEY_REQUIRED`); edit keys are per account and endpoint, not per source video (one fix-scene key on two videos → `409 IDEMPOTENCY_KEY_REUSED`). Edits count toward the 5 active jobs; one open edit per source video (`409 EDIT_IN_PROGRESS`; an edit with no activity for 30 min no longer blocks).

```jsonc
// get_scenes (free)
{ "workflowId": "partner_h3t_…" }
// → { workflow_id, video_type: "talking_head"|"moving_scene", resolution, editable,
//     voice: { source: "ai_voice"|"recording"|"none" }, poster_url?,
//     scenes: [ { index, line, seconds, start_seconds, talks, clip_url?, poster_url? } ], source_workflow_id? }

// fix_scene — 1. quote
{ "workflowId": "partner_h3t_…", "scene_index": 2, "description": "hold the bag closer to the camera", "dry_run": true }
// → { dry_run: true, credits_quoted, credits_required, credits_balance, sufficient_credits, lines, clips,
//     source_workflow_id, scene_indices, edit_kind, price_table_version }

// fix_scene — 2. only after the user approves credits_quoted (say 68)
{ "workflowId": "partner_h3t_…", "scene_index": 2, "description": "hold the bag closer to the camera",
  "expected_credits": 68, "idempotency_key": "promoat-20261019-1530-fix-scene2-p7m2wd" }
// → { workflow_id: "partner_se_…", status: "queued", credits_reserved, credits_quoted, job_type: "scene_edit_video",
//     source_workflow_id, scene_indices, edit_kind, price_table_version, duplicate: false }
```
- **fix-scene** `{ scene_index (0–99), description? ≤500 }`. Talking head: no description = a new take (`new_take`); with description = a new frame for that scene (`new_frame`, +4). Scenes: `description` required (`visual_fix`, else `400 FIX_TEXT_REQUIRED`). An index the video doesn't have → `400 INVALID_SCENE`.
- **edit-script** `{ lines: [{ scene_index, line ≤600 chars }] }` (1–20) — spoken in the video's own AI voice (`edit_kind: "edit_script"`). Only changed lines are re-made (each +TTS); nothing changed → `400 NO_CHANGES`. A line longer than one scene → `400 LINE_TOO_LONG` with `max_words` (32 talking head, 33 scenes; rarely sent without `max_words`). Empty line → `400 EMPTY_LINE`; unknown/duplicate index → `400 INVALID_SCENE`. Videos voiced by a recording, silent, or already sound-fixed → `400 VOICE_EDIT_UNAVAILABLE` (use fix-sound).
- **fix-sound** — exactly one take: `{ "audio_url" }`, `{ "tts_asset_id" }` (your own P3 asset), or `{ "voice_id", "script" ≤4,000, "voice_settings"?, "language"? }`.
  - dry run → `{ dry_run, source_workflow_id, plan: "swap_audio"|"regenerate", credits_quoted, lines, video_ms, price_table_version }`; run → `{ workflow_id: "partner_fs_…", status, plan, credits_reserved, credits_quoted, source_workflow_id, job_type: "fix_sound_video", price_table_version, duplicate }`.
  - `swap_audio` (**free**): a scenes video with no on-camera talking whose new recording is within ±300 ms of the video length — the sound is replaced.
  - `regenerate` (paid, needs `expected_credits`): every talking head, any scenes video with on-camera talking, any other length — remade at the take's length, reusing the frame/photo (no 4-credit line). A `voice_id` + `script` take is always quoted as `regenerate` (+TTS); the job may still swap and charge less.
  - Take too short (under 1 s or under 40% of the video) → `400 TAKE_TOO_SHORT`; over 59.5 s → `400 TAKE_TOO_LONG` (both with `video_ms`); private host → `400 INVALID_URL`; unreadable → `422 INVALID_URL`; unknown `tts_asset_id` / `voice_id` → `404` (+`field`).
- Edit errors also: `404 NOT_FOUND`, `409 VIDEO_NOT_READY`, `409 VIDEO_NOT_EDITABLE` (made before 1.1.0 or without scene data), `409 QUOTE_MISMATCH` (+`credits_quoted`; fix-sound adds `plan`), `409 IDEMPOTENCY_KEY_REUSED`, `402`, `429`, `503 TRY_AGAIN`, `500 START_FAILED | INTERNAL` (refunded). Edit error bodies carry the code in both `error` and `error_code`, plus a `message`.

### P10 — Account, history, assets (all free)

```jsonc
// get_balance
{ "from": "2026-10-01T00:00:00Z", "to": "2026-10-03T00:00:00Z" }
// → { credits_balance, credits_balance_base, credits_spent_lifetime, credits_consumed_in_range,
//     job_counts: { completed, failed, running_or_queued, total_in_range }, from, to }   (default range: this UTC month)
//   credits_spent_lifetime = spend since the LAST TOP-UP (it resets at each top-up), not all-time spend

// list_jobs { "limit": 30, "offset": 0 }
// → { jobs: [ { workflow_id, status, job_type, credits_estimated, credits_actual, queued_at, completed_at, error_message, metadata } ] }

// list_assets { "kind": "video", "limit": 30, "offset": 0 }      get_asset { "id": "ASSET_ID" } for one
// → { assets: [ { asset_id, kind, url, workflow_id, character_id, voice_id, metadata, created_at } ] }
```
Lists are newest first; `limit` default 30, values over 100 are capped at 100. `list_jobs` also lists non-video rows (`job_type` `character_sheet`, `tts`, `voice_clone`, `first_frame_image`, `voice_library`). Asset `kind`: `character_sheet | first_frame | tts_audio | video` (other values → 400). Video asset metadata may include `poster_url, duration_sec, resolution, video_type, video_mode, voice_mode, scene_count, source_workflow_id, edit_kind, price_table_version`; character sheets `mode, presenter_gender, head_covering`; first frames `video_type, head_covering`.

## Polling

The loop, with the `get_job` tool:

1. Right after queueing, tell the user what to expect: "Queued — a talking head takes about 10 minutes, a scenes video about 25. I'll keep checking and tell you when it's ready."
2. Call `get_job` with `{ "workflowId": "…" }`.
3. `queued` / `running` → wait ~20 s, then call `get_job` again. Repeat on your own, **in the same turn**, without waiting for the user to ask. Do not end your turn here (rule 17).
4. `completed` or `failed` → stop and deliver (below).

How to wait between calls: do it inside the tools, never through the user.
   1. If `get_job` accepts a wait/pause argument (for example `wait_seconds`), use it, ~10–20 s per call.
   2. Otherwise just call `get_job` again; each call is an ordinary tool call and needs nothing from the user.
   3. Never use a shell, script or code runner to pause or poll (no `sleep`, `curl`, Python), and never ask the user to run, click or approve anything so that polling can continue.

A few extra checks are fine; slowing to "once a minute", promising to check later, or ending your turn is not. No pause method ever justifies stopping the loop.

Keep your updates short: mention `phase` / `progress` only when they change (for example "generating — 40%"), not after every call.

- **Fields**: `workflow_id, status (queued|running|completed|failed), job_type (talking_head_video | multi_scene_video | scene_edit_video | fix_sound_video), phase (queued → preparing → generating → assembling → finalizing → completed|failed), progress (0–100|null), video_url, image_url, poster_url, source_workflow_id, credits_estimated, credits_actual, credits_consumed, error_code, error_message, result, queued_at, completed_at`. On completion `result` may hold `video_url`, `asset_id`, `poster_url`, `editable` and, only when editable, `scenes_url` — use `get_scenes` with the same `workflowId` rather than that path.
- **Interval**: ~20 s throughout.
- **Expect**: talking head ~10 min, scenes ~25 min; edits like their source type; a free sound swap is quick. Past that, keep polling and tell the user it is slow — do not re-queue. A job with no progress for **75 minutes** is failed with `STALE_TIMEOUT` and refunded automatically.
- **`completed`** (terminal): deliver `video_url` (+`poster_url`), `credits_consumed` (≤ the reservation; script jobs often get a refund), and warnings (the job's `list_jobs` row → `metadata.warnings`). Offer edits if `result.editable`.
- **`failed`** (terminal): the reservation is refunded once, automatically (`credits_consumed` 0, or a recorded partial charge). Show `error_message` (user-safe) and act on `error_code` below.
- `404 {"error":"Job not found", "error_code":"NOT_FOUND", …}`: wrong id or another account's job — recover it from `list_jobs`.

### Job failure codes

| `error_code` | Do this |
|---|---|
| `PROVIDER_MODERATION` | Content refused. Rephrase `video_idea` / `scene_prompt` / fix `description`, or use other photos; don't resend the same body |
| `PROVIDER_INPUT` | A photo or audio file could not be used. Replace it (or regenerate the character) and re-queue |
| `PROVIDER_INFRA`, `PROVIDER_TIMEOUT`, `START_FAILED`, `INTERNAL`, `STALE_TIMEOUT` | Transient. Re-queue **once** with a **new** key (after re-confirming the price); if it fails again, stop and report |
| `LINE_TOO_LONG` | Shorten the offending line(s) to ≤ `max_words_per_scene` (P8) and re-queue |
| `VOICE_UNAVAILABLE` | Voice expired/removed: `reclone_voice` (free if expired) or pick another voice; re-queue with the new id |
| `FIX_NOT_APPLIED` | The edit could not be applied: reword the fix `description` and retry |
| `MISSING_ASSET` | Something the job needed is gone (e.g. the source video): make the video again with `create_video` |
| `AUDIO_TOO_LONG` | The real speech ran over 59.5 s: shorten the script and re-queue |

## Idempotency

**Making a key.** The tools don't make keys for you, so you make one per intended job. Any 1–255 visible ASCII characters work; it only has to be new for that job. Build it from the time, a short label, and random characters you choose fresh each time:

`promoat-<YYYYMMDD>-<HHMM>-<short label>-<6+ random lowercase letters/digits>` → `promoat-20261019-1507-summer-menu-k3x9qa`

Don't reuse the example keys in this file, and don't reuse a key from an earlier job. If you have a shell, `uuidgen` or `python3 -c "import uuid; print(uuid.uuid4())"` is also fine. Write the key down next to the job: a retry of **that** job must send the **same** key.

- `idempotency_key` (tool argument, sent as the `Idempotency-Key` header) or body `client_request_id` (a UUID). Both sent and different → `400 IDEMPOTENCY_KEY_MISMATCH`; malformed → `400 IDEMPOTENCY_KEY_INVALID`. Prefer `idempotency_key`.
- Optional on `create_video`, required on `fix_scene` / `edit_script` / `fix_sound` (except `dry_run`).
- Same key + same body → `200 { workflow_id, status, duplicate: true, credits_reserved }` — the original job, never a second charge (whatever its status). On `create_video` validation and the price check run first, so a retry can get `409 QUOTE_MISMATCH` or `404`/`422` instead (see rule 11); edits answer the duplicate first.
- Same key + different body → `409 IDEMPOTENCY_KEY_REUSED`. The comparison is over the validated request: `expected_credits`, warnings and ignored legacy fields don't count, and `"720p"` equals `"768P"`.
- One key covers all `create_video` modes (a talking-head and then a scenes body under one key → 409). Keys are per account and per endpoint (a `create_video` key never collides with a `fix_scene` key).
- A `402`, `429` or `409 QUOTE_MISMATCH` creates no job: after topping up / waiting / re-confirming, the same key is still usable.

## Pricing

Price table **2026-09-30** (`price_table_version` in responses). A deployment may add a markup, so the estimate / `dry_run` is the number to quote — never this table.

**Internal reference only.** Use these numbers to plan (for example to suggest a cheaper option before estimating). Never show them to the user as prices, never compare a live quote with them, and never mention this table or this file (rules 18–19).

| Item | Credits |
|---|---|
| Character create · studio voice · scene plan · estimate · reads | 0 |
| Character regenerate · first frame / realistic photo | 4 |
| TTS | max(10, ceil(chars / 1,000) × 10) — 600 chars = 10, 1,001 = 20 |
| Voice clone | first per account 0, then 30 · re-clone 30 (0 if expired) |
| Dynamic captions (talking head) | 10 |
| Transcription line (voiced videos) | ceil(seconds / 20) |

**Generation, credits per second** (talking head billed on whole seconds; scenes on whole 5–15 s clips)

| Resolution | Talking head | Scenes reference | Scenes text |
|---|---|---|---|
| 480P | 5 | 5 | 2.5 |
| 768P | 8 | 8 | 4 |
| 1080P | 16 | 16 | 8 |

Quote `lines[].kind`: `generation`, `first_frame` (dropped with your own frame), `reference_allowance` (scenes reference mode: grows with scene photos and voiced clip length), `transcription` (not on silent videos), `tts` (script mode), `captions`, `product` (a fix-sound swap, 0).

**Worked examples** (768P, own audio unless noted)

| Video | Credits |
|---|---|
| 15 s talking head | 125 (120 + frame 4 + transcription 1) |
| 15 s talking head, own frame | 121 |
| 15 s talking head + captions | 135 |
| 15 s talking head at 480P / 1080P | 80 / 245 |
| 5 s talking head at 480P | 30 |
| 59.5 s talking head | 487 |
| ~35-word script (≈17 s quoted) talking head | 151 (incl. TTS 10) |
| 15 s scenes, reference, 0 / 2 / 3 photos | 125 / 131 / 135 |
| 15 s scenes, text mode | 61 |
| 15 s silent scenes, reference / text | 124 / 60 |
| Fix-scene, 8 s talking-head scene: new take / new frame | 64 / 68 |
| Fix-sound, new 15 s recording on a talking head | 121 |
| Fix-sound swap on a scenes video (fits ±300 ms) | 0 |

**Charging**: the quote is reserved when the job starts and is a ceiling; the final charge is min(actual, reserved) and the rest is refunded on completion. Failures refund once, automatically. Instant endpoints (characters, regenerate, voices, TTS, first frame) charge once, return `credits_charged`, and refund on failure. Nothing is charged for a request that fails validation, auth or the balance check.

## Limits

| Limit | Value | Signal |
|---|---|---|
| Active video jobs + edits (queued + running) | 5 | `429 TOO_MANY_ACTIVE_JOBS` (+`max_active_jobs`) |
| Cloned voices / library voices | 3 / 10 | `409 VOICE_LIMIT_REACHED` (+`max_voices`) |
| Voiced video audio | 1–59.5 s (1–5 s bills as 5) | `400 AUDIO_TOO_SHORT` / `AUDIO_TOO_LONG` |
| Silent scenes `target_seconds` | 5–60 s | `400 INVALID_DURATION` |
| Video / fix-sound script | 4,000 chars | `400 INVALID_SCRIPT` |
| `video_idea` · `scene_prompt` · `topic`/`audience` | 2,000 · 400 · 500 (cut; no effect) chars | `400 INVALID_BODY` · `FIELD_IGNORED` |
| `scene_lines` | 1–15, each ≤600 chars | `400 INVALID_SCENE_LINES` |
| Scene photos | 3 used, ≤12 sent, caption ≤200 | `SCENE_PHOTOS_TRUNCATED` / `400 INVALID_SCENE_PHOTOS` |
| TTS text | 5,000 chars | `400` |
| Selfies / reference images | first 3 used | extras ignored |
| Voice samples per clone | 1–25 (extra URLs ignored; non-https dropped) | `400` when none is usable |
| Edit lines | 1–20, each ≤600 chars; scene index 0–99 | `400 INVALID_BODY` |
| Open edits per source video | 1 (an edit idle for 30 min no longer blocks) | `409 EDIT_IN_PROGRESS` |
| Quiet job | 75 min | failed `STALE_TIMEOUT`, refunded |
| List page | `limit` ≤100 (capped) | — |

## Errors

```json
{ "error": "…", "error_code": "UPPER_SNAKE", "message": "human-readable", "field": "resolution" }
```
Every error body carries `error`, `error_code` (UPPER_SNAKE) and `message` (since 1.1.1) — **branch on `error_code`** and the HTTP status. `error` is kept for older integrations: it may be an older sentence (`resolution must be "480p" or "720p"`, `"name is required (max 120 chars)"`, `Unauthorized`) or the code itself. Some bodies also carry a lowercase `code` (e.g. `quote_mismatch`, `no_speech`); ignore it. Extra details: `field`, `credits_required`, `credits_balance`, `credits_quoted`, `plan`, `max_active_jobs`, `max_voices`, `max_words`, `video_ms`, `voice_state`, `sample_errors`.

| Status | Code | Do this |
|---|---|---|
| 400 | `INVALID_BODY`, `INVALID_RESOLUTION`, `INVALID_VIDEO_MODE`, `INVALID_VOICE_MODE`, `INVALID_DURATION`, `INVALID_SCRIPT`, `INVALID_SCENE_LINES`, `INVALID_SCENE_PHOTOS`, `INVALID_VOICE_SETTINGS`, `INVALID_STUDIO_VOICE`, `NOT_A_CLONED_VOICE`, `INVALID_SAMPLES` | Fix the named `field` and resend (no charge happened) |
| 400 | `INVALID_URL` | Use a public https URL (not localhost/private/link-local) |
| 400 | `AUDIO_TOO_SHORT` / `AUDIO_TOO_LONG` | Speech must be 1–59.5 s: lengthen or shorten the script/recording |
| 400 | `FIRST_FRAME_KIND_MISMATCH` | Make a frame with the matching `kind` (P4) |
| 400 | `IDEMPOTENCY_KEY_REQUIRED` / `_INVALID` / `_MISMATCH` | Add a key / send 1–255 visible ASCII (or a UUID body id) / make header and body agree |
| 400 | `FIX_TEXT_REQUIRED`, `INVALID_SCENE`, `NO_CHANGES`, `EMPTY_LINE`, `LINE_TOO_LONG` (+`max_words`), `VOICE_EDIT_UNAVAILABLE` | Fix the edit request (P9); for a recording-voiced video use fix-sound |
| 400 | `TAKE_TOO_SHORT` / `TAKE_TOO_LONG` (+`video_ms`) | Record a take between 40% of the video length (≥1 s) and 59.5 s |
| 401 | `UNAUTHORIZED` (`error`: `Missing Authorization Bearer token` / `Unauthorized`) | `PROMOAT_KEY` is unset, wrong or truncated: ask the user to fix it and restart the app (rule 1), then test with `get_balance`. Never ask for the key in chat |
| 402 | `INSUFFICIENT_CREDITS` (+`credits_required`, `credits_balance`) | Tell the user the gap; dashboard → Buy credits (rule 8); then resend (same key OK). Don't loop |
| 404 | `NOT_FOUND` (`error`: `NOT_FOUND`, `Not found` or `Job not found`; +`field`) | Id is wrong or not this account's; find it with the `list_*` tools |
| 409 | `QUOTE_MISMATCH` (+`credits_quoted`) | Price went up (different body or a price change): show the new price, get a yes, resend with the new `expected_credits` |
| 409 | `IDEMPOTENCY_KEY_REUSED` | You changed the body under an old key: use a new key for a new job |
| 409 | `VOICE_LIMIT_REACHED` (+`max_voices`) | Delete an unused voice of that kind, then retry |
| 409 | `FREE_CLONE_ATTEMPTS_EXHAUSTED` | Stop retrying; fix the samples and contact support |
| 409 | `VOICE_UNAVAILABLE` (+`voice_state`) | Re-clone (P2) or pick another voice |
| 409 | `VIDEO_NOT_READY` | Wait until the source job is `completed` |
| 409 | `VIDEO_NOT_EDITABLE` | Can't edit this video (older engine / no scene data): make a new one |
| 409 | `EDIT_IN_PROGRESS` | Wait for the open edit of this video to finish |
| 422 | `INVALID_URL` (audio could not be probed / take unreadable), `NO_SPEECH`, selfies unloadable, regenerate photos unreadable | Supply reachable public https media with real content (clear speech for clones) |
| 429 | `TOO_MANY_ACTIVE_JOBS` (+`max_active_jobs`) | Wait for a job to finish (keep polling), then resend with the same key |
| 500 | `START_FAILED` / `INTERNAL` (on `/videos` `error` is `Failed to start workflow` / `Failed to queue job`) | Refunded. Resend once; if the answer is a duplicate with `status: "failed"`, use a new key |
| 500 | `First-frame generation failed` + `error_code` | Refunded. `FIRST_FRAME_NOT_VERTICAL`/`PROVIDER_*`: retry once; `CHARACTER_IMAGE_UNAVAILABLE`: regenerate the character |
| 500 | `INTERNAL` (e.g. `Character generation failed`, `TTS synthesis failed`, `Voice clone failed`, `Failed to list voices`, `Database error`) | Refunded if anything was charged. Retry once, then report |
| 502 | `CLONE_UNAVAILABLE` | Cloning is briefly unavailable: retry in a few minutes (refunded) |
| 503 | `TRY_AGAIN` | Nothing charged: retry after a few seconds with the same key (up to ~3 times) |

**Warnings** (`warnings: [{ field, code, message }]` on a 200): `RESOLUTION_MAPPED` (720p served as 768P), `FIELD_IGNORED` (legacy or non-applicable field, `topic`/`audience`, non-https URL, unloadable selfie, photos/frame in text mode, scene photos on a `moving_scene` frame, `voice_id` on a silent video, `target_seconds` without `voice_mode: "none"`, a non-string `video_idea`), `SCENE_PHOTOS_TRUNCATED` (only 3 kept), `LOW_SAMPLE_AUDIO` (clone from <25 s of speech). Job-time: `SCENE_PHOTO_DROPPED` on the job's `list_jobs` row. Always relay them.

## Troubleshooting

- **Quote too high** → read `lines`: drop to 480P, shorten the script, skip captions, use your own approved frame, or scenes `video_mode: "text"`.
- **User dislikes the face** → description mode: bump `recast_attempt`; selfie mode: better-lit selfies or `regenerate` with `edit_instructions`.
- **Wrong language/accent** → set `language` on the video / TTS; studio voices are multilingual and free.
- **`404` on a voice just used** → re-clones get a new id; check `list_voices`.
- **One scene is wrong** → `fix-scene`, not a whole new video.
- **Want another take of the same video** → `create_video` again with a **new** key (each job is an independent generation); vary `video_idea` for a different setting.
- **Ids from before 1.1.0** keep working; videos made before 1.1.0 can't be edited.


## Without the MCP tools (raw HTTP)

Use this only when the user **explicitly** asks for raw HTTP — for example they want `curl` commands or code for their own server — and has set `PROMOAT_KEY` themselves. Missing tools in a chat are not a reason to come here: follow rule 1 instead. Everything above still applies; only the transport changes.

- Base URL `https://platform.promoat.ai`; API root `{BASE}/api/partner/v1/`. JSON in, JSON out. The live API does not serve MCP — the plugin's MCP server is `https://promoat-platform-plugins.vercel.app/mcp`.
- Auth: `Authorization: Bearer $PROMOAT_KEY` on every request. Read the key only from the environment variable `PROMOAT_KEY`. If it is not set, don't ask for the key in chat and don't search for it: tell the user to set it (rule 1), then continue. Key format `pmat_<12 hex>_<48 hex>`; the whole string is the credential. It is a server-side key that spends prepaid credits: never put it in frontend, mobile or shared code.
- Each tool maps to one endpoint (see the [Tools](#tools) table). The tool's arguments are the request body; `workflowId` / `id` go in the path; `idempotency_key` becomes the `Idempotency-Key` header; list/balance arguments become query parameters.
- Spec, docs, playground: `{BASE}/openapi.yaml` · `{BASE}/docs` · `{BASE}/docs/playground`.

```bash
BASE="https://platform.promoat.ai"
# Estimate, then queue only after the user approves the number
EST=$(curl -s -X POST "$BASE/api/partner/v1/videos/estimate" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" -d "$BODY")
QUOTE=$(echo "$EST" | jq -r .credits_required)
KEY=$(uuidgen)   # save it with the job; reuse it for retries of THIS job only
curl -s -X POST "$BASE/api/partner/v1/videos" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" -H "Idempotency-Key: $KEY" \
  -d "$(echo "$BODY" | jq --argjson q "$QUOTE" '. + {expected_credits: $q}')"

# Poll
curl -s "$BASE/api/partner/v1/jobs/$WORKFLOW_ID/status" -H "Authorization: Bearer $PROMOAT_KEY"
```
