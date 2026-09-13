from __future__ import annotations

import re
from dataclasses import dataclass, field

from fhiratwill.conversion import (
    DictationResult,
    LlmInvocation,
    LlmResult,
    SpeechInvocation,
)


@dataclass
class FakeLlmClient:
    calls: list[str] = field(default_factory=list)

    async def complete_json(
        self,
        invocation: LlmInvocation,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LlmResult:
        del system_prompt
        self.calls.append(user_prompt)
        token = re.search(r"\[\[NAME_[A-Z0-9]+\]\]", user_prompt)
        value = token.group(0) if token else "synthetic patient"
        return LlmResult(
            resource={
                "entities": [
                    {
                        "resourceType": "Patient",
                        "keyword": "name",
                        "value": value,
                    }
                ]
            },
            model=invocation.model,
        )


@dataclass
class FakeSpeechClient:
    transcript: str
    calls: int = 0

    async def transcribe(
        self,
        invocation: SpeechInvocation,
        *,
        audio: bytes,
        media_type: str,
    ) -> DictationResult:
        del audio, media_type
        self.calls += 1
        return DictationResult(text=self.transcript, model=invocation.model)
