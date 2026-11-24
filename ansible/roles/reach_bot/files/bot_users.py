"""bot_users: the Telegram screens for managing WireGuard users (ADR 0010).

  /menu        ➕ New user · 👥 Users · 🔎 Check a site
  New user     name -> server -> the bot creates the person's inbound and sends name.conf + QR
  Users        everyone with traffic and devices; per user: 📱 Add device · 🔁 Send config ·
               ⏸ Disable / ▶️ Enable · 🗑 Delete (asks first)
Only the owner's chat reaches this (the bot checks the chat id before calling it)."""
import json
import re

import xui_users as X


def kb(rows):
    return json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]})


def gb(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e8 else f"{n / 1e6:.0f} MB"


class UsersUI:
    def __init__(self, tg, send_file, chat, panels):
        self.tg, self.send_file, self.chat, self.panels = tg, send_file, chat, panels   # panels: key -> X.Panel
        self.state = {}

    # --- helpers ---------------------------------------------------------------------------
    def say(self, text, buttons=None, force_reply=False):
        p = {"chat_id": self.chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
        if buttons:
            p["reply_markup"] = kb(buttons)
        elif force_reply:
            p["reply_markup"] = json.dumps({"force_reply": True})
        self.tg("sendMessage", **p)

    def send_conf(self, panel, ib, client):
        conf = panel.conf(ib, client["email"])
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", ib.get("remark", "user"))[:24].strip("_") or "user"
        dev = client["email"].rsplit("-", 1)[-1]
        fname = f"{name}-{dev}.conf"
        self.send_file("sendDocument", "document", fname, conf.encode(),
                       caption=f"{ib.get('remark', '')} · {dev} · {panel.title}\nWireSock or WireGuard: import this file.")
        self.send_file("sendPhoto", "photo", "qr.png", X.qr_png(conf),
                       caption="Phone: WireGuard app → + → Scan from QR code.")

    # --- entry points ----------------------------------------------------------------------
    def menu(self):
        self.state.pop(self.chat, None)
        self.say("Homelab", [[("➕ New user", "new"), ("👥 Users", "users")], [("🔎 Check a site", "checkhelp")]])

    def pending(self):
        return self.chat in self.state

    def on_text(self, text):
        st = self.state.pop(self.chat, None)
        name = re.sub(r"[\x00-\x1f<>]", "", text).strip()[:40]
        if not st or not name:
            return self.menu()
        if st[0] == "name":
            self.state[self.chat] = ("server", name)
            self.say(f"Where should <b>{name}</b> connect?",
                     [[(p.title, f"srv:{k}") for k, p in self.panels.items()], [("Cancel", "menu")]])
        elif st[0] == "device":
            _, key, iid = st
            p = self.panels[key]
            ib, client = p.add_device(iid, name)
            self.say(f"📱 Device <b>{name}</b> added.")
            self.send_conf(p, ib, client)

    def on_callback(self, data):
        cmd, *a = data.split(":")
        if cmd == "menu":
            return self.menu()
        if cmd == "checkhelp":
            return self.say("Send <code>/check site.com</code>: it is tested from Moscow, for Server 1's users, and from Lithuania.")
        if cmd == "new":
            self.state[self.chat] = ("name",)
            return self.say("Name of the new user (it becomes the inbound's remark in the panel):", force_reply=True)
        if cmd == "srv":
            st = self.state.pop(self.chat, None)
            if not st or st[0] != "server":
                return self.menu()
            p = self.panels[a[0]]
            ib, client = p.create_user(st[1])
            self.say(f"➕ <b>{st[1]}</b> created on {p.title} (port {ib['port']}).")
            return self.send_conf(p, ib, client)
        if cmd == "users":
            rows, lines = [], []
            for key, p in self.panels.items():
                us = p.wg_users()
                lines.append(f"<b>{p.title}</b>: {len(us)} users")
                rows += [[(f"{'' if u['enable'] else '⏸ '}{u['remark'][:22]} · {gb(u['up'] + u['down'])} · {len(u['devices'])}📱",
                           f"u:{key}:{u['id']}")] for u in us]
            return self.say("\n".join(lines), rows + [[("« Menu", "menu")]])
        if cmd == "u":
            key, iid = a[0], int(a[1])
            p = self.panels[key]
            u = next(x for x in p.wg_users() if x["id"] == iid)
            devs = "\n".join(f"• {d.rsplit('-', 1)[-1]}" for d in u["devices"])
            return self.say(f"<b>{u['remark']}</b> · {p.title} · port {u['port']}\n{gb(u['up'] + u['down'])} total · "
                            f"{'enabled' if u['enable'] else 'disabled'}\nDevices:\n{devs}",
                            [[("📱 Add device", f"dev:{key}:{iid}"), ("🔁 Send config", f"send:{key}:{iid}")],
                             [("▶️ Enable" if not u["enable"] else "⏸ Disable", f"{'ena' if not u['enable'] else 'dis'}:{key}:{iid}"),
                              ("🗑 Delete", f"del:{key}:{iid}")],
                             [("« Users", "users")]])
        if cmd == "dev":
            self.state[self.chat] = ("device", a[0], int(a[1]))
            return self.say("Name of the device (e.g. phone, laptop):", force_reply=True)
        if cmd == "send":
            key, iid = a[0], int(a[1])
            p = self.panels[key]
            ib = p.get(iid)
            clients = X.js(ib["settings"]).get("clients", [])
            if len(a) > 2:
                return self.send_conf(p, ib, clients[int(a[2])])
            if len(clients) == 1:
                return self.send_conf(p, ib, clients[0])
            return self.say("Which device?", [[(c["email"].rsplit("-", 1)[-1], f"send:{key}:{iid}:{i}")] for i, c in enumerate(clients)])
        if cmd in ("dis", "ena"):
            key, iid = a[0], int(a[1])
            self.panels[key].set_enable(iid, cmd == "ena")
            return self.on_callback(f"u:{key}:{iid}")
        if cmd == "del":
            key, iid = a[0], int(a[1])
            u = next(x for x in self.panels[key].wg_users() if x["id"] == iid)
            return self.say(f"Delete <b>{u['remark']}</b> and all {len(u['devices'])} device(s)? Their configs stop working.",
                            [[(f"🗑 Yes, delete {u['remark'][:20]}", f"delyes:{key}:{iid}"), ("Cancel", f"u:{key}:{iid}")]])
        if cmd == "delyes":
            key, iid = a[0], int(a[1])
            self.panels[key].delete_user(iid)
            self.say("🗑 Deleted.")
            return self.on_callback("users")
        return self.menu()
