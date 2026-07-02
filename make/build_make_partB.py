#!/usr/bin/env python3
"""
build_make_partB.py — generate the Make blueprint for Scenario B
(Cold-lead Google Form → FUB), full SOW spec.

Flow (3 modules):
  1 gateway:CustomWebHook  — receives the Apps-Script payload:
        { payload: "<full FUB /v1/events JSON string>", noteBodyJson,
          firstName, lastName, source, address, leadManager }
  2 http:ActionSendData    — POST https://api.followupboss.com/v1/events
        body = {{1.payload}} (relayed verbatim — Apps Script already mapped every
        SOW field: name split, address, phone, email, source=campaign,
        customLeadManager, tag "Cold Lead - SMS", stage Lead, note)
  3 http:ActionSendData    — POST https://api.followupboss.com/v1/notes
        intake note ({{1.noteBodyJson}}) attached to {{2.data.id}}

Why /v1/events: FUB's documented lead-ingestion endpoint — dedupes by phone/email
and fires automations (fulfils SOW §10's dedup/"update existing" intent natively).

NOTE: Part B does NOT post Slack. Originally it did, on the premise that "FUB suppresses
Part A's webhook for same-system creates" — but that premise was DISPROVEN live
(2026-06-17): Part A's `peopleCreated` webhook fires fine on a Part-B-created person,
so a Part B Slack post was a DOUBLE notification. Part A is the single new-lead
notifier (it has the authoritative FUB record). The Slack + SetVariables modules were
removed via make/patch_partB_remove_slack.py; this generator matches that end state.

SECURITY: FUB API key is NOT embedded — user sets HTTP Basic auth (User name = key)
in the UI. Writes make/_inspect/partB_make.json.
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _env(k):
    f = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    if not f.exists():
        return None
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.lower().startswith(k.lower() + "="):
            return s.split("=", 1)[1].strip()
    return None


# FUB integration display name shown on records this scenario creates (non-secret).
X_SYSTEM = _env("FUB_X_SYSTEM_PARTB") or "SMS Lead Intake"

webhook = {"id": 1, "module": "gateway:CustomWebHook", "version": 1,
           "parameters": {"hook": None, "maxResults": 1}, "mapper": {},
           "metadata": {"designer": {"x": 0, "y": 0}}}

# POST relayed payload to FUB /v1/events. Basic auth set in the UI (User name = key).
http = {"id": 2, "module": "http:ActionSendData", "version": 3,
        "parameters": {"handleErrors": True, "useNewZLibDeCompress": True},
        "mapper": {"url": "https://api.followupboss.com/v1/events",
                   "method": "post",
                   "headers": [{"name": "X-System", "value": X_SYSTEM}],
                   "qs": [],
                   "bodyType": "raw",
                   "contentType": "application/json",
                   "data": "{{1.payload}}",
                   "parseResponse": True, "followRedirect": True,
                   "rejectUnauthorized": True},
        "metadata": {"designer": {"x": 300, "y": 0}}}

# Note with motivation / property type / Market/State / submitted-by (SOW §9). The
# Apps Script sends noteBodyJson as a pre-escaped JSON string so the body is valid.
# Needs FUB Basic auth in the UI (same key as the events node).
notes = {"id": 3, "module": "http:ActionSendData", "version": 3,
         "parameters": {"handleErrors": True, "useNewZLibDeCompress": True},
         "mapper": {"url": "https://api.followupboss.com/v1/notes", "method": "post",
                    "headers": [{"name": "X-System", "value": X_SYSTEM}], "qs": [],
                    "bodyType": "raw", "contentType": "application/json",
                    "data": '{"personId": {{2.data.id}}, "body": {{1.noteBodyJson}}}',
                    "parseResponse": True, "followRedirect": True, "rejectUnauthorized": True},
         "metadata": {"designer": {"x": 450, "y": 0}}}

bp = {
    "name": "AHB — Part B: Cold-Lead Form → FUB (built via API)",
    "flow": [webhook, http, notes],
    "metadata": {"instant": True, "version": 1,
                 "scenario": {"roundtrips": 1, "maxErrors": 3, "autoCommit": True,
                              "sequential": False, "confidential": False,
                              "dataloss": False, "dlq": False, "freshVariables": False},
                 "designer": {"orphans": []}, "zone": "us2.make.com"},
}

out = ROOT / "make" / "_inspect" / "partB_make.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(bp, indent=2), encoding="utf-8")
print("wrote", out, "— modules:", len(bp["flow"]))
