#!/usr/bin/env python3
"""Keep Transmission's listening port synchronized with Gluetun's forwarded port."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

PORT_FILE = os.getenv("GLUETUN_PORT_FILE", "/gluetun/forwarded_port")
RPC_URL = os.getenv("TRANSMISSION_RPC_URL", "http://127.0.0.1:9091/transmission/rpc")
RPC_USER = os.getenv("TRANSMISSION_RPC_USERNAME", "")
RPC_PASS = os.getenv("TRANSMISSION_RPC_PASSWORD", "")
POLL_SECONDS = int(os.getenv("PORT_SYNC_POLL_SECONDS", "5"))
session_id = None
last_port = None


def request_rpc(port):
    global session_id
    payload = json.dumps({
        "method": "session-set",
        "arguments": {
            "peer-port": int(port),
            "peer-port-random-on-start": False
        }
    }).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if session_id:
        headers["X-Transmission-Session-Id"] = session_id
    if RPC_USER or RPC_PASS:
        credentials = base64.b64encode(f"{RPC_USER}:{RPC_PASS}".encode()).decode()
        headers["Authorization"] = "Basic " + credentials

    req = urllib.request.Request(RPC_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            new_id = exc.headers.get("X-Transmission-Session-Id")
            if not new_id:
                raise RuntimeError("Transmission RPC retornou 409 sem session ID")
            session_id = new_id
            return request_rpc(port)
        raise RuntimeError(f"Transmission RPC HTTP {exc.code}") from exc

    if result.get("result") != "success":
        raise RuntimeError(f"Transmission RPC: {result.get('result', 'resposta inesperada')}")


print("port-sync iniciado; aguardando porta encaminhada pelo Gluetun", flush=True)
while True:
    try:
        with open(PORT_FILE, "r", encoding="utf-8") as port_file:
            value = port_file.read().strip()
        port = int(value)
        if 1 <= port <= 65535 and port != last_port:
            request_rpc(port)
            last_port = port
            print(f"Transmission atualizado para a porta encaminhada {port}", flush=True)
    except FileNotFoundError:
        # Gluetun may remove the file while the VPN tunnel is reconnecting.
        pass
    except Exception as exc:
        print(f"Falha ao sincronizar porta: {exc}", flush=True)
    time.sleep(POLL_SECONDS)
