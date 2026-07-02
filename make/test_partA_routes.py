#!/usr/bin/env python3
"""
test_partA_routes.py — live end-to-end test of Part A (scenario 5389041), MODE=TEST.

For each posting route, POST a real FUB person (already AT that stage) to the live
Make webhook, then read the resulting execution from the Make logs API and report:
  status (1 = success)  +  operations (6 = NO route fired; 7 = a Slack route POSTED)

operations==7 AND status==1  ⇒  the chain webhook→FUB GET→fields→router→Slack ran
and the Slack post was accepted (bot in channel, connection valid) for that stage.

READ-ONLY on FUB (we only GET people, never write). The only side effect is the
intended Slack post to the staging-* channels — exactly what we're verifying.
"""
import sys, json, time, urllib.request, urllib.error, importlib.util, pathlib

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone()
SID = 5389041
HOOK = "https://hook.us2.make.com/xxxxxxxxxxxxxxxxxxxxxxxx"

# (route label, person id @ that stage, event, expected staging channel)
CASES = [
    ("New lead",                    265844, "peopleCreated",       "staging-ahb-new-leads"),
    ("Pending Closer Contact (Flora)",265848, "peopleStageUpdated",  "staging-closer-deals-flora"),
    ("Pending Closer Contact (Reyes)", 263394, "peopleStageUpdated",  "staging-closer-deals-reyes"),
    ("Needs Underwriting",          263415, "peopleStageUpdated",  "staging-underwriter-to-dos"),
    ("Closer Needs To Make Offer (Reyes)",263206,"peopleStageUpdated","staging-closer-deals-reyes"),
    ("Offer Submitted",             258872, "peopleStageUpdated",  "staging-closers-chat"),
    ("Offer Rejected (NEW)",        265573, "peopleStageUpdated",  "staging-closers-chat"),
    ("Needs Contract",              112059, "peopleStageUpdated",  "staging-tc-to-dos"),
    ("Contract Sent (CHANGED)",     259649, "peopleStageUpdated",  "staging-closers-chat"),
    ("Under Contract",              263228, "peopleStageUpdated",  "staging-internal-dispo-chat"),
    ("Closed",                      265849, "peopleStageUpdated",  "staging-team-wins"),
]


def post(event, pid):
    body = json.dumps({"event": event, "resourceIds": [pid]}).encode()
    r = urllib.request.Request(HOOK, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": m.UA})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, resp.read().decode()[:40]


def latest_exec_ids(limit=8):
    c, lg = m.call(ZONE, f"/scenarios/{SID}/logs?pg[limit]={limit}")
    out = []
    for x in (lg.get("scenarioLogs") or []):
        if x.get("eventType") == "EXECUTION_END":
            out.append((x["id"], x.get("status"), x.get("operations"), x.get("centicredits")))
    return out


def wait_for_new(seen, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for eid, st, ops, cc in latest_exec_ids():
            if eid not in seen:
                seen.add(eid)
                return eid, st, ops, cc
        time.sleep(2)
    return None, None, None, None


seen = {e[0] for e in latest_exec_ids(20)}
print(f"{'ROUTE':34} {'POST':>5}  {'exec':>6} {'ops':>4} {'verdict'}")
results = []
for label, pid, event, ch in CASES:
    code, _ = post(event, pid)
    eid, st, ops, cc = wait_for_new(seen)
    if eid is None:
        verdict = "TIMEOUT (no execution seen)"
    elif st != 1:
        verdict = f"NOTE: EXEC ERROR status={st} ops={ops}"
    elif ops and ops >= 7:
        verdict = f"[x] POSTED → {ch}"
    else:
        verdict = f"[ ] NO ROUTE FIRED (ops={ops})"
    results.append((label, ch, code, st, ops, verdict))
    print(f"{label:34} {code:>5}  {ops if ops else '—':>4}  {verdict}")

print("\n--- SUMMARY ---")
ok = sum(1 for r in results if r[5].startswith("[x]"))
print(f"{ok}/{len(results)} routes posted successfully")
for label, ch, code, st, ops, verdict in results:
    if not verdict.startswith("[x]"):
        print("  NEEDS ATTENTION:", label, "->", verdict)
