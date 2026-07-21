"""Neura CodedTool: EDIT Figma via the official remote MCP server (write-to-canvas).

Figma's remote MCP (https://mcp.figma.com/mcp, HTTP) supports creating/editing/deleting
pages, frames, text, components via the `use_figma` tool — but it authenticates with OAuth,
which neuro-san's static-header MCP client can't do. So we bridge it with the official `mcp`
Python SDK's streamable-HTTP + OAuth client. The OAuth sign-in happens ONCE in your browser
(a local callback catches the redirect); the token is cached under data/ and reused.

Requires a browser on the machine running the neuro-san server (i.e. run Neura locally).
"""
from __future__ import annotations

import asyncio
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from neuro_san.interfaces.coded_tool import CodedTool

SERVER_URL = "https://mcp.figma.com/mcp"
CALLBACK_PORT = 3456
CALLBACK_URL = f"http://localhost:{CALLBACK_PORT}/callback"
TOKEN_FILE = Path(__file__).resolve().parents[2] / "data" / "figma_oauth.json"
AUTH_WAIT = 300  # seconds to wait for the user to complete the browser sign-in
CALL_TIMEOUT = 120


class _FileTokenStorage:
    """Persist OAuth tokens + dynamic-client registration to disk so sign-in is one-time."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:  # noqa: BLE001
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data))

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken
        d = self._read().get("tokens")
        return OAuthToken.model_validate(d) if d else None

    async def set_tokens(self, tokens) -> None:
        d = self._read(); d["tokens"] = tokens.model_dump(); self._write(d)

    async def get_client_info(self):
        import os

        from mcp.shared.auth import OAuthClientInformationFull
        d = self._read().get("client_info")
        if d:
            return OAuthClientInformationFull.model_validate(d)
        # Figma's remote MCP blocks anonymous dynamic client registration (403). If you have
        # a pre-registered client (partner credentials), set FIGMA_OAUTH_CLIENT_ID/SECRET to
        # skip registration and use it directly.
        cid = os.environ.get("FIGMA_OAUTH_CLIENT_ID")
        if cid:
            secret = os.environ.get("FIGMA_OAUTH_CLIENT_SECRET")
            return OAuthClientInformationFull(
                client_id=cid,
                client_secret=secret,
                redirect_uris=[CALLBACK_URL],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                token_endpoint_auth_method="client_secret_post" if secret else "none",
                scope="mcp:connect",
            )
        return None

    async def set_client_info(self, client_info) -> None:
        d = self._read(); d["client_info"] = client_info.model_dump(mode="json"); self._write(d)


class _Callback:
    """One-shot local HTTP server to receive the OAuth redirect (?code=&state=)."""

    def __init__(self) -> None:
        self.code: str | None = None
        self.state: str | None = None
        self._event = threading.Event()

    def wait(self, timeout: float):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *_a):  # noqa: N802 — silence
                pass

            def do_GET(self):  # noqa: N802
                q = parse_qs(urlparse(self.path).query)
                outer.code = (q.get("code") or [None])[0]
                outer.state = (q.get("state") or [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h3>Neura connected to Figma. You can close this tab.</h3>")
                outer._event.set()

        srv = HTTPServer(("127.0.0.1", CALLBACK_PORT), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        ok = self._event.wait(timeout)
        srv.shutdown()
        if not ok:
            raise TimeoutError("Timed out waiting for the Figma sign-in redirect.")
        return self.code, self.state


class FigmaEdit(CodedTool):
    """Read AND write Figma via the official remote MCP (use_figma) with OAuth."""

    async def _run(self, args: Dict[str, Any]) -> str:
        try:
            from mcp import ClientSession
            from mcp.client.auth import OAuthClientProvider
            from mcp.client.streamable_http import streamablehttp_client
            from mcp.shared.auth import OAuthClientMetadata
        except Exception as exc:  # noqa: BLE001
            return f"The `mcp` Python SDK (with OAuth) is required: {exc}"

        tool = (args.get("tool") or "").strip()
        arguments = args.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return "`arguments` must be a JSON object."

        cb = _Callback()

        async def redirect_handler(auth_url: str) -> None:
            webbrowser.open(auth_url)

        async def callback_handler():
            return await asyncio.to_thread(cb.wait, AUTH_WAIT)

        oauth = OAuthClientProvider(
            server_url=SERVER_URL,
            client_metadata=OAuthClientMetadata(
                client_name="Neura",
                redirect_uris=[CALLBACK_URL],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
            ),
            storage=_FileTokenStorage(TOKEN_FILE),
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )

        try:
            async with streamablehttp_client(SERVER_URL, auth=oauth) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=AUTH_WAIT)
                    if not tool:
                        listed = await session.list_tools()
                        lines = ["Figma (write-capable) MCP tools:"]
                        for t in listed.tools:
                            lines.append(f"- {t.name}: {(t.description or '').splitlines()[0][:160]}")
                        return "\n".join(lines)
                    result = await asyncio.wait_for(session.call_tool(tool, arguments), timeout=CALL_TIMEOUT)
                    parts = []
                    for c in getattr(result, "content", []) or []:
                        parts.append(c.text if getattr(c, "type", "") == "text" else f"[{getattr(c, 'type', 'content')}]")
                    out = "\n".join(parts).strip()
                    if getattr(result, "isError", False):
                        return f"Figma edit tool '{tool}' error: {out or 'unknown error'}"
                    return out or "(done — no content returned)"
        except TimeoutError as exc:
            return f"Figma OAuth/timeout: {exc} (complete the sign-in in the browser, then retry)."
        except BaseException as exc:  # noqa: BLE001 — unwrap anyio TaskGroup ExceptionGroups
            import traceback

            def flatten(e):
                out = []
                inner = getattr(e, "exceptions", None)
                if inner:
                    for x in inner:
                        out.extend(flatten(x))
                else:
                    out.append(f"{type(e).__name__}: {e}")
                return out

            detail = " | ".join(flatten(exc)) or f"{type(exc).__name__}: {exc}"
            if "Registration failed: 403" in detail:
                return ("Figma's official remote MCP blocks anonymous client registration (403) — "
                        "it's gated to partner apps (VS Code, Cursor, Claude, …). Neura can't "
                        "self-register. Either set FIGMA_OAUTH_CLIENT_ID (a pre-registered Figma "
                        "MCP client) and retry, or use the plugin-based editing path (talk-to-figma).")
            try:
                (TOKEN_FILE.parent / "figma_edit_error.log").write_text(
                    "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                )
            except Exception:  # noqa: BLE001
                pass
            return f"Figma edit failed — real cause: {detail}  (full traceback: data/figma_edit_error.log)"

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await self._run(args)

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return asyncio.run(self._run(args))
