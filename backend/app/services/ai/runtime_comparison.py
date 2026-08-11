from dataclasses import dataclass
from typing import Literal


ComparisonOutcome = Literal["match", "mismatch", "skipped", "validation_failed"]
MismatchCategory = Literal[
    "provider",
    "model",
    "capability",
    "routing_version",
    "state",
    "legacy_unavailable",
    "shadow_unavailable",
    "comparison_disabled",
    "invalid_metadata",
]


@dataclass(frozen=True)
class RuntimeMetadata:
    provider_id: str
    model_id: str | None
    capability: str
    routing_version: int | None
    state: str | None


@dataclass(frozen=True)
class ComparisonMetric:
    outcome: ComparisonOutcome
    mismatch_category: MismatchCategory | None = None
    legacy_provider_id: str | None = None
    shadow_provider_id: str | None = None
    legacy_model_id: str | None = None
    shadow_model_id: str | None = None
    capability: str | None = None
    legacy_state: str | None = None
    shadow_state: str | None = None


class RuntimeComparisonEngine:
    def __init__(self, *, enabled: bool = True):
        self._enabled = enabled

    def compare(self, legacy: RuntimeMetadata | None, shadow: RuntimeMetadata | None) -> ComparisonMetric:
        if not self._enabled:
            return ComparisonMetric("skipped", "comparison_disabled")
        if legacy is None:
            return ComparisonMetric("skipped", "legacy_unavailable")
        if shadow is None:
            return ComparisonMetric("skipped", "shadow_unavailable")
        if not self._valid(legacy) or not self._valid(shadow):
            return self._metric("validation_failed", "invalid_metadata", legacy, shadow)

        for field, category in (
            ("provider_id", "provider"),
            ("model_id", "model"),
            ("capability", "capability"),
            ("routing_version", "routing_version"),
        ):
            legacy_value = getattr(legacy, field)
            shadow_value = getattr(shadow, field)
            if legacy_value is not None and shadow_value is not None and legacy_value != shadow_value:
                return self._metric("mismatch", category, legacy, shadow)

        if legacy.state is not None and shadow.state is not None and legacy.state != shadow.state:
            return self._metric("mismatch", "state", legacy, shadow)
        return self._metric("match", None, legacy, shadow)

    @staticmethod
    def _valid(value: RuntimeMetadata) -> bool:
        return (
            isinstance(value.provider_id, str)
            and bool(value.provider_id.strip())
            and isinstance(value.capability, str)
            and bool(value.capability.strip())
            and (value.model_id is None or (isinstance(value.model_id, str) and bool(value.model_id.strip())))
            and (value.routing_version is None or isinstance(value.routing_version, int))
            and (value.state is None or isinstance(value.state, str))
        )

    @staticmethod
    def _metric(outcome: ComparisonOutcome, category: MismatchCategory | None, legacy: RuntimeMetadata, shadow: RuntimeMetadata) -> ComparisonMetric:
        return ComparisonMetric(
            outcome=outcome,
            mismatch_category=category,
            legacy_provider_id=legacy.provider_id,
            shadow_provider_id=shadow.provider_id,
            legacy_model_id=legacy.model_id,
            shadow_model_id=shadow.model_id,
            capability=shadow.capability,
            legacy_state=legacy.state,
            shadow_state=shadow.state,
        )
