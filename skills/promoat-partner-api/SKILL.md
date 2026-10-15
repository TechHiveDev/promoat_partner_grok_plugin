---
name: promoat-partner-api
description: Operate the Promoat Partner API end to end — make AI presenter (UGC-style) vertical videos from a script or recording, create presenter characters from selfies or a description, pick a free studio voice or clone one, synthesize speech, generate first-frame stills, and edit finished videos (redo a scene, rewrite lines, replace the sound) — always quoting credits before spending, with idempotent retries and job polling. Use whenever the user wants a Promoat / presenter / talking-head / multi-scene marketing video, mentions their Promoat partner API key, credits, balance, top-up, job or workflow status, or any /api/partner/v1 endpoint.
version: 1.1.1
---

# Promoat Partner API — agent operating manual

The **Promoat Partner API** turns a script (or a recording) into a finished vertical 9:16 marketing video fronted by an AI presenter. This file is the agent's source of truth: golden path, rules, decision table, every endpoint, price, limit and error. When the live API disagrees with this file, trust the API response and tell the user.

## Quick facts

| Fact | Value |
|---|---|
| Base URL | `https://platform.promoat.ai` (override with env `PROMOAT_BASE_URL` if the user gives another deployment) |
| API root | `{BASE}/api/partner/v1/` |
| Auth | `Authorization: Bearer $PROMOAT_KEY` on every request |
| Key format | `pmat_<12 hex>_<48 hex>` — the whole string is the credential |
| Format | JSON in, JSON out. Plain `curl`/`fetch`, no SDK |
| Async | Videos and edits return a `workflow_id`; **poll** `GET /jobs/{workflow_id}/status`. No webhooks |
| Output | Always vertical 9:16; default resolution **768P** |
| Money | 1 credit = $0.01 of usage. Quotes are a hard ceiling: you are charged min(actual, reserved) |
| Docs · playground · spec | `{BASE}/docs` · `{BASE}/docs/playground` · `{BASE}/openapi.yaml` |
| Dashboard | `{BASE}/partner` (sign in `{BASE}/sign-in`, new account `{BASE}/sign-up`) |

```bash
BASE="${PROMOAT_BASE_URL:-https://platform.promoat.ai}"
# PROMOAT_KEY comes from the environment — see the key rules below. Never inline it.
```

## MCP

When the Promoat MCP server is connected, call its tools instead of raw HTTP. The spend, idempotency, and polling rules in this file still apply. A tool result is the API's JSON, including `error_code` and `message` when the call fails.

Connect to `https://promoat-platform-plugins.vercel.app/mcp` with header `Authorization: Bearer $PROMOAT_KEY` (the same key as below). Do not paste the key into chat. `{BASE}` is the live API, which does not serve MCP.

| Tool | API |
|---|---|
| `get_balance` | `GET /usage/summary` |
| `create_character` | `POST /characters` |
| `list_voices` | `GET /voices` |
| `clone_voice` | `POST /voices` |
| `estimate_video` | `POST /videos/estimate` |
| `create_video` | `POST /videos` |
| `get_job` | `GET /jobs/{workflow_id}/status` |
| `get_scenes` | `GET /videos/{workflow_id}/scenes` |
| `fix_scene` | `POST /videos/{workflow_id}/fix-scene` |
| `edit_script` | `POST /videos/{workflow_id}/edit-script` |
| `fix_sound` | `POST /videos/{workflow_id}/fix-sound` |
| `list_characters` | `GET /characters` |
| `get_character` | `GET /characters/{id}` |
| `delete_character` | `DELETE /characters/{id}` |
| `regenerate_character` | `POST /characters/{id}/regenerate` |
| `list_voice_presets` | `GET /voices/presets` |
| `delete_voice` | `DELETE /voices/{id}` |
| `reclone_voice` | `POST /voices/{id}/reclone` |
| `synthesize_speech` | `POST /tts` |
| `create_first_frame` | `POST /images/first-frame` |
| `plan_scenes` | `POST /videos/scene-plan` |
| `list_assets` | `GET /assets` |
| `get_asset` | `GET /assets/{id}` |
| `list_jobs` | `GET /usage/jobs` |
| `create_checkout_session` | `POST /billing/checkout-session` |

`create_video`, `fix_scene`, `edit_script`, and `fix_sound` take `idempotency_key`, sent as the `Idempotency-Key` header. `client_request_id` still belongs in the body.

## Golden path

**Make a video**
1. **Key check** — `GET /usage/summary` (free). `401` → the key is wrong; stop and fix it. Note `credits_balance`.
2. **Character** — reuse an existing `character_id` (`GET /characters`) or create one (`POST /characters`, free). Show `sheet_image_url` and get the user's OK on the look.
3. **Voice** — reuse a `voice_id` (`GET /voices`), add a free studio voice, or clone the user's voice (first clone free, then 30). Skip if the user supplies their own audio (`audio_url`) or wants a silent video.
4. **Script & format** — agree the script and pick the mode with the [decision table](#choosing-the-request). Optional: `POST /videos/scene-plan` (free) to preview the scenes.
5. **Estimate** — `POST /videos/estimate` with the exact body you will send (free). Read `credits_required`, `sufficient_credits`, `lines`, `warnings`.
6. **Confirm the price with the user** — "This will cost N credits (balance B). Go?" Wait for a yes unless the user pre-approved a budget that covers N. If `sufficient_credits` is false, stop and send them to top up.
7. **Queue** — `POST /videos`, same body + `"expected_credits": N`, with a fresh `Idempotency-Key` header. Save `workflow_id` and the key.
8. **Poll** — `GET /jobs/{workflow_id}/status` every 8–10 s until `completed` or `failed` ([polling](#polling)).
9. **Deliver** — hand over `video_url` (and `poster_url`), `credits_consumed`, and any warnings. On `failed`, act on `error_code` ([job failures](#job-failure-codes)).

**Edit a finished video** (each edit makes a NEW video; the source stays as the undo)
1. `GET /videos/{workflow_id}/scenes` — show the user the numbered scenes and their lines.
2. Pick the edit: one scene looks wrong → `fix-scene`; change words → `edit-script`; new voice-over / recording → `fix-sound`.
3. Send it with `"dry_run": true` (no key needed, nothing charged) → show `credits_quoted` (and the fix-sound `plan`) → get a yes.
4. Send the same body without `dry_run`, plus `"expected_credits": N` and a fresh `Idempotency-Key` → poll the new `workflow_id` → deliver.

## Hard rules

**Key handling**
1. Read the key from `PROMOAT_KEY` (or a gitignored `.env`). If it is not set, do NOT ask the user to paste it into chat (chats are logged and synced): tell them to run `export PROMOAT_KEY="pmat_..."` in their shell, then continue.
2. Never print, echo, log or commit the key; redact it to `pmat_…` in anything you show. Never write it into source files, scripts or docs.
3. If the user pastes a key into chat anyway, use it for this session and recommend they get it replaced: there is no self-serve rotation for current keys, so they ask Promoat support (the dashboard has no support link; the dashboard's **Replace with new encrypted key** button exists only for older keys stored without an encrypted copy).
4. It is a server-side key that spends prepaid credits: never put it in frontend, mobile or shared code.

**Spend safety**
5. Never call a paid endpoint without telling the user the price first. Videos: `POST /videos/estimate`. Edits: `dry_run: true`. Fixed prices (first frame 4, regenerate 4, TTS, clone 0 or 30) come from the [price list](#pricing). Instant endpoints have no `expected_credits` guard: check `credits_charged` in the answer.
6. Always send `expected_credits` = the price the user approved. If the server would charge more, it refuses with `409 QUOTE_MISMATCH` and charges nothing. A paid fix-sound **requires** it (missing = treated as 0 → 409).
7. Never loop on `402` or `409`. `402 INSUFFICIENT_CREDITS`: report `credits_required` vs `credits_balance` and send the user to the dashboard's **Buy credits**. `409`: read the code, re-quote or fix, and ask the user again.
8. Never re-queue a video while the original is still `queued`/`running` — that pays twice.

**Retries and idempotency**
9. Send an `Idempotency-Key` header on every `POST /videos` and every edit (edits require it). Use a new UUID per intended job and keep it in your notes.
10. Timeout, network error or `503 TRY_AGAIN` → resend the **identical** request with the **same** key: you get the original job (`"duplicate": true`) and nothing is charged twice. On `POST /videos` the body is re-validated and re-priced **before** the duplicate lookup, so a retry can instead get `409 QUOTE_MISMATCH` (the price rose: re-confirm, resend with the new `expected_credits` under the same key) or `404`/`422` (a referenced character, voice or recording is gone). Edits answer the duplicate first. Without a key, never blind-retry a `POST /videos` — check `GET /usage/jobs?limit=5` first.
11. A key is bound to its first job forever, even a failed one: a duplicate answer whose `status` is `failed` means "refunded, start over" — use a **new** key for the new attempt.
12. GETs are always safe to retry.

**Bookkeeping**
13. Record every id the API returns (`character_id`, `voice_id`, `workflow_id`, `asset_id`/`frame_id`) and every idempotency key. Recover lost ids with `GET /characters`, `GET /voices`, `GET /usage/jobs`, `GET /assets`.
14. Always tell the user about `warnings` — the request ran, but not exactly as written.

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
| Lock the opening look before paying for the render | `POST /images/first-frame` (4) → `first_frame_asset_id` | Drops the video's 4-credit frame line (net 0, but the look is approved first) |
| Their own opening still | `first_frame_url` (https, single subject) | −4 |
| Cheaper / sharper | `resolution`: `480P` / `768P` / `1080P` | 5 / 8 / 16 cr/s (text mode 2.5 / 4 / 8) |

Rules of thumb: `talking_head` is the safe default for a single message; `scenes` when movement or real product shots matter. Scene `role`: `product` (the thing sold), `setting` (the place), `prop` (an object handled). `caption` (≤200 chars) says what it is. No voice and no recording → only a silent `scenes` video is possible.

## First-run setup

1. **Account** — `{BASE}/sign-up` (full name, organization, email, password ≥8 characters, confirm password), then the dashboard `{BASE}/partner`.
2. **Buy credits** — dashboard → **Buy credits** → Stripe checkout. Default is the **$19.99 pack**: **1,499 credits** for accounts created on/after 8 July 2026 20:40 UTC (current tier, 750 credits per $10), **1,738** for older accounts (earlier tier, $1.15 per 100 credits). A custom amount is available (multiples of 100 credits). Credits land within seconds; receipts appear in the dashboard's payments list.
3. **API key** — with `/sign-up`, the first top-up creates the key; it is shown after checkout and can be revealed and copied from the dashboard's API key panel (signed in). The homepage sign-up (`{BASE}/`) creates the key straight away; 25 starter credits are added on the key's first call.
4. **Store it** — `export PROMOAT_KEY="pmat_..."` in the shell profile, or a gitignored `.env`. Not in chat, not in code.
5. **Verify** — `curl -s "$BASE/api/partner/v1/usage/summary" -H "Authorization: Bearer $PROMOAT_KEY"` → `{ "credits_balance": …, … }`. `401` = wrong or truncated key.

For scale: a 15 s talking head at 768P from your own audio is 125 credits; a 15 s scenes video with 2 photos is 131.

## Writing the script (idea → approved script)

When the user brings an idea, not a script, do the creative work before any paid call:
1. Get the brief in one pass (skip what they already said): goal (sell / explain / announce / story), product or offer, audience, platform, length, language, tone, the one action viewers should take.
2. Offer three genuinely different hooks (direct benefit, curiosity gap, relatable problem), each sayable in the first 2–3 seconds. Let them pick or combine.
3. Recommend the format from the decision table in one sentence; let them override.
4. Write spoken language for the target length: ~35 words ≈ 15 s, 55–65 ≈ 25 s, 90–100 ≈ 40 s, and stay under ~120 words (~100 for Arabic and other non-Latin scripts) — the hard cap is 59.5 s of speech. Hook → one idea → one CTA.
5. For scenes, write concrete actions the same presenter can perform; follow the identity rules in P7. Use the user's real product/place photos as `scene_photos`.
6. Optional: `POST /videos/scene-plan` and show the scene lines; send approved lines back as `scene_lines`.
7. Show the full script + format for approval, then run the golden path from step 5.

Never claim facts were researched unless you actually checked a source. For medical, legal, financial or current-events claims, verify or ask the user for approved copy.

## Playbooks

Input URLs (selfies, samples, scene photos, frames, audio) must be **public https** URLs; private, link-local or metadata hosts are refused. All ids are scoped to the key's account — another account's id answers the same `404` as a missing one.

### P1 — Character (free)

```bash
# From 1–3 selfies (reproduces the person)
curl -s -X POST "$BASE/api/partner/v1/characters" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d '{ "name": "Omar",
        "selfie_image_urls": ["https://cdn.example.com/omar-1.jpg", "https://cdn.example.com/omar-2.jpg"],
        "edit_instructions": "professional attire, studio lighting" }'

# From a description (invents a person)
curl -s -X POST "$BASE/api/partner/v1/characters" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d '{ "name": "Ava", "description": "a friendly presenter in her early 30s, warm smile",
        "reference_image_urls": ["https://cdn.example.com/mood.jpg"], "recast_attempt": 1 }'
# → { character_id, name, mode: "photos"|"description", sheet_image_url, character_sheet_text, asset_id,
#     presenter_gender: "female"|"male"|"unknown",
#     head_covering: "none"|"hijab"|"niqab"|"headscarf"|"turban"|"kippah"|"unknown",
#     credits_charged: 0, warnings? }
```
- `name` required (≤120). Exactly one of `selfie_image_urls` (https; first 3 used) or `description` (≤2,000). `edit_instructions` ≤500 (longer is cut). `reference_image_urls` (≤3, description mode only) are style inspiration, never an identity. Disliked face → re-run with `recast_attempt` 1, 2, … for a different person.
- An https selfie/reference that cannot be loaded is skipped with a `FIELD_IGNORED` warning; if no selfie loads → `422`. Non-https URLs are dropped silently, and a selfie list with no https URL at all → `400`. Each video re-detects the head covering from the character image, so it is kept.
- **Regenerate the sheet** (same person, same `character_id`, **4 credits**): `POST /characters/{id}/regenerate` `{ "edit_instructions"?: "navy blazer" }` (≤500, else 400) → `{ character_id, sheet_image_url, asset_id, credits_charged }`; it falls back to the current sheet when the original photos can't be read; `422` only when neither can.
- Manage: `GET /characters` (newest 100), `GET /characters/{id}`, `DELETE /characters/{id}` → `{ "deleted": true }`.

> `sheet_image_url` is a multi-pose reference sheet. Show it to the user, but never pass it as `first_frame_url` — the video would animate the grid. Pass `character_id`; to control the opening look use P4.

### P2 — Voice

```bash
# Studio voices (free, multilingual)
curl -s "$BASE/api/partner/v1/voices/presets" -H "Authorization: Bearer $PROMOAT_KEY"
# → { "voices": [ { "studio_voice": "Brian", "gender": "male", "languages": "multilingual" }, … ] }
curl -s -X POST "$BASE/api/partner/v1/voices" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d '{ "name": "Spanish narrator", "language": "spanish", "gender": "female", "studio_voice": "Sarah" }'
# → { voice_id: "sv_…", name, kind: "library", language, credits_charged: 0, studio_voice, gender }

# Clone a real voice (first clone per account free, later 30)
curl -s -X POST "$BASE/api/partner/v1/voices" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d '{ "name": "Ava voice", "sample_urls": ["https://cdn.example.com/ava-1.mp3"], "preview_language": "en" }'
# → { voice_id: "pv_…", name, kind: "cloned", credits_charged, preview_url, warnings }
```
- Studio: send `language` and/or `studio_voice` (not `sample_urls`). Never send `language` with `sample_urls`: that is `400 "Provide exactly one voice source"`; for a clone in another language use `preview_language`. Male Brian, Daniel, George, Chris; female Sarah, Laura, Alice, Jessica. Without `studio_voice` one is picked from `gender` (default `female`). Unknown name → `400 INVALID_STUDIO_VOICE`. Cap 10 library voices.
- Clone: `name` ≤80; 1–25 public https `sample_urls` of clean speech (25 s+ total is best; only the first 25 URLs are used, non-https ones are dropped). The **first** clone per account is free, once ever (deleting it does not reset that); later clones 30. Tell the user "free if it is your first clone, otherwise 30": there is no `expected_credits` guard, and a second clone sent at the same time is charged 30 — read `credits_charged`. Under ~25 s of usable speech → warning `LOW_SAMPLE_AUDIO` (offer a re-clone). Play `preview_url` to the user. Cap 3 cloned voices.
- Clone errors: `400` + `sample_errors: [{index, reason}]` (no sample could be fetched), `400 INVALID_SAMPLES`, `422 NO_SPEECH` (refunded), `502 CLONE_UNAVAILABLE` (retry later, refunded), `409 VOICE_LIMIT_REACHED` (+`max_voices`; delete one), `409 FREE_CLONE_ATTEMPTS_EXHAUSTED` (free clone failed 20 times — fix the samples, ask Promoat support; don't retry).
- **Re-clone** (better samples, or revive an expired clone): `POST /voices/{id}/reclone` `{ "sample_urls": [...], "preview_language"?: "en" }` → `{ voice_id: "pv_NEW…", previous_voice_id, name, kind, credits_charged, preview_url, warnings }`. New id — the old one is removed; update your notes. 30 credits, or **0** if the old voice had expired. Studio voice → `400 NOT_A_CLONED_VOICE`.
- Manage: `GET /voices` (newest 100: `voice_id, name, kind, language, created_at`), `DELETE /voices/{id}` → `{ "deleted": true }` (frees a slot).

### P3 — Text-to-speech (standalone audio)

```bash
curl -s -X POST "$BASE/api/partner/v1/tts" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d '{ "voice_id": "VOICE_ID", "text": "Welcome back! Here is what is new this week.", "language": "en",
        "voice_settings": { "stability": 0.5, "similarity_boost": 0.75, "style": 0.3, "speed": 1.1 } }'
# → { audio_url, duration_sec, asset_id, credits_charged, characters }
```
`text` ≤5,000 chars. `language` (name or ISO code; wins over the older `language_code`). Settings clamped: `speed` 0.7–1.2, others 0–1. **Price max(10, ceil(chars / 1,000) × 10)**. Unknown voice → `404`; expired/removed voice → `409 VOICE_UNAVAILABLE` with `voice_state` (re-clone, P2). For videos you do not need this: pass `voice_id` + `script` to `/videos`. A TTS asset can be reused as a fix-sound take (`tts_asset_id`).

### P4 — First-frame still (4 credits)

```bash
curl -s -X POST "$BASE/api/partner/v1/images/first-frame" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d '{ "character_id": "CHARACTER_ID", "kind": "talking_head",
        "scene_description": "behind the counter of a bright coffee shop, morning light" }'
# → { image_url, asset_id, frame_id, kind, credits_charged: 4, warnings? }
```
- `kind`: `talking_head` (default) or `moving_scene` (the realistic photo a scenes video starts from).
- One of `scene_description` (≤2,000), `scene_prompt` (≤400) or `script` (≤4,000, context only) is required. `scene_photos` (≤3) are used for `talking_head` frames only. `language` optional.
- Pass `frame_id` to `/videos` as `first_frame_asset_id`: the look is locked and the video drops its own 4-credit frame line. The kind must match the video mode, else `400 FIRST_FRAME_KIND_MISMATCH`.
- Failure (refunded): `500` with `error_code` `FIRST_FRAME_NOT_VERTICAL` (retry), `CHARACTER_IMAGE_UNAVAILABLE` (regenerate the character), `PROVIDER_*` or `INTERNAL`.

### P5 — Talking-head video

```bash
BODY='{
  "mode": "talking_head",
  "character_id": "CHARACTER_ID",
  "voice_id": "VOICE_ID",
  "script": "Hi! Three quick updates from the shop this week. First, we extended our opening hours.",
  "video_idea": "standing in a bright modern kitchen, smiling at the camera",
  "resolution": "768P",
  "use_dynamic_captions": true,
  "captions_position": "bottom"
}'
EST=$(curl -s -X POST "$BASE/api/partner/v1/videos/estimate" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" -d "$BODY")
echo "$EST" | jq '{credits_required, credits_balance, sufficient_credits, lines, warnings}'
# → { mode, credits_required, credits_balance, sufficient_credits, estimated_seconds, billed_seconds,
#     resolution, job_type, price_table_version, lines: [{kind, credits, …}], clips, breakdown, warnings }

# Only after the user approves this number:
QUOTE=$(echo "$EST" | jq -r .credits_required)
KEY=$(uuidgen)   # save it with the job; reuse it for retries of THIS job only
curl -s -X POST "$BASE/api/partner/v1/videos" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" -H "Idempotency-Key: $KEY" \
  -d "$(echo "$BODY" | jq --argjson q "$QUOTE" '. + {expected_credits: $q}')"
# → { workflow_id: "partner_h3t_…", status: "queued", credits_reserved, credits_quoted, job_type,
#     resolution, price_table_version, warnings, duplicate: false }
```
- `character_id` required on `/videos` (the estimate prices without it and does not check ids, so `404` or `FIRST_FRAME_KIND_MISMATCH` for a bad `first_frame_asset_id` can first appear on `POST /videos`).
- Audio: exactly one of `voice_id` + `script` (≤4,000 chars, spoken verbatim) or `audio_url` (P6). Speech must be 1–59.5 s (`AUDIO_TOO_SHORT` / `AUDIO_TOO_LONG`); 1–5 s bills as 5.
- `video_idea` (≤2,000) is required unless a frame is given (`first_frame_asset_id` = a `talking_head` frame from P4, or `first_frame_url`; not both). `scene_prompt` (≤400) and `scene_photos` also shape the generated frame.
- `resolution`: `480P`, `768P` (default), `1080P` (any case); `720p` is served as 768P with `RESOLUTION_MAPPED`; anything else `400 INVALID_RESOLUTION`. `video_mode` / `voice_mode: "none"` are refused on talking heads.
- `voice_settings` (as P3), `language` (name or ISO code), `scene_lines` (from P8; 1–15 strings ≤600 chars). `topic` / `audience` are accepted (cut at 500) but have **no effect** (warning `FIELD_IGNORED`): put the brief in `video_idea` / `scene_prompt`, and don't promise the user they steer the video.
- Captions: `use_dynamic_captions: true` (+10) burns word-by-word captions on a solid band; `captions_position` `bottom` (default) | `center` | `top`; `captions_language` optional hint (`"en"`, `"ar"`). Pick a frame that leaves that area clear.
- `expected_credits`: whole number ≥0; a higher server quote → `409 QUOTE_MISMATCH` (+`credits_quoted`), nothing charged.
- Accepted but ignored (warning `FIELD_IGNORED`): `fast`, `narration_mode`, `lipsync`, `audio_duration`, `first_frame_title`, `topic`, `audience`; also a non-https `first_frame_url` / `audio_url` (a non-https `audio_url` with no other audio source is `400 INVALID_BODY` — fix the URL). Every talking head is lip-synced automatically, in windows of 5–14.5 s cut at natural pauses.

### P6 — From the user's own recording

Replace `voice_id` + `script` with `"audio_url": "https://cdn.example.com/narration.mp3"` (talking head or scenes). The length is probed server-side (estimate and queue); a private or unsafe host is `400 INVALID_URL`, and `422 INVALID_URL` means it could not be read as audio. Same 1–59.5 s rule. Recording-voiced videos cannot use `edit-script` later (only fix-scene / fix-sound).

### P7 — Scenes video (the presenter acts the script out)

> **Identity rules for `video_idea` / `scene_prompt`** — state the presenter's gender and lock to one person: `one female barista, the same woman throughout; no other people; do not restyle or recast the presenter`. Describe the presenter *doing* things ("pours", "holds up the bag"), not a scene full of people.

```bash
BODY='{
  "mode": "scenes",
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
  "language": "english"
}'
# estimate → confirm → POST /videos with expected_credits + Idempotency-Key  (workflow_id partner_h3v_…)
```
- `mode`: `scenes` (alias `moving_scene`). Audio: `voice_id` + `script`, or `audio_url`, or none with `voice_mode: "none"`.
- `video_mode`: `reference` (default; the presenter's realistic photo + up to 3 scene photos; voiced clips are spoken on camera) or `text` (half price; scene photos and frames are ignored with `FIELD_IGNORED`).
- `voice_mode: "none"` (silent): `target_seconds` 5–60 required, as a JSON **number** (`"15"` → `400 INVALID_DURATION`); the brief is `script`, else `scene_lines`, else `video_idea` (one is required, `INVALID_SCRIPT`); `audio_url` is refused (`400 INVALID_BODY`), `voice_id` ignored (`FIELD_IGNORED`).
- `scene_photos`: `[{ url, role?: "setting"|"product"|"prop", caption? ≤200 }]`. First 3 unique URLs are used (`SCENE_PHOTOS_TRUNCATED`); more than 12 items or a malformed item → `400 INVALID_SCENE_PHOTOS`. A photo that cannot be fetched at render time is dropped, the charge is re-quoted without it (never above the reservation), and the job carries `SCENE_PHOTO_DROPPED` in `GET /usage/jobs` → `metadata.warnings`.
- `first_frame_asset_id`: a `moving_scene` frame (P4) — a talking-head frame → `400 FIRST_FRAME_KIND_MISMATCH`. Or `first_frame_url`. Either drops the 4-credit photo line; otherwise the job makes the photo.
- `scene_prompt` (≤400), `scene_lines`, `language`, `voice_settings`, `resolution` as in P5. `use_dynamic_captions` has no effect on scenes (no warning).

### P8 — Scene plan (free, instant)

```bash
curl -s -X POST "$BASE/api/partner/v1/videos/scene-plan" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d '{ "video_type": "scenes", "script": "Ever wondered how we roast our beans? ..." }'
# → { "scenes": [ { "index": 0, "line": "…", "seconds": 4.2 }, … ], "max_words_per_scene": 33 }
```
`video_type`: `talking_head` | `scenes` | `moving_scene` | `normal_video` (the last two are aliases of `scenes`). `script` 1–4,000 chars. Optional `audio_duration_seconds` (≤60.5; required and 5–60 with `voice_mode: "none"`), `voice_mode`. `max_words_per_scene` is 32 for talking heads, 33 for scenes. Errors: `400 INVALID_BODY | INVALID_SCRIPT | INVALID_DURATION | INVALID_VOICE_MODE`.

### P9 — Edits

All three: `POST /videos/{workflow_id}/<edit>`; the source must be a `completed` video whose status `result.editable` is `true` (an edit's output can be edited again). fix-scene and edit-script refuse body fields beyond those listed (`400 INVALID_BODY`); **fix-sound silently ignores unknown fields**, so check the spelling of `expected_credits` / `dry_run` (a typo there reads as missing → `409 QUOTE_MISMATCH`). `Idempotency-Key` (or body `client_request_id`, a UUID) is **required** unless `dry_run: true` (`400 IDEMPOTENCY_KEY_REQUIRED`); edit keys are per account and endpoint, not per source video (one fix-scene key on two videos → `409 IDEMPOTENCY_KEY_REUSED`). Edits count toward the 5 active jobs; one open edit per source video (`409 EDIT_IN_PROGRESS`; an edit with no activity for 30 min no longer blocks).

```bash
# See the scenes (free)
curl -s "$BASE/api/partner/v1/videos/$WORKFLOW_ID/scenes" -H "Authorization: Bearer $PROMOAT_KEY"
# → { workflow_id, video_type: "talking_head"|"moving_scene", resolution, editable,
#     voice: { source: "ai_voice"|"recording"|"none" }, poster_url?,
#     scenes: [ { index, line, seconds, start_seconds, talks, clip_url?, poster_url? } ], source_workflow_id? }

# Fix one scene — quote, then run
FIX='{ "scene_index": 2, "description": "hold the bag closer to the camera" }'
DRY=$(curl -s -X POST "$BASE/api/partner/v1/videos/$WORKFLOW_ID/fix-scene" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" \
  -d "$(echo "$FIX" | jq '. + {dry_run: true}')")
echo "$DRY" | jq '{credits_quoted, credits_balance, sufficient_credits, edit_kind, lines}'
# → { dry_run: true, credits_quoted, credits_required, credits_balance, sufficient_credits, lines, clips,
#     source_workflow_id, scene_indices, edit_kind, price_table_version }
# Only after the user approves credits_quoted:
QUOTE=$(echo "$DRY" | jq -r .credits_quoted)
curl -s -X POST "$BASE/api/partner/v1/videos/$WORKFLOW_ID/fix-scene" \
  -H "Authorization: Bearer $PROMOAT_KEY" -H "Content-Type: application/json" -H "Idempotency-Key: $(uuidgen)" \
  -d "$(echo "$FIX" | jq --argjson q "$QUOTE" '. + {expected_credits: $q}')"
# → { workflow_id: "partner_se_…", status: "queued", credits_reserved, credits_quoted, job_type: "scene_edit_video",
#     source_workflow_id, scene_indices, edit_kind, price_table_version, duplicate: false }
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

```bash
curl -s "$BASE/api/partner/v1/usage/summary?from=2026-10-01T00:00:00Z&to=2026-10-03T00:00:00Z" -H "Authorization: Bearer $PROMOAT_KEY"
# → { credits_balance, credits_balance_base, credits_spent_lifetime, credits_consumed_in_range,
#     job_counts: { completed, failed, running_or_queued, total_in_range }, from, to }   (default range: this UTC month)
#   credits_spent_lifetime = spend since the LAST TOP-UP (it resets at each top-up), not all-time spend
curl -s "$BASE/api/partner/v1/usage/jobs?limit=30&offset=0" -H "Authorization: Bearer $PROMOAT_KEY"
# → { jobs: [ { workflow_id, status, job_type, credits_estimated, credits_actual, queued_at, completed_at, error_message, metadata } ] }
curl -s "$BASE/api/partner/v1/assets?kind=video&limit=30&offset=0" -H "Authorization: Bearer $PROMOAT_KEY"
# → { assets: [ { asset_id, kind, url, workflow_id, character_id, voice_id, metadata, created_at } ] };  GET /assets/{id} for one
```
Lists are newest first; `limit` default 30, values over 100 are capped at 100. `/usage/jobs` also lists non-video rows (`job_type` `character_sheet`, `tts`, `voice_clone`, `first_frame_image`, `voice_library`). Asset `kind`: `character_sheet | first_frame | tts_audio | video` (other values → 400). Video asset metadata may include `poster_url, duration_sec, resolution, video_type, video_mode, voice_mode, scene_count, source_workflow_id, edit_kind, price_table_version`; character sheets `mode, presenter_gender, head_covering`; first frames `video_type, head_covering`.

## Polling

```bash
while :; do
  R=$(curl -s "$BASE/api/partner/v1/jobs/$WORKFLOW_ID/status" -H "Authorization: Bearer $PROMOAT_KEY")
  S=$(echo "$R" | jq -r .status); echo "$R" | jq -c '{status, phase, progress}'
  [ "$S" = "completed" ] || [ "$S" = "failed" ] && break
  sleep 10
done
echo "$R" | jq '{status, video_url, poster_url, credits_consumed, error_code, error_message, result}'
```
- **Fields**: `workflow_id, status (queued|running|completed|failed), job_type (talking_head_video | multi_scene_video | scene_edit_video | fix_sound_video), phase (queued → preparing → generating → assembling → finalizing → completed|failed), progress (0–100|null), video_url, image_url, poster_url, source_workflow_id, credits_estimated, credits_actual, credits_consumed, error_code, error_message, result, queued_at, completed_at`. On completion `result` may hold `video_url`, `asset_id`, `poster_url`, `editable` and, only when editable, `scenes_url` — a **relative** path (`/api/partner/v1/videos/{id}/scenes`): prepend `$BASE`.
- **Interval**: 8–10 s; after 10 minutes, 30 s is fine. Show `phase`/`progress` to the user.
- **Expect**: talking head ~10 min, scenes ~25 min; edits like their source type; a free sound swap is quick. Past that, keep polling and tell the user it is slow — do not re-queue. A job with no progress for **75 minutes** is failed with `STALE_TIMEOUT` and refunded automatically.
- **`completed`** (terminal): deliver `video_url` (+`poster_url`), `credits_consumed` (≤ the reservation; script jobs often get a refund), and warnings (`GET /usage/jobs` row → `metadata.warnings`). Offer edits if `result.editable`.
- **`failed`** (terminal): the reservation is refunded once, automatically (`credits_consumed` 0, or a recorded partial charge). Show `error_message` (user-safe) and act on `error_code` below.
- `404 {"error":"Job not found", "error_code":"NOT_FOUND", …}`: wrong id or another account's job — recover it from `GET /usage/jobs`.

### Job failure codes

| `error_code` | Do this |
|---|---|
| `PROVIDER_MODERATION` | Content refused. Rephrase `video_idea` / `scene_prompt` / fix `description`, or use other photos; don't resend the same body |
| `PROVIDER_INPUT` | A photo or audio file could not be used. Replace it (or regenerate the character) and re-queue |
| `PROVIDER_INFRA`, `PROVIDER_TIMEOUT`, `START_FAILED`, `INTERNAL`, `STALE_TIMEOUT` | Transient. Re-queue **once** with a **new** key (after re-confirming the price); if it fails again, stop and report |
| `LINE_TOO_LONG` | Shorten the offending line(s) to ≤ `max_words_per_scene` (P8) and re-queue |
| `VOICE_UNAVAILABLE` | Voice expired/removed: `POST /voices/{id}/reclone` (free if expired) or pick another voice; re-queue with the new id |
| `FIX_NOT_APPLIED` | The edit could not be applied: reword the fix `description` and retry |
| `MISSING_ASSET` | Something the job needed is gone (e.g. the source video): make the video again with `POST /videos` |
| `AUDIO_TOO_LONG` | The real speech ran over 59.5 s: shorten the script and re-queue |

## Idempotency

- Header `Idempotency-Key: <1–255 visible ASCII chars>` (a UUID is ideal) or body `client_request_id` (a UUID). Both sent and different → `400 IDEMPOTENCY_KEY_MISMATCH`; malformed → `400 IDEMPOTENCY_KEY_INVALID`.
- Optional on `POST /videos`, required on fix-scene / edit-script / fix-sound (except `dry_run`).
- Same key + same body → `200 { workflow_id, status, duplicate: true, credits_reserved }` — the original job, never a second charge (whatever its status). On `/videos` validation and the price check run first, so a retry can get `409 QUOTE_MISMATCH` or `404`/`422` instead (see rule 10); edits answer the duplicate first.
- Same key + different body → `409 IDEMPOTENCY_KEY_REUSED`. The comparison is over the validated request: `expected_credits`, warnings and ignored legacy fields don't count, and `"720p"` equals `"768P"`.
- One key covers all `/videos` modes (a talking-head and then a scenes body under one key → 409). Keys are per account and per endpoint (a `/videos` key never collides with a fix-scene key).
- A `402`, `429` or `409 QUOTE_MISMATCH` creates no job: after topping up / waiting / re-confirming, the same key is still usable.

## Endpoint reference

| Method & path | What it does | Cost |
|---|---|---|
| `POST /characters` | Create presenter (selfies or description) | free |
| `POST /characters/{id}/regenerate` | New sheet, same person | 4 |
| `GET /characters` · `GET /characters/{id}` · `DELETE /characters/{id}` | List (newest 100) / fetch / delete | free |
| `GET /voices/presets` | Studio voices | free |
| `POST /voices` | Studio voice, or clone from `sample_urls` | studio 0 · first clone 0, then 30 |
| `POST /voices/{id}/reclone` | New clone from new samples (new id) | 30, or 0 if expired |
| `GET /voices` · `DELETE /voices/{id}` | List (newest 100) / delete | free |
| `POST /tts` | Speech in a voice | max(10, ceil(chars/1,000) × 10) |
| `POST /images/first-frame` | 9:16 still of a character | 4 |
| `POST /videos/scene-plan` | Split a script into scenes | free |
| `POST /videos/estimate` | Exact quote for a `/videos` body | free |
| `POST /videos` | Queue `talking_head` or `scenes` | quote, reserved up front |
| `GET /videos/{id}/scenes` | Scenes of a finished video | free |
| `POST /videos/{id}/fix-scene` · `/edit-script` · `/fix-sound` | New edited video (`dry_run` quotes) | quote; sound swap free |
| `GET /jobs/{workflow_id}/status` | Poll a job | free |
| `GET /usage/summary` · `GET /usage/jobs` | Balance, counts, job history | free |
| `GET /assets` · `GET /assets/{id}` | Every generated output | free |

## Pricing

Price table **2026-09-30** (`price_table_version` in responses). A deployment may add a markup, so the estimate / `dry_run` is the number to quote — never this table.

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
| 401 | `UNAUTHORIZED` (`error`: `Missing Authorization Bearer token` / `Unauthorized`) | Check `PROMOAT_KEY` is set and complete; test with `/usage/summary` |
| 402 | `INSUFFICIENT_CREDITS` (+`credits_required`, `credits_balance`) | Tell the user the gap; dashboard → Buy credits; then resend (same key OK). Don't loop |
| 404 | `NOT_FOUND` (`error`: `NOT_FOUND`, `Not found` or `Job not found`; +`field`) | Id is wrong or not this account's; list with the GET endpoints |
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

**Warnings** (`warnings: [{ field, code, message }]` on a 200): `RESOLUTION_MAPPED` (720p served as 768P), `FIELD_IGNORED` (legacy or non-applicable field, `topic`/`audience`, non-https URL, unloadable selfie, photos/frame in text mode, scene photos on a `moving_scene` frame, `voice_id` on a silent video, `target_seconds` without `voice_mode: "none"`, a non-string `video_idea`), `SCENE_PHOTOS_TRUNCATED` (only 3 kept), `LOW_SAMPLE_AUDIO` (clone from <25 s of speech). Job-time: `SCENE_PHOTO_DROPPED` on the job's `GET /usage/jobs` row. Always relay them.

## Troubleshooting

- **Quote too high** → read `lines`: drop to 480P, shorten the script, skip captions, use your own approved frame, or scenes `video_mode: "text"`.
- **User dislikes the face** → description mode: bump `recast_attempt`; selfie mode: better-lit selfies or `regenerate` with `edit_instructions`.
- **Wrong language/accent** → set `language` on the video / TTS; studio voices are multilingual and free.
- **`404` on a voice just used** → re-clones get a new id; check `GET /voices`.
- **One scene is wrong** → `fix-scene`, not a whole new video.
- **Want another take of the same video** → re-queue with a **new** key (each job is an independent generation); vary `video_idea` for a different setting.
- **Ids from before 1.1.0** keep working; videos made before 1.1.0 can't be edited.

This file is served from `{BASE}/skill/SKILL.md` — re-download it occasionally to pick up API changes.
