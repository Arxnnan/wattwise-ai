"""WattWise AI — Base agent with tool-calling reasoning loop.

Each agent follows: Observe → Think → Act → Observe (ReAct pattern).
Tools are Python callables the agent can invoke to query data or run models.
The LLM (Gemini) decides which tool to call and interprets results.
"""
from __future__ import annotations
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger(__name__)

MAX_ITERATIONS = 8
MAX_MEMORY = 20


@dataclass
class AgentMessage:
    role: str        # "user", "assistant", "tool", "system"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: dict          # JSON-schema-like description of expected args
    func: Callable[..., Any]  # the actual callable


class BaseAgent:
    """LLM-powered agent with tool-use reasoning loop.

    Subclasses define their system prompt and register domain-specific tools.
    The base class handles the observe-think-act loop and LLM interaction.
    """

    def __init__(self, name: str, role: str, system_prompt: str):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.tools: dict[str, AgentTool] = {}
        self.memory: list[AgentMessage] = []
        self._llm_available = False
        self._provider = None
        self._model = None  # kept for backward-compat with existing tests
        self._init_llm()

    def _init_llm(self):
        """Pick a provider via the LLM wrapper — supports Gemini, Groq, Ollama,
        OpenAI, Anthropic, HuggingFace via the LLM_PROVIDER env var."""
        from ml.agents.llm_provider import get_llm_provider
        self._provider = get_llm_provider()
        self._llm_available = self._provider.is_available()
        if self._llm_available:
            info = self._provider.info()
            log.info("[%s] LLM provider: %s (%s)", self.name, info.name, info.model)
        else:
            log.warning("[%s] No LLM provider available — set GEMINI_API_KEY, GROQ_API_KEY or run Ollama", self.name)

    def register_tool(self, tool: AgentTool):
        self.tools[tool.name] = tool

    def _build_tool_descriptions(self) -> str:
        if not self.tools:
            return "No tools available."
        lines = []
        for t in self.tools.values():
            params = ", ".join(f"{k}: {v}" for k, v in t.parameters.items())
            lines.append(f"  - {t.name}({params}) — {t.description}")
        return "\n".join(lines)

    def _build_prompt(self, user_query: str) -> str:
        tool_desc = self._build_tool_descriptions()
        history = ""
        for msg in self.memory[-10:]:
            if msg.role == "tool":
                history += f"\n[Tool Result: {msg.tool_name}]\n{msg.content}\n"
            else:
                history += f"\n[{msg.role.title()}]: {msg.content}\n"

        return f"""{self.system_prompt}

You are {self.name}, a {self.role}.

AVAILABLE TOOLS:
{tool_desc}

TOOL CALLING FORMAT:
When you need to use a tool, respond with EXACTLY this format:
TOOL_CALL: tool_name({{"param1": "value1", "param2": "value2"}})

After receiving tool results, analyze them and either call another tool or give your FINAL ANSWER.
When you have enough information, respond with:
FINAL_ANSWER: <your complete response>

CONVERSATION HISTORY:
{history}

USER QUERY: {user_query}

Think step by step. Use tools to gather real data before making claims."""

    def _parse_tool_call(self, response: str) -> tuple[str, dict] | None:
        match = re.search(r'TOOL_CALL:\s*(\w+)\((\{.*?\})\)', response, re.DOTALL)
        if match:
            name = match.group(1)
            try:
                args = json.loads(match.group(2))
                return name, args
            except json.JSONDecodeError:
                return name, {}
        return None

    def _parse_final_answer(self, response: str) -> str | None:
        match = re.search(r'FINAL_ANSWER:\s*(.*)', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _call_llm(self, prompt: str) -> str:
        if not self._llm_available or self._provider is None:
            return "FINAL_ANSWER: LLM unavailable — configure a provider in Alert Settings."
        try:
            return self._provider.generate(prompt).strip()
        except Exception as e:
            log.error("[%s] LLM call failed via %s: %s", self.name, self._provider.name, e)
            return f"FINAL_ANSWER: LLM error ({self._provider.name}) — {e}"

    def _coerce_arg(self, value: Any, expected_type: str) -> Any:
        """Coerce LLM-provided string args to the expected Python type.
        LLMs sometimes send '30' instead of 30 in JSON."""
        if isinstance(value, str):
            if "int" in expected_type:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass
            if "float" in expected_type:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    pass
        return value

    def _execute_tool(self, name: str, args: dict) -> str:
        if name not in self.tools:
            return f"Error: Unknown tool '{name}'. Available: {list(self.tools.keys())}"
        try:
            tool = self.tools[name]
            coerced_args = {}
            for k, v in args.items():
                expected = tool.parameters.get(k, "str")
                coerced_args[k] = self._coerce_arg(v, expected)
            result = tool.func(**coerced_args)
            if isinstance(result, (dict, list)):
                return json.dumps(result, indent=2, default=str)
            return str(result)
        except Exception as e:
            return f"Tool error: {e}"

    def run(self, query: str) -> str:
        """Execute the agent's reasoning loop for a given query."""
        self.memory.append(AgentMessage(role="user", content=query))
        if len(self.memory) > MAX_MEMORY:
            self.memory = self.memory[-MAX_MEMORY:]
        prompt = self._build_prompt(query)

        for iteration in range(MAX_ITERATIONS):
            response = self._call_llm(prompt)
            self.memory.append(AgentMessage(role="assistant", content=response))

            # Check tool call FIRST — if the LLM wants to call a tool AND
            # gives a final answer in the same response, honor the tool call
            # so data is gathered before answering.
            tool_call = self._parse_tool_call(response)
            if tool_call:
                name, args = tool_call
                log.info("[%s] Calling tool: %s(%s)", self.name, name, args)
                result = self._execute_tool(name, args)
                self.memory.append(AgentMessage(
                    role="tool", content=result, tool_name=name, tool_args=args,
                ))
                prompt = self._build_prompt(
                    query + f"\n\n[Previous tool call: {name} returned: {result[:2000]}]\nContinue your analysis."
                )
                continue

            final = self._parse_final_answer(response)
            if final:
                log.info("[%s] Completed in %d iteration(s)", self.name, iteration + 1)
                return final

            return response

        return "Agent reached maximum iterations without a final answer."

    def run_without_llm(self, query: str) -> str:
        """Fallback: subclasses override this for rule-based reasoning."""
        return "No rule-based fallback implemented for this agent."
