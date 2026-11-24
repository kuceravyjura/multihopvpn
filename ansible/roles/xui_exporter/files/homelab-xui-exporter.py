#!/usr/bin/env python3
"""homelab-xui-exporter: traffic per inbound and per client, read from the 3x-ui database.

Why the database and not Xray's stats API: 3x-ui itself reads Xray's counters and resets them
every few seconds, adding them to running totals in x-ui.db. Reading the API would either steal
those numbers or see almost nothing. The database is opened read-only.

Only this server's own inbounds count (node-sync copies, node_id set, are skipped: their numbers
are not real). Most users have one WireGuard inbound each, so "per inbound" is "per person".

  GET /metrics   Prometheus format, on the management tunnel only
Config: /etc/homelab-xui-exporter.json (role "xui_exporter"; ADR 0009)."""
import json
import sqlite3
import time
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CFG = json.load(open("/etc/homelab-xui-exporter.json"))
DB = CFG.get("db", "/etc/x-ui/x-ui.db")


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def collect():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    try:
        inb = con.execute("select id, tag, remark, protocol, port, up, down, enable from inbounds "
                          "where node_id is null or node_id = ''").fetchall()
        local = {i[0]: i for i in inb}
        cli = con.execute("select inbound_id, email, up, down, enable, last_online from client_traffics").fetchall()
    finally:
        con.close()
    out = []

    def metric(name, help_, typ, rows):
        out.extend([f"# HELP {name} {help_}", f"# TYPE {name} {typ}"])
        out.extend(rows)

    lab = {i: f'tag="{esc(t)}",remark="{esc(r)}",protocol="{esc(p)}",port="{po}"'
           for i, t, r, p, po, *_ in inb}
    metric("xui_inbound_up_bytes_total", "Bytes from users into this inbound (running total kept by 3x-ui).",
           "counter", [f"xui_inbound_up_bytes_total{{{lab[i[0]]}}} {i[5] or 0}" for i in inb])
    metric("xui_inbound_down_bytes_total", "Bytes to users from this inbound.",
           "counter", [f"xui_inbound_down_bytes_total{{{lab[i[0]]}}} {i[6] or 0}" for i in inb])
    metric("xui_inbound_enabled", "1 if the inbound is enabled in the panel.",
           "gauge", [f"xui_inbound_enabled{{{lab[i[0]]}}} {1 if i[7] else 0}" for i in inb])
    rows_up, rows_dn, rows_seen = [], [], []
    for ib, email, up, dn, en, seen in cli:
        if ib not in local:
            continue
        l = f'email="{esc(email)}",inbound="{esc(local[ib][2])}"'
        rows_up.append(f"xui_client_up_bytes_total{{{l}}} {up or 0}")
        rows_dn.append(f"xui_client_down_bytes_total{{{l}}} {dn or 0}")
        rows_seen.append(f"xui_client_last_online_timestamp_seconds{{{l}}} {(seen or 0) / 1000:.0f}")
    metric("xui_client_up_bytes_total", "Bytes from this client (VLESS clients; WireGuard is per inbound).", "counter", rows_up)
    metric("xui_client_down_bytes_total", "Bytes to this client.", "counter", rows_dn)
    metric("xui_client_last_online_timestamp_seconds", "When 3x-ui last saw the client online.", "gauge", rows_seen)
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404); self.end_headers(); return
        try:
            body, code = collect(), 200
            body += f"xui_exporter_up 1\nxui_exporter_scrape_time {time.time():.0f}\n"
        except Exception as e:  # database locked or moved: say so instead of serving stale numbers
            body, code = f"# error: {esc(e)}\nxui_exporter_up 0\n", 200
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class Server(ThreadingHTTPServer):
    """No reverse-DNS lookup of our own address at start (http.server does getfqdn(), which
    waits 30-60 s for a timeout on a private tunnel address)."""
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


if __name__ == "__main__":
    for attempt in range(60):            # the wg-mgmt address may appear a little after boot
        try:
            srv = Server((CFG["listen"], CFG["port"]), Handler)
            break
        except OSError as e:
            print(f"cannot listen on {CFG['listen']}:{CFG['port']} yet ({e}); retrying", flush=True)
            time.sleep(5)
    else:
        raise SystemExit("giving up")
    srv.serve_forever()
