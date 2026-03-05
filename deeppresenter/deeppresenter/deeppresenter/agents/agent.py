import asyncio
import json
import uuid
from abc import abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Literal

import jsonlines
import yaml
from jinja2 import Template
from jinja2.runtime import StrictUndefined
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageFunctionToolCall as ToolCall,
)
from pydantic import BaseModel

from deeppresenter.agents.env import AgentEnv
from deeppresenter.utils.config import (
    LLM,
    DeepPresenterConfig,
    get_json_from_response,
)
from deeppresenter.utils.constants import (
    AGENT_PROMPT,
    CONTEXT_MODE_PROMPT,
    CONTINUE_MSG,
    HALF_BUDGET_NOTICE_MSG,
    HIST_LOST_MSG,
    LAST_ITER_MSG,
    MAX_LOGGING_LENGTH,
    MAX_TOOLCALL_PER_TURN,
    MEMORY_COMPACT_MSG,
    OFFLINE_PROMPT,
    PACKAGE_DIR,
    URGENT_BUDGET_NOTICE_MSG,
)
from deeppresenter.utils.log import (
    debug,
    info,
    timer,
)
from deeppresenter.utils.typings import (
    ChatMessage,
    Cost,
    InputRequest,
    Role,
    RoleConfig,
)


class Agent:
    def __init__(
        self,
        config: DeepPresenterConfig,
        agent_env: AgentEnv,
        workspace: Path,
        language: Literal["zh", "en"],
        config_file: str | None = None,
        keep_reasoning: bool = True,
    ):
        self.name = self.__class__.__name__
        self.cost = Cost()
        self.context_length = 0
        self.context_warning = 0
        self.workspace = workspace
        self.agent_env = agent_env
        self.language = language
        self.keep_reasoning = keep_reasoning
        self.context_window = config.context_window
        self.max_context_turns = config.max_context_folds
        config_file = (
            Path(config_file)
            if config_file
            else PACKAGE_DIR / "roles" / f"{self.name}.yaml"
        )
        if not config_file.exists():
            raise FileNotFoundError(f"Cannot found role config file at: {config_file} ")

        with open(config_file, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        role_config = RoleConfig(**config_data)
        self.llm: LLM = config[role_config.use_model]
        self.model = self.llm.model_name
        self.prompt: Template = Template(
            role_config.instruction, undefined=StrictUndefined
        )

        if role_config.include_tool_servers == "all":
            role_config.include_tool_servers = list(agent_env._server_tools)
        for server in role_config.include_tool_servers:
            assert server in agent_env._server_tools, (
                f"Server {server} is not available"
            )
        for tool in role_config.include_tools + role_config.exclude_tools:
            assert tool in agent_env._tools_dict, f"Tool {tool} is not available"
        self.tools = []
        for server in role_config.include_tool_servers:
            if server not in role_config.exclude_tool_servers:
                for tool in agent_env._server_tools[server]:
                    if tool not in role_config.exclude_tools:
                        self.tools.append(agent_env._tools_dict[tool])

        for tool_name, tool in agent_env._tools_dict.items():
            if tool_name in role_config.include_tools:
                self.tools.append(tool)

        if language not in role_config.system:
            raise ValueError(f"Language '{language}' not found in system prompts")
        self.system = role_config.system[language]

        # ? for those agents equipped with sandbox only
        if any(t["function"]["name"] == "execute_command" for t in self.tools):
            self.system += AGENT_PROMPT.format(
                workspace=self.workspace,
                cutoff_len=self.agent_env.cutoff_len,
                time=datetime.now().strftime("%Y-%m-%d"),
                max_toolcall_per_turn=MAX_TOOLCALL_PER_TURN,
            )

            if config.offline_mode:
                self.system += OFFLINE_PROMPT

        if config.context_folding:
            self.system += CONTEXT_MODE_PROMPT

        self.chat_history: list[ChatMessage] = [
            ChatMessage(role=Role.SYSTEM, content=self.system)
        ]
        # Linear log of failed tool calls and their observations
        self.error_history: list[ToolCall | ChatMessage] = []
        self.research_iter = 0
        if config.context_folding:
            self.context_warning = -1
        debug(f"{self.name} Agent got {len(self.tools)} tools")
        available_tools = [tool["function"]["name"] for tool in self.tools]
        debug(f"Available tools: {', '.join(available_tools)}")

    async def chat(
        self,
        message: ChatMessage,
        response_format: type[BaseModel] | None = None,
        **chat_kwargs,
    ) -> ChatMessage:
        if len(self.chat_history) == 1:
            self.chat_history.append(
                ChatMessage(role=Role.USER, content=self.prompt.render(**chat_kwargs))
            )
            self.log_message(self.chat_history[-1])
        self.chat_history.append(message)
        self.log_message(self.chat_history[-1])
        with timer(f"{self.name} Agent LLM chat"):
            response = await self.llm.run(
                messages=self.chat_history,
                response_format=response_format,
            )
            if response.usage is not None:
                self.cost += response.usage
                self.context_length = response.usage.total_tokens
            self.chat_history.append(
                ChatMessage(
                    role=response.choices[0].message.role,
                    content=response.choices[0].message.content,
                    reasoning_content=getattr(
                        response.choices[0].message, "reasoning_content", None
                    ),
                )
            )
            self.log_message(self.chat_history[-1])
            return self.chat_history[-1]

    async def action(
        self,
        **chat_kwargs,
    ):
        """Tool calling interface"""

        if len(self.chat_history) == 1:
            self.chat_history.append(
                ChatMessage(
                    role=Role.USER,
                    content=self.prompt.render(**chat_kwargs),
                )
            )
            self.log_message(self.chat_history[-1])

        with timer(f"{self.name} Agent LLM call"):
            response = await self.llm.run(
                messages=self.chat_history,
                tools=self.tools,
            )
            if response.usage is not None:
                self.cost += response.usage
                self.context_length = response.usage.total_tokens
            agent_message: ChatCompletionMessage = response.choices[0].message
        if self.keep_reasoning and hasattr(agent_message, "reasoning_content"):
            reasoning = agent_message.reasoning_content
        else:
            reasoning = None
        self.chat_history.append(
            ChatMessage(
                role=agent_message.role,
                content=agent_message.content,
                tool_calls=agent_message.tool_calls,
                reasoning_content=reasoning,
            )
        )
        self.log_message(self.chat_history[-1])
        return self.chat_history[-1]

    @abstractmethod
    async def loop(
        self, req: InputRequest, *args, **kwargs
    ) -> AsyncGenerator[str | ChatMessage, None]:
        """
        Loop interface, return the message or the outcome filepath of the agent.
        """

    @abstractmethod
    async def finish(self, result: str):
        """This function defines when and how should an agent finish their tasks, combined with outcome check"""

    async def execute(self, tool_calls: list[ToolCall]) -> str | list[ChatMessage]:
        coros = []
        observations: list[ChatMessage] = []
        used_tools = set()
        finish_id = None
        outcome = None
        for t in tool_calls:
            arguments = t.function.arguments
            if len(arguments) == 0:
                arguments = None
            else:
                try:
                    assert len(tool_calls) <= MAX_TOOLCALL_PER_TURN, (
                        f"Too many tool calls ({len(tool_calls)}), max allowed is {MAX_TOOLCALL_PER_TURN}"
                    )
                    arguments = get_json_from_response(t.function.arguments)
                    if t.function.name == "finalize":
                        arguments["agent_name"] = self.name
                        finish_id = t.id
                        assert "outcome" in arguments, (
                            "Finalize tool call must have an outcome"
                        )
                        outcome = arguments["outcome"]
                    assert isinstance(arguments, dict), (
                        f"Tool call arguments must be a dict or empty, while {arguments} is given"
                    )
                    t.function.arguments = json.dumps(arguments, ensure_ascii=False)
                except AssertionError as e:
                    observations.append(
                        ChatMessage(
                            role=Role.TOOL,
                            content=str(e),
                            tool_call_id=t.id,
                            is_error=True,
                        )
                    )
                    info(f"Tool call `{t.function}` encountered error: {e}")
                    continue
            used_tools.add(t.function.name)
            coros.append(self.agent_env.tool_execute(t))

        observations.extend(await asyncio.gather(*coros))
        for obs in observations:
            if obs.has_image:
                if "gemini" in self.model.lower() or "qwen" in self.model.lower():
                    obs.role = Role.USER
                if "claude" in self.model.lower():
                    oai_b64 = obs.content[0]["image_url"]["url"]
                    obs.content = [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": oai_b64.split(";")[0].split(":")[1],
                                "data": oai_b64.split(",")[1],
                            },
                        }
                    ]

        self.chat_history.extend(observations)

        for t, o in zip(
            sorted(tool_calls, key=lambda x: x.id or ""),
            sorted(observations, key=lambda x: x.id or ""),
        ):
            if o.is_error:
                self.error_history.append(t)
                self.error_history.append(o)

        if finish_id is not None:
            for obs in observations:
                if obs.tool_call_id == finish_id and obs.text == outcome:
                    info(f"{self.name} Agent finished with result: {obs.text}")
                    return obs.text

        if (
            self.context_warning == 0
            and self.context_length > self.context_window * 0.5
        ):
            self.context_warning += 1
            observations[0].content.insert(0, HALF_BUDGET_NOTICE_MSG)
        elif (
            self.context_warning == 1
            and self.context_length > self.context_window * 0.8
        ):
            observations[0].content.insert(0, URGENT_BUDGET_NOTICE_MSG)
            self.context_warning = 2

        for obs in observations:
            self.log_message(obs)

        if self.context_length > self.context_window:
            if self.context_warning == -1:
                await self.compact_history()
            else:
                raise RuntimeError(
                    f"{self.name} agent exceeded context window: {self.context_length}/{self.context_window}"
                )
        return observations

    def log_message(self, msg: ChatMessage):
        if len(msg.text) < MAX_LOGGING_LENGTH:
            debug(f"{self.name}: {msg.text}")
        else:
            debug(f"{self.name}: {msg.text[:MAX_LOGGING_LENGTH]}...")

    async def compact_history(self, keep_head: int = 10, keep_tail: int = 8):
        """Summarize the history."""
        # ? it's 10 = system + user + (thinking, read, design, write)*2
        if keep_head + keep_tail > len(self.chat_history):
            return

        if self.research_iter == self.max_context_turns:
            return

        self.save_history(message_only=True)
        self.research_iter += 1
        head, tail = self._split_history(keep_head, keep_tail)
        summary_ask = ChatMessage(
            role=Role.USER, content=MEMORY_COMPACT_MSG.format(language=self.language)
        )
        response = await self.llm.run(
            self.chat_history + [summary_ask],
            tools=self.tools,
        )
        agent_message = response.choices[0].message
        if self.keep_reasoning and hasattr(agent_message, "reasoning_content"):
            reasoning = agent_message.reasoning_content
        else:
            reasoning = None
        summary_message = ChatMessage(
            id=f"context_fold_{uuid.uuid4().hex[:8]}",
            role=agent_message.role,
            content=agent_message.content,
            tool_calls=agent_message.tool_calls,
            reasoning_content=reasoning,
        )
        debug(
            f"Summary of Resarch Iter {self.research_iter:02d}: \n"
            + summary_message.text
        )
        tasks = [
            self.agent_env.tool_execute(tc) for tc in summary_message.tool_calls or []
        ]
        observations = await asyncio.gather(*tasks)
        observations[-1].content.append(CONTINUE_MSG)
        if self.research_iter == self.max_context_turns:
            observations[-1].content.append(LAST_ITER_MSG)
        new_tail = [
            summary_ask,
            summary_message,
            *observations,
        ]
        self.chat_history = head + tail + new_tail

    def _split_history(self, keep_head, keep_tail):
        # ensure the left context window contains the paired tool call and tool call result
        head = []
        for msg in self.chat_history:
            if len(head) < keep_head or msg.role == Role.TOOL:
                head.append(msg)
            else:
                break
        head[-1].content.append(HIST_LOST_MSG)

        tail = self.chat_history[-keep_tail:]
        for i, m in enumerate(tail):
            if m.role == Role.ASSISTANT and m not in head:
                tail = tail[i:]
                break
        else:
            tail = []

        return head, tail

    def save_history(self, hist_dir: Path | None = None, message_only: bool = False):
        hist_dir = hist_dir or self.workspace / ".history"
        hist_dir.mkdir(parents=True, exist_ok=True)

        history_file = hist_dir / f"{self.name}-history.jsonl"
        if self.research_iter >= 0:
            history_file = (
                hist_dir / f"{self.name}-{self.research_iter:02d}-history.jsonl"
            )
        with jsonlines.open(history_file, mode="w") as writer:
            for message in self.chat_history:
                writer.write(message.model_dump())

        if message_only:
            return

        config_file = hist_dir / f"{self.name}-config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": self.name,
                    "model": self.model,
                    "context_window": self.context_length,
                    "cost": self.cost.model_dump(),
                    "tools": self.tools,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        if self.error_history:
            error_file = hist_dir / f"{self.name}-errors.jsonl"
            with jsonlines.open(error_file, mode="w") as writer:
                for msg in self.error_history:
                    writer.write(msg.model_dump())

        info(
            f"{self.name} done | cost:{self.cost} ctx:{self.context_length} | history:{history_file.name} config:{config_file.name}"
        )
