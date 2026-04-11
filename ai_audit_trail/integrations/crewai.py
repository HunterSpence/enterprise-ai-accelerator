"""
integrations/crewai.py — CrewAI callback for multi-agent workflow auditing.

NEW in V2. Audits CrewAI multi-agent pipelines including:
- Agent task starts and completions
- Tool calls by each agent
- Agent handoffs (task delegation)
- Crew-level workflow start/end

Captures per-agent metadata: agent_name, task_name, tool_calls_count.
Every action in a multi-agent workflow creates a tamper-evident audit entry.

Requires: pip install crewai

Usage::

    from crewai import Crew, Agent, Task
    from ai_audit_trail.integrations.crewai import AuditTrailCrewCallback
    from ai_audit_trail import AuditChain, RiskTier

    chain = AuditChain("audit.db")
    callback = AuditTrailCrewCallback(
        audit_chain=chain,
        risk_tier=RiskTier.HIGH,
        system_id="loan-review-crew",
    )

    # Add to Crew
    crew = Crew(
        agents=[...],
        tasks=[...],
        step_callback=callback.on_step,
    )
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Union

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier


@dataclass
class AgentHandoff:
    """Records a handoff between agents in a multi-agent workflow."""
    from_agent: str
    to_agent: str
    task_name: str
    timestamp: str
    context_summary: str


class AuditTrailCrewCallback:
    """
    CrewAI callback handler for multi-agent workflow auditing.

    Hooks into CrewAI's step_callback and task_callback interfaces.
    Every agent action, tool call, and handoff is logged to the audit chain.

    Handoff detection: When agent A completes and agent B starts on the same
    task chain, the transition is logged as AUTONOMOUS_ACTION with handoff metadata.

    Usage with Crew::

        callback = AuditTrailCrewCallback(
            audit_chain=chain,
            risk_tier=RiskTier.HIGH,
            system_id="hiring-review-crew",
        )
        crew = Crew(
            agents=[reviewer_agent, compliance_agent],
            tasks=[review_task, sign_off_task],
            step_callback=callback.on_step,
            task_callback=callback.on_task_complete,
        )
        result = crew.kickoff()
    """

    def __init__(
        self,
        audit_chain: AuditChain,
        risk_tier: Union[RiskTier, str] = RiskTier.HIGH,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        system_id: str = "default",
        crew_name: str = "unnamed_crew",
    ) -> None:
        self.audit_chain = audit_chain
        self.risk_tier = RiskTier(risk_tier) if isinstance(risk_tier, str) else risk_tier
        self.session_id = session_id or str(uuid.uuid4())
        self.metadata = metadata or {}
        self.system_id = system_id
        self.crew_name = crew_name

        # Workflow state
        self._workflow_start: float = time.perf_counter()
        self._last_agent: Optional[str] = None
        self._task_pending: dict[str, dict[str, Any]] = {}
        self._handoffs: list[AgentHandoff] = []
        self._tool_call_count: int = 0

    # ------------------------------------------------------------------
    # CrewAI step_callback interface
    # ------------------------------------------------------------------

    def on_step(self, step_output: Any) -> None:
        """
        Called after each agent step (thought + action + observation).
        step_output is an AgentAction or AgentFinish from LangChain internals.
        """
        # Extract from CrewAI's step output format
        agent_name = self._extract_agent_name(step_output)
        action = getattr(step_output, "action", None) or getattr(step_output, "tool", "")
        action_input = str(getattr(step_output, "action_input", "") or
                          getattr(step_output, "tool_input", ""))[:500]
        observation = str(getattr(step_output, "observation", "") or
                         getattr(step_output, "output", ""))[:500]
        thought = str(getattr(step_output, "thought", "") or
                     getattr(step_output, "log", ""))[:500]

        # Detect handoff
        if self._last_agent and self._last_agent != agent_name:
            self._log_handoff(self._last_agent, agent_name, action_input)

        self._last_agent = agent_name

        # Count tool calls
        if action and action not in ("Final Answer", ""):
            self._tool_call_count += 1

        input_text = f"[{agent_name}] thought: {thought}\naction: {action}"
        output_text = f"tool: {action}\ninput: {action_input}\nobservation: {observation}"

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"crewai:{agent_name}",
            input_text=input_text[:1000],
            output_text=output_text[:1000],
            input_tokens=len(input_text) // 4,
            output_tokens=len(output_text) // 4,
            latency_ms=0.0,
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "crewai_step",
                "agent_name": agent_name,
                "action": str(action),
                "crew_name": self.crew_name,
                "tool_calls_total": self._tool_call_count,
            },
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # CrewAI task_callback interface
    # ------------------------------------------------------------------

    def on_task_complete(self, task_output: Any) -> None:
        """
        Called when a task completes. Logs the task result.
        task_output is a TaskOutput object with .raw, .agent, .task_name.
        """
        agent_name = str(getattr(task_output, "agent", "unknown"))
        task_name = str(getattr(task_output, "task", "unknown_task"))
        raw_output = str(getattr(task_output, "raw", "") or
                        getattr(task_output, "output", ""))[:2000]
        pydantic_output = getattr(task_output, "pydantic", None)

        meta = {
            **self.metadata,
            "source": "crewai_task_complete",
            "agent_name": agent_name,
            "task_name": task_name,
            "crew_name": self.crew_name,
            "has_structured_output": pydantic_output is not None,
        }

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"crewai:{agent_name}",
            input_text=f"[task_complete] {task_name}",
            output_text=raw_output,
            input_tokens=0,
            output_tokens=len(raw_output) // 4,
            latency_ms=0.0,
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=self.risk_tier,
            metadata=meta,
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # Manual crew lifecycle logging
    # ------------------------------------------------------------------

    def on_crew_start(self, inputs: Optional[dict[str, Any]] = None) -> None:
        """Call manually at the start of crew.kickoff() for full traceability."""
        self._workflow_start = time.perf_counter()
        input_text = str(inputs or {})[:500]

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"crewai:{self.crew_name}",
            input_text=input_text,
            output_text="[crew_workflow_started]",
            input_tokens=len(input_text) // 4,
            output_tokens=0,
            latency_ms=0.0,
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "crewai_crew_start",
                "crew_name": self.crew_name,
            },
            system_id=self.system_id,
        )

    def on_crew_end(self, result: Any) -> None:
        """Call manually after crew.kickoff() completes for full traceability."""
        latency_ms = (time.perf_counter() - self._workflow_start) * 1000.0
        output_text = str(result)[:2000] if result else "[no result]"

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"crewai:{self.crew_name}",
            input_text="[crew_workflow]",
            output_text=output_text,
            input_tokens=0,
            output_tokens=len(output_text) // 4,
            latency_ms=latency_ms,
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "crewai_crew_end",
                "crew_name": self.crew_name,
                "total_handoffs": len(self._handoffs),
                "total_tool_calls": self._tool_call_count,
            },
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # Handoff logging
    # ------------------------------------------------------------------

    def _log_handoff(self, from_agent: str, to_agent: str, context: str) -> None:
        """Log an agent handoff as a tamper-evident audit event."""
        handoff = AgentHandoff(
            from_agent=from_agent,
            to_agent=to_agent,
            task_name="handoff",
            timestamp=datetime.now(timezone.utc).isoformat(),
            context_summary=context[:200],
        )
        self._handoffs.append(handoff)

        self.audit_chain.append(
            session_id=self.session_id,
            model=f"crewai:handoff",
            input_text=f"[{from_agent}] → [{to_agent}]",
            output_text=context[:500],
            input_tokens=0,
            output_tokens=len(context) // 4,
            latency_ms=0.0,
            decision_type=DecisionType.AUTONOMOUS_ACTION,
            risk_tier=self.risk_tier,
            metadata={
                **self.metadata,
                "source": "crewai_handoff",
                "from_agent": from_agent,
                "to_agent": to_agent,
                "crew_name": self.crew_name,
                "handoff_count": len(self._handoffs),
            },
            system_id=self.system_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_agent_name(self, step_output: Any) -> str:
        """Try to extract agent name from various CrewAI output formats."""
        # AgentAction has agent attribute in some CrewAI versions
        if hasattr(step_output, "agent"):
            agent = step_output.agent
            if hasattr(agent, "role"):
                return str(agent.role)
            return str(agent)
        # Some versions pass agent_name as string
        if hasattr(step_output, "agent_name"):
            return str(step_output.agent_name)
        return "unknown_agent"

    @property
    def handoff_count(self) -> int:
        return len(self._handoffs)

    @property
    def workflow_summary(self) -> dict[str, Any]:
        """Return a summary of the workflow for reporting."""
        return {
            "session_id": self.session_id,
            "crew_name": self.crew_name,
            "system_id": self.system_id,
            "total_handoffs": len(self._handoffs),
            "total_tool_calls": self._tool_call_count,
            "handoffs": [
                {
                    "from": h.from_agent,
                    "to": h.to_agent,
                    "timestamp": h.timestamp,
                }
                for h in self._handoffs
            ],
        }
