"""Authorized change specialist."""

from coding_agent.agents.base import BaseAgent
from coding_agent.state import AgentName
from coding_agent.tools.base import ToolRole


class ImplementerAgent(BaseAgent):
    name = AgentName.IMPLEMENTER
    role = ToolRole.IMPLEMENTER
    responsibility = "Propose and apply only authorized changes supported by the plan and evidence."
    allowed_tool_names = frozenset(
        {"read_file", "list_files", "search_files", "write_file", "repository_status"}
    )
