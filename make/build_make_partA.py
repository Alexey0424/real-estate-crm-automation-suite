#!/usr/bin/env python3
"""
build_make_partA.py — generate the Make blueprint for Scenario A (FUB → Slack),
using the EXACT module slugs/format reverse-engineered from AHB's working Podio
scenarios (slack:CreateMessage v4 + channelWType "manualy", gateway:CustomWebHook,
builtin:BasicRouter, util:SetVariables, text:equal:ci filters, MODE test/prod
channel switch). Writes make/_inspect/partA_make.json (gitignored — embeds keys).

FUB auth is embedded as an Authorization header on the API-call module, so NO FUB
connection is needed; only a Slack connection must be linked after import.
"""
import json, base64, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def env(k):
    envf = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in open(envf, encoding="utf-8"):
        s = line.strip()
        for sep in ("=", ":"):
            if s.lower().startswith(k.lower() + sep):
                return s.split(sep, 1)[1].strip()


X_SYSTEM = env("FUB_X_SYSTEM") or env("X-System") or "AHB"  # non-secret system label only
# SECURITY: the FUB API key + X-System-Key are NOT embedded. They live in a Make
# connection the user creates on the HTTP module (Basic auth, key = username).

# channel IDs (prod, staging) — staging falls back to prod where none exists
CH = {
    "newLeads":     ("C0PORTFOL01", "C0PORTFOL11"),
    "underwriter":  ("C0PORTFOL02", "C0PORTFOL12"),
    "closersChat":  ("C0PORTFOL03", "C0PORTFOL13"),
    "tc":         ("C0PORTFOL04", "C0PORTFOL14"),
    "dispo":        ("C0PORTFOL05", "C0PORTFOL15"),
    "teamWins":     ("C0PORTFOL06", "C0PORTFOL16"),   # staging-team-wins
    "leadManagers": ("C0PORTFOL07", "C0PORTFOL17"),   # staging-lead-managers
    "closerReyes":    ("C0PORTFOL08", "C0PORTFOL18"),   # staging-closer-deals-reyes (recreated 2026-06-16; old C0PORTFOL19 was poisoned for the Make Slack connection)
    "closerFlora":   ("C0PORTFOL09", "C0PORTFOL20"),   # staging-closer-deals-flora
    "closerMarco":   ("C0PORTFOL10", "C0PORTFOL21"),   # staging-closer-deals-marco
}
# Make function expressions must be wrapped in a SINGLE {{ }} with BARE variable
# refs inside (not each ref in its own {{ }}). The earlier per-ref-braced form made
# Make treat switch(...) as a literal string -> channel_not_found on every closer
# route. Fixed 2026-06-16.
CLOSER_SWITCH = ('{{switch(5.closer; "Reyes Rivero"; 4.closerReyes; '
                 '"Flora Stefoni"; 4.closerFlora; "Marco Diaz"; 4.closerMarco; '
                 '4.leadManagers)}}')

_id = 0
def nid():
    global _id; _id += 1; return _id

def slack(channel, text, filt, x, y):
    return {
        "id": nid(), "module": "slack:CreateMessage", "version": 4,
        "parameters": {},  # Slack connection linked after import
        "filter": filt,
        "mapper": {"channel": channel, "text": text, "parse": False,
                   "mrkdwn": True, "channelWType": "manualy"},
        "metadata": {"designer": {"x": x, "y": y}},
    }

def F(name, conditions):
    return {"name": name, "conditions": conditions}

def eq(a, b):  return {"a": a, "b": b, "o": "text:equal:ci"}
def eqcs(a, b):return {"a": a, "b": b, "o": "text:equal"}
def ne(a, b):  return {"a": a, "b": b, "o": "text:notequal"}

# message texts (AHB style: bold title, plain labels, FUB Link)
M = {
  # New-lead post intentionally omits Lead Manager (Alexey 2026-06-17). Other routes
  # (e.g. prequalified) keep it. Mirrors live patch make/patch_partA_newlead_no_lm.py.
  "newLead": "*New Seller Lead!* :rocket:\nMarketing Campaign: {{5.source}}\nSeller Name: {{5.seller_name}}\nAddress: {{5.address}}\nFUB Link: {{5.link}}",
  "prequalified": "*:telephone_receiver: PREQUALIFIED LEAD ASSIGNED TO YOU*\nSeller Name: {{5.seller_name}}\nAddress: {{5.address}}\nSource: {{5.source}}\nLead Manager: {{5.lead_manager}}\nFUB Link: {{5.link}}",
  "underwritingRequest": "*UNDERWRITING REQUEST*\nSeller Name: {{5.seller_name}}\nCloser: {{5.closer}}\nAddress: {{5.address}}\nSource: {{5.source}}\nFUB Link: {{5.link}}",
  "offerProvidedByUw": "*OFFER PROVIDED BY UW!*\nSeller Name: {{5.seller_name}}\nCloser: {{5.closer}}\nAddress: {{5.address}}\nSource: {{5.source}}\nFUB Link: {{5.link}}",
  "offerMade": "*:envelope_with_arrow: OFFER MADE*\nCloser: {{5.closer}}\nSeller Name: {{5.seller_name}}\nAddress: {{5.address}}\nFUB Link: {{5.link}}",
  "offerRejected": "*:x: OFFER REJECTED*\nCloser: {{5.closer}}\nSeller Name: {{5.seller_name}}\nAddress: {{5.address}}\nFUB Link: {{5.link}}",
  "contractRequest": "*:memo: CONTRACT REQUEST*\nSeller Name: {{5.seller_name}}\nCloser: {{5.closer}}\nAddress: {{5.address}}\nFUB Link: {{5.link}}",
  "contractSent": "*:white_check_mark: CONTRACT SENT*\nSeller Name: {{5.seller_name}}\nCloser: {{5.closer}}\nAddress: {{5.address}}\nFUB Link: {{5.link}}",
  "underContract": "*NEW DEAL UNDER CONTRACT!*\nSeller Name: {{5.seller_name}}\nCloser: {{5.closer}}\nAddress: {{5.address}}\nSource: {{5.source}}\nFUB Link: {{5.link}}",
  "closed": "*:tada: Congrats to the closer!*\nCloser: {{5.closer}}\nProperty: {{5.address}}\nSource: {{5.source}}\nFUB Link: {{5.link}}",
  "catchall": "*:warning: Lead moved to {{5.stage}} with no closer assigned*\nSeller Name: {{5.seller_name}}\nFUB Link: {{5.link}}",
}

EV = "{{1.event}}"; STG = "{{5.stage}}"; CL = "{{5.closer}}"

_id = 6  # fixed modules take ids 1-6; route (slack) modules get 7+
routes = [
  # New lead: fire on first creation AND on a move INTO "Lead" (e.g. recovered
  # from Trash) — two OR-groups, each gated on stage=Lead so other webhook types
  # can't trigger it. See patch_partA_trash_to_lead.py.
  slack("{{4.newLeads}}", M["newLead"], F("New lead",
        [[eqcs(EV, "peopleCreated"), eq(STG, "Lead")], [eqcs(EV, "peopleStageUpdated"), eq(STG, "Lead")]]), 900, -600),
  # catch-all: closer stage with NO assignee → lead-managers warning
  slack("{{4.leadManagers}}", M["catchall"], F("No-closer catch-all",
        [[eq(STG, "Pending Closer Contact"), eq(CL, "")], [eq(STG, "Closer Needs To Make Offer"), eq(CL, "")]]), 900, -480),
  slack(CLOSER_SWITCH, M["prequalified"], F("Pending Closer Contact", [[eq(STG, "Pending Closer Contact"), ne(CL, "")]]), 900, -360),
  slack("{{4.underwriter}}", M["underwritingRequest"], F("Needs Underwriting", [[eq(STG, "Needs Underwriting")]]), 900, -240),
  slack(CLOSER_SWITCH, M["offerProvidedByUw"], F("Closer Needs To Make Offer", [[eq(STG, "Closer Needs To Make Offer"), ne(CL, "")]]), 900, -120),
  slack("{{4.closersChat}}", M["offerMade"], F("Offer Submitted", [[eq(STG, "Offer Submitted - Waiting to Hear Back")]]), 900, 0),
  # Offer Rejected → closers-chat too (Marco 2026-06-16). Was a no-notify stage;
  # now notifies with a distinct "OFFER REJECTED" message.
  slack("{{4.closersChat}}", M["offerRejected"], F("Offer Rejected", [[eq(STG, "Offer Rejected - Future Follow Up")]]), 900, 60),
  slack("{{4.tc}}", M["contractRequest"], F("Needs Contract", [[eq(STG, "Needs Contract (Automatically Requested To TC)")]]), 900, 120),
  # Contract Sent → closers-chat (Marco 2026-06-16; was tc-to-dos).
  slack("{{4.closersChat}}", M["contractSent"], F("Contract Sent", [[eq(STG, "Contract Sent")]]), 900, 240),
  # Under Contract → {{4.dispo}} = dispo-EXTERNAL-chat in PROD (Marco confirmed).
  slack("{{4.dispo}}", M["underContract"], F("Under Contract", [[eq(STG, "Under Contract")]]), 900, 360),
  slack("{{4.teamWins}}", M["closed"], F("Closed", [[eq(STG, "Closed")]]), 900, 480),
]

webhook = {"id": 1, "module": "gateway:CustomWebHook", "version": 1,
           "parameters": {"hook": None, "maxResults": 1}, "mapper": {}, "metadata": {"designer": {"x": 0, "y": 0}}}

# HTTP GET to FUB. Auth is supplied by a Make "Basic Auth" connection the user
# links on this module (FUB API key = username, blank password) — NOT embedded.
http = {"id": 2, "module": "http:ActionSendData", "version": 3,
        "parameters": {"handleErrors": True, "useNewZLibDeFlate": True},
        "mapper": {"url": "https://api.followupboss.com/v1/people/{{first(1.resourceIds)}}",
                   "method": "get", "headers": [
                       {"name": "X-System", "value": X_SYSTEM}],
                   "qs": [{"name": "fields", "value": "allFields"}],
                   "parseResponse": True, "followRedirect": True, "rejectUnauthorized": True},
        "metadata": {"designer": {"x": 300, "y": 0}}}

ch_raw = [{"name": "MODE", "value": "TEST"}]
for k, (prod, test) in CH.items():
    ch_raw.append({"name": f"{k}_production", "value": prod})
    ch_raw.append({"name": f"{k}_test", "value": test})
setch_raw = {"id": 3, "module": "util:SetVariables", "version": 1, "parameters": {},
             "mapper": {"scope": "roundtrip", "variables": ch_raw}, "metadata": {"designer": {"x": 600, "y": -200}}}

ch_res = [{"name": k, "value": f'{{{{if(3.MODE = "TEST"; 3.{k}_test; 3.{k}_production)}}}}'} for k in CH]
setch_res = {"id": 4, "module": "util:SetVariables", "version": 1, "parameters": {},
             "mapper": {"scope": "roundtrip", "variables": ch_res}, "metadata": {"designer": {"x": 600, "y": 0}}}

fields = [
    {"name": "event", "value": "{{1.event}}"},
    {"name": "stage", "value": "{{2.data.stage}}"},
    {"name": "seller_name", "value": "{{2.data.name}}"},
    # address: adjacency + literal-returning if() so each separator only appears
    # when its part is present; an all-empty address collapses to a clean em-dash
    # instead of bare commas (", ,  "). See patch_partA_fields.py.
    # ifempty(...; "") wraps each part so a NULL address (person with no addresses)
    # normalizes to "" before the `= ""` guard — otherwise null != "" and every
    # separator prints (", ,  "). Empty address collapses to "—". Fixed 2026-06-16.
    {"name": "address", "value": (
        '{{if(ifempty(2.data.addresses[1].street; "") = ""; "—"; "")}}{{ifempty(2.data.addresses[1].street; "")}}'
        '{{if(ifempty(2.data.addresses[1].city; "") = ""; ""; ", ")}}{{ifempty(2.data.addresses[1].city; "")}}'
        '{{if(ifempty(2.data.addresses[1].state; "") = ""; ""; ", ")}}{{ifempty(2.data.addresses[1].state; "")}}'
        '{{if(ifempty(2.data.addresses[1].code; "") = ""; ""; " ")}}{{ifempty(2.data.addresses[1].code; "")}}')},
    {"name": "source", "value": "{{2.data.source}}"},
    {"name": "closer", "value": '{{ifempty(2.data.assignedTo; "")}}'},
    {"name": "lead_manager", "value": '{{ifempty(2.data.customLeadManager; "—")}}'},
    {"name": "link", "value": "https://app.followupboss.com/2/people/view/{{2.data.id}}"},
]
setf = {"id": 5, "module": "util:SetVariables", "version": 1, "parameters": {},
        "mapper": {"scope": "roundtrip", "variables": fields}, "metadata": {"designer": {"x": 600, "y": 200}}}

router = {"id": 6, "module": "builtin:BasicRouter", "version": 1, "mapper": None,
          "metadata": {"designer": {"x": 750, "y": 0}}, "routes": [{"flow": [r]} for r in routes]}

bp = {
    "name": "AHB — Part A: FUB → Slack (built via API)",
    "flow": [webhook, http, setch_raw, setch_res, setf, router],
    "metadata": {"instant": True, "version": 1,
                 "scenario": {"roundtrips": 1, "maxErrors": 3, "autoCommit": True,
                              "sequential": False, "confidential": False, "dataloss": False,
                              "dlq": False, "freshVariables": False},
                 "designer": {"orphans": []}, "zone": "us2.make.com"},
}

out = ROOT / "make" / "_inspect" / "partA_make.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(bp, indent=2), encoding="utf-8")
print("wrote", out, "— modules:", len(bp["flow"]), "routes:", len(routes))
