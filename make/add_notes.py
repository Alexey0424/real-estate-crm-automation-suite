#!/usr/bin/env python3
"""
add_notes.py — document a Make scenario with module-attached, colour-coded notes
(the Make equivalent of n8n sticky notes). Idempotent: wipes the scenario's
existing notes, then re-posts the curated set so docs stay in sync.

  python make/add_notes.py partA      # scenario 5389041
  python make/add_notes.py partB      # scenario 5390808

Notes attach to a module via moduleIds:[n] and carry a metadata.color. They show
on the canvas as a coloured note marker on that module, expandable to the text.
"""
import sys, json, urllib.request, urllib.error
import importlib.util, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_api", ROOT / "make" / "make_api.py")
mapi = importlib.util.module_from_spec(spec); spec.loader.exec_module(mapi)
ZONE, _ = mapi.find_zone()
TOKEN, UA = mapi.TOKEN, mapi.UA

# colour palette (section → hex), mirroring the n8n sticky-note sectioning
C_TRIGGER = "#51CF66"  # green  — entry / trigger
C_FETCH   = "#4DABF7"  # blue   — external API calls
C_CONFIG  = "#FFD43B"  # yellow — variables / config
C_ROUTER  = "#FF922B"  # orange — routing
C_SLACK   = "#B197FC"  # purple — Slack outputs


def call(method, path, body=None):
    url = f"https://{ZONE}.make.com/api/v2{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Token {TOKEN}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def wipe(sid):
    _, body = call("GET", f"/scenarios/{sid}/notes")
    for n in (body.get("notes") or []):
        call("DELETE", f"/scenarios/{sid}/notes/{n['id']}")


def apply(sid, notes):
    wipe(sid)
    for mod_ids, color, content in notes:
        code, resp = call("POST", f"/scenarios/{sid}/notes",
                          {"content": content, "moduleIds": mod_ids, "metadata": {"color": color}})
        tag = "OK" if code == 200 else f"ERR {code} {resp}"
        print(f"  [{tag}] mod {mod_ids}: {content[:48]}")


# ── Part A: FUB → Slack (scenario 5389041, modules 1-6 + slack routes 7-16) ──
PART_A = (5389041, [
    ([1], C_TRIGGER, "① TRIGGER — FUB webhook (peopleCreated + peopleStageUpdated). "
                     "Payload is thin: just event + resourceIds[]."),
    ([2], C_FETCH,   "② FETCH PERSON — GET /v1/people/{id}?fields=allFields. "
                     "Basic auth: FUB API key = User name, blank password. "
                     "We re-fetch because the webhook payload lacks custom fields."),
    ([3], C_CONFIG,  "③ CHANNEL IDs — every Slack channel ID, prod + staging. "
                     "Single source of truth; edit here if a channel changes."),
    ([4], C_CONFIG,  "④ MODE SWITCH — resolves prod vs staging IDs from {{3.MODE}}. "
                     "MODE=TEST → staging channels. Flip to PROD for go-live."),
    ([5], C_CONFIG,  "⑤ FIELD MAP — extracts seller_name / address / source / closer "
                     "(assignedTo) / lead_manager / FUB link from the person."),
    ([6], C_ROUTER,  "⑥ ROUTER — one route per FUB stage. First matching filter wins; "
                     "the No-closer catch-all guarantees nothing drops silently."),
    ([7],  C_SLACK,  "New Lead (peopleCreated, stage Lead) → #new-leads."),
    ([8],  C_SLACK,  "CATCH-ALL — closer-stage but NO assignee → #lead-managers warning. "
                     "Keeps un-routed leads visible instead of dropping."),
    ([9],  C_SLACK,  "Pending Closer Contact (has closer) → DM the closer's channel "
                     "via switch(assignedTo): Reyes / Flora / Marco → lead-managers fallback."),
    ([10], C_SLACK,  "Needs Underwriting → #underwriting."),
    ([11], C_SLACK,  "Closer Needs To Make Offer (has closer) → closer's channel (switch)."),
    ([12], C_SLACK,  "Offer Submitted – Waiting to Hear Back → #closers-chat."),
    ([13], C_SLACK,  "Needs Contract (auto-requested to TC) → #tc (contract team)."),
    ([14], C_SLACK,  "Contract Sent → #tc."),
    ([15], C_SLACK,  "Under Contract → #dispo."),
    ([16], C_SLACK,  "Closed → #team-wins 🎉."),
])

# ── Part B: Cold-Lead Form → FUB (scenario 5390808, modules 1,2,5,6) ──
PART_B = (5390808, [
    ([1], C_TRIGGER, "① TRIGGER — Google Form submission via Apps Script. Sends "
                     "{payload: <full FUB /v1/events JSON>, firstName, lastName, source, "
                     "address}. The script does name-split + note + empty-field omission."),
    ([2], C_FETCH,   "② CREATE LEAD — POST /v1/events, body = {{1.payload}} (relayed). "
                     "FUB dedupes by phone/email + updates existing if matched. Maps all "
                     "SOW fields incl. Market/State + tag 'Cold Lead - SMS' + stage 'Lead'. "
                     "Basic auth: FUB API key = User name, blank password."),
    ([3], C_FETCH,   "③ ADD NOTE — POST /v1/notes for the person ({{2.data.id}}) with "
                     "motivation / property type / Market/State / submitted-by (SOW §9 "
                     "'appended to Notes'). Needs the SAME FUB Basic auth as ②."),
    ([5], C_CONFIG,  "⑤ MODE — TEST → staging-ahb-new-leads, PROD → all-ahb-new-leads. "
                     "Flip to PROD at cutover."),
    ([6], C_SLACK,   "⑥ NEW LEAD POST — Route 1 'New Seller Lead' to the new-leads channel. "
                     "Part B posts this itself (FUB suppresses Part A's webhook for "
                     "same-system creates). Link uses the person id from the events response."),
])

SCENARIOS = {"partA": PART_A, "partB": PART_B}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "partA"
    sid, notes = SCENARIOS[which]
    print(f"Documenting {which} (scenario {sid}) — {len(notes)} notes")
    apply(sid, notes)
    print("done.")
