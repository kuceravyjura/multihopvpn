#!/usr/bin/env python3
"""homelab-reach: can this server open a website, and how far does it get?

Each check runs curl against https://<site>/ and reports the stage it reached:
  ok       an HTTP answer arrived (the site is reachable)
  refused  the site answered 403/451: it turns this address away (e.g. OpenAI refuses Russia)
  dns      the name did not resolve
  tcp      no TCP connection (IP blocked, or the site is down)
  tls      TCP connected but the TLS handshake never finished (typical SNI blocking)
  http     TLS done but no HTTP answer in time (throttled or stalled)
Paths:
  direct   from this server's own address
  user     through a local proxy inbound of this server's Xray, so the panel's routing rules
           apply exactly as for a VPN user (Server 1 only: relay list, DNS, direct)

Schedule: the watched list every `interval` s on every path, except the direct path when
`direct_interval` is set (Server 1): then the direct path runs rarely (about every
`direct_interval` s, +-20 %, random order, random 20-120 s pauses), so the server doesn't look
like a censorship probe. Its last results are kept in the state directory across restarts.

HTTP on the management tunnel only:
  GET /check?site=example.com   check now, all paths, JSON
  GET /metrics                  watched list (refreshed every `interval` s), Prometheus format
Config: /etc/homelab-reach.json (role "reach"; ADR 0007, runbook 11)."""
import ipaddress
import json
import os
import random
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CFG = json.load(open("/etc/homelab-reach.json"))
PATHS = {"direct": None}
if CFG.get("socks"):
    PATHS["user"] = CFG["socks"]
HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_state = {"results": {}, "last_run": 0, "direct_last": 0}
STATE = os.environ.get("STATE_DIRECTORY", "/var/lib/homelab-reach")
DIRECT_EVERY = int(CFG.get("direct_interval") or 0)        # 0: direct path on the normal schedule
UA = CFG.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
_lock = threading.Lock()
_busy = threading.Semaphore(4)          # at most 4 on-demand checks at once (512 MB server)


def clean_site(raw):
    """Accept a host name or a public IPv4/IPv6 address; strip a pasted URL down to its host."""
    s = (raw or "").strip().lower()
    s = re.sub(r"^[a-z]+://", "", s).split("/")[0].split("?")[0]
    if s.count(":") == 1:
        s = s.split(":")[0]
    try:
        ip = ipaddress.ip_address(s.strip("[]"))
        return str(ip) if ip.is_global else None
    except ValueError:
        return s if HOST_RE.match(s) else None


def check(site, proxy=None, timeout=10):
    url = f"https://[{site}]/" if ":" in site else f"https://{site}/"
    cmd = ["curl", "-s", "-o", "/dev/null", "--connect-timeout", "5", "--max-time", str(timeout),
           "-A", UA,
           "-w", "%{json}", url]
    if proxy:
        cmd[1:1] = ["--socks5-hostname", proxy]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        w = json.loads(r.stdout or "{}")
    except Exception as e:  # curl missing, killed, unparsable
        return {"result": "error", "detail": str(e)[:80], "seconds": round(time.time() - t0, 2)}
    code, exit_ = int(w.get("http_code") or 0), int(w.get("exitcode", r.returncode))
    conn, tls = float(w.get("time_connect") or 0), float(w.get("time_appconnect") or 0)
    if code in (403, 451):
        res = "refused"
    elif code > 0:
        res = "ok"
    elif exit_ in (5, 6):
        res = "dns"
    elif proxy and exit_ == 97:          # the proxy could not reach the site
        res = "tcp"
    elif conn == 0:
        res = "tcp"
    elif tls == 0:
        res = "tls"
    else:
        res = "http"
    out = {"result": res, "http": code, "seconds": round(float(w.get("time_total") or 0), 2),
           "connect": round(conn, 2), "tls": round(tls, 2), "curl_exit": exit_}
    if w.get("remote_ip") and not proxy:
        out["ip"] = w["remote_ip"]
    return out


def check_once_more(site, proxy):
    """One retry after a short pause, so a single slow moment doesn't count as blocked.
    A refusal (403/451) is an answer, not a glitch: no retry."""
    r = check(site, proxy)
    if r["result"] not in ("ok", "refused"):
        time.sleep(2)
        r2 = check(site, proxy)
        r2["retried"] = True
        return r2
    return r


def check_all(site):
    with ThreadPoolExecutor(len(PATHS)) as ex:
        futs = {p: ex.submit(check_once_more, site, proxy) for p, proxy in PATHS.items()}
        return {p: f.result() for p, f in futs.items()}


def _store(site, path, res):
    with _lock:
        _state["results"].setdefault(site, {})[path] = res


def refresh_loop():
    """The frequent schedule: every path, except a rare direct path (see direct_loop)."""
    fast = {p: proxy for p, proxy in PATHS.items() if not (p == "direct" and DIRECT_EVERY)}
    while True:
        start = time.time()

        def run(site):
            for p, proxy in fast.items():
                _store(site, p, check_once_more(site, proxy))
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(run, CFG["sites"]))
        with _lock:
            _state["last_run"] = time.time()
        time.sleep(max(30, CFG.get("interval", 600) - (time.time() - start)))


def direct_loop():
    """The rare direct schedule (Server 1). Saved, so a restart neither loses nor repeats it."""
    path = os.path.join(STATE, "direct.json")
    try:
        saved = json.load(open(path))
    except Exception:
        # First round: some random time within one interval (at most a day), not right away.
        saved = {"results": {}, "last": 0,
                 "next": time.time() + random.uniform(min(3600, DIRECT_EVERY / 2), min(86400, DIRECT_EVERY))}
    for site, res in saved["results"].items():
        _store(site, "direct", res)
    _state["direct_last"] = saved["last"]
    while True:
        time.sleep(max(0, saved["next"] - time.time()))
        sites = list(CFG["sites"])
        random.shuffle(sites)
        for i, site in enumerate(sites):
            res = check_once_more(site, None)
            _store(site, "direct", res)
            saved["results"][site] = res
            if i < len(sites) - 1:
                time.sleep(random.uniform(20, 120))
        saved["last"] = time.time()
        saved["next"] = saved["last"] + DIRECT_EVERY * random.uniform(0.8, 1.2)
        _state["direct_last"] = saved["last"]
        try:
            with open(path + ".tmp", "w") as f:
                json.dump(saved, f)
            os.replace(path + ".tmp", path)
        except OSError:
            pass


def metrics():
    with _lock:
        res = {s: dict(p) for s, p in _state["results"].items()}   # both schedules write
        last = _state["last_run"]
    lines = ["# HELP homelab_reach_up 1 if the site gave an HTTP answer on this path.",
             "# TYPE homelab_reach_up gauge"]
    for site, paths in res.items():
        for p, r in paths.items():
            lines.append(f'homelab_reach_up{{site="{site}",path="{p}"}} {1 if r["result"] == "ok" else 0}')
    lines += ["# HELP homelab_reach_seconds Total time of the last check.", "# TYPE homelab_reach_seconds gauge"]
    for site, paths in res.items():
        for p, r in paths.items():
            lines.append(f'homelab_reach_seconds{{site="{site}",path="{p}"}} {r.get("seconds", 0)}')
    lines += ["# HELP homelab_reach_result Stage the last check reached (ok, refused, dns, tcp, tls, http).",
              "# TYPE homelab_reach_result gauge"]
    for site, paths in res.items():
        for p, r in paths.items():
            lines.append(f'homelab_reach_result{{site="{site}",path="{p}",result="{r["result"]}"}} 1')
    lines += ["# TYPE homelab_reach_last_run_timestamp_seconds gauge",
              f"homelab_reach_last_run_timestamp_seconds {last}",
              "# HELP homelab_reach_direct_last_run_timestamp_seconds Last rare direct round (0: not yet).",
              "# TYPE homelab_reach_direct_last_run_timestamp_seconds gauge",
              f"homelab_reach_direct_last_run_timestamp_seconds {_state['direct_last']}"]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/metrics":
            return self._send(200, metrics(), "text/plain; version=0.0.4")
        if u.path == "/check":
            site = clean_site((parse_qs(u.query).get("site") or [""])[0])
            if not site:
                return self._send(400, json.dumps({"error": "give a public host name or address"}))
            if not _busy.acquire(timeout=30):
                return self._send(503, json.dumps({"error": "busy"}))
            try:
                return self._send(200, json.dumps({"server": CFG["server"], "site": site, "paths": check_all(site)}))
            finally:
                _busy.release()
        self._send(404, json.dumps({"error": "use /check?site=... or /metrics"}))

    def log_message(self, *a):
        pass


class Server(ThreadingHTTPServer):
    """No reverse-DNS lookup of our own address at start (http.server does getfqdn(), which
    waits 30-60 s for a timeout on a private tunnel address)."""
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


if __name__ == "__main__":
    threading.Thread(target=refresh_loop, daemon=True).start()
    if DIRECT_EVERY:
        threading.Thread(target=direct_loop, daemon=True).start()
    for attempt in range(60):            # the wg-mgmt address may appear a little after boot
        try:
            srv = Server((CFG["listen"], CFG["port"]), Handler)
            break
        except OSError as e:
            print(f"cannot listen on {CFG['listen']}:{CFG['port']} yet ({e}); retrying", flush=True)
            time.sleep(5)
    else:
        raise SystemExit(f"cannot listen on {CFG['listen']}:{CFG['port']}")
    srv.serve_forever()
