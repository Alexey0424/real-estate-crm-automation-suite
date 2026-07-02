#!/usr/bin/env python3
"""
check_bot_membership.py — READ-ONLY: for each PROD channel Part A posts to, ask
Slack (as the bot) whether the bot is already a member. Uses conversations.info,
which returns `is_member` for the calling token + `is_private`.

Public channels don't strictly need membership (chat:write.public covers posting),
but private channels DO — a missing bot there fails the route with not_in_channel.

Usage:  SLACK_BOT_TOKEN=xoxb-… python shared/fub-scripts/check_bot_membership.py
        (falls back to .env)
"""
import os, sys, json, urllib.request, urllib.error, pathlib

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[2]

# PROD channel IDs (from shared/lib/config.js / build_make_partA.py)
PROD = {
    "all-ahb-new-leads":   "C0PORTFOL01",
    "underwriter-to-dos":  "C0PORTFOL02",
    "closers-chat":        "C0PORTFOL03",
    "tc-to-dos":         "C0PORTFOL04",
    "dispo-external-chat": "C0PORTFOL05",
    "team-wins":           "C0PORTFOL06",
    "lead-managers":       "C0PORTFOL07",
    "closer-deals-reyes":    "C0PORTFOL08",
    "closer-deals-flora":   "C0PORTFOL09",
    "closer-deals-marco":   "C0PORTFOL10",
}


def token():
    t = os.environ.get("SLACK_BOT_TOKEN")
    if t: return t.strip()
    envf = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    for line in envf.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("SLACK_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    sys.exit("No SLACK_BOT_TOKEN in env or .env")


def call(method, tok, params=""):
    url = f"https://slack.com/api/{method}{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    tok = token()
    who = call("auth.test", tok)
    if not who.get("ok"):
        sys.exit(f"auth.test failed: {who.get('error')}")
    print(f"Bot: {who.get('user')} (id {who.get('user_id')}) @ {who.get('team')}\n")

    need_invite = []
    print(f"{'channel':24s} {'priv':5s} {'member':7s}")
    print("-" * 40)
    for name, cid in PROD.items():
        res = call("conversations.info", tok, f"?channel={cid}")
        if not res.get("ok"):
            print(f"{name:24s}  ERROR: {res.get('error')}")
            # channel_not_found on a private channel often means the bot can't even see it = not a member
            if res.get("error") in ("channel_not_found", "not_in_channel"):
                need_invite.append((name, cid, "private?"))
            continue
        ch = res["channel"]
        priv = ch.get("is_private", False)
        member = ch.get("is_member", False)
        print(f"{name:24s} {'yes' if priv else 'no ':5s} {'YES' if member else 'NO':7s}")
        if priv and not member:
            need_invite.append((name, cid, "private"))

    print()
    if need_invite:
        print("NOTE:  Bot must be invited to these PRIVATE channels (route will 'not_in_channel' otherwise):")
        for name, cid, _ in need_invite:
            print(f"     /invite @{who.get('user')}    in  #{name}  ({cid})")
    else:
        print("[x] Bot is a member of every PRIVATE prod channel — no invites needed.")


if __name__ == "__main__":
    main()
