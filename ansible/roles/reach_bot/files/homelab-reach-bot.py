#!/usr/bin/env python3
"""homelab-reach-bot: the homelab's Telegram bot (ADR 0007 reachability, ADR 0010 users).

  /menu           buttons: ➕ New user, 👥 Users (WireGuard users on both panels), 🔎 Check a site

  /check <site>   test now from Moscow (direct), for Server 1's users (through its routing),
                  and from Lithuania (direct); reply with a verdict
  /sites          the watched list, from Prometheus
  /help
/check also says whether the site is on Russia's block lists (runetfreedom: ru-blocked =
antifilter community + re:filter; ru-blocked-all = everything known, incl. the registry),
downloaded every 12 hours into the service's state directory.
Answers only the owner's chat. Config /etc/homelab-reach-bot.json, secrets in
/etc/homelab-reach-bot.env (BOT_TOKEN, CHAT_ID). Long polling: no open port."""
import json
import os
import sys
import threading
import uuid
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CFG = json.load(open("/etc/homelab-reach-bot.json"))
sys.path.insert(0, "/usr/local/lib/homelab-bot")
TOKEN, CHAT = os.environ["BOT_TOKEN"], str(os.environ["CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
STATE = os.environ.get("STATE_DIRECTORY", "/var/lib/homelab-reach-bot")
LISTS = {"ru-blocked": "https://github.com/runetfreedom/russia-blocked-geosite/releases/latest/download/ru-blocked.txt",
         "ru-blocked-all": "https://github.com/runetfreedom/russia-blocked-geosite/releases/latest/download/ru-blocked-all.txt"}
_small = {"set": set(), "when": 0}       # ru-blocked kept in memory (~73k names); the big one is scanned on disk
STAGE = {"ok": "opens", "refused": "the site refuses this address (HTTP 403/451, e.g. a country block)",
         "dns": "name does not resolve", "tcp": "no connection",
         "tls": "connects, but TLS stalls (typical block by name)", "http": "no answer after TLS (throttled?)",
         "error": "check failed"}


def get(url, timeout=45):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def tg(method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"{API}/{method}", data=data, timeout=70) as r:
        return json.load(r)


def send_file(method, field, filename, data, **params):
    """Telegram upload (multipart): a .conf document or a QR photo."""
    b = uuid.uuid4().hex
    parts = []
    for k, v in {"chat_id": CHAT, **params}.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                 f'Content-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n")
    body = b"".join(parts) + f"--{b}--\r\n".encode()
    req = urllib.request.Request(f"{API}/{method}", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def make_users_ui():
    """The users screens, if panels are configured (tokens in the environment)."""
    if not CFG.get("panels"):
        return None
    import bot_users
    import xui_users
    panels = {}
    for p in CFG["panels"]:
        tok = os.environ.get(f"XUI_TOKEN_{p['key'].upper()}")
        if tok:
            panels[p["key"]] = xui_users.Panel(p["key"], p["title"], p["base"], tok, p["endpoint_host"],
                                                int(p["port_lo"]), int(p["port_hi"]))
    return bot_users.UsersUI(tg, send_file, CHAT, panels) if panels else None


def say(text):
    tg("sendMessage", chat_id=CHAT, text=text, parse_mode="HTML", disable_web_page_preview="true")


def refresh_lists():
    while True:
        for name, url in LISTS.items():
            dst = os.path.join(STATE, name + ".txt")
            try:
                if os.path.exists(dst) and time.time() - os.path.getmtime(dst) < 11 * 3600:
                    continue
                with urllib.request.urlopen(url, timeout=120) as r, open(dst + ".tmp", "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                if os.path.getsize(dst + ".tmp") > 1000:
                    os.replace(dst + ".tmp", dst)
            except Exception:
                pass
        small = os.path.join(STATE, "ru-blocked.txt")
        if os.path.exists(small) and os.path.getmtime(small) != _small["when"]:
            with open(small) as f:
                _small["set"] = {x.strip() for x in f if x.strip()}
            _small["when"] = os.path.getmtime(small)
        time.sleep(3600)


def listed(site):
    """Which list names the site or one of its parent domains: ru-blocked, ru-blocked-all or None."""
    parts = site.split(".")
    cands = {f"domain:{'.'.join(parts[i:])}" for i in range(len(parts) - 1)} | {f"full:{site}"}
    if cands & _small["set"]:
        return "ru-blocked"
    big = os.path.join(STATE, "ru-blocked-all.txt")
    if os.path.exists(big):
        with open(big) as f:
            if any(x.strip() in cands for x in f):
                return "ru-blocked-all"
    return None if _small["set"] else "unknown"


LIST_TEXT = {"ru-blocked": "📋 On Russia's block list (ru-blocked: community-checked)",
             "ru-blocked-all": "📋 Only on the full block list (ru-blocked-all, incl. the registry)",
             None: "📋 Not on Russia's block lists", "unknown": "📋 Block lists not downloaded yet"}


def line(label, r):
    if not r:
        return f"⚪ {label}: no data"
    mark = "✅" if r["result"] == "ok" else "❌"
    return f"{mark} {label}: {STAGE.get(r['result'], r['result'])}, {r.get('seconds', 0)} s"


def check(site):
    def ask(url):
        try:
            return get(f"{url}/check?site={urllib.parse.quote(site)}")
        except Exception as e:
            return {"error": str(e)[:60]}
    with ThreadPoolExecutor(2) as ex:
        s1, s2 = ex.map(ask, [CFG["agents"]["s1"], CFG["agents"]["s2"]])
    if "error" in s1 and "error" in s2:
        return f"Could not check <b>{site}</b>: {s1['error']}"
    name = s1.get("site") or s2.get("site") or site
    lst = listed(name)
    msk = s1.get("paths", {}).get("direct")
    users = s1.get("paths", {}).get("user")
    lt = s2.get("paths", {}).get("direct")
    ok = lambda r: bool(r) and r["result"] == "ok"
    if ok(users):
        if msk and msk["result"] == "refused":
            verdict = "The site refuses Russian addresses; Server 1's users get it from Lithuania through the relay."
        elif not ok(msk):
            verdict = "Blocked in Russia; Server 1's users get it through the relay."
        elif lst in ("ru-blocked", "ru-blocked-all"):
            verdict = ("Listed as blocked, yet it opens directly from the Moscow datacenter: home and mobile "
                       "networks may still block or slow it. Server 1's users are fine.")
        else:
            verdict = "Open in Russia; Server 1's users are fine."
    elif users is None:
        verdict = "No user-path check on Server 1 yet."
    elif ok(lt) and msk and msk["result"] == "refused" and users["result"] == "refused":
        verdict = ("The site itself refuses Russian addresses and users reach it from Moscow: "
                   "<b>add it to the relay list</b> so it goes out from Lithuania.")
    elif ok(lt) and not ok(msk):
        verdict = "Blocked in Russia and <b>not on the relay list</b>: add it to Server 1's relay rules."
        if lst is None:
            verdict += " (Not on the block lists yet either: a new or unofficial block.)"
    elif ok(lt) and ok(msk):
        verdict = "Opens directly in Moscow and in Lithuania, but not for users: check Server 1's routing."
    elif lt and lt["result"] == "dns" and msk and msk["result"] == "dns":
        verdict = "The name does not resolve anywhere: check the spelling."
    else:
        verdict = "Lithuania cannot open it either: the site is down or blocks these servers."
    return "\n".join([f"🔎 <b>{name}</b>", line("Moscow, direct", msk), line("Server 1 users", users),
                      line("Lithuania, direct", lt), LIST_TEXT[lst], "", verdict])


def sites():
    q = urllib.parse.quote("homelab_reach_up")
    res = get(f"{CFG['prometheus']}/api/v1/query?query={q}", timeout=10)["data"]["result"]
    table = {}
    for x in res:
        m = x["metric"]
        col = {("s1-msk", "direct"): 0, ("s1-msk", "user"): 1, ("s2-lt", "direct"): 2}.get((m.get("host"), m.get("path")))
        if col is not None:
            table.setdefault(m["site"], ["·", "·", "·"])[col] = "✅" if x["value"][1] == "1" else "❌"
    if not table:
        return "No data yet (the agents check every 10 minutes)."
    rows = [f"{''.join(v)}  {s}" for s, v in sorted(table.items())]
    return "Moscow · users · Lithuania\n" + "\n".join(rows)


HELP = ("/menu: users and checks (buttons)\n"
        "/check <site>: test it now from Moscow, for Server 1's users, and from Lithuania\n"
        "/sites: the watched list\n/help: this text")


def handle(text):
    cmd, _, arg = text.strip().partition(" ")
    cmd = cmd.split("@")[0].lower()
    if cmd == "/check":
        return check(arg.strip()) if arg.strip() else "Usage: /check youtube.com"
    if cmd == "/sites":
        return sites()
    return HELP


def main():
    threading.Thread(target=refresh_lists, daemon=True).start()
    ui = make_users_ui()
    try:
        tg("setMyCommands", commands=json.dumps([{"command": "menu", "description": "users and checks"},
                                                 {"command": "check", "description": "test a site now"},
                                                 {"command": "sites", "description": "watched list"}]))
    except Exception:
        pass
    offset = 0
    while True:
        try:
            upd = tg("getUpdates", offset=offset, timeout=50)
            for u in upd.get("result", []):
                offset = u["update_id"] + 1
                cq = u.get("callback_query")
                if cq:
                    if str((cq.get("message") or {}).get("chat", {}).get("id")) != CHAT:
                        continue
                    try:
                        tg("answerCallbackQuery", callback_query_id=cq["id"])
                        if ui:
                            ui.on_callback(cq.get("data", ""))
                    except Exception as e:
                        say(f"Error: {str(e)[:300]}")
                    continue
                msg = u.get("message") or {}
                if str(msg.get("chat", {}).get("id")) != CHAT or "text" not in msg:
                    continue
                text = msg["text"]
                try:
                    if ui and text.split("@")[0].lower() in ("/menu", "/start"):
                        ui.menu()
                    elif ui and ui.pending() and not text.startswith("/"):
                        ui.on_text(text)
                    else:
                        say(handle(text))
                except Exception as e:
                    say(f"Error: {str(e)[:300]}")
        except Exception:
            time.sleep(10)


if __name__ == "__main__":
    main()
