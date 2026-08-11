import pytest

from app.config import Settings
from app.services.ai.cloudflare_execution import CloudflareResponse
from app.services.ai.gemini_execution import GeminiResponse, register_gemini_execution
from app.services.ai.provider_executor import ProviderExecutionRegistry, ExecutionOutput
from app.services.ai.runtime_comparison import RuntimeMetadata
from app.services.ai.shadow_execution import ShadowExecutionRunner, ShadowMetrics


def _settings(**overrides):
    kwargs = dict(
        n8n_base_url="http://localhost:5678",
        n8n_api_key="n8n-key",
        supabase_url="http://localhost:8000",
        supabase_service_role_key="supabase-key",
        data_dir="/tmp",
        gemini_api_key="test-gemini-key",
        gemini_text_model="gemini-2.5-flash",
        gemini_image_enabled=False,
        gemini_image_model="",
        cloudflare_ai_token="test-cf-token",
        cloudflare_account_id="test-cf-account",
    )
    kwargs.update(overrides)
    return Settings(**kwargs)


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeDatabase:
    def __init__(self, rows=None):
        self.rows = rows or {}

    def get_credential_for_test(self, provider_id: str):
        return self.rows.get(provider_id)


def _gemini_registry(response):
    transport = FakeTransport(response)
    registry = ProviderExecutionRegistry()
    register_gemini_execution(registry, transport=transport)
    return registry


class TestShadowDisabled:
    def test_disabled_never_invokes_registered_handler(self):
        calls = []

        async def handler(request):
            calls.append(request)
            return ExecutionOutput(
                provider_id="gemini",
                model_id=request.model_id,
                capability="text_generation",
                text="must not be returned",
            )

        registry = ProviderExecutionRegistry()
        registry.register("gemini", "text_generation", handler)
        runner = ShadowExecutionRunner(_settings(shadow_provider_execution=False), execution_registry=registry)

        runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        assert calls == []

    def test_does_not_execute_providers(self):
        settings = _settings(shadow_provider_execution=False)
        runner = ShadowExecutionRunner(settings)

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        for metric in metrics:
            assert metric.execution_duration_ms is None
            assert metric.state in ("ready", "failed")

    def test_routing_failure_returns_empty(self):
        settings = _settings(shadow_provider_execution=False)
        runner = ShadowExecutionRunner(settings)

        metrics = runner.run(
            text_provider=None,
            text_model=None,
            database=None,
            encryption=None,
        )

        assert metrics == ()

    def test_metrics_never_contain_credentials(self):
        settings = _settings(shadow_provider_execution=False)
        runner = ShadowExecutionRunner(settings)

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        for metric in metrics:
            text = repr(metric)
            assert "test-gemini-key" not in text
            assert "supabase-key" not in text
            assert "n8n-key" not in text

    def test_metrics_contain_only_allowed_fields(self):
        settings = _settings(shadow_provider_execution=False)
        runner = ShadowExecutionRunner(settings)

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        for metric in metrics:
            assert metric.provider_id
            assert metric.model_id
            assert metric.capability
            assert metric.state
            assert metric.routing_duration_ms > 0
            assert metric.credential_duration_ms >= 0
            assert metric.preparation_duration_ms >= 0

    def test_ai_visual_source_produces_two_entries(self):
        settings = _settings(shadow_provider_execution=False)
        runner = ShadowExecutionRunner(settings)

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        assert len(metrics) == 2
        assert {m.provider_id for m in metrics} == {"gemini", "cloudflare"}

    def test_unimplemented_pexels_routing_is_isolated(self):
        settings = _settings(shadow_provider_execution=True)
        runner = ShadowExecutionRunner(settings)

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            visual_source="pexels",
            database=FakeDatabase(),
            encryption=None,
        )

        assert metrics == ()


class TestShadowEnabled:
    def test_runs_execution_with_completed_state(self):
        settings = _settings(shadow_provider_execution=True)
        response = GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "shadow output"}]}}]})
        runner = ShadowExecutionRunner(settings, execution_registry=_gemini_registry(response))

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        text_metrics = [metric for metric in metrics if metric.capability == "text_generation"]
        assert len(text_metrics) == 1
        assert text_metrics[0].state == "completed"
        assert text_metrics[0].execution_duration_ms is not None
        assert text_metrics[0].error_category is None

    def test_execution_failure_is_isolated(self):
        settings = _settings(shadow_provider_execution=True)
        response = GeminiResponse(401, {"error": {}})
        runner = ShadowExecutionRunner(settings, execution_registry=_gemini_registry(response))

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        text_metrics = [metric for metric in metrics if metric.capability == "text_generation"]
        assert len(text_metrics) == 1
        assert text_metrics[0].state == "failed"

    def test_timeout_is_isolated(self):
        class TimedOutTransport:
            async def generate(self, **kwargs):
                raise TimeoutError("timeout")

        settings = _settings(shadow_provider_execution=True)
        registry = ProviderExecutionRegistry()
        register_gemini_execution(registry, transport=TimedOutTransport())
        runner = ShadowExecutionRunner(settings, execution_registry=registry)

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        assert isinstance(metrics, tuple)
        assert any(metric.capability == "text_generation" for metric in metrics)

    def test_metrics_never_leak_content(self):
        settings = _settings(shadow_provider_execution=True)
        response = GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "never-shown"}]}}]})
        runner = ShadowExecutionRunner(settings, execution_registry=_gemini_registry(response))

        metrics = runner.run(
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        for metric in metrics:
            text = repr(metric)
            assert "test-gemini-key" not in text
            assert "never-shown" not in text


class TestFeatureFlag:
    def test_comparison_defaults_to_enabled(self, monkeypatch):
        monkeypatch.delenv("SHADOW_RUNTIME_COMPARISON", raising=False)
        assert Settings.from_env().shadow_runtime_comparison is True

    def test_comparison_can_be_disabled_from_env(self, monkeypatch):
        monkeypatch.setenv("SHADOW_RUNTIME_COMPARISON", "false")
        assert Settings.from_env().shadow_runtime_comparison is False

    def test_runtime_comparison_matches_persisted_routing(self):
        runner = ShadowExecutionRunner(_settings(shadow_provider_execution=False, shadow_runtime_comparison=True))
        report = runner.run_with_comparison(
            legacy_metadata=(
                RuntimeMetadata("gemini", "gemini-2.5-flash", "text_generation", 1, None),
                RuntimeMetadata("cloudflare", "@cf/black-forest-labs/flux-1-schnell", "image_generation", 1, None),
            ),
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        assert [item.outcome for item in report.comparisons] == ["match", "match"]
        assert report.metrics[0].execution_duration_ms is None

    def test_runtime_comparison_disabled_is_skipped(self):
        runner = ShadowExecutionRunner(_settings(shadow_provider_execution=False, shadow_runtime_comparison=False))
        report = runner.run_with_comparison(
            legacy_metadata=(RuntimeMetadata("gemini", "gemini-2.5-flash", "text_generation", 1, None),),
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        assert report.comparisons[0].outcome == "skipped"
        assert report.comparisons[0].mismatch_category == "comparison_disabled"

    def test_runtime_comparison_detects_provider_mismatch(self):
        runner = ShadowExecutionRunner(_settings(shadow_provider_execution=False, shadow_runtime_comparison=True))
        report = runner.run_with_comparison(
            legacy_metadata=(RuntimeMetadata("cloudflare", "gemini-2.5-flash", "text_generation", 1, None),),
            text_provider="gemini",
            text_model="gemini-2.5-flash",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            visual_source="ai",
            database=FakeDatabase(),
            encryption=None,
        )

        assert report.comparisons[0].outcome == "mismatch"
        assert report.comparisons[0].mismatch_category == "provider"

    def test_default_is_disabled(self):
        settings = _settings()
        assert settings.shadow_provider_execution is False

    def test_from_env_respected(self, monkeypatch):
        monkeypatch.setenv("SHADOW_PROVIDER_EXECUTION", "true")
        actual = Settings.from_env()
        assert actual.shadow_provider_execution is True

    def test_from_env_defaults_to_false(self, monkeypatch):
        monkeypatch.delenv("SHADOW_PROVIDER_EXECUTION", raising=False)
        actual = Settings.from_env()
        assert actual.shadow_provider_execution is False

    def test_shadow_exception_does_not_change_create_response(self, tmp_path):
        from fastapi.testclient import TestClient
        from app.main import create_app

        class FakeDb:
            def __init__(self):
                self.rows = []

            def insert_job(self, job):
                self.rows.append(dict(job))
                return dict(job)

        app = create_app(database_client=FakeDb(), data_dir=tmp_path)
        app.state.shadow_runner.run_with_comparison = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("shadow failed"))

        response = TestClient(app).post("/api/videos", json={
            "prompt": "test",
            "duration": "30",
            "style": "cinematic",
            "voice": "default",
            "captions": "off",
        })

        assert response.status_code == 202
        assert response.json()["status"] == "queued"


class TestPostApiIntegration:
    def test_create_video_unchanged_with_shadow_disabled(self, tmp_path):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.clients import WorkflowClient

        class FakeSimpleDb:
            def __init__(self):
                self.rows = []

            def insert_job(self, job):
                job["id"] = job.get("id", "dummy-id")
                self.rows.append(dict(job))
                return dict(job)

            def get_job(self, job_id):
                return next((r for r in self.rows if str(r.get("id")) == str(job_id)), None)

            def list_jobs(self):
                return self.rows

            def get_credential_for_test(self, provider_id):
                return None

        database = FakeSimpleDb()
        import os
        os.environ["SHADOW_PROVIDER_EXECUTION"] = "false"
        client = TestClient(create_app(database_client=database, data_dir=tmp_path))
        os.environ.pop("SHADOW_PROVIDER_EXECUTION", None)

        response = client.post("/api/videos", json={
            "title": "Shadow Test",
            "prompt": "test",
            "duration": "30",
            "style": "cinematic",
            "voice": "default",
            "captions": "off",
        })

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert body["id"]
        assert "shadow" not in str(body).lower()
        assert "metric" not in str(body).lower()
