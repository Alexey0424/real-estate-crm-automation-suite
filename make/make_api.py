#!/usr/bin/env python3
"""
make_api.py — thin Make.com API helper + discovery. READ-ONLY by default.
Reads MAKE_API_KEY (and optional MAKE_ZONE) from ../.env.txt.

Usage:
  python make/make_api.py discover                 # find zone, orgs, teams
  python make/make_api.py scenarios <teamId>       # list scenarios in a team
  python make/make_api.py blueprint <scenarioId>   # dump a scenario blueprint
Creating scenarios is done by a separate explicit script — this one never writes.
"""
import sys, json, urllib.request, urllib.error, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZONES = ["us1", "us2", "eu1", "eu2"]


def env(key):
    f = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        for sep in ("=", ":"):
            if s.lower().startswith(key.lower() + sep):
                return s.split(sep, 1)[1].strip()
    return None


TOKEN = env("MAKE_API_KEY") or env("MAKE_API_TOKEN")


# Cloudflare in front of the Make API blocks the default Python UA (error 1010) —
# send a normal browser UA.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def call(zone, path):
    url = f"https://{zone}.make.com/api/v2{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}", "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:300]}
    except Exception as e:  # noqa
        return None, {"_err": str(e)}


def find_zone():
    forced = env("MAKE_ZONE")
    zones = [forced] if forced else ZONES
    for z in zones:
        code, body = call(z, "/users/me")
        if code == 200:
            return z, body
    return None, None


def discover():
    if not TOKEN:
        sys.exit("No MAKE_API_KEY in .env.txt")
    zone, me = find_zone()
    if not zone:
        sys.exit("Could not authenticate against any zone — check token/scopes.")
    print(f"ZONE: {zone}")
    u = (me or {}).get("authUser") or me
    print("USER:", json.dumps(u)[:200])
    code, orgs = call(zone, "/organizations")
    print("\nORGANIZATIONS:")
    for o in (orgs.get("organizations") or []):
        print(f"  org id={o.get('id')}  name={o.get('name')!r}  zone={o.get('zone')}")
        c2, teams = call(zone, f"/teams?organizationId={o.get('id')}")
        for t in (teams.get("teams") or []):
            print(f"      team id={t.get('id')}  name={t.get('name')!r}")
    print("\n(use a team id with: python make/make_api.py scenarios <teamId>)")


def scenarios(team_id):
    zone, _ = find_zone()
    code, body = call(zone, f"/scenarios?teamId={team_id}")
    for s in (body.get("scenarios") or []):
        print(f"  scenario id={s.get('id')}  name={s.get('name')!r}  active={s.get('isActive') or s.get('isactive')}")


def blueprint(scenario_id):
    zone, _ = find_zone()
    code, body = call(zone, f"/scenarios/{scenario_id}/blueprint")
    print(json.dumps(body, indent=2)[:6000])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"
    if cmd == "discover":
        discover()
    elif cmd == "scenarios":
        scenarios(sys.argv[2])
    elif cmd == "blueprint":
        blueprint(sys.argv[2])
    else:
        print("unknown command")
