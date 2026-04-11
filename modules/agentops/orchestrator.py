"""
AgentOps — Multi-Agent Orchestration Engine.

Demonstrates Claude as an AI orchestrator that decomposes tasks, routes to
specialized sub-agents (via tool calls), collects results, and synthesizes
a final answer. Each tool call represents a "specialized agent" with a
distinct domain: security, cost, migration, reporting.

Architecture:
  User Task → Orchestrator (Claude) → [tool calls = agent dispatches]
                                     ↓
                    Security Agent | Cost Agent | Migration Agent | Report Agent
                                     ↓
                              Final Synthesis
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

ORCHESTRATOR_SYSTEM = """You are an AI Orchestrator managing a team of specialized AI sub-agents for
enterprise cloud transformation. Your job is to:

1. Analyze the incoming task and decompose it into subtasks
2. Route each subtask to the appropriate specialized agent using the available tools
3. Each tool call represents dispatching work to a specialized agent
4. After collecting all agent results, synthesize a comprehensive final answer

Available specialized agents (tools):
- security_agent: Analyzes security posture, identifies vulnerabilities, checks compliance
- cost_agent: Analyzes cloud spend, identifies waste, models optimization scenarios
- migration_agent: Plans workload migrations, assesses complexity, sequences waves
- reporting_agent: Synthesizes findings into executive narratives for leadership

Always decompose the task and call multiple agents when the task spans multiple domains.
Think step by step about which agents are needed before making calls."""

# Specialized agent implementations — in production these would be separate services
AGENT_SYSTEM_PROMPTS = {
    "security_agent": """You are a senior cloud security architect. Analyze the provided context
and deliver a concise security assessment: key vulnerabilities, compliance gaps, and top 3 remediation priorities.
Be specific — name the resources, the risks, and the exact fixes. Respond in 3-5 bullet points.""",

    "cost_agent": """You are a FinOps specialist. Analyze the provided context and identify:
the biggest cost waste drivers, savings opportunities with dollar estimates, and quick-win optimizations.
Focus on actionable savings achievable in 30-90 days. Respond in 3-5 bullet points.""",

    "migration_agent": """You are a cloud migration architect. Analyze the provided context and provide:
a recommended migration approach, complexity assessment (1-10), key dependencies to resolve, and
the phasing strategy. Be specific about which workloads move first and why. Respond in 3-5 bullet points.""",

    "reporting_agent": """You are a management consulting partner. Given the technical findings,
create a concise executive narrative: the business situation, financial impact, top risk, and
the one decision the leadership team must make. Write for a CEO — no jargon. Respond in 2-3 paragraphs.""",
}


@dataclass
class AgentCallRecord:
    agent_name: str
    task_input: str
    result: str
    duration_ms: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrchestrationResult:
    task: str
    orchestration_plan: str = ""
    agent_calls: list = field(default_factory=list)  # list of AgentCallRecord
    final_synthesis: str = ""
    total_duration_ms: int = 0
    agents_invoked: list = field(default_factory=list)
    error: str = ""


class AgentOrchestrator:
    """
    Orchestrates multi-agent workflows using Claude's tool use capability.
    Each tool call represents dispatching a task to a specialized sub-agent,
    which is itself a Claude API call with a domain-specific system prompt.
    """

    def __init__(self, model: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

    @property
    def tools(self) -> list:
        """Tool definitions that represent specialized sub-agents."""
        return [
            {
                "name": "security_agent",
                "description": "Dispatch a task to the Security Analysis Agent. Use for: vulnerability assessment, compliance checking, IAM review, network security analysis, encryption gaps.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The specific security analysis task to perform"
                        },
                        "context": {
                            "type": "string",
                            "description": "Relevant context or data for the security agent to analyze"
                        }
                    },
                    "required": ["task", "context"]
                }
            },
            {
                "name": "cost_agent",
                "description": "Dispatch a task to the FinOps Cost Analysis Agent. Use for: spend analysis, waste identification, savings modeling, reserved instance recommendations, rightsizing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The specific cost analysis task to perform"
                        },
                        "context": {
                            "type": "string",
                            "description": "Relevant context or data for the cost agent to analyze"
                        }
                    },
                    "required": ["task", "context"]
                }
            },
            {
                "name": "migration_agent",
                "description": "Dispatch a task to the Migration Planning Agent. Use for: 6R classification, migration wave planning, dependency mapping, effort estimation, risk assessment.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The specific migration planning task to perform"
                        },
                        "context": {
                            "type": "string",
                            "description": "Relevant context or data for the migration agent to analyze"
                        }
                    },
                    "required": ["task", "context"]
                }
            },
            {
                "name": "reporting_agent",
                "description": "Dispatch a task to the Executive Reporting Agent. Use for: synthesizing findings into executive narratives, board deck content, stakeholder summaries, financial impact framing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The specific reporting task to perform"
                        },
                        "context": {
                            "type": "string",
                            "description": "All findings and data to synthesize into an executive report"
                        }
                    },
                    "required": ["task", "context"]
                }
            },
        ]

    def _run_sub_agent(self, agent_name: str, task: str, context: str) -> tuple[str, int]:
        """Execute a specialized sub-agent and return (result, duration_ms)."""
        system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_name, "You are a helpful expert. Analyze the provided context.")
        start = time.time()
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Task: {task}\n\nContext:\n{context}"
            }]
        )
        elapsed_ms = int((time.time() - start) * 1000)
        result = message.content[0].text
        return result, elapsed_ms

    def orchestrate(self, task: str, context: str = "") -> OrchestrationResult:
        """
        Run the multi-agent orchestration loop.

        Args:
            task: High-level task description for the orchestrator
            context: Optional context data (config, metrics, workload list, etc.)

        Returns:
            OrchestrationResult with full execution trace
        """
        start_total = time.time()
        result = OrchestrationResult(task=task)
        agent_calls: list[AgentCallRecord] = []

        # Build the user message
        user_message = f"Task: {task}"
        if context:
            user_message += f"\n\nContext/Data:\n{context[:4000]}"

        messages = [{"role": "user", "content": user_message}]

        # Orchestration loop — Claude decides which agents to call
        max_iterations = 6  # Safety limit
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=ORCHESTRATOR_SYSTEM,
                tools=self.tools,
                messages=messages
            )

            # Capture orchestrator's reasoning on first pass
            if iteration == 1:
                for block in response.content:
                    if hasattr(block, "text") and block.text:
                        result.orchestration_plan = block.text
                        break

            # If no more tool calls, we're done
            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text") and block.text:
                        result.final_synthesis = block.text
                break

            # Process tool calls (agent dispatches)
            if response.stop_reason != "tool_use":
                break

            # Append assistant response to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call (dispatch to sub-agents)
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                agent_name = block.name
                agent_input = block.input
                task_for_agent = agent_input.get("task", "")
                context_for_agent = agent_input.get("context", "")

                # Track which agents were invoked
                if agent_name not in result.agents_invoked:
                    result.agents_invoked.append(agent_name)

                # Run the sub-agent
                agent_result, duration_ms = self._run_sub_agent(
                    agent_name, task_for_agent, context_for_agent
                )

                # Record the call
                agent_calls.append(AgentCallRecord(
                    agent_name=agent_name,
                    task_input=task_for_agent,
                    result=agent_result,
                    duration_ms=duration_ms,
                ))

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": agent_result,
                })

            # Feed all agent results back to orchestrator
            messages.append({"role": "user", "content": tool_results})

        result.agent_calls = agent_calls
        result.total_duration_ms = int((time.time() - start_total) * 1000)

        if not result.final_synthesis and agent_calls:
            # Fallback: use last agent result as synthesis
            result.final_synthesis = agent_calls[-1].result

        return result
