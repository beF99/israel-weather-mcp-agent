import asyncio
from contextlib import AsyncExitStack
import json
import os
from typing import Any

import httpx

from client import MCPClient
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


class ChatHost:
    def __init__(self):
        self.mcp_clients: list[MCPClient] = [
            MCPClient("./weather_Israel.py"),
            MCPClient("./weather_USA.py"),
        ]
        self.tool_clients: dict[str, tuple[MCPClient, str]] = {}
        self.clients_connected = False
        self.exit_stack = AsyncExitStack()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        # For Netfree
        self.http_client = httpx.AsyncClient(verify=False)
        self.openai = AsyncOpenAI(http_client=self.http_client)

    async def connect_mcp_clients(self):
        """Connect all configured MCP clients once."""
        if self.clients_connected:
            return

        for client in self.mcp_clients:
            if client.session is None:
                await client.connect_to_server()

        if not self.mcp_clients:
            raise RuntimeError("No MCP clients are connected")

        self.clients_connected = True

    async def get_available_tools(self) -> list[dict[str, Any]]:
        """Collect tools from all MCP clients and map them back to their owner."""
        await self.connect_mcp_clients()
        self.tool_clients = {}
        available_tools: list[dict[str, Any]] = []

        for client in self.mcp_clients:
            if client.session is None:
                print(f"Warning: MCP client {client.client_name} is not connected, skipping")
                continue

            try:
                response = await client.session.list_tools()
                for tool in response.tools:
                    exposed_name = f"{client.client_name}__{tool.name}"
                    if exposed_name in self.tool_clients:
                        raise RuntimeError(f"Duplicate tool name detected: {exposed_name}")

                    self.tool_clients[exposed_name] = (client, tool.name)
                    available_tools.append(
                        {
                            "name": exposed_name,
                            "description": f"[{client.client_name}] {tool.description}",
                            "input_schema": tool.inputSchema,
                        }
                    )
            except Exception as e:
                print(f"Warning: Failed to get tools from {client.client_name}: {str(e)}")
                continue

        if not available_tools:
            raise RuntimeError("No tools available from any MCP client")

        return available_tools

    @staticmethod
    def _to_openai_tools(available_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in available_tools
        ]

    @staticmethod
    def _tool_result_to_text(result: Any) -> str:
        content = getattr(result, "content", None)
        if content is None:
            return str(result)

        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
                continue

            if isinstance(item, dict):
                item_text = item.get("text")
                if item_text:
                    parts.append(str(item_text))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
                continue

            parts.append(str(item))

        return "\n".join(parts) if parts else "Tool executed successfully."

    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available tools."""
        messages = [{"role": "user", "content": query}]
        available_tools = self._to_openai_tools(await self.get_available_tools())
        print(f"\n[Host] Available tools count: {len(available_tools)}")

        while True:
            response = await self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=available_tools,
                tool_choice="auto",
            )

            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []
            print(f"[Host] Model responded. tool_calls count: {len(tool_calls)}")
            if assistant_message.content:
                preview = assistant_message.content.strip().replace("\n", " ")
                print(f"[Host] Assistant text preview: {preview[:200]}")

            assistant_payload: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_message.content or "",
            }
            if tool_calls:
                assistant_payload["tool_calls"] = [tool_call.model_dump() for tool_call in tool_calls]
            messages.append(assistant_payload)

            if not tool_calls:
                return assistant_message.content or ""

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments or "{}")
                print(f"[Host] Calling tool: {tool_name}")
                print(f"[Host] Tool args: {tool_args}")

                if tool_name not in self.tool_clients:
                    raise RuntimeError(f"Unknown tool requested by model: {tool_name}")

                client, original_tool_name = self.tool_clients[tool_name]
                if client.session is None:
                    raise RuntimeError(f"MCP client {client.client_name} is not connected")

                result = await client.session.call_tool(original_tool_name, tool_args)
                tool_output = self._tool_result_to_text(result)
                preview = tool_output.strip().replace("\n", " ")
                print(f"[Host] Tool result preview: {preview[:250]}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": tool_output,
                    }
                )
    
    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                
                response = await self.process_query(query)
                print("\n" + response)
                
            except Exception as e:
                print(f"\nchat_loop Error: {str(e)}")
                
    async def cleanup(self):
        """Clean up resources"""
        for client in reversed(self.mcp_clients):
            await client.cleanup()
        await self.http_client.aclose()
        await self.exit_stack.aclose()
        
        
async def main():
    host = ChatHost()
    try:
        await host.chat_loop()
    finally:
        await host.cleanup()
        
if __name__ == "__main__":
    asyncio.run(main())
