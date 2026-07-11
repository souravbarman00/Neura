# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

import logging
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.agent_network_editor.constants import AGENT_NETWORK_DEFINITION
from coded_tools.agent_network_editor.progress_handler import ProgressHandler


class SetToolArgs(CodedTool):
    """
    CodedTool implementation which sets the non-secret `args` (and `toolbox`) of a
    tool node inside the agent network definition held in the sly data.

    This is the definition-path producer of non-secret tool selection (backend,
    index/namespace, embedding model/dimensions, chunk params). It is kept separate
    from `update_agent` (whose mandatory `new_down_chains` check blocks a body-less
    tool node and whose semantics are down-chain editing) so an args-only edit can
    never silently clear an agent's down-chains.

    Secrets (DB credentials, API keys, endpoints) are NEVER written here — they flow
    at runtime via sly_data. `args` must be a flat dict of scalar values only.
    """

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: An argument dictionary whose keys are the parameters
                to the coded tool and whose values are the values passed for them
                by the calling agent.  This dictionary is to be treated as read-only.

                The argument dictionary expects the following keys:
                    "agent_name": the name of the tool node to set args on.
                    "args": a flat dict of non-secret str|int|float|bool selections.
                    "toolbox": (optional) the toolbox tool this node references.

        :param sly_data: A dictionary whose keys are defined by the agent hierarchy,
                but whose values are meant to be kept out of the chat stream.

                Keys expected for this implementation are:
                    "agent_network_definition": an outline of an agent network

        :return:
            In case of successful execution:
                a text string confirming the args were set on the tool node.
            otherwise:
                a text string of an error message in the format:
                "Error: <error message>"
        """
        network_def: dict[str, Any] = sly_data.get(AGENT_NETWORK_DEFINITION)
        if not network_def:
            return "Error: No network in sly data!"

        the_agent_name: str = args.get("agent_name")
        if not the_agent_name:
            return "Error: No agent_name provided."

        node: dict[str, Any] = network_def.get(the_agent_name)
        if node is None:
            return f"Error: node '{the_agent_name}' not found."

        # Must be a tool node (body-less or already carrying a toolbox), never an agent.
        # Guarding here prevents an args write from clobbering an agent definition.
        if (
            node.get("instructions")
            or node.get("description")
            or (isinstance(node.get("tools"), list) and node["tools"])
        ):
            return f"Error: '{the_agent_name}' is an agent node, not a tool node."

        toolbox = args.get("toolbox")
        if toolbox:
            node["toolbox"] = toolbox

        new_args = args.get("args")
        if new_args is not None:
            # Flat, scalar, secret-free (HOCON-scalar guard): reject nested/None values.
            if not isinstance(new_args, dict) or any(
                not isinstance(v, (str, int, float, bool)) for v in new_args.values()
            ):
                return "Error: args must be a flat dict of str|int|float|bool (no nested/None)."
            node.setdefault("toolbox", toolbox or the_agent_name)
            node["args"] = new_args

        network_def[the_agent_name] = node
        sly_data[AGENT_NETWORK_DEFINITION] = network_def

        logger = logging.getLogger(self.__class__.__name__)
        logger.info(">>>>>>>>>>>>>>>>>>>Set Tool Args>>>>>>>>>>>>>>>>>>")
        logger.info("Tool Node: %s", str(the_agent_name))
        logger.info("Args: %s", str(new_args))
        logger.info("The resulting agent network definition: \n %s", str(network_def))

        await ProgressHandler.report_progress(args, network_def)

        logger.debug(">>>>>>>>>>>>>>>>>>> DONE %s !!!>>>>>>>>>>>>>>>>>>", self.__class__.__name__)
        return f"Set args on tool node '{the_agent_name}'."
