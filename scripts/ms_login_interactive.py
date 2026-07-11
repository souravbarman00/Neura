#!/usr/bin/env python3
"""Interactive Microsoft sign-in for Neura (Outlook + Teams via Graph).

Unlike the old device-code flow (scripts/ms_login.py), this opens your DEFAULT
BROWSER for an authorization-code + PKCE sign-in. On an Entra-registered /
Intune-managed Mac (Company Portal + the Microsoft Enterprise SSO extension),
the browser carries your device's compliance claim (the Primary Refresh Token),
so a Conditional Access policy that demands a "compliant device" is satisfied —
the exact check that device-code could not pass.

On success it writes MS_REFRESH_TOKEN into .env; Neura's graph_tool refreshes it
from there. Uses the MS_CLIENT_ID / MS_TENANT_ID already in your .env.

Run it yourself so the browser can open:
    ! .venv/bin/python scripts/ms_login_interactive.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import msal

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

# Delegated scopes for Outlook mail+calendar and Teams chats. Reserved scopes
# (offline_access / openid / profile) are added by MSAL automatically — don't list them.
SCOPES = [
    "User.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Chat.Read",
    "Chat.ReadWrite",
]


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# Well-known Microsoft first-party PUBLIC clients that support interactive
# (loopback / localhost redirect) sign-in with broad delegated Graph scopes.
# If one is blocked by an "assignment required" policy (AADSTS50105), try the next.
KNOWN_CLIENTS: dict[str, str] = {
    "azure-cli": "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
    "azure-powershell": "1950a258-227b-4e31-a9cf-717495945fc2",
    "graph-cli": "14d82eec-204b-4c2f-b7e8-296a70dab67e",
    "office": "d3590ed6-52b3-4102-aeff-aad2292ab01c",
}


def _set_env(key: str, val: str) -> None:
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    out, done = [], False
    for ln in lines:
        if ln.startswith(f"{key}="):
            out.append(f"{key}={val}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={val}")
    ENV.write_text("\n".join(out) + "\n")


def main() -> int:
    env = _load_env()
    # Pick the client to try: an alias/id passed as the first arg wins, else .env's MS_CLIENT_ID.
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    client_id = KNOWN_CLIENTS.get(arg, arg) or os.environ.get("MS_CLIENT_ID") or env.get("MS_CLIENT_ID")
    tenant = os.environ.get("MS_TENANT_ID") or env.get("MS_TENANT_ID") or "organizations"
    if not client_id:
        print("ERROR: no client id. Pass one, or set MS_CLIENT_ID in .env.", file=sys.stderr)
        print("Try:  scripts/ms_login_interactive.py azure-cli", file=sys.stderr)
        return 2

    authority = f"https://login.microsoftonline.com/{tenant}"
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)

    print(f"Signing in to tenant '{tenant}' with client {client_id}.")
    print("Your browser will open — complete the Microsoft sign-in there.\n")

    # Opens the system browser, listens on http://localhost:<free port> for the
    # redirect. The Enterprise SSO extension injects the device PRT into that
    # browser session, satisfying device-based Conditional Access.
    result = app.acquire_token_interactive(SCOPES, prompt="select_account")

    if "access_token" not in result:
        print("\nSign-in failed:", result.get("error"), "-", result.get("error_description"),
              file=sys.stderr)
        return 1

    # Pull the raw refresh token out of the serialized MSAL cache so graph_tool
    # (which does its own refresh over HTTP) can reuse it.
    blob = json.loads(cache.serialize() or "{}")
    rts = blob.get("RefreshToken", {})
    rt = next((e.get("secret") for e in rts.values() if e.get("secret")), None)
    if not rt:
        print("\nSigned in, but no refresh token was returned (offline_access may be blocked).",
              file=sys.stderr)
        return 1

    # Persist BOTH the working client id and its refresh token, so graph_tool
    # refreshes with the same client the token was minted for.
    _set_env("MS_CLIENT_ID", client_id)
    _set_env("MS_REFRESH_TOKEN", rt)
    account = (result.get("id_token_claims") or {}).get("preferred_username", "your account")
    granted = result.get("scope", "")
    print(f"\n✅ Connected as {account} (client {client_id}).")
    print(f"   Granted scopes: {granted}")
    print("   MS_CLIENT_ID + MS_REFRESH_TOKEN written to .env — Outlook & Teams are now live.")
    print("   (Restart the runtime if it was already running: scripts/run_server.sh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
