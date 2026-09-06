from __future__ import annotations

import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from fhiratwill.adapters.litellm import LiteLlmClient, LiteLlmPolicy, LiteLlmSpeechClient
from fhiratwill.conversion import (
    CostLimitError,
    EgressPolicyError,
    LlmInvocation,
    ProviderUnavailableError,
    SpeechInvocation,
)


def test_invocation_repr_masks_secrets() -> None:
    invocation = LlmInvocation("fake", "fake/model", SecretStr("never-render-this"))
    assert "never-render-this" not in repr(invocation)
    assert "**********" in repr(invocation)


@pytest.mark.asyncio
async def test_external_egress_requires_allowlist_and_phi_ack() -> None:
    client = LiteLlmClient(
        LiteLlmPolicy(
            egress_allowlist=frozenset({"api.example.test"}),
            local_only=False,
        )
    )
    invocation = LlmInvocation(
        "custom",
        "custom/model",
        SecretStr("fake"),
        base_url="https://api.example.test/v1",
    )
    with pytest.raises(EgressPolicyError):
        await client.complete_json(invocation, system_prompt="safe", user_prompt="safe")


@pytest.mark.asyncio
async def test_audio_egress_is_separately_blocked() -> None:
    client = LiteLlmSpeechClient(
        LiteLlmPolicy(
            egress_allowlist=frozenset({"audio.example.test"}),
            local_only=False,
        )
    )
    invocation = SpeechInvocation(
        "custom",
        "custom/stt",
        SecretStr("fake"),
        base_url="https://audio.example.test/v1",
        phi_egress_acknowledged=True,
    )
    with pytest.raises(EgressPolicyError):
        await client.transcribe(invocation, audio=b"safe", media_type="audio/wav")


@pytest.mark.asyncio
async def test_cost_bound_is_checked_before_lazy_import() -> None:
    client = LiteLlmClient(LiteLlmPolicy(max_cost_usd=Decimal("0.10")))
    invocation = LlmInvocation(
        "local",
        "custom/model",
        SecretStr("fake"),
        base_url="http://localhost:4000",
        max_cost_usd=Decimal("0.20"),
    )
    with pytest.raises(CostLimitError):
        await client.complete_json(invocation, system_prompt="safe", user_prompt="safe")


@pytest.mark.asyncio
async def test_provider_outage_is_normalized_without_unsafe_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(**kwargs: object) -> object:
        del kwargs
        raise RuntimeError("unsafe patient and credential detail")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fail))
    client = LiteLlmClient(LiteLlmPolicy())
    invocation = LlmInvocation(
        "local",
        "custom/model",
        SecretStr("fake-secret"),
        base_url="http://127.0.0.1:4000",
    )

    with pytest.raises(ProviderUnavailableError) as caught:
        await client.complete_json(invocation, system_prompt="safe", user_prompt="safe")
    assert str(caught.value) == "LLM provider request failed"
    assert "patient" not in str(caught.value)
    assert caught.value.__cause__ is None
