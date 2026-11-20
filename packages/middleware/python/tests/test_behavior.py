"""D9: the same behavioral contract for every adapter, driven through the real framework.

Each driver makes one native call whose history holds a successful tool result
and returns the text the native provider/model actually received. A driver
skips when its framework is absent (CI installs each family in its own lane).
The five contracts:

- projection applied, caller input untouched (free-form scope IDs work);
- runtime outage passes the original through;
- an adapter exception becomes an ``adapter_error`` pass-through;
- an invalid scope is recovery-free (``invalid_scope``), never an error;
- a framework version outside the tested range warns once and skips,
  unless ``accept_framework_version=True``.

Stage 4 adds, for every family: a blackholed runtime (accepts, never answers),
shutdown before and during a call, and a forked child. For the certified
families (langchain, openai, anthropic) it adds an image plus a long history,
and an async caller cancellation while the runtime is slow.
"""
import asyncio
import copy
import json
import os
import signal
import socket
import sys
import threading
import time
import warnings

import pytest

from frameworks import require_adapter

ORIGINAL = "[INFO] café 🌍\r\n" * 300
MARKER = "[cstman: shortened;"
DRIVERS = {}


def driver(family, target):
    """Register ``drive(runtime, scope, **options) -> received text``; ``target`` is the
    ``module:attribute`` a test breaks to prove the fail-open guard."""
    def register(function):
        DRIVERS[family] = (function, target)
        return function
    return register


def again(wrap, twice):
    """``twice=True`` wraps with the entry point a second time, as a host that wraps defensively would."""
    return (lambda target, **options: wrap(wrap(target, **options), **options)) if twice else wrap


def untouched(value):
    snapshot = copy.deepcopy(value)
    return lambda: value == snapshot


# ---------------------------------------------------------------- certified


@driver("langchain", "cstman_middleware.langchain:_message_view")
def drive_langchain(runtime, scope, twice=False, **options):
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from cstman_middleware.langchain import with_cstman_agent

    history = [HumanMessage("summarize"), AIMessage("", tool_calls=[{"id": "call-1", "name": "read_log", "args": {}}]),
               ToolMessage(ORIGINAL, tool_call_id="call-1", name="read_log")]
    same = untouched(history)
    agent = again(with_cstman_agent, twice)({"tools": []}, runtime=runtime, scope=scope, **options)
    request = ModelRequest(model=FakeListChatModel(responses=["unused"]), messages=history, tools=agent["tools"])
    seen = []
    agent["middleware"][0].wrap_model_call(request, lambda projected: seen.append(projected.messages[-1].content) or ModelResponse(result=[AIMessage("done")]))
    assert same()
    return seen[0]


def _openai_http():
    import importlib
    from openai import DefaultHttpxClient
    from cstman_middleware._httpx2 import sdk_flavour
    return importlib.import_module(sdk_flavour(DefaultHttpxClient))


@driver("openai", "cstman_middleware._native:leaves")
def drive_openai(runtime, scope, twice=False, **options):
    from openai import OpenAI
    from cstman_middleware.openai import with_cstman_openai, with_cstman_openai_tools

    http, received = _openai_http(), []

    def provider(request):
        received.append(json.loads(request.content)["messages"][-1]["content"])
        return http.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "m", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})

    messages = [{"role": "user", "content": "summarize"},
                {"role": "assistant", "tool_calls": [{"type": "function", "id": "call-1", "function": {"name": "read_log", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call-1", "content": ORIGINAL}]
    same = untouched(messages)
    tools = [{"type": "function", "function": {"name": "read_log", "description": "Read", "parameters": {"type": "object", "properties": {}}}}]
    with OpenAI(api_key="test", http_client=http.Client(transport=http.MockTransport(provider))) as client:
        base = with_cstman_openai(client, runtime=runtime, scope=scope, **options) if twice else client
        loop = with_cstman_openai_tools(base, runtime=runtime, scope=scope, protocol="openai-chat", tools=tools,
                                         functions={"read_log": lambda _: ORIGINAL}, **options)
        loop.client.chat.completions.create(model="m", tools=loop.tools, messages=messages)
    assert same()
    return received[0]


@driver("anthropic", "cstman_middleware._native:leaves")
def drive_anthropic(runtime, scope, twice=False, **options):
    from anthropic import Anthropic, DefaultHttpxClient
    from anthropic.lib.tools import beta_tool
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.anthropic import with_cstman_anthropic
    import importlib

    http, received = importlib.import_module(sdk_flavour(DefaultHttpxClient)), []

    def provider(request):
        received.append(json.loads(request.content)["messages"][-1]["content"][0]["content"])
        return http.Response(200, json={"id": "msg", "type": "message", "role": "assistant", "model": "m", "stop_reason": "end_turn",
                                        "stop_sequence": None, "content": [{"type": "text", "text": "done"}],
                                        "usage": {"input_tokens": 1, "output_tokens": 1}})

    @beta_tool
    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    messages = [{"role": "user", "content": "summarize"},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "read_log", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": ORIGINAL}]}]
    same = untouched(messages)
    with Anthropic(api_key="test", http_client=http.Client(transport=http.MockTransport(provider))) as client:
        wrapped = again(with_cstman_anthropic, twice)(client, runtime=runtime, scope=scope, **options)
        runner = wrapped.beta.messages.tool_runner(model="m", max_tokens=16, messages=messages, tools=[read_log])
        runner.until_done()
    assert same()
    return received[0]


@driver("litellm", "cstman_middleware._native:leaves")
def drive_litellm(runtime, scope, **options):
    from cstman_cloud.middleware import ensure_sync
    from cstman_middleware.litellm import CSTMANLiteLLM

    received = []
    server, base = _openai_server(received)
    binding = []

    def operator_recovery(resolved):
        bound = ensure_sync(runtime).recovery(resolved)
        binding.append(bound)
        return (bound, json.dumps({"name": bound.name})) if bound else None

    messages = [{"role": "user", "content": "summarize"},
                {"role": "assistant", "tool_calls": [{"type": "function", "id": "call-1", "function": {"name": "read_log", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call-1", "content": ORIGINAL}]
    same = untouched(messages)
    from cstman_cloud.middleware import RECOVERY_DESCRIPTION, RECOVERY_SCHEMA
    tools = [{"type": "function", "function": {"name": "read_log", "description": "Read", "parameters": {"type": "object", "properties": {}}}},
             {"type": "function", "function": {"name": "cstman_retrieve", "description": RECOVERY_DESCRIPTION, "parameters": RECOVERY_SCHEMA}}]
    try:
        with CSTMANLiteLLM(runtime=runtime, operator_recovery=operator_recovery, **options) as cstman:
            cstman.completion(scope=scope, model="openai/m", api_base=base, api_key="test", messages=messages, tools=tools)
    finally:
        server.shutdown()
    assert same()
    return received[0]["messages"][-1]["content"]


def _openai_server(received):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            payload = json.dumps({"id": "c", "object": "chat.completion", "created": 0, "model": "m", "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


# ---------------------------------------------------------------- experimental


@driver("asgi", "cstman_middleware._native:leaves")
def drive_asgi(runtime, scope, **options):
    from cstman_cloud.middleware import RECOVERY_DESCRIPTION, RECOVERY_SCHEMA, ensure_async
    from cstman_middleware._guard import recovery
    from cstman_middleware.asgi import ASGIContext, CSTMANASGIMiddleware

    binding = recovery(ensure_async(runtime), scope)
    body = {"model": "m", "messages": [
        {"role": "user", "content": "summarize"},
        {"role": "assistant", "tool_calls": [{"type": "function", "id": "c1", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": ORIGINAL}],
        "tools": [{"type": "function", "function": {"name": "read", "description": "Read", "parameters": {"type": "object"}}},
                  {"type": "function", "function": {"name": "cstman_retrieve", "description": RECOVERY_DESCRIPTION, "parameters": RECOVERY_SCHEMA}}]}
    seen = []

    async def application(scope_, receive, send):
        chunks = b""
        while True:
            message = await receive()
            chunks += message.get("body", b"")
            if not message.get("more_body"):
                break
        seen.append(json.loads(chunks)["messages"][-1]["content"])
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}"})

    async def drive():
        middleware = CSTMANASGIMiddleware(application, runtime=runtime, routes={"/v1/chat/completions": "openai-chat"},
                                           resolve_context=lambda _: ASGIContext(scope, recovery=binding, recovery_overhead="{}"), **options)
        received = iter([{"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}])

        async def receive():
            return next(received)

        async def send(_):
            pass

        await middleware({"type": "http", "method": "POST", "path": "/v1/chat/completions",
                          "headers": [(b"content-type", b"application/json")]}, receive, send)

    asyncio.run(drive())
    return seen[0]


@driver("google", "cstman_middleware.google:manifest")
def drive_google(runtime, scope, **options):
    import httpx
    from google import genai
    from google.genai import types
    from cstman_middleware.google import CSTMANGoogleTransport, with_cstman_google

    received = []

    def provider(request):
        body = json.loads(request.content)
        received.append(body["contents"][2]["parts"][0]["functionResponse"]["response"]["output"])
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "done"}]}, "finishReason": "STOP"}]})

    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    contents = [types.Content(role="user", parts=[types.Part(text="summarize")]),
                types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="read_log", args={}))]),
                types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(name="read_log", response={"output": ORIGINAL}))])]
    same = untouched(contents)
    transport = CSTMANGoogleTransport(runtime=runtime, transport=httpx.MockTransport(provider), **options)
    client = genai.Client(api_key="test", http_options=types.HttpOptions(httpx_client=httpx.Client(transport=transport)))
    wrapped = with_cstman_google(client, runtime=runtime, scope=scope, **options)
    wrapped.models.generate_content(model="gemini-test", contents=contents, config=types.GenerateContentConfig(tools=[read_log]))
    assert same()
    return received[0]


@driver("strands", "cstman_middleware.strands:manifest")
def drive_strands(runtime, scope, model_first=False, **options):
    from strands import Agent
    from strands.models.model import Model
    from cstman_middleware.strands import with_cstman_agent, with_cstman_model

    received = []

    class Provider(Model):
        def update_config(self, **config):
            pass

        def get_config(self):
            return {"model_id": "fake"}

        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            received.append(messages[-1]["content"][0]["toolResult"]["content"][0]["text"])
            yield {"messageStart": {"role": "assistant"}}
            yield {"messageStop": {"stopReason": "end_turn"}}

        async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
            yield {}

    messages = [{"role": "user", "content": [{"text": "summarize"}]},
                {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "read_log", "input": {}}}]},
                {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "status": "success", "content": [{"text": ORIGINAL}]}}]}]
    same = untouched(messages)
    model = with_cstman_model(Provider(), runtime=runtime, scope=scope, **options) if model_first else Provider()
    agent_options = with_cstman_agent({"model": model, "tools": []}, runtime=runtime, scope=scope, **options)
    agent = Agent(**agent_options, callback_handler=None)  # the plugin attests registration in this agent's tool registry
    specs = [tool.tool_spec for tool in agent_options.get("tools", [])]

    async def drive():
        async for _ in agent_options["model"].stream(messages, specs, None):
            pass
        return agent

    asyncio.run(drive())
    assert same()
    return received[0]


@driver("agno", "cstman_middleware.agno:manifest")
def drive_agno(runtime, scope, model_first=False, **options):
    from agno.models.base import Model
    from agno.models.message import Message
    from agno.models.response import ModelResponse
    from cstman_middleware.agno import with_cstman_agent, with_cstman_model

    received = []

    class Provider(Model):
        def invoke(self, messages, assistant_message=None, response_format=None, tools=None, tool_choice=None, run_response=None,
                   compress_tool_results=False):
            received.append(messages[-1].content)
            return ModelResponse(role="assistant", content="done")

        async def ainvoke(self, *args, **kwargs):
            return self.invoke(*args, **kwargs)

        def invoke_stream(self, *args, **kwargs):
            yield self.invoke(*args, **kwargs)

        async def ainvoke_stream(self, *args, **kwargs):
            yield self.invoke(*args, **kwargs)

        def _parse_provider_response(self, response, **kwargs):
            return response

        def _parse_provider_response_delta(self, response):
            return response

    history = [Message(role="user", content="summarize"),
               Message(role="assistant", tool_calls=[{"id": "call-1", "type": "function", "function": {"name": "read_log", "arguments": "{}"}}]),
               Message(role="tool", tool_call_id="call-1", tool_name="read_log", content=ORIGINAL)]
    same = untouched(history)
    model = Provider(id="fake")
    model = with_cstman_model(model, runtime=runtime, scope=scope, **options) if model_first else model
    agent = with_cstman_agent({"model": model, "tools": []}, runtime=runtime, scope=scope, **options)
    model, tools = agent["model"], agent.get("tools") or []
    # Agno's Model.response() opens this per-run frame with the run's tools; drive one provider call inside it.
    token = model.connection.active.set(model._frame("response", (), {"messages": history, "tools": tools}))
    try:
        model.invoke(history, Message(role="assistant"), tools=[{"type": "function", "function": tool.to_dict()} for tool in tools])
    finally:
        model.connection.active.reset(token)
    assert same()
    return received[0]


@driver("crewai", "cstman_middleware.crewai:manifest")
def drive_crewai(runtime, scope, model_first=False, **options):
    from types import SimpleNamespace
    from crewai import BaseLLM
    from crewai.tools import BaseTool
    from crewai.utilities.agent_utils import convert_tools_to_openai_schema
    from cstman_middleware import crewai as adapter

    received = []

    class Provider(BaseLLM):
        def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None, response_model=None):
            received.append(messages[-1]["content"])
            return "done"

    class ReadLog(BaseTool):
        name: str = "read_log"
        description: str = "Read the log"

        def _run(self):
            return ORIGINAL

    class Executor:  # the fields CrewAI's PRE_MODEL_CALL context exposes for the running executor
        pass

    messages = [{"role": "user", "content": "summarize"},
                {"role": "assistant", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "read_log", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call-1", "name": "read_log", "content": ORIGINAL}]
    same = untouched(messages)
    llm = Provider(model="fake")
    llm = adapter.with_cstman_llm(llm, runtime=runtime, scope=scope, **options) if model_first else llm
    agent = adapter.with_cstman_agent({"llm": llm, "tools": [ReadLog()]}, runtime=runtime, scope=scope, **options)
    model, executor = agent["llm"], Executor()
    executor.llm, executor.messages, executor.task, executor.agent, executor.original_tools = model, messages, None, None, agent["tools"]
    adapter._before_model_call(SimpleNamespace(llm=model, executor=executor))
    model.call(messages, tools=convert_tools_to_openai_schema(agent["tools"])[0])
    assert same()
    return received[0]


@driver("pydantic_ai", "cstman_middleware.pydantic_ai:_message_view")
def drive_pydantic_ai(runtime, scope, **options):
    from openai import AsyncOpenAI
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from cstman_middleware.pydantic_ai import CSTMANCapability

    http, received = _openai_http(), []

    def provider(request):
        body = json.loads(request.content)
        received.append(next(message["content"] for message in body["messages"] if message["role"] == "tool"))
        return http.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "m", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})

    client = AsyncOpenAI(api_key="test", http_client=http.AsyncClient(transport=http.MockTransport(provider)))
    agent = Agent(OpenAIChatModel("gpt-test", provider=OpenAIProvider(openai_client=client)),
                  capabilities=[CSTMANCapability(runtime=runtime, scope=scope, **options)])

    @agent.tool_plain
    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    history = [ModelRequest(parts=[UserPromptPart("summarize")]),
               ModelResponse(parts=[ToolCallPart("read_log", {}, tool_call_id="call-1")]),
               ModelRequest(parts=[ToolReturnPart("read_log", ORIGINAL, tool_call_id="call-1")])]
    same = untouched(history)
    agent.run_sync(message_history=history)
    assert same()
    return received[0]


@driver("autogen", "cstman_middleware.autogen:manifest")
def drive_autogen(runtime, scope, model_first=False, **options):
    from autogen_core import FunctionCall
    from autogen_core.models import AssistantMessage, FunctionExecutionResult, FunctionExecutionResultMessage, UserMessage
    from autogen_ext.models.replay import ReplayChatCompletionClient
    from cstman_middleware.autogen import with_cstman_agent, with_cstman_model

    received = []
    provider = ReplayChatCompletionClient(["done"])
    native_create = provider.create

    async def create(messages, **kwargs):
        received.append(messages[-1].content[0].content)
        return await native_create(messages, **kwargs)

    provider.create = create

    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    history = [UserMessage(content="summarize", source="user"),
               AssistantMessage(content=[FunctionCall(id="call-1", name="read_log", arguments="{}")], source="assistant"),
               FunctionExecutionResultMessage(content=[FunctionExecutionResult(call_id="call-1", name="read_log", content=ORIGINAL)])]
    same = untouched(history)
    client = with_cstman_model(provider, runtime=runtime, scope=scope, **options) if model_first else provider
    agent = with_cstman_agent({"model_client": client, "tools": [read_log]}, runtime=runtime, scope=scope, **options)

    async def drive():
        workbench = agent.get("workbench")
        tools = await workbench.list_tools() if workbench is not None else []
        await agent["model_client"].create(history, tools=tools)

    asyncio.run(drive())
    assert same()
    return received[0]


@driver("llama_index", "cstman_middleware.llama_index:manifest")
def drive_llama_index(runtime, scope, **options):
    from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole, TextBlock, ToolCallBlock
    from llama_index.core.llms.llm import ToolSelection
    from llama_index.llms.openai import OpenAI
    from cstman_middleware.llama_index import with_cstman_tools

    received = []

    class Provider(OpenAI):  # a subclass (like AzureOpenAI) keeps the OpenAI message shape
        def chat_with_tools(self, tools, user_msg=None, chat_history=None, **kwargs):
            received.append(chat_history[-1].blocks[0].text)
            return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content="done"))

    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    bundle = with_cstman_tools(Provider(api_key="test", model="gpt-4o"), runtime=runtime, scope=scope, tools=[read_log], **options)
    bundle.execute(ToolSelection(tool_id="call-1", tool_name="read_log", tool_kwargs={}))  # the application loop's dispatch
    history = [ChatMessage(role=MessageRole.USER, content="summarize"),
               ChatMessage(role=MessageRole.ASSISTANT, blocks=[ToolCallBlock(tool_call_id="call-1", tool_name="read_log", tool_kwargs={})]),
               ChatMessage(role=MessageRole.TOOL, blocks=[TextBlock(text=ORIGINAL)], additional_kwargs={"tool_call_id": "call-1"})]
    same = untouched(history)
    bundle.model.chat_with_tools(bundle.tools, chat_history=history)
    assert same()
    return received[0]


@driver("mcp", "cstman_middleware.mcp:sha256")
def drive_mcp(runtime, scope, **options):
    from mcp.types import CallToolResult, TextContent, Tool
    from cstman_middleware.mcp import CSTMANMCPHost, MCPToolBinding

    result = CallToolResult(content=[TextContent(type="text", text=ORIGINAL)])
    same = untouched(result.model_dump())
    tool = Tool(name="read_log", input_schema={"type": "object"})

    async def execute(arguments=None, **_):
        return result

    async def drive():
        host = CSTMANMCPHost(runtime=runtime, scope=scope, server_id="server", protocol_version="2025-06-18", **options)
        registered = host.register([MCPToolBinding(tool, execute)])
        view = await host.project_result(result, tool=tool, call_id="c1", registered_tools=registered,
                                         context_manifest=[{"id": "message-0", "sha256": "0" * 64}])
        return view.content[0].text

    text = asyncio.run(drive())
    assert same()
    return text


# ---------------------------------------------------------------- the contracts


def _drive(family, runtime, scope, **options):
    require_adapter(family)
    return DRIVERS[family][0](runtime, scope, **options)


def _reasons(runtime):
    return [event.reason for event in runtime.reports]


@pytest.mark.parametrize("family", sorted(DRIVERS))
@pytest.mark.parametrize("session", ["user@example.com", "user 42 / chat #7"])
@pytest.mark.parametrize("view", ["sync", "async"])  # D5: either runtime type works on every path
def test_projection_applied_and_caller_input_untouched(family, session, view, protocol_runtime):
    from cstman_cloud.middleware import Scope, normalize_scope_token
    from cstman_middleware._versions import installed_version
    runtime = protocol_runtime if view == "sync" else protocol_runtime.as_async()
    received = _drive(family, runtime, Scope("tests", session))
    assert received.startswith(MARKER), f"{family} did not apply the plan"
    assert "applied" in [event.status for event in protocol_runtime.reports]
    # Adapter.version on the wire is the installed cstman-middleware release.
    assert {request["adapter"]["version"] for request in protocol_runtime.requests} == {installed_version("cstman-middleware") or "unknown"}
    hashed = normalize_scope_token(session)
    assert hashed.startswith("h-") and {request["scope"]["session_id"] for request in protocol_runtime.requests} == {hashed}
    assert all(receipt["scope"]["session_id"] == hashed for receipt in protocol_runtime.receipts)


@pytest.mark.parametrize("family", ["openai", "anthropic", "langchain"])
def test_wrapping_twice_runs_one_cstman_layer(family, protocol_runtime):
    """A second wrap neither stacks middleware nor turns compression off with a false recovery_name_conflict."""
    from cstman_cloud.middleware import Scope
    assert _drive(family, protocol_runtime, Scope("tests", "one"), twice=True).startswith(MARKER)
    assert [event.status for event in protocol_runtime.reports] == ["applied"], _reasons(protocol_runtime)


@pytest.mark.parametrize("family", ["strands", "agno", "crewai", "autogen"])
def test_agent_over_a_model_wrapper_still_binds_recovery(family, protocol_runtime):
    """with_cstman_agent({"model": with_cstman_model(m)}) replaces the record-only layer: recovery binds and it compresses."""
    from cstman_cloud.middleware import Scope
    assert _drive(family, protocol_runtime, Scope("tests", "one"), model_first=True).startswith(MARKER)
    assert [event.status for event in protocol_runtime.reports] == ["applied"], _reasons(protocol_runtime)


@pytest.mark.parametrize("family", sorted(DRIVERS))
def test_strict_mode_raises_adapter_error_instead_of_passing_through(family, protocol_runtime, monkeypatch):
    import importlib
    from cstman_cloud.middleware import MiddlewareError, Scope
    require_adapter(family)
    module, attribute = DRIVERS[family][1].split(":")
    monkeypatch.setattr(importlib.import_module(module), attribute, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("adapter bug")))
    with pytest.raises(MiddlewareError) as raised:
        _drive(family, protocol_runtime, Scope("tests", "strict"))
    assert raised.value.code == "adapter_error"


@pytest.mark.parametrize("family", sorted(DRIVERS))
def test_runtime_outage_passes_the_original_through(family, unreachable_runtime):
    from cstman_cloud.middleware import Scope
    assert _drive(family, unreachable_runtime, Scope("tests", "outage")) == ORIGINAL
    assert unreachable_runtime.reports and all(event.status == "skipped" for event in unreachable_runtime.reports)


@pytest.mark.parametrize("family", sorted(DRIVERS))
def test_adapter_exception_becomes_adapter_error_pass_through(family, lenient_runtime, monkeypatch, caplog):
    import importlib
    from cstman_cloud.middleware import Scope
    require_adapter(family)
    module, attribute = DRIVERS[family][1].split(":")

    def broken(*args, **kwargs):
        raise RuntimeError("adapter bug")

    monkeypatch.setattr(importlib.import_module(module), attribute, broken)
    assert _drive(family, lenient_runtime, Scope("tests", "broken")) == ORIGINAL
    assert "adapter_error" in _reasons(lenient_runtime)
    assert "reason=adapter_error" in caplog.text


@pytest.mark.parametrize("family", sorted(DRIVERS))
def test_invalid_scope_is_recovery_free(family, lenient_runtime, caplog):
    from cstman_cloud.middleware import Scope
    assert _drive(family, lenient_runtime, Scope("tests", "")) == ORIGINAL
    assert "invalid_scope" in _reasons(lenient_runtime)
    assert lenient_runtime.requests == []
    assert "reason=invalid_scope" in caplog.text


@pytest.mark.parametrize("family", sorted(set(DRIVERS) - {"asgi"}))  # pure ASGI has no framework version
def test_out_of_range_version_warns_once_and_skips(family, lenient_runtime, monkeypatch, caplog):
    from cstman_cloud.middleware import Scope
    from cstman_middleware import _versions
    require_adapter(family)
    monkeypatch.setattr(_versions, "installed_version", lambda name: "0.0.1")
    assert _drive(family, lenient_runtime, Scope("tests", "old")) == ORIGINAL
    assert "unsupported_version" in _reasons(lenient_runtime)
    assert "reason=unsupported_version" in caplog.text
    assert _drive(family, lenient_runtime, Scope("tests", "old"), accept_framework_version=True).startswith(MARKER)


# ---------------------------------------------------------------- Stage 4 matrix


@pytest.fixture
def blackhole():
    """A runtime endpoint that accepts connections and never answers: up, but wedged."""
    server, held = socket.socket(), []
    server.bind(("127.0.0.1", 0))
    server.listen(64)

    def accept():
        while True:
            try:
                held.append(server.accept()[0])
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.getsockname()[1]}"
    finally:
        server.close()
        for connection in held:
            connection.close()


def _runtime(endpoint, deadline_ms):
    from cstman_cloud.middleware import MiddlewareRuntime
    reports = []
    runtime = MiddlewareRuntime(endpoint=endpoint, deadline_ms=deadline_ms, on_report=reports.append)
    runtime.reports = reports
    return runtime


@pytest.mark.parametrize("family", sorted(DRIVERS))
def test_blackholed_runtime_passes_the_original_through_at_the_deadline(family, blackhole):
    from cstman_cloud.middleware import Scope
    runtime = _runtime(blackhole, 150)
    try:
        started = time.monotonic()
        assert _drive(family, runtime, Scope("tests", "blackholed")) == ORIGINAL
        assert time.monotonic() - started < 10, "the call waited far past its 150 ms deadline"
        assert "deadline" in _reasons(runtime)
    finally:
        runtime.close()


@pytest.mark.parametrize("family", sorted(DRIVERS))
def test_closed_runtime_passes_the_original_through(family, lenient_runtime):
    from cstman_cloud.middleware import Scope
    require_adapter(family)
    lenient_runtime.close()
    assert _drive(family, lenient_runtime, Scope("tests", "closed")) == ORIGINAL
    assert lenient_runtime.requests == []


@pytest.mark.parametrize("family", sorted(DRIVERS))
def test_close_during_an_in_flight_call_passes_the_original_through_promptly(family, blackhole):
    from cstman_cloud.middleware import Scope
    require_adapter(family)
    runtime = _runtime(blackhole, 20000)
    threading.Timer(0.2, runtime.close).start()
    started = time.monotonic()
    assert _drive(family, runtime, Scope("tests", "shutdown")) == ORIGINAL
    assert time.monotonic() - started < 10, "close() did not release the in-flight call"


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")
@pytest.mark.parametrize("family", sorted(DRIVERS))
@pytest.mark.parametrize("view", ["sync", "async"])
def test_forked_child_drives_the_adapter_without_hanging(family, view, lenient_runtime, monkeypatch):
    """D3: the parent's pools, threads and loops exist before the fork; the child must still finish, and compress."""
    from cstman_cloud.middleware import Scope
    require_adapter(family)
    # macOS only: with no proxy variable set, urllib asks SystemConfiguration, which segfaults in a forked child
    # (litellm's httpx client does this). Any *_proxy variable skips that lookup; loopback is never proxied anyway.
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    runtime = lenient_runtime if view == "sync" else lenient_runtime.as_async()
    assert _drive(family, runtime, Scope("tests", "parent")).startswith(MARKER)
    read, write = os.pipe()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # "multi-threaded, use of fork() may lead to deadlocks": the point
        pid = os.fork()
    if pid == 0:
        outcome = b"error"
        try:
            # Upstream, not the adapter: CPython < 3.12 leaves the parent's current event loop set in a forked child
            # (reset at fork since 3.12, gh-66285) and agent.run_sync() reuses it. Its kqueue (macOS) and its default
            # executor's worker thread (everywhere) do not survive fork, so plain pydantic-ai hangs there, CSTMAN or
            # not. Do what 3.12 does at fork so the adapter itself stays under test on the 3.11 floor.
            if family == "pydantic_ai" and sys.version_info < (3, 12):
                asyncio.set_event_loop(asyncio.new_event_loop())
            text = _drive(family, runtime, Scope("tests", "child"))
            outcome = b"compressed" if text.startswith(MARKER) else b"original" if text == ORIGINAL else b"other"
        finally:
            os.write(write, outcome)
            os._exit(0)
    os.close(write)
    deadline = time.monotonic() + 30
    while not (waited := os.waitpid(pid, os.WNOHANG))[0]:
        if time.monotonic() > deadline:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            pytest.fail(f"{family} ({view}) hung in a forked child")
        time.sleep(0.05)
    outcome = os.read(read, 64)
    os.close(read)
    assert outcome == b"compressed", f"child {outcome!r}, exit {os.waitstatus_to_exitcode(waited[1])}"


# Certified families with a caller-built history. Each takes (runtime, scope, first_user_content, earlier_turns) and
# returns (text the provider received for the newest tool result, the provider's first user turn, history intact).
PNG = "iVBORw0KGgoAAAANSUhEUg=="


def earlier(i):
    """An earlier tool result. Longer than a replacement marker: the test peer replaces every segment it is sent."""
    return f"earlier result {i} " + "." * 200


def _history_openai(runtime, scope, first, turns):
    from openai import OpenAI
    from cstman_middleware.openai import with_cstman_openai_tools

    http, received = _openai_http(), []

    def provider(request):
        received.append(json.loads(request.content))
        return http.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "m", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})

    def turn(call, content):
        return [{"role": "assistant", "tool_calls": [{"type": "function", "id": call, "function": {"name": "read_log", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": call, "content": content}]

    messages = [{"role": "user", "content": first("openai")}] + [m for i in range(turns) for m in turn(f"old-{i}", earlier(i))] + turn("call-1", ORIGINAL)
    same = untouched(messages)
    tools = [{"type": "function", "function": {"name": "read_log", "description": "Read", "parameters": {"type": "object", "properties": {}}}}]
    with OpenAI(api_key="test", http_client=http.Client(transport=http.MockTransport(provider))) as client:
        loop = with_cstman_openai_tools(client, runtime=runtime, scope=scope, protocol="openai-chat", tools=tools, functions={"read_log": lambda _: ORIGINAL})
        loop.client.chat.completions.create(model="m", tools=loop.tools, messages=messages)
    return received[0]["messages"][-1]["content"], received[0]["messages"][0], same()


def _history_anthropic(runtime, scope, first, turns):
    import importlib
    from anthropic import Anthropic, DefaultHttpxClient
    from anthropic.lib.tools import beta_tool
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.anthropic import with_cstman_anthropic

    http, received = importlib.import_module(sdk_flavour(DefaultHttpxClient)), []

    def provider(request):
        received.append(json.loads(request.content))
        return http.Response(200, json={"id": "msg", "type": "message", "role": "assistant", "model": "m", "stop_reason": "end_turn",
                                        "stop_sequence": None, "content": [{"type": "text", "text": "done"}], "usage": {"input_tokens": 1, "output_tokens": 1}})

    @beta_tool
    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    def turn(call, content):
        return [{"role": "assistant", "content": [{"type": "tool_use", "id": call, "name": "read_log", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call, "content": content}]}]

    messages = [{"role": "user", "content": first("anthropic")}] + [m for i in range(turns) for m in turn(f"toolu_old{i}", earlier(i))] + turn("toolu_1", ORIGINAL)
    same = untouched(messages)
    with Anthropic(api_key="test", http_client=http.Client(transport=http.MockTransport(provider))) as client:
        with_cstman_anthropic(client, runtime=runtime, scope=scope).beta.messages.tool_runner(
            model="m", max_tokens=16, messages=messages, tools=[read_log]).until_done()
    return received[0]["messages"][-1]["content"][0]["content"], received[0]["messages"][0], same()


def _history_langchain(runtime, scope, first, turns):
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from cstman_middleware.langchain import with_cstman_agent

    def turn(call, content):
        return [AIMessage("", tool_calls=[{"id": call, "name": "read_log", "args": {}}]), ToolMessage(content, tool_call_id=call, name="read_log")]

    history = [HumanMessage(content=first("langchain"))] + [m for i in range(turns) for m in turn(f"old-{i}", earlier(i))] + turn("call-1", ORIGINAL)
    same = untouched(history)
    agent = with_cstman_agent({"tools": []}, runtime=runtime, scope=scope)
    request = ModelRequest(model=FakeListChatModel(responses=["unused"]), messages=history, tools=agent["tools"])
    seen = []
    agent["middleware"][0].wrap_model_call(request, lambda projected: seen.append(projected.messages) or ModelResponse(result=[AIMessage("done")]))
    return seen[0][-1].content, seen[0][0].content, same()


HISTORIES = {"openai": _history_openai, "anthropic": _history_anthropic, "langchain": _history_langchain}
IMAGE = {"openai": {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}},
         "anthropic": {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}},
         "langchain": {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}}


@pytest.mark.parametrize("family", sorted(HISTORIES))
def test_image_and_long_history_still_compress_the_newest_result(family, protocol_runtime):
    """C5/D6: 2100 earlier tool turns (over 256 candidates and 4096 manifest items) and an image never skip the call."""
    from cstman_cloud.middleware import Scope
    require_adapter(family)
    first = lambda name: [{"type": "text", "text": "summarize"}, IMAGE[name]]  # noqa: E731
    received, first_turn, intact = HISTORIES[family](protocol_runtime, Scope("tests", "long"), first, 2100)
    assert received.startswith(MARKER), "the newest tool result was not compressed"
    assert PNG in json.dumps(first_turn, default=str), "the image did not reach the provider"
    assert intact, "the caller's history changed"
    assert len(protocol_runtime.requests) == 1
    request = protocol_runtime.requests[0]
    assert any(segment["content"] == ORIGINAL for segment in request["segments"]), "the newest result was not sent"
    assert len(request["segments"]) <= 256 and len(request["context_manifest"]) <= 4096


@pytest.mark.parametrize("family", ["langchain", "openai", "anthropic"])
def test_async_cancellation_while_the_runtime_is_slow_propagates_promptly(family, blackhole):
    """An async caller cancelled while optimize waits on a wedged runtime gets CancelledError at once, not at the deadline."""
    from cstman_cloud.middleware import Scope
    require_adapter(family)
    runtime = _runtime(blackhole, 20000)

    async def cancel_after_start():
        task = asyncio.ensure_future(_async_drive(family, runtime.as_async(), Scope("tests", "cancel")))
        await asyncio.sleep(0.2)
        task.cancel()
        started = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        return time.monotonic() - started

    try:
        assert asyncio.run(cancel_after_start()) < 5, "cancellation waited for the runtime deadline"
    finally:
        runtime.close()


async def _async_drive(family, runtime, scope):
    """One async native call per certified family; the provider must never be reached."""
    if family == "openai":
        from openai import AsyncOpenAI
        http = _openai_http()

        def provider(request):
            raise AssertionError("a cancelled call reached the provider")

        async with AsyncOpenAI(api_key="test", http_client=http.AsyncClient(transport=http.MockTransport(provider))) as client:
            wrapped = _openai_tool_loop(client, runtime, scope)
            return await wrapped.client.chat.completions.create(model="m", tools=wrapped.tools, messages=_chat_history())
    if family == "anthropic":
        import importlib
        from anthropic import AsyncAnthropic, DefaultHttpxClient
        from anthropic.lib.tools import beta_async_tool
        from cstman_middleware._httpx2 import sdk_flavour
        from cstman_middleware.anthropic import with_cstman_anthropic
        http = importlib.import_module(sdk_flavour(DefaultHttpxClient))

        def provider(request):
            raise AssertionError("a cancelled call reached the provider")

        @beta_async_tool
        async def read_log() -> str:
            """Read the log."""
            return ORIGINAL

        messages = [{"role": "user", "content": "summarize"},
                    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "read_log", "input": {}}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": ORIGINAL}]}]
        async with AsyncAnthropic(api_key="test", http_client=http.AsyncClient(transport=http.MockTransport(provider))) as client:
            runner = with_cstman_anthropic(client, runtime=runtime, scope=scope).beta.messages.tool_runner(
                model="m", max_tokens=16, messages=messages, tools=[read_log])
            return await runner.until_done()
    from langchain.agents.middleware.types import ModelRequest
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from cstman_middleware.langchain import with_cstman_agent
    history = [HumanMessage("summarize"), AIMessage("", tool_calls=[{"id": "call-1", "name": "read_log", "args": {}}]),
               ToolMessage(ORIGINAL, tool_call_id="call-1", name="read_log")]
    agent = with_cstman_agent({"tools": []}, runtime=runtime, scope=scope)
    request = ModelRequest(model=FakeListChatModel(responses=["unused"]), messages=history, tools=agent["tools"])

    async def handler(projected):
        raise AssertionError("a cancelled call reached the model")

    return await agent["middleware"][0].awrap_model_call(request, handler)


def _chat_history():
    return [{"role": "user", "content": "summarize"},
            {"role": "assistant", "tool_calls": [{"type": "function", "id": "call-1", "function": {"name": "read_log", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call-1", "content": ORIGINAL}]


def _openai_tool_loop(client, runtime, scope):
    from cstman_middleware.openai import with_cstman_openai_tools
    tools = [{"type": "function", "function": {"name": "read_log", "description": "Read", "parameters": {"type": "object", "properties": {}}}}]

    async def read_log(_):
        return ORIGINAL

    return with_cstman_openai_tools(client, runtime=runtime, scope=scope, protocol="openai-chat", tools=tools, functions={"read_log": read_log})


def test_anthropic_tool_runner_executes_recovery_and_the_model_receives_the_exact_original(protocol_runtime):
    """openai and langchain recovery run in their native suites; this is the anthropic tool_runner's."""
    require_adapter("anthropic")
    import importlib
    import re
    from anthropic import Anthropic, DefaultHttpxClient
    from anthropic.lib.tools import beta_tool
    from cstman_cloud.middleware import Scope
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.anthropic import with_cstman_anthropic
    http, received = importlib.import_module(sdk_flavour(DefaultHttpxClient)), []

    def provider(request):
        body = json.loads(request.content)
        received.append(body)
        if len(received) == 1:
            handle = re.search(r"handle=(cmw_[a-f0-9]{48})\]", body["messages"][-1]["content"][0]["content"]).group(1)
            content, stop = [{"type": "tool_use", "id": "toolu_r", "name": "cstman_retrieve", "input": {"handle": handle}}], "tool_use"
        else:
            content, stop = [{"type": "text", "text": "done"}], "end_turn"
        return http.Response(200, json={"id": "msg", "type": "message", "role": "assistant", "model": "m", "stop_reason": stop,
                                        "stop_sequence": None, "content": content, "usage": {"input_tokens": 1, "output_tokens": 1}})

    @beta_tool
    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    messages = [{"role": "user", "content": "summarize"},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "read_log", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": ORIGINAL}]}]
    same = untouched(messages)
    with Anthropic(api_key="test", http_client=http.Client(transport=http.MockTransport(provider))) as client:
        with_cstman_anthropic(client, runtime=protocol_runtime, scope=Scope("tests", "recover")).beta.messages.tool_runner(
            model="m", max_tokens=16, messages=messages, tools=[read_log]).until_done()
    assert same()
    assert received[0]["messages"][-1]["content"][0]["content"].startswith(MARKER)
    result = next(block for block in received[1]["messages"][-1]["content"] if block.get("tool_use_id") == "toolu_r")
    text = result["content"] if isinstance(result["content"], str) else "".join(block["text"] for block in result["content"])
    assert ORIGINAL in text or json.loads(text)["text"] == ORIGINAL, "the model did not receive the exact original"
    assert len(protocol_runtime.retrievals) == 1
