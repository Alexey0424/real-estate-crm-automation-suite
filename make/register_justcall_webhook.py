#!/usr/bin/env python3
"""
register_justcall_webhook.py — register / list / delete JustCall webhooks that feed
Make Part C (JustCall → FUB call + text mirror). Replaces register_quo_webhook.py.

NOTE: WRITES TO THE LIVE JUSTCALL ACCOUNT. Run only after the Make Part-C webhook URL
exists and Alexey/Marco approve.

JustCall v2.1: base https://api.justcall.io/v2.1 · auth = "api_key:api_secret" RAW in the
Authorization header (NOT Bearer, NOT Basic). One webhook = one event TYPE; all point at
the SAME Make URL; the Part C scenario routes by {{1.type}}.

Topics we need (Part C):
  call.completed          — log the call (clean note + recording)
  jc.call_ai_generated    — append the AI summary to the logged call's note
  sms.received, sms.sent  — log texts (clean: from, to, body)
  sd.call_completed, sd.call_ai_generated — Sales Dialer equivalents (same payload shape)

Usage (reads JUSTCALL_API_KEY/SECRET from ../.env):
  python make/register_justcall_webhook.py setup <https-make-url>   # register all 6
  python make/register_justcall_webhook.py add <type> <https-url>   # register one
  python make/register_justcall_webhook.py --list
  python make/register_justcall_webhook.py --delete <id>
"""
import os, sys, json, pathlib, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST = "https://api.justcall.io/v2.1"
TOPICS = ["call.completed", "jc.call_ai_generated", "sms.received", "sms.sent",
          "sd.call_completed", "sd.call_ai_generated"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def env(key):
    f = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        for sep in ("=", ":"):
            if s.lower().startswith(key.lower() + sep):
                return s.split(sep, 1)[1].strip()
    return None


KEY = os.environ.get("JUSTCALL_API_KEY") or env("JUSTCALL_API_KEY")
SECRET = os.environ.get("JUSTCALL_API_SECRET") or env("JUSTCALL_API_SECRET")
AUTH = f"{KEY}:{SECRET}" if KEY and SECRET else None


def req(method, path, body=None):
    if not AUTH:
        sys.exit("Missing JUSTCALL_API_KEY / JUSTCALL_API_SECRET (in .env or env).")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{HOST}{path}", data=data, method=method, headers={
        "Authorization": AUTH, "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:500]}
    except Exception as e:  # noqa
        return None, {"_err": str(e)}


def add(topic, url):
    if not url.startswith("https://"):
        sys.exit("URL must be HTTPS (the Make Part-C webhook URL)")
    code, body = req("POST", "/webhooks", {"webhook_url": url, "type": topic})
    ok = code in (200, 201)
    print(f"  {topic:24} -> HTTP {code} {'OK' if ok else json.dumps(body)[:200]}")
    return ok


def main():
    if "--list" in sys.argv:
        print("LIST:", *(json.dumps(x, indent=2)[:2500] for x in req("GET", "/webhooks")))
        return
    if "--delete" in sys.argv:
        wid = sys.argv[sys.argv.index("--delete") + 1]
        print("DELETE:", *req("DELETE", f"/webhooks/{wid}"))
        return
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup":
        url = sys.argv[2]
        print(f"Registering {TOPICS} -> {url}")
        for t in TOPICS:
            add(t, url)
        print("Done. Check `--list`. (sd.* may error if Sales Dialer isn't enabled — harmless.)")
        return
    if cmd == "add" and len(sys.argv) >= 4:
        add(sys.argv[2], sys.argv[3])
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
