#!/usr/bin/env python3
"""
tidy_layout.py — neatly auto-position the modules of a Make scenario.

SURGICAL: fetches the LIVE blueprint, rewrites ONLY each module's
metadata.designer x/y (left-to-right columns, router routes spread vertically),
and PATCHes it back. Everything else — connections, inline auth, the webhook hook,
mappers — is preserved untouched. The blueprint is never written to disk (so no
secrets land in a repo file).

  python make/tidy_layout.py <scenarioId>
"""
import sys, json, urllib.request, urllib.error, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZONE = "us2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
COL = 320  # horizontal gap between columns


def env(k):
    f = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        for sep in ("=", ":"):
            if s.lower().startswith(k.lower() + sep):
                return s.split(sep, 1)[1].strip()


TOKEN = env("MAKE_API_KEY")


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
        return e.code, {"_err": e.read().decode()[:500]}


def label_for(m):
    """Derive a human-readable node name from what the module does / touches."""
    mod = m.get("module", "")
    mp = m.get("mapper") or {}
    if mod == "gateway:CustomWebHook":
        return "Quo webhook (calls + messages)"
    if mod == "util:SetVariables":
        names = [v.get("name") for v in mp.get("variables", [])]
        if "leadPhone" in names:
            return "Parse Quo fields (direction, phone, duration)"
        if "noteBody" in names or "textBody" in names:
            return "Build note / text bodies (sanitized)"
        return "Set variables"
    if mod == "builtin:BasicRouter":
        cond = "".join(json.dumps((rt.get("flow") or [{}])[0].get("filter", {}))
                       for rt in m.get("routes", []))
        if "people[1].id" in cond:
            return "Person exists in FUB?"
        return "Route by event type"
    if mod == "http:ActionSendData":
        url, method = mp.get("url", ""), mp.get("method", "")
        new = ".data.id}" in (mp.get("data") or "")  # personId from POST /events
        tag = " (new contact)" if new else " (existing)"
        if method == "get" and "/people" in url:
            return "Find FUB contact by phone"
        if "/events" in url:
            return "Create FUB contact (tag Quo Call)"
        if "/calls" in url:
            return "Log call to FUB" + tag
        if "/notes" in url:
            return "Add note: recording / transcript / summary"
        if "/textMessages" in url:
            return "Log SMS to FUB" + tag
        return "HTTP request"
    return mod


def layout(flow, x, y, dy):
    """Place each module in a column at `x`; a router's routes fan out vertically
    around the router's own y with total span `dy`, and recurse one column right.
    Also sets a descriptive node name (metadata.designer.name)."""
    cx = x
    for m in flow:
        d = m.setdefault("metadata", {}).setdefault("designer", {})
        d["x"], d["y"] = cx, y
        d["name"] = label_for(m)
        routes = m.get("routes")
        if routes:
            n = len(routes)
            top = y - dy * (n - 1) / 2.0
            child_dy = dy / max(1, n)
            for i, rt in enumerate(routes):
                layout(rt.get("flow", []), cx + COL, int(top + i * dy), child_dy)
        cx += COL


def main():
    sid = sys.argv[1]
    code, body = req("GET", f"/scenarios/{sid}/blueprint")
    if code != 200:
        sys.exit(f"GET blueprint failed: {code} {body}")
    bp = body["response"]["blueprint"]
    layout(bp.get("flow", []), 0, 0, 900)
    code, resp = req("PATCH", f"/scenarios/{sid}", {"blueprint": json.dumps(bp)})
    s = resp.get("scenario", {})
    print("UPDATE:", code, "isinvalid=", s.get("isinvalid"),
          "islinked=", s.get("islinked"), "hookId=", s.get("hookId"))


if __name__ == "__main__":
    main()
