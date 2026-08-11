from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class GeneratedImage:
    data: bytes
    format: str
    width: int
    height: int


class ImageGenerationProvider(ABC):
    @abstractmethod
    async def generate_image(
        self,
        *,
        model: str,
        prompt: str,
        width: int,
        height: int,
        generation_config: dict[str, Any] | None = None,
    ) -> GeneratedImage:
        ...