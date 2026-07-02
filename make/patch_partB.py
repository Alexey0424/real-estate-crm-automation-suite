#!/usr/bin/env python3
"""
patch_partB.py — upgrade Part B (scenario 5390808) to the full SOW spec.

The Apps Script now builds the complete FUB /v1/events JSON (name split, note
composition, empty-field omission, Market/State custom field, tag) and sends it
as `payload` plus a few display fields. So Part B becomes:

  1 webhook → 2 HTTP POST /v1/events (body = {{1.payload}}, relayed) →
  5 SetVariables (MODE) → 6 Slack "New Seller Lead" (Route 1)

Part B posts the New-Lead Slack message ITSELF (SOW §11) so the notification is
guaranteed even though FUB suppresses Part A's webhook for same-system creates.

Surgical: fetches the live blueprint, rewrites module 2's body + drops the stale
filter, appends the SetVariables + Slack modules. Webhook (module 1) untouched.
NOTE: re-verify the FUB Basic auth + link the Slack connection in the UI after.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5390808

NEW_LEADS_PROD = "C0PORTFOL01"   # all-ahb-new-leads
NEW_LEADS_TEST = "C0PORTFOL11"   # staging-ahb-new-leads

# Route 1 message (SOW §11). Lead Manager is "—": cold form leads have no
# appointment-setter assigned yet. Link uses the person id from the events
# response ({{2.data.id}}) — the response is "nearly identical to /v1/people".
SLACK_TEXT = (
    "*New Seller Lead!* :rocket:\n"
    "Marketing Campaign: {{1.source}}\n"
    "Seller Name: {{1.firstName}} {{1.lastName}}\n"
    "Address: {{1.address}}\n"
    "Lead Manager: —\n"
    "FUB Link: https://app.followupboss.com/2/people/view/{{2.data.id}}"
)
SLACK_CHANNEL = f'{{{{if(5.MODE = "TEST"; "{NEW_LEADS_TEST}"; "{NEW_LEADS_PROD}")}}}}'


def patch(path, body):
    url = f"https://{ZONE}.make.com/api/v2{path}"
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="PATCH",
        headers={"Authorization": f"Token {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


code, body = m.call(ZONE, f"/scenarios/{SID}/blueprint")
bp = body["response"]["blueprint"] if "response" in body else body

for mod in bp["flow"]:
    if mod.get("id") == 2:
        mod["mapper"]["data"] = "{{1.payload}}"   # relay the Apps-Script-built body
        mod.pop("filter", None)                    # validation now lives in the form/script

# add a Note with motivation / property type / Market/State / submitted-by (SOW §9
# "appended to Notes"). noteBodyJson is a pre-escaped JSON string → valid JSON body.
# Needs FUB Basic auth set in the UI (same key as the events node).
notes = {"id": 3, "module": "http:ActionSendData", "version": 3,
         "parameters": {"handleErrors": True, "useNewZLibDeCompress": True},
         "mapper": {"url": "https://api.followupboss.com/v1/notes", "method": "post",
                    "headers": [{"name": "X-System", "value": "AHB"}], "qs": [],
                    "bodyType": "raw", "contentType": "application/json",
                    "data": '{"personId": {{2.data.id}}, "body": {{1.noteBodyJson}}}',
                    "parseResponse": True, "followRedirect": True, "rejectUnauthorized": True},
         "metadata": {"designer": {"x": 450, "y": 0}}}
setvars = {"id": 5, "module": "util:SetVariables", "version": 1, "parameters": {},
           "mapper": {"scope": "roundtrip", "variables": [{"name": "MODE", "value": "TEST"}]},
           "metadata": {"designer": {"x": 600, "y": 0}}}
slack = {"id": 6, "module": "slack:CreateMessage", "version": 4, "parameters": {},
         "mapper": {"channel": SLACK_CHANNEL, "text": SLACK_TEXT, "parse": False,
                    "mrkdwn": True, "channelWType": "manualy"},
         "metadata": {"designer": {"x": 900, "y": 0}}}
# keep webhook(1) + events(2, edited above), then note(3) → MODE(5) → Slack(6)
bp["flow"] = [md for md in bp["flow"] if md.get("id") in (1, 2)] + [notes, setvars, slack]

print("flow now:", [(md["id"], md["module"]) for md in bp["flow"]])
c, r = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", c, json.dumps(r)[:160] if isinstance(r, dict) else r[:300])
