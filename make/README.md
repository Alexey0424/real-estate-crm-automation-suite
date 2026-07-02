# Make.com implementation - authoritative build guide

Platform = **Make.com Core** (paid, 10,000 credits/mo). This is the SOW's platform
and the chosen one. Build the two scenarios below **exactly**; all data-specific
values (channel IDs, stages, custom-field keys, closer map) are real and confirmed
live from the FUB + Slack accounts (2026-06-14).

> NOTE: **Architecture rule (from the credit research): use WEBHOOKS, never the native
> polling triggers.** FUB's "Watch …" modules and Google Sheets "Watch Rows" poll on
> a schedule and **cost 1 credit per check even when idle** (1-min polling ≈ 43,000
> credits/month - it would blow the 10k plan instantly). Both scenarios below are
> webhook-triggered, so credits are spent only on real events.

Shared inputs: Slack block JSON to paste -> `../shared/slack-messages/examples.md`;
field map + routes -> `../docs/architecture.md`; confirmed account values ->
`../docs/architecture.md` + `../docs/architecture.md`. Credentials needed ->
`../the README`.

---

## Connections to create first (Make -> Connections)
1. **Follow Up Boss** - API key (the FUB key already in `.env`). Basic-auth style; key as username.
2. **Slack** - the `ahb_channel_bot` bot connection (scopes `chat:write`, `chat:write.public`). Bot is already invited to all private channels.
3. *(Scenario B only)* nothing for Google needed if we use the Apps Script->webhook path; the form posts directly to Make.

---

## Channel IDs (post by ID, not name)

| key | channel | ID (prod) |
|---|---|---|
| newLeads | all-ahb-new-leads | `C0PORTFOL01` |
| underwriter | underwriter-to-dos | `C0PORTFOL02` |
| closersChat | closers-chat | `C0PORTFOL03` |
| tc | tc-to-dos | `C0PORTFOL04` |
| dispo | dispo-external-chat | `C0PORTFOL05` |
| teamWins | team-wins | `C0PORTFOL06` |
| leadManagers | lead-managers | `C0PORTFOL07` |
| closerReyes | closer-deals-reyes | `C0PORTFOL08` |
| closerFlora | closer-deals-flora | `C0PORTFOL09` |
| closerMarco | closer-deals-marco | `C0PORTFOL10` |

*(Staging equivalents for testing are in `shared/lib/config.js`.)*

---

## SCENARIO A - FUB -> Slack stage notifications

**Module sequence:**

```
[1] Webhooks › Custom webhook            <- copy its URL
[2] FUB › Make an API call               GET /v1/people/{{1.resourceIds[0]}}?fields=allFields
[3] Router
     ├─ (filters per stage, below) -> Slack › Send a Message
     └─ Fallback route -> (no-op / optional log)
```

### Step 1 - Custom webhook
- Add **Webhooks › Custom webhook** -> **Add** -> copy the generated URL.
- Register BOTH FUB events to it (run from the repo, with FUB system creds):
  ```
  FUB_API_KEY=… X_SYSTEM=AHB-Automation X_SYSTEM_KEY=… \
  TARGET_URL=<the Make webhook URL> python shared/fub-scripts/register_webhooks.py
  ```
  (Registers `peopleCreated` + `peopleStageUpdated`.) Then trigger one test event and click **Re-determine data structure** so Make learns the payload (`event`, `resourceIds`, `uri`).

### Step 2 - Hydrate the record (required for the Lead Manager field)
- **FUB › Make an API call**: Method `GET`, URL `/v1/people/{{1.resourceIds[0]}}?fields=allFields`.
- This returns the full person incl. `stage`, `assignedTo`, `source`, `addresses[]`, and **`customLeadManager`** (the trigger payload does NOT include custom fields).

### Step 3 - Router (one route per stage) + fallback
Add a **Router** after module 2. For each route, set a **filter** and a **Slack › Send a Message**. Stage strings are exact (confirmed):

| Route | Filter (stage **Equal to**, case-insensitive) | Channel (ID) | Message template |
|---|---|---|---|
| 1 New lead | `event` = `peopleCreated` **AND** stage `Lead` | newLeads `C0PORTFOL01` | newLead |
| 2 Pending Closer Contact | `Pending Closer Contact` | **by closer** (switch, below) | prequalified |
| 3 Needs Underwriting | `Needs Underwriting` | underwriter `C0PORTFOL02` | underwritingRequest |
| 4 Closer Needs To Make Offer | `Closer Needs To Make Offer` | **by closer** | offerProvidedByUw |
| 5 Offer Submitted | `Offer Submitted - Waiting to Hear Back` | closersChat `C0PORTFOL03` | offerMade |
| 6 Needs Contract | `Needs Contract (Automatically Requested To TC)` | tc `C0PORTFOL04` | contractRequest |
| 7 Contract Sent | `Contract Sent` | tc `C0PORTFOL04` NOTE:confirm | contractSent |
| 8 Under Contract | `Under Contract` | dispo `C0PORTFOL05` | underContract |
| 9 Closed | `Closed` | teamWins `C0PORTFOL06` | closed |
| Catch-all | stage `Pending Closer Contact` OR `Closer Needs To Make Offer` **AND** `assignedTo` empty | leadManagers `C0PORTFOL07` | catch-all warning |
| Fallback | (the fallback route = Yes) | - | drop silently (no-notify/unknown stages) |

- **Route by closer (routes 2 & 4):** in the Slack module's **Channel** field, map:
  ```
  switch({{2.assignedTo}};
    "Reyes Rivero"; "C0PORTFOL08";
    "Flora Stefoni"; "C0PORTFOL09";
    "Marco Diaz"; "C0PORTFOL10";
    "C0PORTFOL07")          <- else -> #lead-managers (safety net)
  ```
  Add the **catch-all route** (stage is a closer stage AND `assignedTo` Equal to empty) BEFORE these, posting the warning to lead-managers.
- **Message:** paste the route's Block Kit JSON from `examples.md` into the Slack **Blocks** field; put the plain-text line in **Text** (notification fallback). Map `{{2.firstName}}`, `{{2.addresses[].street}}`, `{{2.source}}`, `{{2.assignedTo}}`, `{{2.customLeadManager}}`, and the FUB link `https://app.followupboss.com/2/people/view/{{2.id}}`.
- **Fallback route:** set "The fallback route -> Yes" so unmatched/no-notify stages don't error.

### Error handling
On each Slack module: right-click -> **Add error handler -> Break**; set attempts 3, interval ~1 min. In **scenario settings, enable "Store incomplete executions"** or Break does nothing.

---

## SCENARIO B - Cold-lead form -> FUB

**Avoid Watch Rows polling.** Use the form's Apps Script to POST each submission to a Make webhook (instant, credit-cheap).

```
[1] Webhooks › Custom webhook            <- copy URL into shared/apps-script/build-form.gs (WEBHOOK_URL) + installInstantWebhook()
[2] Tools › Set variable                 phone_e164 = normalized phone
[3] FUB › Search Contacts                phone = {{phone_e164}}
[4] Router
     ├─ exists (search returned ≥1) -> FUB › Create a Note (on matched contact)   <- no duplicate
     └─ fallback (new) -> FUB › Create a Contact -> FUB › Create a Note
```

- **Create a Contact** fields: `stage` = `Lead` (constant), `source` = the campaign, tag `Cold Lead - SMS` (constant), `customMarketState` = the form's Market/State (PA/NJ/IN/TN/NC - skip "Other"), name/phone/email mapped.
- **No Slack here** - the created contact triggers Scenario A's Route 1.
- NOTE: FUB note: `POST /people` (Create a Contact) does **not** run FUB lead automations. That's fine for our use (Scenario A fires Route 1 off the created person). If AHB later wants FUB's own action plans to fire on cold leads, switch the create to `POST /v1/events` via **Make an API call**.
- Error handling: **Break** on the FUB modules; same incomplete-executions setting.

---

## NOTE: Credit budget (Core = 10,000 credits/mo) - READ THIS
Per the research: ~**3 credits per Scenario-A event** (webhook + API-call + Slack) and
~**4–5 per Scenario-B submission** (webhook + set + search + create + note). With
webhooks (no idle polling) you only pay per real event:

| Monthly events (each scenario) | A credits | B credits | Total |
|---|---|---|---|
| 500 | 1,500 | 2,500 | 4,000 [x] |
| 1,000 | 3,000 | 5,000 | 8,000 [x] |
| 1,500 | 4,500 | 7,500 | 12,000 NOTE: over 10k |

So Core is comfortable up to ~1,000 events/scenario/month. Beyond that: trim Scenario B
to a single search (≈4 credits) and/or top up credits, or split the scenarios across
orgs. **Polling instead of webhooks would blow this at any volume - don't.**

---

## Build options
- **Recommended:** build Scenario A once in the UI per the spec above, **export the
  blueprint** (⋮ -> Export Blueprint) to version it, then clone for tweaks.
- The `blueprints/*.draft.json` files are a structural starting point with the real
  stages/channels baked in - import to see the shape, then fix module slugs/operators
  (Make has no public blueprint schema, so a hand-authored import isn't guaranteed).
- Core **does include Make API access** - if you want, give me a Make API token +
  region + teamId and I can push a scenario via `POST /api/v2/scenarios` (you'd still
  reconnect FUB/Slack and re-register the webhook).

Then run `../docs/engineering-notes.md` against the staging channels first.
