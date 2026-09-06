"""Optional LiteLLM adapters with fail-closed egress policy."""

from __future__ import annotations

import importlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import ModuleType
from typing import Any, Final
from urllib.parse import urlparse

from fhiratwill.conversion.errors import (
    CostLimitError,
    EgressPolicyError,
    ExtractionSchemaError,
    ProviderUnavailableError,
)
from fhiratwill.conversion.models import (
    DictationResult,
    LlmInvocation,
    LlmResult,
    SpeechInvocation,
)

_LOOPBACK: Final = frozenset({"localhost", "127.0.0.1", "::1"})
_PROVIDER_URLS: Final = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com",
    "groq": "https://api.groq.com/openai/v1",
}


@dataclass(frozen=True, slots=True)
class LiteLlmPolicy:
    """Explicit policy; no values are read from process environment or headers."""

    egress_allowlist: frozenset[str] = frozenset()
    local_only: bool = True
    require_phi_acknowledgement: bool = True
    max_cost_usd: Decimal = Decimal("1.00")
    max_tokens: int = 4096

    def __post_init__(self) -> None:
        if self.max_cost_usd <= 0 or self.max_tokens <= 0:
            raise ValueError("cost and token limits must be positive")


@dataclass(slots=True)
class LiteLlmClient:
    policy: LiteLlmPolicy

    async def complete_json(
        self,
        invocation: LlmInvocation,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LlmResult:
        _authorize(self.policy, invocation)
        module = _load_litellm()
        started = time.perf_counter()
        try:
            response = await module.acompletion(
                model=invocation.model,
                api_key=invocation.api_key.get_secret_value(),
                base_url=invocation.base_url,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=self.policy.max_tokens,
            )
        except Exception:
            raise ProviderUnavailableError("LLM provider request failed") from None
        resource = _json_resource(response)
        cost = _cost(response)
        _enforce_actual_cost(self.policy, invocation.max_cost_usd, cost)
        return LlmResult(
            resource=resource,
            model=str(_read(response, "model") or invocation.model),
            usage=_usage(response),
            cost_usd=cost,
            latency_ms=round((time.perf_counter() - started) * 1000),
            finish_reason=_finish_reason(response),
        )


@dataclass(slots=True)
class LiteLlmSpeechClient:
    policy: LiteLlmPolicy
    allow_audio_egress: bool = False

    async def transcribe(
        self,
        invocation: SpeechInvocation,
        *,
        audio: bytes,
        media_type: str,
    ) -> DictationResult:
        host = _authorize(self.policy, invocation)
        if not self.allow_audio_egress and host not in _LOOPBACK:
            raise EgressPolicyError("raw audio egress is disabled")
        module = _load_litellm()
        started = time.perf_counter()
        try:
            response = await module.atranscription(
                model=invocation.model,
                api_key=invocation.api_key.get_secret_value(),
                api_base=invocation.base_url,
                file=("dictation", audio, media_type),
                language=invocation.language,
            )
        except Exception:
            raise ProviderUnavailableError("speech provider request failed") from None
        text = _read(response, "text")
        if not isinstance(text, str):
            raise ExtractionSchemaError("speech provider returned no transcript")
        cost = _cost(response)
        _enforce_actual_cost(self.policy, invocation.max_cost_usd, cost)
        return DictationResult(
            text=text,
            model=str(_read(response, "model") or invocation.model),
            usage=_usage(response),
            cost_usd=cost,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )


def _load_litellm() -> ModuleType:
    try:
        return importlib.import_module("litellm")
    except ImportError:
        raise ProviderUnavailableError("LiteLLM adapter dependency is not installed") from None


def _authorize(policy: LiteLlmPolicy, invocation: LlmInvocation | SpeechInvocation) -> str:
    target = invocation.base_url or _PROVIDER_URLS.get(invocation.provider.casefold(), "")
    host = (urlparse(target).hostname or "").casefold()
    allowed = frozenset(_normalize_host(value) for value in policy.egress_allowlist)
    if policy.local_only:
        if host not in _LOOPBACK:
            raise EgressPolicyError("local-only policy permits only loopback providers")
    elif not host or host not in allowed:
        raise EgressPolicyError("provider host is not in the explicit egress allowlist")
    if (
        policy.require_phi_acknowledgement
        and host not in _LOOPBACK
        and not invocation.phi_egress_acknowledged
    ):
        raise EgressPolicyError("external clinical-data egress was not acknowledged")
    declared = invocation.max_cost_usd or policy.max_cost_usd
    if declared <= 0 or declared > policy.max_cost_usd:
        raise CostLimitError("invocation cost bound exceeds adapter policy")
    return host


def _normalize_host(value: str) -> str:
    text = value.strip().casefold()
    return (urlparse(text).hostname or text).rstrip(".")


def _json_resource(response: Any) -> dict[str, Any]:
    choices = _read(response, "choices")
    try:
        content = _read(_read(choices[0], "message"), "content")
    except (IndexError, KeyError, TypeError):
        raise ExtractionSchemaError("LLM provider returned no completion") from None
    if not isinstance(content, str):
        raise ExtractionSchemaError("LLM completion was not text")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        raise ExtractionSchemaError("LLM completion was not valid JSON") from None
    if not isinstance(parsed, dict):
        raise ExtractionSchemaError("LLM completion must be one JSON object")
    return parsed


def _read(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _usage(response: Any) -> dict[str, int]:
    usage = _read(response, "usage")
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {
        key: value for key in keys if isinstance((value := _read(usage, key)), int) and value >= 0
    }


def _cost(response: Any) -> Decimal | None:
    raw = _read(response, "_hidden_params")
    raw = _read(raw, "response_cost")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def _enforce_actual_cost(
    policy: LiteLlmPolicy, invocation_limit: Decimal | None, cost: Decimal | None
) -> None:
    limit = invocation_limit or policy.max_cost_usd
    if cost is not None and cost > limit:
        raise CostLimitError("provider-reported cost exceeded the invocation bound")


def _finish_reason(response: Any) -> str | None:
    choices = _read(response, "choices")
    try:
        value = _read(choices[0], "finish_reason")
    except (IndexError, KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


__all__ = ["LiteLlmClient", "LiteLlmPolicy", "LiteLlmSpeechClient"]
