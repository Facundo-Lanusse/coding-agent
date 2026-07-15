"""Request and diff compliance specialist."""

from coding_agent.agents.base import BaseAgent
from coding_agent.state import AgentName, AgentResult, AgentResultStatus
from coding_agent.tools.base import ToolRole


class ReviewerAgent(BaseAgent):
    name = AgentName.REVIEWER
    role = ToolRole.REVIEWER
    responsibility = (
        "Inspect changes and checks, then validate every user criterion without writing."
    )
    allowed_tool_names = frozenset({"read_file", "list_files", "search_files", "repository_status"})

    def validate_result(self, result: AgentResult) -> None:
        if result.status is AgentResultStatus.SUCCEEDED and result.criteria_met is not True:
            raise ValueError("Reviewer cannot accept a change without meeting the criteria.")
