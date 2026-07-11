"""Conversation memory compression via the `memory_compressor` agent network.

Keeps the most recent turns verbatim and folds older ones into a rolling summary
stored on the conversation — the compact/"compressed" representation of history.
"""
from __future__ import annotations

from backend import store
from backend.nsclient import collect

# Start compressing once this many un-summarized messages accumulate,
# always leaving the most recent `KEEP_RECENT` messages verbatim.
THRESHOLD = 10
KEEP_RECENT = 4


async def maybe_compress(cid: str):
    """Fold older turns into the rolling summary. Returns the new summary or None."""
    total = store.message_count(cid)
    summary, upto = store.get_summary_state(cid)
    if total - upto < THRESHOLD:
        return None

    fold_upto = total - KEEP_RECENT
    if fold_upto <= upto:
        return None

    batch = store.messages_after(cid, upto)[: fold_upto - upto]
    if not batch:
        return None

    transcript = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Neura'}: {m['text']}" for m in batch
    )
    prompt = f"PRIOR SUMMARY:\n{summary or '(none)'}\n\nNEW TURNS:\n{transcript}"

    new_summary, _sources, _ctx = await collect("memory_compressor", prompt)
    if new_summary:
        store.set_summary(cid, new_summary.strip(), fold_upto)
        return new_summary.strip()
    return None
