#!/usr/bin/env python3
"""
inject_keys.py — inject API keys into Part C (scenario 5396442) nodes via the Make API,
so the user never has to paste them in the UI (standing instruction).

Reads keys from .env at RUNTIME and PATCHes them straight into the live blueprint:
  • Quo node(s) (http to api.quo.com)  -> raw `Authorization` header = QUO_APY_KEY
  • FUB node(s) (http to followupboss) -> mapper.authUser = FUB_API_KEY (only if blank;
    existing inline keys are left as-is)

SECURITY: the key is never printed, never written to a repo file, never committed —
it flows from .env -> memory -> the PATCH body to Make only.

  python make/inject_keys.py [scenarioId]   # default 5396442
"""
import sys, json, urllib.request, urllib.error, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZONE = "us2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def env(k):
    f = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        for sep in ("=", ":"):
            if s.lower().startswith(k.lower() + sep):
                return s.split(sep, 1)[1].strip()


TOKEN = env("MAKE_API_KEY")
QUO = env("QUO_APY_KEY") or env("QUO_API_KEY")
FUB = env("FUB_API_KEY")
# JustCall REST auth = "api_key:api_secret" raw in the Authorization header.
_JC_K = env("JUSTCALL_API_KEY")
_JC_S = env("JUSTCALL_API_SECRET")
JUSTCALL = f"{_JC_K}:{_JC_S}" if _JC_K and _JC_S else None


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
        return e.code, {"_err": e.read().decode()[:400]}


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else "5396442"
    code, body = req("GET", f"/scenarios/{sid}/blueprint")
    if code != 200:
        sys.exit(f"GET blueprint failed: {code} {body}")
    bp = body["response"]["blueprint"]
    touched = []

    def walk(flow):
        for m in flow:
            if m.get("module") == "http:ActionSendData":
                mp = m.get("mapper", {})
                url = mp.get("url", "")
                nm = m.get("metadata", {}).get("designer", {}).get("name", m.get("id"))
                if "api.quo.com" in url or "api.openphone.com" in url:
                    if QUO:
                        for h in mp.get("headers", []):
                            if h.get("name", "").lower() == "authorization":
                                h["value"] = QUO
                                touched.append(f"Quo key -> #{m.get('id')} {nm}")
                elif "api.justcall.io" in url:
                    if JUSTCALL:
                        for h in mp.get("headers", []):
                            if h.get("name", "").lower() == "authorization":
                                h["value"] = JUSTCALL
                                touched.append(f"JustCall key -> #{m.get('id')} {nm}")
                elif "followupboss.com" in url:
                    if FUB and not mp.get("authUser"):
                        mp["authUser"] = FUB
                        touched.append(f"FUB key -> #{m.get('id')} {nm} (was blank)")
            for rt in m.get("routes", []) or []:
                walk(rt.get("flow", []))

    walk(bp.get("flow", []))
    if not touched:
        print("Nothing to inject (all keys already present)."); return
    for t in touched:
        print(" ", t)
    code, resp = req("PATCH", f"/scenarios/{sid}", {"blueprint": json.dumps(bp)})
    s = resp.get("scenario", {})
    print("UPDATE:", code, "isinvalid=", s.get("isinvalid"),
          "islinked=", s.get("islinked"), "hookId=", s.get("hookId"))
    if code != 200:
        print("ERR:", json.dumps(resp)[:400])


if __name__ == "__main__":
    main()
