"""Every eligible adapter must import and expose its documented entry points."""

import pytest

from frameworks import require_adapter

ADAPTERS = {
    "openai": ("with_cstman_openai", "with_cstman_openai_tools"),
    "anthropic": ("with_cstman_anthropic", "CSTMANAnthropicMiddleware"),
    "google": ("with_cstman_google", "with_cstman_google_chat"),
    "langchain": ("CSTMANMiddleware", "with_cstman_agent", "with_cstman_model", "CSTMANDocumentCompressor"),
    "litellm": ("CSTMANLiteLLM",),
    "strands": ("CSTMANModel", "with_cstman_model", "with_cstman_agent"),
    "agno": ("CSTMANModel", "with_cstman_model", "with_cstman_agent"),
    "asgi": ("CSTMANASGIMiddleware", "ASGIContext"),
    "mcp": ("CSTMANMCPHost", "bind_mcp_tool"),
    "crewai": ("CSTMANLLM", "with_cstman_llm", "with_cstman_agent"),
    "pydantic_ai": ("CSTMANModel", "with_cstman_model"),
    "autogen": ("CSTMANChatCompletionClient", "CSTMANWorkbench", "with_cstman_model"),
    "llama_index": ("CSTMANLLMTools",),
}


@pytest.mark.parametrize("family,names", sorted(ADAPTERS.items()))
def test_adapter_exposes_its_documented_entry_points(family, names):
    module = require_adapter(family)
    missing = [name for name in names if not hasattr(module, name)]
    assert not missing, f"cstman_middleware.{family} lost {missing}"
