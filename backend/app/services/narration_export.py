from typing import Any, Literal


NarrationExportStyle = Literal["clean", "expressive"]
_SUPPORTED_DELIVERY_CUES = frozenset({"dramatic", "pause", "warm"})


def export_narration(script: dict[str, Any], style: NarrationExportStyle | str) -> str:
    if style not in {"clean", "expressive"}:
        raise ValueError("unsupported narration export style")

    paragraphs: list[str] = []
    for scene in script.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        narration = scene.get("narration")
        if not isinstance(narration, str) or not (spoken_text := narration.strip()):
            continue
        delivery = scene.get("delivery")
        if style == "expressive" and isinstance(delivery, str) and delivery in _SUPPORTED_DELIVERY_CUES:
            spoken_text = f"[{delivery}] {spoken_text}"
        paragraphs.append(spoken_text)
    return "\n\n".join(paragraphs)
