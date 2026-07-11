#!/usr/bin/env python
"""One-time Microsoft sign-in (device-code flow) for Neura's Outlook + Teams tools.

Reads MS_CLIENT_ID / MS_TENANT_ID from .env (set them in the Configuration panel first),
walks you through the device-code sign-in, and saves MS_REFRESH_TOKEN to .env.

Run:  .venv/bin/python scripts/ms_login.py
Then in Neura's Configuration panel click "Save & apply" (reloads the runtime).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
SCOPES = "offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite Chat.Read Chat.ReadWrite"


def env_get(key: str) -> str | None:
    if ENV.exists():
        for ln in ENV.read_text(encoding="utf-8").splitlines():
            if ln.startswith(key + "="):
                return ln.split("=", 1)[1].strip()
    return None


def env_set(key: str, value: str) -> None:
    lines, found = [], False
    if ENV.exists():
        for ln in ENV.read_text(encoding="utf-8").splitlines():
            if ln.startswith(key + "="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(ln)
    if not found:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ENV.chmod(0o600)


def main() -> None:
    tenant = env_get("MS_TENANT_ID") or "common"
    client = env_get("MS_CLIENT_ID")
    if not client:
        print("MS_CLIENT_ID is not set. Add MS_CLIENT_ID (and MS_TENANT_ID) in Neura's "
              "Configuration panel and Save, then re-run this script.")
        sys.exit(1)

    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    dc = httpx.post(f"{base}/devicecode", data={"client_id": client, "scope": SCOPES}, timeout=30).json()
    if "device_code" not in dc:
        print("Failed to start device-code login:", dc)
        sys.exit(1)

    print("\n" + "=" * 60)
    print(dc.get("message", f"Go to {dc.get('verification_uri')} and enter code {dc.get('user_code')}"))
    print("=" * 60 + "\n")

    interval = int(dc.get("interval", 5))
    device_code = dc["device_code"]
    expires = time.time() + int(dc.get("expires_in", 900))
    print("Waiting for you to complete sign-in in the browser…")
    while time.time() < expires:
        time.sleep(interval)
        tok = httpx.post(
            f"{base}/token",
            data={
                "client_id": client,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
            timeout=30,
        ).json()
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err:
            print("Sign-in failed:", tok.get("error_description", err))
            sys.exit(1)
        rt = tok.get("refresh_token")
        if rt:
            env_set("MS_REFRESH_TOKEN", rt)
            print("\n✓ Signed in. MS_REFRESH_TOKEN saved to .env.")
            print("Now click 'Save & apply' in Neura's Configuration panel (reloads the runtime).")
            return
        print("No refresh token returned:", tok)
        sys.exit(1)
    print("Device code expired — please run the script again.")
    sys.exit(1)


if __name__ == "__main__":
    main()
