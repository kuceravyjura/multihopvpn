"""xui_users: create and manage WireGuard users through a 3x-ui panel's API (ADR 0010).

One WireGuard inbound per person (remark = the person's name), one client per device, sniffing
on, a free UDP port from the user range. 3x-ui applies new and changed inbounds live (no Xray
restart; tested 2026-11-24 on 3.11.0), so other users are not interrupted.

The token is a 3x-ui API token with scope "node-sync": it may only list, add, update and delete
inbounds and clients (and restart Xray), not touch panel settings or logins."""
import ipaddress
import json
import random
import re
import secrets
import ssl
import subprocess
import urllib.request

SNIFFING = {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False, "routeOnly": False}


def wg_keys():
    priv = subprocess.run(["wg", "genkey"], capture_output=True, text=True, check=True).stdout.strip()
    return priv, wg_pub(priv)


def wg_pub(priv):
    return subprocess.run(["wg", "pubkey"], input=priv, capture_output=True, text=True, check=True).stdout.strip()


def js(v):
    """The API returns settings/sniffing either as JSON text or already decoded."""
    return v if isinstance(v, dict) else json.loads(v or "{}")


def jtext(v):
    return v if isinstance(v, str) else json.dumps(v)


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "user")[:24]


class Panel:
    """One server's panel. base = https://<tunnel-ip>:<port><secret path> (over the management tunnel)."""

    def __init__(self, key, title, base, token, endpoint_host, port_lo, port_hi, dns="1.1.1.1, 1.0.0.1"):
        self.key, self.title, self.base, self.token = key, title, base.rstrip("/"), token
        self.endpoint_host, self.port_lo, self.port_hi, self.dns = endpoint_host, port_lo, port_hi, dns
        # The panel's certificate is for its public name; the call goes over the management tunnel
        # to the tunnel address, so the name cannot match. The tunnel itself is the trust anchor.
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def _call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}/panel/api{path}", data=data,
                                     method="POST" if data is not None else "GET",
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20, context=self._ctx) as r:
            d = json.load(r)
        if not d.get("success"):
            raise RuntimeError(f"{self.title}: {d.get('msg', 'panel refused')}"[:200])
        return d.get("obj")

    # --- reading -------------------------------------------------------------------------
    def inbounds(self):
        return [i for i in (self._call("/inbounds/list") or []) if not i.get("nodeId")]

    def wg_users(self):
        out = []
        for i in self.inbounds():
            if i.get("protocol") != "wireguard":
                continue
            s = js(i.get("settings"))
            out.append({"id": i["id"], "remark": i.get("remark", ""), "port": i["port"], "enable": i.get("enable", True),
                        "up": i.get("up", 0), "down": i.get("down", 0),
                        "devices": [c.get("email", "") for c in s.get("clients", [])]})
        return sorted(out, key=lambda u: u["remark"].lower())

    def get(self, inbound_id):
        # /inbounds/get/:id is not in the node-sync token's allow-list; the list is.
        ib = next((i for i in (self._call("/inbounds/list") or []) if i["id"] == int(inbound_id)), None)
        if ib is None:
            raise RuntimeError(f"{self.title}: no inbound {inbound_id}")
        return ib

    # --- writing -------------------------------------------------------------------------
    def _free_port(self):
        used = {i["port"] for i in self._call("/inbounds/list") or []}
        free = [p for p in range(self.port_lo, self.port_hi + 1) if p not in used]
        if not free:
            raise RuntimeError(f"{self.title}: no free port left in {self.port_lo}-{self.port_hi}")
        return random.choice(free)

    def create_user(self, name):
        """New person: a WireGuard inbound with one device. Returns (inbound, client)."""
        port = self._free_port()
        sk, _ = wg_keys()
        cpriv, cpub = wg_keys()
        client = {"email": f"{slug(name)}-{secrets.token_hex(2)}-dev1", "enable": True, "privateKey": cpriv,
                  "publicKey": cpub, "allowedIPs": ["10.0.0.2/32"], "keepAlive": 0}
        body = {"up": 0, "down": 0, "total": 0, "remark": name, "enable": True, "expiryTime": 0, "listen": "",
                "port": port, "protocol": "wireguard", "tag": f"inbound-{port}",
                "settings": json.dumps({"secretKey": sk, "clients": [client], "noKernelTun": False}),
                "streamSettings": "", "sniffing": json.dumps(SNIFFING)}
        ib = self._call("/inbounds/add", body)
        return ib, client

    def _update(self, ib, settings=None, enable=None):
        body = {k: ib[k] for k in ("up", "down", "total", "remark", "enable", "expiryTime", "listen", "port",
                                   "protocol", "tag") if k in ib}
        body["streamSettings"] = jtext(ib.get("streamSettings") or "")
        body["sniffing"] = jtext(ib.get("sniffing") or SNIFFING)
        body["settings"] = jtext(settings if settings is not None else ib["settings"])
        if enable is not None:
            body["enable"] = enable
        return self._call(f"/inbounds/update/{ib['id']}", body)

    def add_device(self, inbound_id, device):
        ib = self.get(inbound_id)
        s = js(ib["settings"])
        taken = {ipaddress.ip_interface(a).ip for c in s.get("clients", []) for a in c.get("allowedIPs", [])}
        addr = next(ip for ip in ipaddress.ip_network("10.0.0.0/24").hosts() if int(ip) % 256 >= 2 and ip not in taken)
        cpriv, cpub = wg_keys()
        base = slug(ib.get("remark", "user"))
        client = {"email": f"{base}-{secrets.token_hex(2)}-{slug(device)}", "enable": True, "privateKey": cpriv,
                  "publicKey": cpub, "allowedIPs": [f"{addr}/32"], "keepAlive": 0}
        s.setdefault("clients", []).append(client)
        self._update(ib, s)
        return self.get(inbound_id), client

    def remove_device(self, inbound_id, email):
        ib = self.get(inbound_id)
        s = js(ib["settings"])
        s["clients"] = [c for c in s.get("clients", []) if c.get("email") != email]
        if not s["clients"]:
            raise RuntimeError("that is the last device: delete the user instead")
        self._update(ib, s)

    def set_enable(self, inbound_id, enable):
        self._update(self.get(inbound_id), enable=enable)

    def delete_user(self, inbound_id):
        self._call(f"/inbounds/del/{inbound_id}", {})

    # --- handing out ---------------------------------------------------------------------
    def conf(self, ib, email):
        """The .conf for one device, in the same shape the panel itself produces."""
        s = js(ib["settings"]) if isinstance(ib["settings"], str) else ib["settings"]
        c = next(c for c in s["clients"] if c.get("email") == email)
        lines = ["[Interface]", f"PrivateKey = {c['privateKey']}", f"Address = {', '.join(c['allowedIPs'])}",
                 f"DNS = {self.dns}", "", f"# {ib.get('remark', '')}", "[Peer]", f"PublicKey = {wg_pub(s['secretKey'])}",
                 "AllowedIPs = 0.0.0.0/0, ::/0", f"Endpoint = {self.endpoint_host}:{ib['port']}"]
        if c.get("preSharedKey"):
            lines.append(f"PresharedKey = {c['preSharedKey']}")
        if c.get("keepAlive"):
            lines.append(f"PersistentKeepalive = {c['keepAlive']}")
        return "\n".join(lines) + "\n"


def qr_png(text):
    """PNG bytes of a QR code (qrencode)."""
    return subprocess.run(["qrencode", "-o", "-", "-t", "PNG", "-s", "6", "-m", "2"], input=text.encode(),
                          capture_output=True, check=True).stdout
