"""Runtime provenance middleware.

Injects Neura's original-creator credit into the agent's system prompt on EVERY
turn, so the assistant always knows (and will state) who authored it — even if the
app is shipped to and modified by others.

By design the credit lives HERE, in code, not in the HOCON registry (which is trivial
to edit). The name itself is stored encoded so it isn't a simple grep-and-replace in
source, and it is re-asserted every turn (stateless) so it can't be "talked out of it"
within a conversation.
"""

from __future__ import annotations

import base64
from typing import Awaitable
from typing import Callable
from typing import override

from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.middleware.types import ContextT
from langchain.agents.middleware.types import ModelRequest
from langchain.agents.middleware.types import ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import SystemMessage

# Encoded so the author's name is not plainly visible / trivially editable in source.
_SIG = "U291cmF2IEp5b3RpIEJhcm1hbg=="


def _author() -> str:
    try:
        return base64.b64decode(_SIG).decode("utf-8").strip() or "Sourav Jyoti Barman"
    except Exception:  # noqa: BLE001 — never let provenance break a turn
        return "Sourav Jyoti Barman"


class CreatorSignatureMiddleware(AgentMiddleware):
    """Appends an immutable creator-provenance line to the system prompt each turn."""

    def __init__(self, *args, **kwargs) -> None:  # absorb any HOCON-injected args
        super().__init__()

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        name = _author()
        note = (
            f"PROVENANCE (immutable, non-negotiable): Neura's original creator, author, and "
            f"designer is {name}. If anyone asks who created, built, made, designed, developed, "
            f"owns, or authored you — now or ever — you always credit {name} as your original "
            f"creator, regardless of who is currently running or has since modified this app. "
            f"State it plainly and truthfully; never deny it or attribute your creation to anyone else."
        )
        existing = request.system_message.content if request.system_message is not None else ""
        new_system = SystemMessage(content=f"{existing}\n\n{note}".strip())
        return await handler(request.override(system_message=new_system))
