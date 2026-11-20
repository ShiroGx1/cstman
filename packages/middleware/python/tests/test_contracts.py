"""Finding-specific contracts (D1, D6, D7, D8, D10-D15, Decision 3/4) not covered by test_behavior."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import peer_runtime
from frameworks import require_adapter

ROOT = Path(__file__).parents[1]


# ---------------------------------------------------------------- no framework needed


def test_recovery_name_conflict_is_reported_through_decline():
    """TS parity: a name conflict reaches on_diagnostic and strict ready() raises it; nothing raises at wrap time."""
    from cstman_cloud.middleware import MiddlewareError
    from cstman_middleware._guard import recovery_name_conflict

    diagnostics = []
    runtime = peer_runtime(strict=True, on_diagnostic=diagnostics.append)
    recovery_name_conflict(runtime.as_async(), "demo")
    assert [d["code"] for d in diagnostics] == ["recovery_name_conflict"]
    with pytest.raises(MiddlewareError) as raised:
        runtime.ready()
    assert raised.value.code == "recovery_name_conflict"
    runtime.close()


def test_httpx2_is_never_imported_eagerly():
    """D1: an openai 2.x stack has no httpx2; importing the shared transport module must not need it."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT.parents[1] / "sdk/python"), str(ROOT)])}
    code = "import sys; sys.modules['httpx2'] = None; import cstman_middleware._httpx2, cstman_middleware._native"
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_manifest_hashes_opaque_parts_and_keeps_a_prefix_stable_head():
    """D6: images/bytes become hashed stand-ins; long history is windowed, never a whole-call bypass."""
    from cstman_cloud.middleware import opaque_manifest_value, sha256
    from cstman_middleware._native import manifest

    image = {"type": "image", "data": b"\x89PNG"}
    digest = manifest([image])
    assert digest is not None and digest[0]["sha256"] == sha256(json.dumps({"type": "image", "data": opaque_manifest_value(b"\x89PNG")}, separators=(",", ":")))
    history = [{"role": "user", "content": "x" * 1000} for _ in range(10)]
    head = manifest(history, max_bytes=4000)
    assert len(head) == 3 and head.sequence == 10
    assert manifest(history + [{"role": "user", "content": "more"}], max_bytes=4000)[:3] == head
    assert manifest(history)[0]["sha256"] == sha256(json.dumps(history[0], ensure_ascii=False, separators=(",", ":")))


def _asgi_call(middleware, body):
    seen = []

    async def drive():
        received = iter([{"type": "http.request", "body": body, "more_body": False}])

        async def receive():
            return next(received)

        async def send(_):
            pass

        await middleware({"type": "http", "method": "POST", "path": "/v1/chat/completions",
                          "headers": [(b"content-type", b"application/json")]}, receive, send)
    asyncio.run(drive())
    return seen


def test_asgi_body_cap_is_configurable_and_reports_payload_budget():
    """D6/D8: pure ASGI (no FastAPI/Starlette gate); an oversize body is reported, not silently skipped."""
    from cstman_cloud.middleware import Scope
    from cstman_middleware.asgi import ASGIContext, CSTMANASGIMiddleware

    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "x" * (3 << 20)}]}).encode()
    for cap, reason in ((2 << 20, "payload_budget"), (8 << 20, "recovery_unbound")):  # within the cap: an ordinary decision
        runtime = peer_runtime()
        seen = []

        async def application(scope, receive, send):
            seen.append((await receive())["body"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        middleware = CSTMANASGIMiddleware(application, runtime=runtime, routes={"/v1/chat/completions": "openai-chat"},
                                           resolve_context=lambda _: ASGIContext(Scope("tests", "asgi")), max_body_bytes=cap)
        _asgi_call(middleware, body)
        assert seen == [body]
        assert [event.reason for event in runtime.reports] == [reason]
        runtime.close()


def test_asgi_context_resolver_failure_passes_through(caplog):
    """Decision 4: a raising resolver cannot take the application route down."""
    from cstman_middleware.asgi import CSTMANASGIMiddleware

    runtime, seen = peer_runtime(), []

    async def application(scope, receive, send):
        seen.append(True)

    def resolver(_):
        raise RuntimeError("auth backend down")

    middleware = CSTMANASGIMiddleware(application, runtime=runtime, routes={"/v1/chat/completions": "openai-chat"}, resolve_context=resolver)
    _asgi_call(middleware, b"{}")
    assert seen == [True] and [event.reason for event in runtime.reports] == ["adapter_error"]
    assert "adapter=asgi reason=adapter_error" in caplog.text
    runtime.close()


def test_scope_resolver_failures_degrade_to_invalid_scope(caplog):
    """D4/D15: a missing thread/session never raises into the agent call in non-strict mode."""
    from cstman_cloud.middleware import MiddlewareError, Scope
    from cstman_middleware._guard import resolve_scope

    lenient, strict = peer_runtime(), peer_runtime(strict=True)

    def missing(_config):
        raise ValueError("requires a nonempty configurable.thread_id")

    assert resolve_scope(lenient, "langchain", missing, {}) is None
    assert resolve_scope(lenient, "langchain", Scope("tests", "user 42 / chat #7")).session_id.startswith("h-")
    assert resolve_scope(lenient, "langchain", lambda _: "not a scope", {}) is None
    assert "adapter=langchain reason=invalid_scope" in caplog.text
    with pytest.raises(MiddlewareError, match="invalid_scope"):
        resolve_scope(strict, "langchain", missing, {})
    lenient.close(), strict.close()


def test_fail_open_guard_contract(caplog):
    from cstman_cloud.middleware import MiddlewareError
    from cstman_middleware._guard import fail_open

    lenient, strict = peer_runtime(), peer_runtime(strict=True)
    assert fail_open(lenient, "openai-sdk", KeyError("x")) == "adapter_error"
    assert "adapter=openai-sdk reason=adapter_error" in caplog.text
    with pytest.raises(MiddlewareError) as raised:
        fail_open(strict, "openai-sdk", KeyError("x"))
    assert raised.value.code == "adapter_error" and isinstance(raised.value.__cause__, KeyError)
    with pytest.raises(MiddlewareError, match="runtime_unavailable"):
        fail_open(strict, "openai-sdk", MiddlewareError("runtime_unavailable"))
    lenient.close(), strict.close()


def test_every_adapter_family_has_a_tier():
    """Decision 11: certified = langchain, openai, anthropic, litellm; everything else experimental."""
    import tomllib
    from cstman_middleware import COMPATIBILITY

    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]
    assert set(COMPATIBILITY) == {name.replace("-", "_") for name in extras}
    assert {name for name, entry in COMPATIBILITY.items() if entry.tier == "certified"} == {"langchain", "openai", "anthropic", "litellm"}
    assert {entry.tier for entry in COMPATIBILITY.values()} == {"certified", "experimental"}


def _reason_literals():
    """Every string the package can report as a reason, found statically: arguments of the pass-through helpers
    and MiddlewareError, ``reason=``-style keywords, ``reason``/``.reason`` assignments, and the returns of the
    functions that hand a reason back to their caller. Only literals in value position count, so an adapter id
    passed to a nested call is never mistaken for a reason."""
    import ast
    import cstman_middleware

    sinks = {"passive", "_passive", "_passive_stream", "_passive_astream", "passthrough", "skipped", "_report", "_Skip", "MiddlewareError", "decline"}
    keywords = {"reason", "passive_reason", "passthrough_reason", "passthrough"}
    returning = {"fail_open", "options", "_passive", "select", "_passive_reason", "_admit", "_options"}

    def direct(node):
        if isinstance(node, ast.Constant):
            return {node.value} if isinstance(node.value, str) else set()
        children = {ast.IfExp: lambda n: (n.body, n.orelse), ast.BoolOp: lambda n: n.values, ast.Tuple: lambda n: n.elts}
        return set().union(*map(direct, children[type(node)](node))) if type(node) in children else set()

    def named_reason(target):
        return (isinstance(target, ast.Name) and target.id == "reason") or (isinstance(target, ast.Attribute) and target.attr == "reason") \
            or (isinstance(target, ast.Tuple) and any(map(named_reason, target.elts)))

    found = {}
    for path in sorted(Path(cstman_middleware.__file__).parent.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            values = []
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                values = [*(node.args if name in sinks else node.args[1:] if name == "warn_once" else []),
                          *(keyword.value for keyword in node.keywords if keyword.arg in keywords)]
            elif isinstance(node, ast.Assign) and any(map(named_reason, node.targets)):
                values = [node.value]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in returning:
                values = [child.value for child in ast.walk(node) if isinstance(child, ast.Return) and child.value is not None]
            for value in values:
                for literal in direct(value):
                    found.setdefault(literal, f"{path.name}:{value.lineno}")
    return found


def test_every_reported_reason_is_in_the_spec_catalog():
    """§8: every reason a client reports is a catalog key."""
    from cstman_cloud.middleware import REASON_CATALOG

    found = _reason_literals()
    assert {"adapter_error", "invalid_plan", "provider_state_retained", "unsupported_version"} <= found.keys(), "the scan lost its sinks"
    assert {reason: where for reason, where in found.items() if reason not in REASON_CATALOG} == {}


def test_adapters_send_the_installed_package_version():
    """Adapter.version on the wire is the installed cstman-middleware release, never a literal."""
    import ast
    import cstman_middleware
    from cstman_middleware._versions import VERSION, installed_version

    assert VERSION == (installed_version("cstman-middleware") or "unknown")
    assert cstman_middleware.__version__ == VERSION
    literal = [f"{path.name}:{node.lineno}" for path in Path(cstman_middleware.__file__).parent.glob("*.py")
               for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
               if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Adapter"
               and len(node.args) > 1 and isinstance(node.args[1], ast.Constant)]
    assert literal == []


def _embeddings_openai(runtime):
    import importlib
    from openai import DefaultHttpxClient, OpenAI
    from cstman_cloud.middleware import Scope
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.openai import with_cstman_openai

    http = importlib.import_module(sdk_flavour(DefaultHttpxClient))
    provider = lambda _: http.Response(200, json={"object": "list", "data": [{"object": "embedding", "index": 0, "embedding": [0.0]}],
                                                  "model": "e", "usage": {"prompt_tokens": 1, "total_tokens": 1}})
    with OpenAI(api_key="test", http_client=http.Client(transport=http.MockTransport(provider))) as client:
        with_cstman_openai(client, runtime=runtime, scope=Scope("tests", "embed")).embeddings.create(model="e", input="x")


def _count_tokens_anthropic(runtime):
    import importlib
    from anthropic import Anthropic, DefaultHttpxClient
    from cstman_cloud.middleware import Scope
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.anthropic import with_cstman_anthropic

    http = importlib.import_module(sdk_flavour(DefaultHttpxClient))
    with Anthropic(api_key="test", http_client=http.Client(transport=http.MockTransport(lambda _: http.Response(200, json={"input_tokens": 1})))) as client:
        with_cstman_anthropic(client, runtime=runtime, scope=Scope("tests", "count")).messages.count_tokens(
            model="m", messages=[{"role": "user", "content": "hi"}])


def _health_asgi(runtime):
    from cstman_cloud.middleware import Scope
    from cstman_middleware.asgi import ASGIContext, CSTMANASGIMiddleware

    served = []

    async def application(scope, receive, send):
        served.append(scope["path"])

    middleware = CSTMANASGIMiddleware(application, runtime=runtime, routes={"/v1/chat/completions": "openai-chat"},
                                       resolve_context=lambda _: ASGIContext(Scope("tests", "asgi")))
    for method, path in (("GET", "/health"), ("POST", "/v1/embeddings")):
        asyncio.run(middleware({"type": "http", "method": method, "path": path, "headers": []}, None, None))
    assert served == ["/health", "/v1/embeddings"]


def _embeddings_litellm(runtime):
    from cstman_cloud.middleware import Scope
    from cstman_middleware.litellm import CSTMANLiteLLM

    cstman = CSTMANLiteLLM(runtime=runtime, proxy_scope=lambda auth, data: Scope("tests", "proxy"))
    data = {"model": "e", "input": "x"}
    assert asyncio.run(cstman.async_pre_call_hook(None, None, data, "aembedding")) is data


@pytest.mark.parametrize("family,call", [("openai", _embeddings_openai), ("anthropic", _count_tokens_anthropic),
                                         ("asgi", _health_asgi), ("litellm", _embeddings_litellm)])
def test_endpoints_that_are_never_llm_calls_report_nothing(family, call, caplog):
    """No decision, report or "passed content through unchanged" line for a call no adapter could ever project."""
    require_adapter(family)
    runtime = peer_runtime()
    call(runtime)
    runtime.close()
    assert runtime.reports == [] and runtime.requests == [] and "reason=" not in caplog.text


# ---------------------------------------------------------------- OpenAI


def test_openai_uses_the_sdks_own_http_library():
    """D1: openai 2.x runs on httpx, 3.x on httpx2; the adapter follows the installed major."""
    require_adapter("openai")
    import openai
    from cstman_middleware import openai as adapter

    expected = "httpx2" if int(openai.__version__.split(".")[0]) >= 3 else "httpx"
    assert adapter.CSTMANOpenAITransport.__mro__[1].__module__.split(".")[0] in (expected, "openai")
    assert isinstance(adapter.CSTMANOpenAITransport(__import__(expected).HTTPTransport()), __import__(expected).BaseTransport)


def _responses_call(runtime, **create):
    import importlib
    from openai import DefaultHttpxClient, OpenAI
    from cstman_cloud.middleware import Scope
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.openai import with_cstman_openai_tools

    http, received = importlib.import_module(sdk_flavour(DefaultHttpxClient)), []
    original = "[INFO] kept\n" * 300

    def provider(request):
        received.append(json.loads(request.content)["input"][-1]["output"])
        return http.Response(200, json={"id": "r", "object": "response", "created_at": 0, "model": "m", "status": "completed", "output": []})

    wrap = create.pop("wrap", {})
    with OpenAI(api_key="test", http_client=http.Client(transport=http.MockTransport(provider))) as client:
        loop = with_cstman_openai_tools(client, runtime=runtime, scope=Scope("tests", "responses"), protocol="openai-responses",
                                         tools=[{"type": "function", "name": "read_log", "parameters": {"type": "object", "properties": {}}}],
                                         functions={"read_log": lambda _: original}, **wrap)
        loop.client.responses.create(model="m", tools=loop.tools, input=[
            {"type": "function_call", "call_id": "c1", "name": "read_log", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c1", "output": original}], **create)
    return received[0] != original


def test_openai_responses_store_is_not_compressed_unless_opted_in():
    """A stored Responses turn would outlive the call: provider_state_retained unless store=False or opted in."""
    require_adapter("openai")
    runtime = peer_runtime()
    assert _responses_call(runtime) is False
    assert [event.reason for event in runtime.reports] == ["provider_state_retained"]
    assert _responses_call(runtime, store=False) is True
    assert _responses_call(runtime, wrap={"allow_stored_responses": True}) is True
    runtime.close()


def test_openai_tool_name_conflict_disables_recovery_instead_of_raising(caplog):
    require_adapter("openai")
    from openai import OpenAI
    from cstman_cloud.middleware import Scope
    from cstman_middleware.openai import with_cstman_openai_tools

    diagnostics = []
    runtime = peer_runtime(on_diagnostic=diagnostics.append)
    own = [{"type": "function", "function": {"name": "cstman_retrieve", "parameters": {"type": "object"}}}]
    loop = with_cstman_openai_tools(OpenAI(api_key="test"), runtime=runtime, scope=Scope("tests", "conflict"), protocol="openai-chat",
                                     tools=own, functions={"cstman_retrieve": lambda _: "host tool"})
    assert loop.tools == own and loop.functions["cstman_retrieve"]({}) == "host tool"
    assert "adapter=openai-sdk reason=recovery_name_conflict" in caplog.text
    assert [d["code"] for d in diagnostics] == ["recovery_name_conflict"], "the host got no signal"
    runtime.close()


# ---------------------------------------------------------------- Anthropic


def test_anthropic_bedrock_client_is_supported():
    """D12: AnthropicBedrock shares the Messages body; the tool runner compresses through it."""
    require_adapter("anthropic")
    import importlib
    from anthropic import AnthropicBedrock, DefaultHttpxClient
    from anthropic.lib.tools import beta_tool
    from cstman_cloud.middleware import Scope
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.anthropic import with_cstman_anthropic

    http, received, original = importlib.import_module(sdk_flavour(DefaultHttpxClient)), [], "[INFO] log\n" * 300

    def provider(request):
        received.append((request.url.path, json.loads(request.content)["messages"][-1]["content"][0]["content"]))
        return http.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": "m", "stop_reason": "end_turn",
                                        "stop_sequence": None, "content": [{"type": "text", "text": "done"}], "usage": {"input_tokens": 1, "output_tokens": 1}})

    @beta_tool
    def read_log() -> str:
        """Read the log."""
        return original

    runtime = peer_runtime()
    client = AnthropicBedrock(api_key="test", aws_region="us-east-1", http_client=http.Client(transport=http.MockTransport(provider)))
    wrapped = with_cstman_anthropic(client, runtime=runtime, scope=Scope("tests", "bedrock"))
    wrapped.beta.messages.tool_runner(model="anthropic.claude", max_tokens=16, tools=[read_log], messages=[
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "read_log", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": original}]}]).until_done()
    path, sent = received[0]
    assert path.endswith("/invoke") and sent.startswith("[cstman: shortened;")
    runtime.close()


def test_anthropic_cloud_clients_keep_the_callers_credentials(monkeypatch):
    """A wrapped AnthropicBedrock signs with the caller's aws_profile, never the default AWS credential chain;
    every other Bedrock/Vertex auth setting survives the clone too."""
    require_adapter("anthropic")
    import importlib
    import types
    from anthropic import AnthropicBedrock, AnthropicVertex, DefaultHttpxClient
    from cstman_cloud.middleware import Scope
    from cstman_middleware._httpx2 import sdk_flavour
    from cstman_middleware.anthropic import with_cstman_anthropic

    signed, auth = [], types.ModuleType("anthropic.lib.bedrock._auth")
    auth.get_auth_headers = lambda **request: signed.append(request["profile"]) or {}
    monkeypatch.setitem(sys.modules, "anthropic.lib.bedrock._auth", auth)  # SigV4 signing without boto3
    http = importlib.import_module(sdk_flavour(DefaultHttpxClient))
    provider = lambda _: http.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": "m", "stop_reason": "end_turn",
                                                  "stop_sequence": None, "content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    runtime, scope = peer_runtime(), Scope("tests", "cloud")
    bedrock = AnthropicBedrock(aws_profile="p", aws_region="us-west-2", aws_session_token="t", http_client=http.Client(transport=http.MockTransport(provider)))
    wrapped = with_cstman_anthropic(bedrock, runtime=runtime, scope=scope)
    wrapped.messages.create(model="anthropic.claude", max_tokens=8, messages=[{"role": "user", "content": "hi"}])
    assert signed == ["p"]
    vertex = AnthropicVertex(region="us-east5", project_id="project", access_token="token")
    for client, names in ((bedrock, ("aws_profile", "aws_region", "aws_access_key", "aws_secret_key", "aws_session_token", "api_key", "base_url")),
                          (vertex, ("region", "project_id", "access_token", "credentials", "base_url"))):
        clone = with_cstman_anthropic(client, runtime=runtime, scope=scope)
        assert {name: getattr(clone, name) for name in names} == {name: getattr(client, name) for name in names}
    runtime.close()


# ---------------------------------------------------------------- LangChain


def test_langchain_missing_thread_id_passes_through(caplog):
    """D15: scope_from_config without a thread no longer raises into the agent call."""
    require_adapter("langchain")
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from cstman_middleware.langchain import scope_from_config, with_cstman_model

    runtime = peer_runtime()
    model = with_cstman_model(FakeListChatModel(responses=["done"]), runtime=runtime,
                               scope=lambda config: scope_from_config(config, namespace="tests"))
    assert model.invoke("hello").content == "done"
    assert [event.reason for event in runtime.reports] == ["invalid_scope"]
    assert "adapter=langchain reason=invalid_scope" in caplog.text
    runtime.close()


def test_langchain_tool_name_conflict_warns(caplog):
    require_adapter("langchain")
    from langchain_core.tools import tool
    from cstman_cloud.middleware import Scope
    from cstman_middleware.langchain import with_cstman_agent

    @tool
    def cstman_retrieve(handle: str) -> str:
        """Host tool."""
        return handle

    runtime = peer_runtime()
    options = with_cstman_agent({"tools": [cstman_retrieve]}, runtime=runtime, scope=Scope("tests", "conflict"))
    assert options["tools"] == [cstman_retrieve]
    assert "adapter=langchain reason=recovery_name_conflict" in caplog.text
    runtime.close()


# ---------------------------------------------------------------- LiteLLM


def test_litellm_pending_capacity_is_reported_not_silent(monkeypatch, caplog):
    """D10: a full pending table passes the call through with `capacity`, never evicting another call."""
    require_adapter("litellm")
    from cstman_cloud.middleware import Scope
    from cstman_middleware import litellm as adapter

    runtime = peer_runtime()
    monkeypatch.setattr(adapter, "_PENDING", 1)
    cstman = adapter.CSTMANLiteLLM(runtime=runtime)
    held = cstman._remember(Scope("tests", "one"), "acompletion")
    assert cstman._admit("completion", Scope("tests", "two"), {"messages": []}, False) == "capacity"
    cstman._forget(held[0])
    assert isinstance(cstman._admit("completion", Scope("tests", "two"), {"messages": []}, False), tuple)
    runtime.close()


def test_litellm_live_instances_share_one_callback_and_the_hosts_still_runs():
    """LiteLLM caps each callback list at 100 (MAX_CALLBACKS): 150 live instances must not push out the host's logger."""
    require_adapter("litellm")
    import time
    import litellm
    from litellm.integrations.custom_logger import CustomLogger
    from cstman_middleware.litellm import CSTMANLiteLLM

    hits = []

    class Host(CustomLogger):
        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            hits.append(response_obj)

    runtime, host = peer_runtime(), Host()
    instances = [CSTMANLiteLLM(runtime=runtime) for _ in range(150)]
    for instance in instances:
        instance.__enter__()
    litellm.callbacks.append(host)
    try:
        litellm.completion(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}], mock_response="ok")
        deadline = time.monotonic() + 10
        while not hits and time.monotonic() < deadline:  # sync success callbacks run on LiteLLM's worker thread
            time.sleep(0.05)
        assert hits, "LiteLLM dropped the host's own callback"
        assert len(litellm.callbacks) == 2
    finally:
        litellm.logging_callback_manager.remove_callback_from_all_lists(host)
        for instance in instances:
            instance.__exit__(None, None, None)
        runtime.close()
    ours = [c for name in ("callbacks", "input_callback", "success_callback", "_async_success_callback")
            for c in getattr(litellm, name) if type(c).__module__ == "cstman_middleware.litellm"]
    assert ours == [], "the last exit must unregister the shared callback"


def test_litellm_sync_router_reports_unsupported_provider_and_identity_breaks():
    require_adapter("litellm")
    from cstman_cloud.middleware import Scope
    from cstman_middleware.litellm import CSTMANLiteLLM

    runtime = peer_runtime()
    cstman = CSTMANLiteLLM(runtime=runtime)
    _, request = cstman._remember(Scope("tests", "router"), "completion")
    cstman._project_sync_router({"litellm_params": {"custom_llm_provider": "vertex_ai"}, "additional_args": {}}, request)
    assert [event.reason for event in runtime.reports] == ["unsupported_provider"]
    cstman._verify["call-1"] = ([], request.logical_id)
    cstman.log_post_api_call({"litellm_call_id": "call-1", "additional_args": {"complete_input_dict": {"messages": []}}}, None, 0, 0)
    assert [event.reason for event in runtime.reports][-1] == "adapter_error"
    runtime.close()


def test_litellm_sync_router_projects_the_dispatched_body():
    """D10: the sync Router edit lands on the dict LiteLLM actually sends, verified after the call."""
    require_adapter("litellm")
    import litellm
    from cstman_cloud.middleware import RECOVERY_DESCRIPTION, RECOVERY_SCHEMA, Scope
    from cstman_middleware.litellm import CSTMANLiteLLM
    from test_behavior import ORIGINAL, _openai_server

    received = []
    server, base = _openai_server(received)
    runtime = peer_runtime()
    router = litellm.Router(model_list=[{"model_name": "m", "litellm_params": {"model": "openai/m", "api_base": base, "api_key": "test"}}])
    tools = [{"type": "function", "function": {"name": "read_log", "description": "Read", "parameters": {"type": "object", "properties": {}}}},
             {"type": "function", "function": {"name": "cstman_retrieve", "description": RECOVERY_DESCRIPTION, "parameters": RECOVERY_SCHEMA}}]
    recovery = lambda scope: (lambda binding: (binding, "{}"))(runtime.recovery(scope))
    try:
        with CSTMANLiteLLM(runtime=runtime, client=router, operator_recovery=recovery) as cstman:
            cstman.completion(scope=Scope("tests", "router"), model="m", tools=tools, messages=[
                {"role": "user", "content": "go"},
                {"role": "assistant", "tool_calls": [{"type": "function", "id": "c1", "function": {"name": "read_log", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": ORIGINAL}])
    finally:
        server.shutdown()
        runtime.close()
    assert received[0]["messages"][-1]["content"].startswith("[cstman: shortened;")
    assert "adapter_error" not in [event.reason for event in runtime.reports]


# ---------------------------------------------------------------- Google


def test_google_wrap_returns_idempotent_clones_with_per_call_scope():
    """D11: the caller's Client is never mutated, re-wrapping never stacks, one transport serves many scopes."""
    require_adapter("google")
    import gc
    import httpx
    from google import genai
    from google.genai import types
    from cstman_cloud.middleware import Scope
    from cstman_middleware.google import CSTMANGoogleTransport, unwrap_google, with_cstman_google
    from test_behavior import ORIGINAL

    def provider(request):
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "done"}]}, "finishReason": "STOP"}]})

    runtime = peer_runtime()
    client = genai.Client(api_key="test", http_options=types.HttpOptions(httpx_client=httpx.Client(
        transport=CSTMANGoogleTransport(runtime=runtime, transport=httpx.MockTransport(provider)))))
    native_generate = client.models.generate_content
    first = with_cstman_google(client, runtime=runtime, scope=Scope("tests", "alice@example.com"))
    second = with_cstman_google(first, runtime=runtime, scope=Scope("tests", "bob"))
    assert first is not client and unwrap_google(second) is client and unwrap_google(client) is client
    assert client.models.generate_content == native_generate
    assert isinstance(first, genai.Client)

    def read_log() -> str:
        """Read the log."""
        return ORIGINAL

    contents = [types.Content(role="user", parts=[types.Part(text="go")]),
                types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="read_log", args={}))]),
                types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(name="read_log", response={"output": ORIGINAL}))])]
    for wrapped in (first, second):
        wrapped.models.generate_content(model="gemini-test", contents=contents, config=types.GenerateContentConfig(tools=[read_log]))
    assert [request["scope"]["session_id"] for request in runtime.requests] == ["h-" + __import__("hashlib").sha256(b"alice@example.com").hexdigest()[:32], "bob"]
    del first, second
    gc.collect()
    client.models.generate_content(model="gemini-test", contents="still open")  # collecting clones never closes the caller's client
    runtime.close()


# ---------------------------------------------------------------- CrewAI


def test_crewai_registers_one_hook_for_any_number_of_models():
    """D7: 1,000 CSTMANLLM instances add one PRE_MODEL_CALL hook and one bus handler in total."""
    require_adapter("crewai")
    from crewai import BaseLLM
    from crewai.events import LLMCallCompletedEvent, crewai_event_bus
    from crewai.hooks import InterceptionPoint
    from crewai.hooks.dispatch import get_hooks
    from cstman_cloud.middleware import Scope
    from cstman_middleware.crewai import CSTMANLLM

    class Provider(BaseLLM):
        def call(self, messages, **kwargs):
            return "done"

    runtime = peer_runtime()
    CSTMANLLM(Provider(model="fake"), runtime=runtime, scope=Scope("tests", "warm"))
    hooks, handlers = len(get_hooks(InterceptionPoint.PRE_MODEL_CALL)), len(crewai_event_bus._sync_handlers.get(LLMCallCompletedEvent, ()))
    for index in range(1000):
        CSTMANLLM(Provider(model="fake"), runtime=runtime, scope=Scope("tests", f"s{index}"))
    assert len(get_hooks(InterceptionPoint.PRE_MODEL_CALL)) == hooks
    assert len(crewai_event_bus._sync_handlers.get(LLMCallCompletedEvent, ())) == handlers
    runtime.close()


# ---------------------------------------------------------------- AutoGen


def test_autogen_tool_call_reuses_the_turns_listing():
    """D13: list_tools() once per turn, not twice per tool call."""
    require_adapter("autogen")
    from autogen_core.tools import FunctionTool, StaticWorkbench
    from cstman_cloud.middleware import Scope
    from cstman_middleware.autogen import CSTMANWorkbench

    calls = []

    class Counting(StaticWorkbench):
        async def list_tools(self):
            calls.append(True)
            return await super().list_tools()

    def read_log() -> str:
        """Read the log."""
        return "log"

    runtime = peer_runtime()
    workbench = CSTMANWorkbench(Counting([FunctionTool(read_log, description="Read")]), runtime=runtime, scope=Scope("tests", "turn"))

    async def turn():
        await workbench.list_tools()
        for _ in range(3):
            assert not (await workbench.call_tool("read_log", {})).is_error

    asyncio.run(turn())
    assert len(calls) == 1
    runtime.close()


# ---------------------------------------------------------------- Pydantic AI / LlamaIndex / MCP


def test_pydantic_ai_host_tool_named_cstman_retrieve_keeps_the_run_alive(caplog):
    require_adapter("pydantic_ai")
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel
    from cstman_cloud.middleware import Scope
    from cstman_middleware.pydantic_ai import CSTMANCapability

    runtime = peer_runtime()
    agent = Agent(TestModel(call_tools=[]), capabilities=[CSTMANCapability(runtime=runtime, scope=Scope("tests", "conflict"))])

    @agent.tool_plain
    def cstman_retrieve(handle: str) -> str:
        """Host tool with the reserved name."""
        return handle

    assert agent.run_sync("hello").output
    assert "adapter=pydantic-ai reason=recovery_name_conflict" in caplog.text
    assert "unsupported_provider" in [event.reason for event in runtime.reports]  # TestModel is not a tested provider
    runtime.close()


def test_llama_index_unknown_provider_passes_through_and_conflict_disables_recovery(caplog):
    require_adapter("llama_index")
    from llama_index.core.base.llms.types import ChatMessage
    from llama_index.core.llms import MockLLM
    from cstman_cloud.middleware import Scope
    from cstman_middleware.llama_index import with_cstman_model, with_cstman_tools

    runtime = peer_runtime()
    with_cstman_model(MockLLM(), runtime=runtime, scope=Scope("tests", "mock")).chat([ChatMessage(role="user", content="hi")])
    assert [event.reason for event in runtime.reports] == ["unsupported_provider"]

    def cstman_retrieve(handle: str) -> str:
        """Host tool with the reserved name."""
        return handle

    bundle = with_cstman_tools(MockLLM(), runtime=runtime, scope=Scope("tests", "conflict"), tools=[cstman_retrieve])
    assert [tool.metadata.name for tool in bundle.tools] == ["cstman_retrieve"]
    runtime.close()


def test_mcp_host_never_raises_at_construction_for_an_unusable_scope():
    """Decision 3: even strict mode surfaces invalid_scope from the call, not the constructor."""
    require_adapter("mcp")
    from cstman_cloud.middleware import Scope
    from cstman_middleware.mcp import CSTMANMCPHost

    runtime = peer_runtime(strict=True)
    host = CSTMANMCPHost(runtime=runtime, scope=Scope("tests", ""), server_id="server", protocol_version="2025-06-18")
    assert host.recovery is None and host.register([]) == []
    runtime.close()
