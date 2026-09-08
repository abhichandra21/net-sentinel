#!/usr/bin/env python3
"""Deploy the Net Sentinel dashboard and theme to Home Assistant.

Why this exists
---------------
The Net Sentinel dashboard is a **storage-mode** Lovelace dashboard. Home
Assistant reads `.storage/lovelace.net_sentinel` and never reads a YAML file,
so copying `dashboards/net_sentinel.yaml` into the HA config directory does
nothing at all. This repo previously carried two YAML "dashboards" that were
never read by anything and drifted for months.

So the YAML here is the source, and this script is the only way it reaches
Home Assistant:

  dashboard -> websocket `lovelace/config/save` (no restart, takes effect at once)
  theme     -> scp into <config>/themes/, then `frontend.reload_themes`

The theme is a real file that HA does read, so it needs file access; the
dashboard does not.

Usage
-----
    export HA_TOKEN=...                      # long-lived access token
    ./deploy_dashboard.py save               # push the dashboard
    ./deploy_dashboard.py theme              # push the theme, reload themes
    ./deploy_dashboard.py all                # both
    ./deploy_dashboard.py get out.yaml       # fetch the live dashboard back

Environment
-----------
    HA_TOKEN        required. Long-lived access token.
    HA_HOST         default 192.168.1.50:8123
    HA_DASHBOARD    default net-sentinel   (the dashboard's url_path)
    HA_SSH          default root@192.168.1.50      (theme deploy only)
    HA_CONFIG_DIR   default /usr/share/hassio/homeassistant
    HA_CONFIG_OWNER default abhishek:abhishek      (theme file ownership)
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import websockets
import yaml

HERE = Path(__file__).resolve().parent
DASHBOARD = HERE / "dashboards" / "net_sentinel.yaml"
THEME = HERE / "themes" / "net-sentinel.yaml"

HOST = os.environ.get("HA_HOST", "192.168.1.50:8123")
URL_PATH = os.environ.get("HA_DASHBOARD", "net-sentinel")
SSH = os.environ.get("HA_SSH", "root@192.168.1.50")
CONFIG_DIR = os.environ.get("HA_CONFIG_DIR", "/usr/share/hassio/homeassistant")
OWNER = os.environ.get("HA_CONFIG_OWNER", "abhishek:abhishek")


def token():
    value = os.environ.get("HA_TOKEN")
    if not value:
        sys.exit("HA_TOKEN is not set. Export a long-lived access token.")
    return value


def load_dashboard():
    config = yaml.safe_load(DASHBOARD.read_text())
    # ns_styles only exists to host YAML anchors for the card_mod blocks. The
    # loader has already expanded them, so the holder key must not be shipped.
    config.pop("ns_styles", None)
    return config


async def _ws(message, expect_result=False):
    async with websockets.connect(
        f"ws://{HOST}/api/websocket", max_size=32 * 1024 * 1024
    ) as ws:
        hello = json.loads(await ws.recv())
        if hello.get("type") != "auth_required":
            sys.exit(f"unexpected greeting from {HOST}: {hello}")
        await ws.send(json.dumps({"type": "auth", "access_token": token()}))
        ack = json.loads(await ws.recv())
        if ack.get("type") != "auth_ok":
            sys.exit(f"auth failed: {ack}")
        await ws.send(json.dumps({"id": 1, **message}))
        while True:
            reply = json.loads(await ws.recv())
            if reply.get("id") != 1:
                continue
            if not reply.get("success"):
                sys.exit(f"FAILED: {json.dumps(reply.get('error'), indent=2)}")
            return reply.get("result") if expect_result else None


def save_dashboard():
    config = load_dashboard()
    asyncio.run(_ws({
        "type": "lovelace/config/save",
        "url_path": URL_PATH,
        "config": config,
    }))
    views = ", ".join(v.get("title", "?") for v in config.get("views", []))
    print(f"dashboard -> {URL_PATH} ({len(config.get('views', []))} views: {views})")


def get_dashboard(out_path):
    result = asyncio.run(_ws(
        {"type": "lovelace/config", "url_path": URL_PATH, "force": True},
        expect_result=True,
    ))
    Path(out_path).write_text(yaml.safe_dump(
        result, sort_keys=False, allow_unicode=True,
        default_flow_style=False, width=100,
    ))
    print(f"live dashboard -> {out_path}")


def deploy_theme():
    remote_dir = f"{CONFIG_DIR}/themes/net-sentinel"
    remote_file = f"{remote_dir}/net-sentinel.yaml"
    subprocess.run(["ssh", SSH, f"mkdir -p {remote_dir}"], check=True)
    subprocess.run(["scp", "-q", str(THEME), f"{SSH}:{remote_file}"], check=True)
    subprocess.run(
        ["ssh", SSH, f"chown {OWNER} {remote_file} && chmod 644 {remote_file}"],
        check=True,
    )
    # A theme file on disk does nothing until the frontend re-reads it.
    subprocess.run([
        "curl", "-sS", "-X", "POST",
        "-H", f"Authorization: Bearer {token()}",
        "-H", "Content-Type: application/json",
        f"http://{HOST}/api/services/frontend/reload_themes",
        "-d", "{}", "-o", "/dev/null",
    ], check=True)
    print(f"theme -> {remote_file} (themes reloaded)")
    print("  note: reload_themes transiently drops card-mod styling on any "
          "already-open tab. Reload the page once; it is not a real failure.")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "all"
    if action == "save":
        save_dashboard()
    elif action == "theme":
        deploy_theme()
    elif action == "all":
        deploy_theme()
        save_dashboard()
    elif action == "get":
        if len(sys.argv) != 3:
            sys.exit("usage: deploy_dashboard.py get <out.yaml>")
        get_dashboard(sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
