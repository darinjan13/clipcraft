from abc import ABC, abstractmethod
from typing import Any


class TextGenerationProvider(ABC):
    @abstractmethod
    async def generate_structured_content(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...