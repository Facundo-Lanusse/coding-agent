"""Human-approval boundary used by plan and supervision modes."""

from __future__ import annotations

from typing import Protocol

from coding_agent.models import ApprovalDecision, ApprovalRequest


class ApprovalProvider(Protocol):
    """Resolve an approval request without coupling the core to a terminal UI."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Return an explicit approval or rejection."""


class DenyAllApprovalProvider:
    """Safe default when no interactive or pre-authorized provider is supplied."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(
            approved=False,
            reason=f"No approval provider authorized {request.action}.",
        )
