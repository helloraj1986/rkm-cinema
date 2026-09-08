#!/usr/bin/env python3
"""Probe what the sandbox can reach for deploying the watchlist dashboard:
- Docker daemon (socket or tcp 2375)
- host.docker.internal network
- Tailscale MagicDNS resolution (likely no — sandbox not on tailnet)
- Is anything already on port 8123?"""
import json, os, socket, subprocess, sys, urllib.request

print("== 1. docker CLI ==")
r = subprocess.run(["bash", "-lc", "command -v docker && docker version --format '{{.Server.Version}}' 2>&1 | head -2 || echo NO_DOCKER_CLI"], capture_output=True, text=True)
print(r.stdout.strip()[:300])

print("\n== 2. docker socket ==")
if os.path.exists("/var/run/docker.sock"):
    print("socket exists")
    try:
        req = urllib.request.Request("http://localhost/version", headers={"Host": "docker"})
        # can't easily use unix socket via urllib; try via curl
        r = subprocess.run(["curl", "-s", "--unix-socket", "/var/run/docker.sock", "http://localhost/version"], capture_output=True, text=True, timeout=8)
        print("api via socket:", r.stdout.strip()[:150])
    except Exception as e:
        print("socket probe err:", e)
else:
    print("no /var/run/docker.sock")

print("\n== 3. docker daemon tcp 2375 (host) ==")
for host in ("host.docker.internal", "192.168.65.254"):
    try:
        with urllib.request.urlopen(f"http://{host}:2375/version", timeout=4) as resp:
            print(f"  {host}:2375 ->", resp.read().decode()[:120])
        break
    except Exception as e:
        print(f"  {host}:2375 -> unreachable ({e.__class__.__name__})")

print("\n== 4. MagicDNS resolution from sandbox ==")
try:
    ip = socket.gethostbyname("rkm-hp.tail8d5e8.ts.net")
    print("  resolves to", ip)
except Exception as e:
    print("  cannot resolve rkm-hp.tail8d5e8.ts.net:", e)

print("\n== 5. anything on host:8123 already? ==")
try:
    with urllib.request.urlopen("http://host.docker.internal:8123/", timeout=4) as resp:
        print("  host:8123 -> HTTP", resp.status)
except Exception as e:
    print("  host:8123 ->", e.__class__.__name__)