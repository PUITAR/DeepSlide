import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

from docker.errors import DockerException, NotFound
from mcp.types import CallToolResult, TextContent
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageFunctionToolCall as ToolCall,
)
from pydantic import BaseModel

import docker
from deeppresenter.utils.config import GLOBAL_CONFIG, DeepPresenterConfig
from deeppresenter.utils.constants import (
    CUTOFF_WARNING,
    LOGGING_LEVEL,
    MCP_CALL_TIMEOUT,
    TOOL_CACHE,
    TOOL_CUTOFF_LEN,
    WORKSPACE_BASE,
)
from deeppresenter.utils.log import (
    debug,
    error,
    info,
    set_logger,
    timer,
    warning,
)
from deeppresenter.utils.mcp_client import MCPClient
from deeppresenter.utils.typings import ChatMessage, MCPServer, Role


class ToolTiming(BaseModel):
    total_time: float = 0
    success_count: int = 0
    error_count: int = 0


class AgentEnv:
    def __init__(
        self,
        workspace: Path,
        config: DeepPresenterConfig = GLOBAL_CONFIG,
        cutoff_len: int = TOOL_CUTOFF_LEN,
    ):
        if isinstance(workspace, str):
            workspace = Path(workspace)
        self.workspace = workspace.absolute()
        self.cutoff_len = cutoff_len
        with open(config.mcp_config_file, encoding="utf-8") as f:
            raw_conf = json.load(f)
            self.mcp_configs: list[MCPServer] = [MCPServer(**s) for s in raw_conf]

        # Pass workspace-specific variables to client to avoid global env pollution
        host_workspace_base = os.environ.get("DEEPPRESENTER_HOST_WORKSPACE_BASE", None)
        if host_workspace_base:
            # calculate HOST_WORKSPACE for docker-in-docker volume mounting
            host_workspace = str(self.workspace).replace(
                str(WORKSPACE_BASE), host_workspace_base
            )
            debug(
                f"HOST WORKSPACE DETECTED: mapping {host_workspace} to {self.workspace}"
            )
        else:
            # assume paths are the same (local development)
            host_workspace = str(self.workspace)

        envs = {
            "WORKSPACE": str(self.workspace),
            "HOST_WORKSPACE": host_workspace,
            "WORKSPACE_ID": self.workspace.stem,
            "CONFIG_FILE": str(config.file_path),
            "FASTMCP_LOG_LEVEL": logging.getLevelName(LOGGING_LEVEL),
        }
        if config.offline_mode:
            envs["OFFLINE_MODE"] = "1"
        self.client = MCPClient(envs=envs)
        # caching overlong content
        self.timing_dict = defaultdict(ToolTiming)
        self._tools_dict: dict[str, dict] = {}
        self._server_tools = defaultdict(list)
        self._tool_to_server = {}
        self.tool_history: list[tuple[ToolCall, ChatMessage]] = []
        self.tool_history_file = self.workspace / ".history" / "tool_history.jsonl"

    async def tool_execute(
        self,
        tool_call: ToolCall,
    ):
        try:
            start_time = time.time()
            server_id = self._tool_to_server[tool_call.function.name]
            if len(tool_call.function.arguments) == 0:
                arguments = None
            else:
                arguments = json.loads(tool_call.function.arguments)
            result = await self.client.tool_execute(
                server_id, tool_call.function.name, arguments
            )
        except KeyError:
            result = CallToolResult(
                type="text",
                content=[
                    TextContent(
                        text=f"Tool `{tool_call.function.name}` not found.", type="text"
                    )
                ],
                isError=True,
            )
        except TimeoutError:
            result = CallToolResult(
                content=[
                    TextContent(
                        text=f"Tool `{tool_call.function.name}` execution timed out after {MCP_CALL_TIMEOUT} seconds.",
                        type="text",
                    )
                ],
                isError=True,
            )
        except Exception as e:
            result = CallToolResult(
                content=[
                    TextContent(
                        text=f"Tool `{tool_call.function.name}` execution failed with error: {e}",
                        type="text",
                    )
                ],
                isError=True,
            )
        finally:
            elapsed = time.time() - start_time
            debug(
                f"Tool `{tool_call.function.name}` execution took {elapsed:.2f} seconds"
            )
            self.timing_dict[tool_call.function.name].total_time += elapsed
        if result.isError:
            self.timing_dict[tool_call.function.name].error_count += 1
            warning(
                f"Tool `{tool_call.function.name}` with params:`{tool_call.function.arguments}` encountered error: {result.content}"
            )
        else:
            self.timing_dict[tool_call.function.name].success_count += 1

        if len(result.content) != 1 and any(
            c.type not in ["image", "text"] for c in result.content
        ):
            raise ValueError("Only one text/image block is supported currently.")
        content = []
        block = result.content[0]
        if block.type == "text":
            if len(block.text) > self.cutoff_len:
                truncated = block.text[: self.cutoff_len]
                truncated = truncated[: truncated.rfind("\n")]

                # checking if we are reading from local file
                if tool_call.function.name == "read_file":
                    local_file = arguments["path"]
                else:
                    hash_id = uuid.uuid4().hex[:4]
                    local_file = (
                        self.workspace / f"{tool_call.function.name}_{hash_id}.txt"
                    )
                    local_file.write_text(block.text)

                truncated += CUTOFF_WARNING.format(
                    line=truncated.count("\n"), resource_id=str(local_file)
                )
                block.text = truncated

            content.append(
                {
                    "type": "text",
                    "text": block.text,
                }
            )
        elif block.type == "image":
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": block.data},
                }
            )
        msg = ChatMessage(
            role=Role.TOOL,
            content=content,
            from_tool=tool_call.function,
            tool_call_id=tool_call.id,
            is_error=result.isError,
        )
        self.tool_history.append((tool_call, msg))
        return msg

    async def __aenter__(self):
        try:
            client = docker.from_env()
            container = client.containers.get(self.workspace.stem)
            warning(
                f"Found duplicated sandbox container id={self.workspace.stem}, killed."
            )
            container.remove(force=True)
        # happend if cannot find the container
        except NotFound:
            pass
        except DockerException as e:
            error(f"Docker is not accessible: {e}.")
            sys.exit(1)
        except Exception as e:
            error(f"Unexpected error when launching docker containers: {e}.")
            sys.exit(1)

        with timer("Connecting MCP servers"):
            connect_tasks = []
            server_configs = []

            for server in self.mcp_configs:
                name = server.name
                connect_tasks.append(self.client.connect_server(name, server))
                keep_tools = server.keep_tools
                exclude_tools = set(server.exclude_tools)
                server_configs.append((name, keep_tools, exclude_tools))

            # Connect to all servers in parallel
            await asyncio.gather(*connect_tasks)

            # Update tools for each connected server
            for name, keep_tools, exclude_tools in server_configs:
                info(f"Connected to server {name}")
                tools_dict = await self.client.list_tools(name)
                for tool_name, tool_info in tools_dict.items():
                    if (
                        keep_tools is None or tool_name in keep_tools
                    ) and tool_name not in exclude_tools:
                        tool = {
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "description": tool_info.description,
                                "parameters": tool_info.inputSchema,
                            },
                        }
                        self._tools_dict[tool_name] = tool
                        self._server_tools[name].append(tool_name)
                        self._tool_to_server[tool_name] = name

        if LOGGING_LEVEL <= logging.INFO:
            debug(
                f"Found {len(self._tools_dict)} tools, writing to {TOOL_CACHE}\nTools: {', '.join(self._tools_dict.keys())}"
            )
            with open(TOOL_CACHE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "server_tools": self._server_tools,
                        "tool_specs": list(self._tools_dict.values()),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up all MCP connections and resources"""
        await self.client.cleanup()
        self.tool_history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tool_history_file, "a", encoding="utf-8") as f:
            for tool_call, msg in self.tool_history:
                f.write(
                    json.dumps(
                        [tool_call.model_dump(), msg.model_dump()], ensure_ascii=False
                    )
                    + "\n"
                )
        with (self.workspace / ".history" / "tools_time_cost.json").open(
            "w", encoding="utf-8"
        ) as f:
            timing_data = {
                name: timing.model_dump()
                for name, timing in sorted(
                    self.timing_dict.items(),
                    key=lambda x: x[1].total_time,
                    reverse=True,
                )
            }
            json.dump(
                timing_data,
                f,
                ensure_ascii=False,
                indent=2,
            )
        debug(
            f"Agent Environment exited successfully, interaction history saved to: {self.tool_history_file}."
        )

    def get_server_tools(self, server_id: str):
        tools = []
        for tool_name in self._server_tools[server_id]:
            tools.append(self._tools_dict[tool_name])
        return tools


if __name__ == "__main__":
    import asyncio

    from openai.types.chat.chat_completion_message_tool_call import Function

    set_logger("mcp manager")

    async def main():
        workspace = Path("/opt/workspace/test")
        workspace.mkdir(exist_ok=True)
        async with AgentEnv(workspace) as tool_execute:
            result = await tool_execute.tool_execute(
                ToolCall(
                    function=Function(
                        name="convert_to_markdown",
                        arguments=json.dumps(
                            {
                                "file_path": "/Users/forcelss/Code/PPTea/data/arxiv/0706.0028.pdf",
                                "output_folder": "/Users/forcelss/Code/PPTea/test_output",
                            }
                        ),
                    ),
                    id="test-tool-call-001",
                    type="function",
                )
            )
            print(result)

    asyncio.run(main())
