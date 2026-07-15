"""Concrete verification specialist."""

from coding_agent.agents.base import BaseAgent
from coding_agent.state import AgentName, AgentResult, AgentResultStatus
from coding_agent.tools.base import ToolRole


class TesterAgent(BaseAgent):
    name = AgentName.TESTER
    role = ToolRole.TESTER
    responsibility = "Execute concrete allowed checks and preserve their real structured outcomes."
    allowed_tool_names = frozenset(
        {"read_file", "list_files", "search_files", "run_command", "repository_status"}
    )

    def validate_result(self, result: AgentResult) -> None:
        if result.status is AgentResultStatus.SUCCEEDED and not result.checks:
            raise ValueError("Tester cannot succeed without at least one recorded check.")
