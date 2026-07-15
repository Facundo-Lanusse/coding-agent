"""Repository discovery specialist."""

from coding_agent.agents.base import BaseAgent
from coding_agent.state import AgentName
from coding_agent.tools.base import ToolRole


class ExplorerAgent(BaseAgent):
    name = AgentName.EXPLORER
    role = ToolRole.EXPLORER
    responsibility = (
        "Understand repository structure, architecture, dependencies, conventions, "
        "and relevant files."
    )
    allowed_tool_names = frozenset(
        {"read_file", "list_files", "search_files", "repository_status", "run_command"}
    )
