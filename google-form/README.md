# Part B - Cold-Lead Intake -> FUB (SOW §8–§12)

The SMS agency logs cold leads through a **branded web form**. Each submission creates
a FollowUpBoss lead - deduped by phone/email, at stage **Lead**, tagged
**Cold Lead - SMS**, with a round-robin **Lead Manager**. The new person then flows
into **Part A**, which posts the **New Seller Lead** message to Slack - Part B does
**not** post Slack itself (see "Notifications" below).

## Form: branded Apps Script Web App (live build)

The form is the custom-designed page in `Index.html`, **hosted by Google Apps Script
itself** (Option 1 - $0, no external infrastructure, no CORS). One deployment serves
the page *and* receives the submission.

| Piece | Where | What it does |
|---|---|---|
| `Code.gs` | script.google.com | `doGet()` serves the page · `submitLead()`/`doPost()` build the FUB `/v1/events` payload (name, note, round-robin Lead Manager, tag, stage) and relay it to Make |
| `Index.html` | served by `doGet()` | The branded AHB form; submits via `google.script.run` (no endpoint URL to paste) |
| Make scenario **5390808** | Make org | webhook -> `POST /v1/events` (relayed) -> `POST /v1/notes` (intake note). No Slack - Part A notifies. |
| FollowUpBoss | live account | Creates/merges the person |

> `shared/apps-script/build-form.gs` is the **fallback** plain Google Form builder
> (Option 3 - zero hosting, but no branding). Not the live build; kept for reference.

## Form fields
| Field | Type | Required | -> FUB |
|---|---|---|---|
| First name | Short answer | [x] | `firstName` |
| Last name | Short answer | - | `lastName` |
| Cell phone | Short answer | [x] | `phones[].value` (dedupe key) |
| Email | Short answer | - | `emails[].value` (dedupe key) |
| Property address | Short answer | [x] | `addresses[].street` - paste the full address from Google Maps |
| Lead source | **Dropdown** | [x] | `source` -> Slack "Marketing Campaign". Options: `Seller Outreach`, `Agent Outreach` |
| Notes | Paragraph | [x] | note body |

Assigned **server-side by `Code.gs`**, never on the form:
- **stage = `Lead`**, **tag = `Cold Lead - SMS`** (constants).
- **Lead Manager** -> `customLeadManager`, strict round-robin **Ethan Rivers -> Pam
  Alvarez -> …** (persisted in Script Properties + a lock, so it truly alternates;
  not the submit-second hack from the mockup). This is the field Part A routes
  lead-manager channels on.

## Flow
```
Browser opens the web-app URL (doGet -> Index.html)
  -> user submits -> google.script.run -> submitLead(data)  [server]
      -> nextLeadManager() picks Ethan/Pam (alternating, locked counter)
      -> builds FUB /v1/events payload (person + customLeadManager + tag + stage)
      -> UrlFetchApp POST -> Make webhook (node)
  -> Make HTTP (node) POST /v1/events  (body = {{1.payload}}, relayed)
  -> FUB dedupes by phone/email (updates existing if matched)
  -> Make HTTP (node) POST /v1/notes   (intake note on the person)
  -> FUB person-created fires Part A's peopleCreated webhook -> Part A posts the
    "New Seller Lead" message (Route 1) to new-leads
```

We use **`/v1/events`** (not `/people`): FUB's documented lead-ingestion endpoint -
it dedupes by phone/email, satisfying §10's "search / don't duplicate / update
existing" in one call. The relay payload shape is unchanged, so **Make scenario
5390808 needs no edit** - it just relays `{{1.payload}}`.

## Notifications - Part A owns the Slack post (no double-post)

**Part B does NOT post Slack.** It was originally built to, on the premise that "FUB
suppresses Part A's webhook for same-system (AHB) creates." That premise was
**disproven live (2026-06-17)**: Part A's `peopleCreated` webhook fires fine on a
Part-B-created person, so a Part B Slack post was a **double notification** (Part B's
hardcoded `Lead Manager: -` + Part A's real one). Part B's Slack + MODE modules were
removed (`make/patch_partB_remove_slack.py`); **Part A is the single new-lead
notifier** for every source. Verified E2E: one form submit -> one FUB person -> exactly
one Slack post.

## Deploy (≈2 min, as alexey@acmehomebuyers.example)
1. script.google.com -> **New project**.
2. Paste `Code.gs` into the default `Code.gs`.
3. **File ▸ New ▸ HTML file**, name it exactly **`Index`** (no `.html`), paste `Index.html`.
4. **Deploy ▸ New deployment ▸ Web app**:
   - **Execute as:** Me (alexey@acmehomebuyers.example)
   - **Who has access:** Anyone *(so the agency opens it without a Google login)*
   - Deploy -> approve the permission prompt -> copy the **Web app URL**.
5. That URL **is the live form** - share it with the SMS agency (bookmark it).
   - NOTE: After editing either file: **Deploy ▸ Manage deployments ▸ ✏️ ▸ Version: New
     version** so the live URL serves the update.

## Test (staging)
1. Open the web-app URL, submit a lead -> confirm in FUB: person at stage **Lead**,
   tag `Cold Lead - SMS`, **Lead Manager** set, note populated; and a **single** Slack
   New-Lead post in `#staging-ahb-new-leads` (posted by **Part A**, not Part B).
2. Submit twice -> confirm the Lead Manager **alternates** (Ethan, then Pam).
3. Submit the **same phone** again -> confirm FUB merges (no duplicate).
4. Activate the scenario. (Part B has no MODE switch - staging vs. live is decided by
   **Part A's** MODE, flipped to PROD at cutover.)
