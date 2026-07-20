"""Neura CodedTool: drive a real browser with Playwright.

Neura can open a page, optionally run a few interaction steps, and then:
  - action="screenshot" — capture the page (viewport or full-page) as a PNG,
  - action="inspect"    — diagnose issues: collect console errors/warnings, uncaught
                          page errors, failed requests and 4xx/5xx responses, plus a
                          screenshot for context,
  - action="video"      — record a .webm of the session (great for reproducing a bug).

Artifacts are written under data/artifacts/ and returned as markdown that the chat
renders inline (`![…](/artifacts/…png)`; .webm/.mp4 render as a <video> player).

Needs the browser binary once:  python -m playwright install chromium
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "data" / "artifacts"
DEFAULT_TIMEOUT = 45          # seconds for the whole run
MAX_TIMEOUT = 180
MAX_STEPS = 30
KEEP_ARTIFACTS = 80           # prune older files beyond this many
VIEWPORT = {"width": 1280, "height": 800}

_INSTALL_HINT = (
    "Playwright's browser isn't installed. Run this once, then retry:\n"
    "`python -m playwright install chromium`"
)


def _slug(url: str) -> str:
    m = re.sub(r"^https?://", "", url or "page").strip("/")
    m = re.sub(r"[^a-zA-Z0-9]+", "-", m).strip("-").lower()
    return (m[:32] or "page")


def _prune() -> None:
    try:
        files = sorted(ARTIFACTS.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[KEEP_ARTIFACTS:]:
            try:
                old.unlink()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


async def _do_step(page, step: str) -> str:
    """Run one interaction step; returns a short note for the report."""
    step = (step or "").strip()
    if not step:
        return ""
    verb, _, rest = step.partition(":")
    verb = verb.strip().lower()
    rest = rest.strip()
    if verb == "goto" or (verb == "" and step.startswith("http")):
        await page.goto(rest or step, wait_until="load")
    elif verb == "click":
        await page.click(rest, timeout=15000)
    elif verb in ("fill", "type"):
        sel, _, val = rest.partition("|")
        await page.fill(sel.strip(), val)
    elif verb == "press":
        await page.keyboard.press(rest)
    elif verb in ("wait", "sleep"):
        await page.wait_for_timeout(float(rest or 1000))
    elif verb == "waitfor":
        await page.wait_for_selector(rest, timeout=15000)
    elif verb == "scroll":
        if "bottom" in rest.lower():
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        else:
            await page.evaluate(f"window.scrollBy(0, {int(rest or 600)})")
    else:
        return f"(skipped unknown step: {step})"
    return f"✓ {step}"


class BrowserTool(CodedTool):
    """Screenshot, record, or inspect a web page with a real (headless) browser."""

    async def _run(self, args: Dict[str, Any]) -> str:
        try:
            from playwright.async_api import async_playwright
        except Exception:  # noqa: BLE001
            return ("Playwright isn't installed. Run `pip install playwright` and "
                    "`python -m playwright install chromium`, then retry.")

        url = (args.get("url") or "").strip()
        action = (args.get("action") or "screenshot").strip().lower()
        steps: List[str] = args.get("steps") or []
        if isinstance(steps, str):
            steps = [s for s in re.split(r"[\n;]+", steps) if s.strip()]
        steps = steps[:MAX_STEPS]
        full_page = str(args.get("full_page", "false")).lower() in ("1", "true", "yes")
        try:
            timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT

        if not url and not any(str(s).strip().startswith(("goto", "http")) for s in steps):
            return "Provide a `url` to open (or a first step like `goto:https://…`)."

        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time())}-{_slug(url)}-{uuid.uuid4().hex[:6]}"

        # Collectors for inspect mode.
        console: List[str] = []
        page_errors: List[str] = []
        req_failed: List[str] = []
        bad_resp: List[str] = []

        try:
            return await asyncio.wait_for(
                self._drive(
                    async_playwright, url, action, steps, full_page, name,
                    console, page_errors, req_failed, bad_resp,
                ),
                timeout=timeout + 15,
            )
        except asyncio.TimeoutError:
            return f"Browser run timed out after {timeout}s."
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "Executable doesn't exist" in msg or "playwright install" in msg:
                return _INSTALL_HINT
            return f"Browser error: {msg}"

    async def _drive(self, async_playwright, url, action, steps, full_page, name,
                     console, page_errors, req_failed, bad_resp) -> str:
        record = {"record_video_dir": str(ARTIFACTS), "record_video_size": VIEWPORT} \
            if action == "video" else {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport=VIEWPORT, **record)
            page = await context.new_page()

            if action == "inspect":
                page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.on("requestfailed",
                        lambda r: req_failed.append(f"{r.url} — {(r.failure or '')}"))

                def _on_response(r):
                    if r.status >= 400:
                        bad_resp.append(f"{r.status} {r.url}")
                page.on("response", _on_response)

            notes: List[str] = []
            if url:
                await page.goto(url, wait_until="load")
            for s in steps:
                try:
                    n = await _do_step(page, s)
                    if n:
                        notes.append(n)
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"✗ {s} — {exc}")
            await page.wait_for_timeout(600)  # let late console/network settle

            title = await page.title()
            final_url = page.url

            if action == "video":
                vid = page.video
                await context.close()          # finalizes the recording
                await browser.close()
                out = ARTIFACTS / f"{name}.webm"
                try:
                    src = await vid.path()
                    Path(src).replace(out)
                except Exception:  # noqa: BLE001
                    pass
                _prune()
                head = f"**Recording** of {final_url}" + (f" — *{title}*" if title else "")
                steps_note = ("\n\n" + "\n".join(f"- {n}" for n in notes)) if notes else ""
                if out.exists():
                    return f"{head}\n\n![recording](/artifacts/{out.name}){steps_note}"
                return f"{head}\n\n(could not save the video){steps_note}"

            # screenshot / inspect both capture a PNG
            shot = ARTIFACTS / f"{name}.png"
            await page.screenshot(path=str(shot), full_page=full_page)
            await context.close()
            await browser.close()
            _prune()

            head = f"**{title or final_url}**  \n{final_url}"
            steps_note = ("\n\n**Steps:** " + "; ".join(notes)) if notes else ""
            img = f"\n\n![screenshot](/artifacts/{shot.name})"

            if action != "inspect":
                return f"{head}{steps_note}{img}"

            # ---- inspection report ----
            def _block(title_, items, limit=15):
                if not items:
                    return f"- {title_}: none ✓"
                shown = items[:limit]
                more = f" (+{len(items) - limit} more)" if len(items) > limit else ""
                body = "\n".join(f"  - {x}" for x in shown)
                return f"- {title_}: {len(items)}{more}\n{body}"

            errs = [c for c in console if c.startswith("[error]")]
            warns = [c for c in console if c.startswith("[warning]")]
            report = "\n".join([
                head,
                "",
                "**Inspection**",
                _block("Console errors", errs),
                _block("Console warnings", warns),
                _block("Uncaught page errors", page_errors),
                _block("Failed requests", req_failed),
                _block("HTTP 4xx/5xx responses", bad_resp),
            ])
            return f"{report}{steps_note}{img}"

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return asyncio.run(self._run(args))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await self._run(args)
