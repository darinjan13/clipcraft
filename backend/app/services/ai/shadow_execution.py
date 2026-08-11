import time
from dataclasses import dataclass
from typing import Any

try:
    import asyncio
except ImportError:
    asyncio = None

from .adapters import ProviderAdapter, default_adapter_registry
from .cloudflare_execution import register_cloudflare_executions
from .credential_resolution import CredentialResolutionError, CredentialResolver, ExecutionContext, ResolvedProviderCredential
from .gemini_execution import register_gemini_execution
from .provider_executor import ProviderExecutor, ProviderExecutionError, ProviderExecutionRegistry
from .routing import DryRunProviderRouter, RoutingConfiguration, RoutingDecision, RoutingValidationError
from .runtime_comparison import ComparisonMetric, RuntimeComparisonEngine, RuntimeMetadata


@dataclass(frozen=True)
class ShadowMetrics:
    provider_id: str
    model_id: str | None
    capability: str
    state: str
    routing_duration_ms: float
    credential_duration_ms: float
    preparation_duration_ms: float
    execution_duration_ms: float | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class ShadowRunReport:
    metrics: tuple[ShadowMetrics, ...]
    comparisons: tuple[ComparisonMetric, ...]


_SHADOW_PARAMETERS: dict[str, dict[str, Any]] = {
    "text_generation": {"prompt": "shadow"},
    "image_generation": {"prompt": "shadow"},
}
_SAFE_ERROR_CATEGORIES = frozenset({
    "invalid_request",
    "invalid_credentials",
    "permission_denied",
    "timeout",
    "rate_limited",
    "unavailable",
    "provider_error",
    "malformed_response",
    "empty_response",
    "blocked_response",
    "credential_resolution_error",
    "missing_capability",
    "configuration_error",
    "execution_error",
})


class ShadowExecutionRunner:
    def __init__(self, settings: object, *, execution_registry: object | None = None, adapters: object | None = None):
        self._settings = settings
        self._enabled = getattr(settings, "shadow_provider_execution", False)
        self._adapters = adapters or default_adapter_registry()
        self._execution_registry = execution_registry or _build_registry()

    def run(
        self,
        *,
        configuration: RoutingConfiguration | None = None,
        database: object | None = None,
        encryption: object | None = None,
        job_id: str | None = None,
        text_provider: str | None = None,
        text_model: str | None = None,
        image_provider: str | None = None,
        image_model: str | None = None,
        visual_source: str | None = None,
        credential_source: str | None = None,
    ) -> tuple[ShadowMetrics, ...]:
        return self._run_internal(
            configuration=configuration,
            database=database,
            encryption=encryption,
            job_id=job_id,
            text_provider=text_provider,
            text_model=text_model,
            image_provider=image_provider,
            image_model=image_model,
            visual_source=visual_source,
            credential_source=credential_source,
            legacy_metadata=(),
            comparison_enabled=False,
        ).metrics

    def run_with_comparison(
        self,
        *,
        legacy_metadata: tuple[RuntimeMetadata, ...],
        comparison_enabled: bool | None = None,
        **kwargs: Any,
    ) -> ShadowRunReport:
        return self._run_internal(
            legacy_metadata=legacy_metadata,
            comparison_enabled=getattr(self._settings, "shadow_runtime_comparison", True) if comparison_enabled is None else comparison_enabled,
            **kwargs,
        )

    def _run_internal(
        self,
        *,
        configuration: RoutingConfiguration | None = None,
        database: object | None = None,
        encryption: object | None = None,
        job_id: str | None = None,
        text_provider: str | None = None,
        text_model: str | None = None,
        image_provider: str | None = None,
        image_model: str | None = None,
        visual_source: str | None = None,
        credential_source: str | None = None,
        legacy_metadata: tuple[RuntimeMetadata, ...] = (),
        comparison_enabled: bool = False,
    ) -> ShadowRunReport:
        if configuration is None:
            configuration = RoutingConfiguration(
                text_provider=text_provider,
                text_model=text_model,
                image_provider=image_provider,
                image_model=image_model,
                visual_source=visual_source,
                credential_source=credential_source,
            )
        metrics: list[ShadowMetrics] = []
        resolver = CredentialResolver(self._settings, database, encryption)
        router = DryRunProviderRouter(self._settings)

        routing_started = time.perf_counter()
        try:
            decision = router.resolve(configuration)
        except (RoutingValidationError, Exception):
            comparisons = tuple(ComparisonMetric("validation_failed", "invalid_metadata") for _ in legacy_metadata) if comparison_enabled else ()
            return ShadowRunReport((), comparisons)
        routing_duration = round((time.perf_counter() - routing_started) * 1000, 2)

        credential_started = time.perf_counter()
        try:
            context = _build_execution_context(decision, resolver, job_id)
        except Exception:
            context = None
        credential_duration = round((time.perf_counter() - credential_started) * 1000, 2)

        executor = ProviderExecutor(self._execution_registry)
        entries = self._entries(decision)
        for adapter_id, capability, model_id in entries:
            self._run_one(adapter_id, model_id, capability, context, executor, routing_duration, credential_duration, metrics)

        comparisons: list[ComparisonMetric] = []
        comparison_engine = RuntimeComparisonEngine(enabled=comparison_enabled)
        for index, (provider_id, capability, model_id) in enumerate(entries):
            legacy = legacy_metadata[index] if index < len(legacy_metadata) else None
            shadow_state = metrics[index].state if index < len(metrics) else None
            shadow = RuntimeMetadata(provider_id, model_id, capability, decision.routing_version, shadow_state)
            comparisons.append(comparison_engine.compare(legacy, shadow))
        return ShadowRunReport(tuple(metrics), tuple(comparisons))

    def _entries(self, decision: RoutingDecision) -> list[tuple[str, str, str | None]]:
        entries: list[tuple[str, str, str | None]] = [
            (decision.text_provider, "text_generation", decision.text_model),
        ]
        if decision.visual_source == "ai" and decision.image_provider and decision.image_model:
            entries.append((decision.image_provider, "image_generation", decision.image_model))
        return entries

    def _run_one(self, adapter_id: str, model_id: str | None, capability: str, context: ExecutionContext | None, executor: ProviderExecutor, routing_duration: float, credential_duration: float, metrics: list[ShadowMetrics]) -> None:
        try:
            adapter = self._adapters.get(adapter_id)
        except Exception:
            metrics.append(_metric(adapter_id, model_id, capability, "failed", routing_duration, credential_duration, 0, "configuration_error"))
            return

        try:
            capabilities_fn = getattr(adapter, "supports", None)
            if callable(capabilities_fn) and not capabilities_fn(capability):
                metrics.append(_metric(adapter_id, model_id, capability, "failed", routing_duration, credential_duration, 0, "missing_capability"))
                return
        except Exception:
            metrics.append(_metric(adapter_id, model_id, capability, "failed", routing_duration, credential_duration, 0, "configuration_error"))
            return

        parameters = _SHADOW_PARAMETERS.get(capability, {})

        preparation_started = time.perf_counter()
        try:
            actual_context = context or ExecutionContext(
                RoutingDecision(adapter_id, "model", "ai", None, None, "environment", 1),
                (),
                job_id=None,
            )
            prepared = executor.prepare(
                adapter=adapter,
                context=actual_context,
                capability=capability,
                model_id=model_id,
                parameters=parameters,
                request_id=f"shadow-{adapter_id}-{capability}",
            )
        except ProviderExecutionError as exc:
            metrics.append(_metric(adapter_id, model_id, capability, "failed", routing_duration, credential_duration, round((time.perf_counter() - preparation_started) * 1000, 2), _safe_error_category(exc.code)))
            return
        except Exception:
            metrics.append(_metric(adapter_id, model_id, capability, "failed", routing_duration, credential_duration, round((time.perf_counter() - preparation_started) * 1000, 2), "configuration_error"))
            return
        preparation_duration = round((time.perf_counter() - preparation_started) * 1000, 2)

        if not self._enabled:
            metrics.append(_metric(adapter_id, model_id, capability, "ready", routing_duration, credential_duration, preparation_duration))
            return

        execution_started = time.perf_counter()
        try:
            result = asyncio.run(executor.execute(prepared))
        except Exception:
            execution_duration = round((time.perf_counter() - execution_started) * 1000, 2)
            metrics.append(_metric(adapter_id, model_id, capability, "failed", routing_duration, credential_duration, preparation_duration, execution_duration, "execution_error"))
            return
        execution_duration = round((time.perf_counter() - execution_started) * 1000, 2)
        error_code = result.error.code if hasattr(result, "error") and result.error else None
        metrics.append(_metric(adapter_id, model_id, capability, result.state, routing_duration, credential_duration, preparation_duration, execution_duration, _safe_error_category(error_code)))


def _build_execution_context(decision: RoutingDecision, resolver: CredentialResolver, job_id: str | None) -> ExecutionContext:
    strategy = decision.credential_strategy
    provider_ids = [decision.text_provider]
    if decision.visual_source == "ai" and decision.image_provider:
        provider_ids.append(decision.image_provider)
    credentials: list[ResolvedProviderCredential] = []
    for provider_id in provider_ids:
        if any(item.provider_id == provider_id for item in credentials):
            continue
        try:
            credentials.append(resolver.resolve(decision, strategy, provider_id))
        except (CredentialResolutionError, Exception):
            pass
    return ExecutionContext(decision, tuple(credentials), job_id=job_id)


def _build_registry() -> ProviderExecutionRegistry:
    registry = ProviderExecutionRegistry()
    register_gemini_execution(registry)
    register_cloudflare_executions(registry)
    return registry


def _metric(provider_id: str, model_id: str | None, capability: str, state: str, routing_duration: float, credential_duration: float, preparation_duration: float, execution_duration: float | None = None, error_category: str | None = None) -> ShadowMetrics:
    return ShadowMetrics(
        provider_id=provider_id,
        model_id=model_id,
        capability=capability,
        state=state,
        routing_duration_ms=routing_duration,
        credential_duration_ms=credential_duration,
        preparation_duration_ms=preparation_duration,
        execution_duration_ms=execution_duration,
        error_category=error_category,
    )


def _safe_error_category(value: str | None) -> str | None:
    if value is None:
        return None
    return value if value in _SAFE_ERROR_CATEGORIES else "execution_error"
