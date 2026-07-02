#!/usr/bin/env python3
"""
build_make_partC.py — generate the Make blueprint for Scenario C
(**JustCall → Follow Up Boss** call + text mirror).  Migrated from Quo/OpenPhone
2026-06-18 — see docs/architecture.md + docs/architecture.md.

Goal (Marco, 2026-06-18): mirror JustCall **calls** and **text messages** into FUB so
the CRM stays CLEAN and minimal:
  • texts show clean (from number, to number, message body — nothing else)
  • calls show clean (logged call + recording on the call)
  • NO transcript notes (they bury the closers' own notes)
  • the AI summary goes ONTO the logged call's note (appended, coexists with closer notes)

Why JustCall is simpler than the old Quo build: JustCall's `call.completed` webhook
carries everything inline — direction, both numbers, duration, the recording URL, and
the agent (id/name/email). So this build DROPS the Quo `participants[]` guessing, the
46-number `ahb` list, the separate recording-lookup route, the transcript aggregator,
and the phoneNumberId→user map. There is NO live JustCall API call at runtime — the
scenario is purely webhook → FUB.

Part C now OWNS the FUB call note (native JustCall call-logging is DISABLED in the
JustCall account so there are no duplicates). The note mimics native's format MINUS the
5 lines Marco's boss dropped (Call ID, Call Duration, Date & Time, Assigned To, Call
Recording). Text logging stays with JustCall's native integration (Part C's text route
was removed — FUB 403s a 2nd integration's POST /v1/textMessages).

SINGLE-STEP (the AI event carries call_info + call_duration + agent + justcall_ai, so one
POST writes the whole note). The earlier two-step (basic at call.completed, then PUT-enrich
matched to "most recent call") was REPLACED 2026-06-24: a delayed/out-of-order AI event
matched the WRONG call and overwrote it (erased a real Call Score). Now each AI event makes
ONE self-contained call → nothing can clobber another. Trade-off: a call appears ~1-2 min
after it ends (when AI fires); voicemail/unanswered calls still fire an AI event so they ARE
logged, but a pure ring-no-answer (no voicemail, no AI event) is not.

Flow:
  1 gateway:CustomWebHook   — JustCall event ({{1.type}}, fields under {{1.data.*}})
  2 util:SetVariables (raw) — MODE + computed fields (leadPhone, direction, from/to,
                              duration, closerUid via agent_email→FUB userId)
  3 util:SetVariables (res) — note pieces: leadName, aiSummary, uidFrag, and conditional
                              scoreFrag/topicsFrag/sentimentFrag/transcriptFrag
                              (each "\n<Label>: <value>" when present)
  4 Route [jc.call_ai_generated | sd.call_ai_generated, summary present]:
        GET /v1/people?phone → router(Existing: POST /v1/calls (full note)
                                      New: POST /v1/events + POST /v1/calls (full note))
        Note = Called on/via + Call Score + Topics (join call_moments) + Customer
        Sentiments + transcription link (from call_sid) + JustCall's verbatim summary
        (bundles Action Items). "Interactivity" is NOT in the webhook (only the REST
        API's interaction_stats) → omitted.

SECURITY: no secrets embedded. FUB auth = inline mapper.authUser, injected at runtime by
make/inject_keys.py (key = User name, blank password). Only the non-secret X-System label
is embedded. Full-overwrite via create_scenario.py wipes inline auth → ALWAYS re-run
inject_keys.py after updating.
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FUB = "https://api.followupboss.com/v1"


def env(k):
    f = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        for sep in ("=", ":"):
            if s.lower().startswith(k.lower() + sep):
                return s.split(sep, 1)[1].strip()
    return None


X_SYSTEM = env("FUB_X_SYSTEM_PARTC") or "JustCall Phone Sync"
HDRS = [{"name": "X-System", "value": X_SYSTEM}]

# Make's per-module parameter SCHEMA (expect/restore/parameters) — required for the
# scenario to validate. Extracted once from a known-good live module (schema only, no
# secrets) into make/partC_http_templates.json. GET vs POST/PUT differ (POST carries the
# body/contentType fields). Without these blocks Make flags the scenario isinvalid.
_TPL = json.loads((ROOT / "make" / "partC_http_templates.json").read_text(encoding="utf-8"))


def _meta(method, name):
    t = _TPL["get"] if method == "get" else _TPL["post"]
    return {"expect": t["expect"], "restore": t["restore"], "advanced": True,
            "parameters": t["parameters"], "designer": {"x": 0, "y": 0, "name": name}}

# agent_email (JustCall) → FUB userId. Emails match 1:1 between JustCall and FUB
# (verified live 2026-06-18). Used to attribute the logged call to the right closer.
AGENT_MAP = {
    "reyes@acmehomebuyers.example": 80, "flora@acmehomebuyers.example": 79,
    "hank@acmehomebuyers.example": 82, "marco@acmehomebuyers.example": 1,
    "ethan@acmehomebuyers.example": 81, "pam@acmehomebuyers.example": 83,
    "tc@acmehomebuyers.example": 77, "alexey@acmehomebuyers.example": 78,
}

_id = 0
def nid():
    global _id; _id += 1; return _id


def san_inner(src):
    """Make formula (no braces) that strips " and newlines from a free-text field so it
    can be embedded inside a hand-built JSON string body. ifempty() guard so a missing
    field yields "" (Make if() evaluates all branches eagerly). Uses the 2.q literal-quote
    var for the quote match."""
    safe = 'ifempty(' + src + '; "")'
    return 'replace(replace(' + safe + '; 2.q; "\'"); "/[\\n\\r]+/g"; " ")'


def san_lines(src):
    """Like san_inner but PRESERVES line breaks: each run of real newlines becomes a
    literal "\\n" (backslash-n text). The regex pattern's \\n/\\r match actual newline
    chars; the replacement "\\n" is literal text (Make doesn't interpret escapes) → it
    reaches FUB's JSON parser as \\n and renders as a line break. Used for action items
    so each item lands on its own line instead of running together."""
    safe = 'ifempty(' + src + '; "")'
    return 'replace(replace(' + safe + '; 2.q; "\'"); "/[\\n\\r]+/g"; "\\n")'


def switch_expr(src, mapping, default='""'):
    """Build a Make switch(src; k1;v1; k2;v2; …; default) expression."""
    parts = [src]
    for k, v in mapping.items():
        parts.append('"%s"' % k)
        parts.append(str(v))
    parts.append(default)
    return "switch(" + ";".join(parts) + ")"


# direction is at call_info.direction for calls, data.direction for SMS → coalesce.
DIR = 'ifempty(1.data.call_info.direction; ifempty(1.data.direction; ""))'

# ── filters / operators ─────────────────────────────────────────────────
def eqcs(a, b):  return {"a": a, "b": b, "o": "text:equal"}
def exist(a):    return {"a": a, "o": "exist"}
def F(name, conds): return {"name": name, "conditions": conds}
TYPE = "{{1.type}}"


# ── HTTP module helpers ─────────────────────────────────────────────────
# Full mapper field set + metadata.advanced=true, matching the live working modules.
# `advanced: true` exposes the inline Basic-auth fields (authUser/authPass) so Make
# treats the module's auth as configured (otherwise the scenario is flagged invalid).
# authUser is left "" — inject_keys.py fills it at runtime.
def _base_mapper(url, method):
    return {"ca": "", "url": url, "gzip": True, "method": method, "headers": HDRS,
            "qs": [], "timeout": "", "useMtls": False, "authPass": "", "authUser": "",
            "bodyType": "", "serializeUrl": False, "shareCookies": False,
            "parseResponse": True, "followRedirect": True, "useQuerystring": False,
            "followAllRedirects": False, "rejectUnauthorized": True}


def http_get(url, qs, filt=None, name="HTTP GET"):
    mp = _base_mapper(url, "get"); mp["qs"] = qs
    n = {"id": nid(), "module": "http:ActionSendData", "version": 3,
         "parameters": {"handleErrors": True, "useNewZLibDeCompress": True},
         "mapper": mp, "metadata": _meta("get", name)}
    if filt:
        n["filter"] = filt
    return n


def get_people(filt):
    return http_get(f"{FUB}/people",
                    [{"name": "phone", "value": "{{2.leadPhone}}"},
                     {"name": "fields", "value": "id,name"},
                     {"name": "limit", "value": "1"}], filt,
                    name="Find FUB contact by phone")


def http_send(url, method, body, filt=None, name="HTTP"):
    mp = _base_mapper(url, method)
    mp.update({"bodyType": "raw", "contentType": "application/json", "data": body})
    n = {"id": nid(), "module": "http:ActionSendData", "version": 3,
         "parameters": {"handleErrors": True, "useNewZLibDeCompress": True},
         "mapper": mp, "metadata": _meta(method, name)}
    if filt:
        n["filter"] = filt
    return n


def events_create(tag, filt=None):
    """POST /v1/events — create+dedupe the person. firstName = JustCall contact_name if
    known, else the phone number (so FUB shows something until the lead is named)."""
    body = ('{"source":"JustCall","system":"AHB","type":"General Inquiry",'
            '"person":{"firstName":"{{3.leadName}}",'
            '"lastName":"","stage":"Lead","tags":["' + tag + '"],'
            '"phones":[{"value":"{{2.leadPhone}}"}]}}')
    return http_send(f"{FUB}/events", "post", body, filt, name="Create FUB contact")


def calls_body(pid):
    # SINGLE-STEP: the full enriched note is built right here, on the jc.call_ai_generated
    # event, so each AI event creates ONE self-contained call. (The old two-step matched
    # "most recent call for the person" and a delayed/out-of-order AI event could overwrite
    # the WRONG call — that bug erased a real Call Score, 2026-06-24.) Boss's format;
    # Score/Topics/Sentiment lines appear only when present. recordingUrl NOT set (boss
    # dropped it). uidFrag adds userId (agent). outcome omitted (FUB 400s on bad enum).
    # Boss dropped "Called on" + "Called via" (2026-06-25) → note now starts at the first
    # present fragment. Fragments carry a TRAILING "\n" (not leading) so there's no blank
    # leading line; aiSummary comes last with no trailing newline.
    note = ('{{3.scoreFrag}}{{3.topicsFrag}}{{3.sentimentFrag}}{{3.transcriptFrag}}'
            '{{3.aiSummary}}')
    return ('{"personId":' + pid + ',"phone":"{{2.leadPhone}}",'
            '"isIncoming":{{2.isIncoming}},"duration":{{2.duration}},'
            '"fromNumber":"{{2.fromNumber}}","toNumber":"{{2.toNumber}}",'
            '"note":"' + note + '"{{3.uidFrag}}}')


# ── module 1: webhook ────────────────────────────────────────────────────
# Needs its parameter SCHEMA (metadata.parameters) + restore for the scenario to
# validate — same reason the http modules need metadata.expect.
# interface = the JustCall webhook data shape (so downstream {{1.data.*}} references
# resolve in the editor). Covers the fields we read across call/AI/SMS events.
_WH_INTERFACE = [
    {"name": "request_id", "type": "text"},
    {"name": "type", "type": "text"},
    {"name": "data", "type": "collection", "spec": [
        {"name": "id", "type": "number"},
        {"name": "call_sid", "type": "text"},
        {"name": "contact_number", "type": "text"},
        {"name": "contact_name", "type": "text"},
        {"name": "justcall_number", "type": "text"},
        {"name": "agent_id", "type": "number"},
        {"name": "agent_name", "type": "text"},
        {"name": "agent_email", "type": "text"},
        {"name": "direction", "type": "text"},
        {"name": "call_info", "type": "collection", "spec": [
            {"name": "direction", "type": "text"},
            {"name": "type", "type": "text"},
            {"name": "disposition", "type": "text"},
            {"name": "notes", "type": "text"},
            {"name": "recording", "type": "text"},
            {"name": "voicemail_transcription", "type": "text"}]},
        {"name": "call_duration", "type": "collection", "spec": [
            {"name": "total_duration", "type": "number"},
            {"name": "friendly_duration", "type": "text"}]},
        {"name": "sms_info", "type": "collection", "spec": [
            {"name": "body", "type": "text"},
            {"name": "is_mms", "type": "text"}]},
        {"name": "justcall_ai", "type": "collection", "spec": [
            {"name": "call_summary", "type": "text"},
            {"name": "action_items", "type": "text"},
            {"name": "customer_sentiment", "type": "text"}]},
    ]},
]
webhook = {"id": nid(), "module": "gateway:CustomWebHook", "version": 1,
           "parameters": {"hook": None, "maxResults": 1}, "mapper": {},
           "metadata": {
               "restore": {"parameters": {"hook": {"data": {"editable": "true"},
                                                   "label": "JustCall Part C"}}},
               "parameters": [
                   {"name": "hook", "type": "hook:gateway-webhook", "label": "Webhook",
                    "required": True},
                   {"name": "maxResults", "type": "number",
                    "label": "Maximum number of results"}],
               "interface": _WH_INTERFACE,
               "designer": {"x": 0, "y": 0, "name": "JustCall webhook (calls + texts + AI)"}}}

# ── module 2: raw computed vars ──────────────────────────────────────────
raw_vars = [
    {"name": "MODE", "value": "TEST"},
    {"name": "q", "value": '"'},
    {"name": "dirLabel", "value": "{{%s}}" % DIR},
    {"name": "leadPhone", "value": "{{1.data.contact_number}}"},
    {"name": "isIncoming", "value": '{{if(%s = "Incoming"; true; false)}}' % DIR},
    {"name": "fromNumber", "value": '{{if(%s = "Incoming"; 1.data.contact_number; 1.data.justcall_number)}}' % DIR},
    {"name": "toNumber", "value": '{{if(%s = "Incoming"; 1.data.justcall_number; 1.data.contact_number)}}' % DIR},
    {"name": "duration", "value": "{{ifempty(1.data.call_duration.total_duration; 0)}}"},
    {"name": "recUrl", "value": '{{ifempty(1.data.call_info.recording; "")}}'},
    {"name": "closerUid", "value": "{{%s}}" % switch_expr('lower(ifempty(1.data.agent_email; ""))', AGENT_MAP)},
]
setraw = {"id": nid(), "module": "util:SetVariables", "version": 1, "parameters": {},
          "mapper": {"scope": "roundtrip", "variables": raw_vars},
          "metadata": {"designer": {"x": 0, "y": 0, "name": "Parse JustCall fields"}}}

# ── module 3: resolved call-note pieces (sanitized) + JSON fragments ──────
# Part C now OWNS the FUB call note (native JustCall call-logging is turned off in the
# JustCall account). The note mimics native's format MINUS the 5 lines the boss dropped
# (Call ID, Call Duration, Date & Time, Assigned To, Call Recording). Two-step:
#   • call.completed     → POST /v1/calls with the BASIC note (Called on / Called via),
#                          so EVERY call (incl. pure missed, which never gets an AI event)
#                          appears in the Calls tab immediately.
#   • jc.call_ai_generated → PUT the ENRICHED note (adds Call Score / Topics / Sentiment
#                          / transcription link / summary+action-items) onto that call.
# Newlines are literal "\n" (Make doesn't interpret escapes → FUB's JSON parser resolves
# them). Free-text via san_inner; the summary via san_lines (keeps its 1./2./3. lines).
lead_name_var = '{{' + san_inner('ifempty(1.data.contact_name; 2.leadPhone)') + '}}'
uid_frag = ('{{if(ifempty(2.closerUid; "") = ""; ""; "," + 2.q + "userId" + 2.q + ":" + 2.closerUid)}}')
ai_summary_var = '{{' + san_lines('1.data.justcall_ai.call_summary') + '}}'

# Note fragments. Each = "<Label>: <value>\n" when present, else "". TRAILING "\n"
# (not leading) so the first present line has no blank line above it — needed now that
# "Called on"/"Called via" are gone (boss, 2026-06-25). transcript is always present, so
# it always supplies the newline before the summary.
# NOTE: "Interactivity" is NOT in the jc.call_ai_generated webhook (only JustCall's REST
# API has interaction_stats) → omitted. Add a JustCall GET if the boss requires it.
_topics = san_inner('join(1.data.justcall_ai.call_moments; ", ")')
_sent = san_inner('1.data.justcall_ai.customer_sentiment')
score_frag = ('{{if(ifempty(1.data.justcall_ai.call_score; "0") = "0"; ""; '
              '"Call Score: " + 1.data.justcall_ai.call_score + "\\n")}}')
topics_frag = '{{if(' + _topics + ' = ""; ""; "Topics: " + ' + _topics + ' + "\\n")}}'
sentiment_frag = '{{if(' + _sent + ' = ""; ""; "Customer Sentiments: " + ' + _sent + ' + "\\n")}}'
transcript_frag = ('{{"JustCall AI Transcription: '
                   'https://iq-app.justcall.io/app/voicetranscript?sid=" + 1.data.call_sid + "\\n"}}')

res_vars = [
    {"name": "leadName", "value": lead_name_var},
    {"name": "uidFrag", "value": uid_frag},
    {"name": "aiSummary", "value": ai_summary_var},
    {"name": "scoreFrag", "value": score_frag},
    {"name": "topicsFrag", "value": topics_frag},
    {"name": "sentimentFrag", "value": sentiment_frag},
    {"name": "transcriptFrag", "value": transcript_frag},
]
setres = {"id": nid(), "module": "util:SetVariables", "version": 1, "parameters": {},
          "mapper": {"scope": "roundtrip", "variables": res_vars},
          "metadata": {"designer": {"x": 0, "y": 0, "name": "Build note / text bodies"}}}


# ── Route: AI call (jc.call_ai_generated | sd.call_ai_generated) ─────────
# SINGLE-STEP. Fires on the AI event (which carries call_info + call_duration + agent +
# justcall_ai), so one self-contained POST /v1/calls writes the whole boss-format note.
# No "find the most recent call" matching → a delayed/out-of-order AI event can never
# overwrite a different call (the bug that erased a Call Score, 2026-06-24).
def ai_route():
    ai_filter = F("AI call", [
        [eqcs(TYPE, "jc.call_ai_generated"), exist("{{1.data.justcall_ai.call_summary}}")],
        [eqcs(TYPE, "sd.call_ai_generated"), exist("{{1.data.justcall_ai.call_summary}}")],
    ])
    get = get_people(ai_filter)
    matched = "{{%d.data.people[1].id}}" % get["id"]
    exist_f = F("Existing person", [[exist(matched)]])
    new_f = F("New person", [[{"a": matched, "o": "notexist"}]])
    log_existing = http_send(f"{FUB}/calls", "post", calls_body(matched), exist_f,
                             name="Log call to FUB (existing)")
    create = events_create("JustCall Call", new_f)
    new_pid = "{{%d.data.id}}" % create["id"]
    log_new = http_send(f"{FUB}/calls", "post", calls_body(new_pid),
                        name="Log call to FUB (new contact)")
    sub = {"id": nid(), "module": "builtin:BasicRouter", "version": 1, "mapper": None,
           "metadata": {"designer": {"x": 0, "y": 0, "name": "Person exists?"}},
           "routes": [{"flow": [log_existing]}, {"flow": [create, log_new]}]}
    return [get, sub]


# NOTE: only the AI-event route remains.
#  • call.completed is NO LONGER logged on its own → a call appears once JustCall's AI
#    fires (~1-2 min after the call). Calls that reach voicemail still fire an AI event
#    (so they ARE logged); a pure ring-no-answer with no voicemail won't be logged.
#  • Text route REMOVED — native JustCall owns texts (FUB 403s a 2nd integration).
flow = [webhook, setraw, setres] + ai_route()

bp = {
    "name": "AHB — Part C: JustCall → FUB call + text mirror (built via API)",
    "flow": flow,
    "metadata": {"instant": True, "version": 1,
                 "scenario": {"roundtrips": 1, "maxErrors": 3, "autoCommit": True,
                              "sequential": False, "confidential": False,
                              "dataloss": False, "dlq": False, "freshVariables": False},
                 "designer": {"orphans": []}, "zone": "us2.make.com"},
}

out = ROOT / "make" / "_inspect" / "partC_make.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(bp, indent=2), encoding="utf-8")
print("wrote", out, "- single-step: AI event -> POST /v1/calls (full note) - module ids:", _id)
