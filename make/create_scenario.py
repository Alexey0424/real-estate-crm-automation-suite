#!/usr/bin/env python3
"""
create_scenario.py — create / get / delete a Make scenario via API.
WRITES, but only ever creates NEW scenarios (named explicitly) or deletes ones
created by this tool. Never touches pre-existing scenarios.

  python make/create_scenario.py create <blueprint.json> "<name>"
  python make/create_scenario.py update <scenarioId> <blueprint.json> [hookId]
  python make/create_scenario.py get <scenarioId>
  python make/create_scenario.py delete <scenarioId>

`update` PATCHes an EXISTING scenario's blueprint in place. Pass the webhook hookId
to preserve the already-created webhook URL (sets flow[0].parameters.hook). Only
use on scenarios this tool created.
"""
import sys, json, urllib.request, urllib.error, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZONE = "us2"
TEAM_ID = 1578826


def env(k):
    envf = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in open(envf, encoding="utf-8"):
        s = line.strip()
        for sep in ("=", ":"):
            if s.lower().startswith(k.lower() + sep):
                return s.split(sep, 1)[1].strip()


TOKEN = env("MAKE_API_KEY")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def req(method, path, body=None):
    url = f"https://{ZONE}.make.com/api/v2{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Token {TOKEN}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:600]}


def create(bp_file, name):
    bp = json.loads(pathlib.Path(bp_file).read_text(encoding="utf-8"))
    bp["name"] = name
    body = {
        "blueprint": json.dumps(bp),
        "teamId": TEAM_ID,
        "scheduling": json.dumps({"type": "indefinitely"}),
    }
    code, resp = req("POST", "/scenarios", body)
    print("CREATE:", code, json.dumps(resp)[:700])


def update(sid, bp_file, hook_id=None):
    bp = json.loads(pathlib.Path(bp_file).read_text(encoding="utf-8"))
    if hook_id:  # preserve the already-created webhook URL
        bp["flow"][0].setdefault("parameters", {})["hook"] = int(hook_id)
    body = {"blueprint": json.dumps(bp)}
    code, resp = req("PATCH", f"/scenarios/{sid}", body)
    print("UPDATE:", code, json.dumps(resp)[:700])


def get(sid):
    code, resp = req("GET", f"/scenarios/{sid}")
    print("GET:", code, json.dumps(resp)[:700])


def delete(sid):
    code, resp = req("DELETE", f"/scenarios/{sid}")
    print("DELETE:", code, json.dumps(resp)[:300])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "create":
        create(sys.argv[2], sys.argv[3])
    elif cmd == "update":
        update(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "get":
        get(sys.argv[2])
    elif cmd == "delete":
        delete(sys.argv[2])
