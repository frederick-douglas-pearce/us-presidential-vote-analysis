"""The budget kill-switch (`deploy/killswitch/main.py`) pauses one target per deployment:
Cloud Run for the API, App Engine for the dashboard (#283 / D071).

Its Cloud Function deps are installed by Cloud Functions at deploy time and are not in
`uv.lock`, so these tests load the module by path against **strict hand-written fakes** of
`functions_framework`, `cloudevents.http`, `google.cloud.run_v2` and
`google.cloud.appengine_admin_v1`. Not `MagicMock`: it would accept any call shape,
including a wrong one. Each fake exposes exactly the methods the function uses, with
signatures narrower than the real clients' (checked against google-cloud-appengine-admin
1.18.0 and google-cloud-run 0.16.1): keyword-only where the real ones also accept
positionals, and without the optional parameters the function does not pass. So an
unexpected argument is a `TypeError`.

The tests pin the **mechanism**: which client is constructed, which call it makes, and the
exact request it sends. Whether the real service accepts that request is a question for
#283's live probes (`docs/deploy-dashboard.md` §6), not for this file.
"""

from __future__ import annotations

import base64
import enum
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_MAIN = _REPO / "deploy" / "killswitch" / "main.py"

API_ENV = {
    "KILLSWITCH_TARGET": "cloud_run",
    "GCP_PROJECT": "uspv-api",
    "CLOUD_RUN_REGION": "us-west1",
    "CLOUD_RUN_SERVICE": "usvote-api",
}
DASHBOARD_ENV = {"KILLSWITCH_TARGET": "app_engine", "GCP_PROJECT": "uspv-explore"}
ALL_KEYS = (
    *API_ENV,
    "PAUSE_AT_FRACTION",
    "APP_ENGINE_OPERATION_TIMEOUT_S",
)


class ServingStatus(enum.IntEnum):
    """Mirrors `appengine_admin_v1.Application.ServingStatus`."""

    UNSPECIFIED = 0
    SERVING = 1
    USER_DISABLED = 2
    SYSTEM_DISABLED = 3


@dataclass
class Calls:
    """What the fakes observed, and what they are primed to return."""

    run_clients: int = 0
    appengine_clients: int = 0
    run_log: list[tuple[str, Any]] = field(default_factory=list)
    appengine_log: list[tuple[str, Any]] = field(default_factory=list)
    service_max_instances: int = 1
    # What `get_application` reports; the operation's `result()` moves it to
    # `status_after_update`, so a re-read after the wait sees the server's new state.
    app_status: ServingStatus = ServingStatus.SERVING
    status_after_update: ServingStatus = ServingStatus.USER_DISABLED


def _fake_modules(calls: Calls) -> dict[str, ModuleType]:
    class ServicesClient:
        def __init__(self) -> None:
            calls.run_clients += 1

        def service_path(self, project: str, location: str, service: str) -> str:
            return f"projects/{project}/locations/{location}/services/{service}"

        def get_service(self, *, name: str) -> SimpleNamespace:
            calls.run_log.append(("get_service", name))
            scaling = SimpleNamespace(max_instance_count=calls.service_max_instances)
            return SimpleNamespace(name=name, template=SimpleNamespace(scaling=scaling))

        def update_service(self, *, service: SimpleNamespace) -> None:
            calls.run_log.append(("update_service", service))

    class Operation:
        def result(self, *, timeout: float) -> SimpleNamespace:
            calls.appengine_log.append(("result", timeout))
            calls.app_status = calls.status_after_update
            # A response that omits the field, as the real one may; the function must
            # re-read the app rather than trust this.
            return SimpleNamespace(serving_status=ServingStatus.UNSPECIFIED)

    class ApplicationsClient:
        def __init__(self) -> None:
            calls.appengine_clients += 1

        def get_application(self, *, name: str) -> SimpleNamespace:
            calls.appengine_log.append(("get_application", name))
            return SimpleNamespace(name=name, serving_status=calls.app_status)

        def update_application(self, *, request: dict[str, Any]) -> Operation:
            calls.appengine_log.append(("update_application", request))
            return Operation()

    run_v2 = ModuleType("google.cloud.run_v2")
    run_v2.ServicesClient = ServicesClient  # type: ignore[attr-defined]
    appengine = ModuleType("google.cloud.appengine_admin_v1")
    appengine.ApplicationsClient = ApplicationsClient  # type: ignore[attr-defined]
    appengine.Application = SimpleNamespace(ServingStatus=ServingStatus)  # type: ignore[attr-defined]
    google = ModuleType("google")
    cloud = ModuleType("google.cloud")
    google.cloud = cloud  # type: ignore[attr-defined]
    cloud.run_v2 = run_v2  # type: ignore[attr-defined]
    cloud.appengine_admin_v1 = appengine  # type: ignore[attr-defined]
    framework = ModuleType("functions_framework")
    framework.cloud_event = lambda fn: fn  # type: ignore[attr-defined]
    cloudevents = ModuleType("cloudevents")
    http = ModuleType("cloudevents.http")
    http.CloudEvent = object  # type: ignore[attr-defined]
    cloudevents.http = http  # type: ignore[attr-defined]
    return {
        "google": google,
        "google.cloud": cloud,
        "google.cloud.run_v2": run_v2,
        "google.cloud.appengine_admin_v1": appengine,
        "functions_framework": framework,
        "cloudevents": cloudevents,
        "cloudevents.http": http,
    }


@pytest.fixture
def calls() -> Calls:
    return Calls()


@pytest.fixture
def load(monkeypatch: pytest.MonkeyPatch, calls: Calls) -> Any:
    """Return a loader: set the env, install the fakes, import `main.py` by path."""

    def _load(env: dict[str, str]) -> ModuleType:
        for key in ALL_KEYS:
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        for name, module in _fake_modules(calls).items():
            monkeypatch.setitem(sys.modules, name, module)
        spec = importlib.util.spec_from_file_location("killswitch_main", _MAIN)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolves the module through sys.modules while decorating.
        monkeypatch.setitem(sys.modules, "killswitch_main", module)
        spec.loader.exec_module(module)
        return module

    return _load


def _event(cost: float, budget: float) -> SimpleNamespace:
    data = base64.b64encode(
        json.dumps({"costAmount": cost, "budgetAmount": budget}).encode()
    )
    return SimpleNamespace(data={"message": {"data": data}})


class TestConfig:
    """The target is required and the config is validated at import, so a bad
    deployment fails to start rather than at the over-threshold moment."""

    def test_a_missing_target_fails_the_import(self, load: Any) -> None:
        env = {k: v for k, v in API_ENV.items() if k != "KILLSWITCH_TARGET"}
        with pytest.raises(ValueError, match="KILLSWITCH_TARGET"):
            load(env)

    def test_an_unknown_target_fails_the_import(self, load: Any) -> None:
        with pytest.raises(ValueError, match="KILLSWITCH_TARGET"):
            load({**DASHBOARD_ENV, "KILLSWITCH_TARGET": "app-engine"})

    @pytest.mark.parametrize("key", ["CLOUD_RUN_REGION", "CLOUD_RUN_SERVICE", "GCP_PROJECT"])
    def test_cloud_run_needs_its_env(self, load: Any, key: str) -> None:
        env = {k: v for k, v in API_ENV.items() if k != key}
        with pytest.raises(ValueError, match=key):
            load(env)

    def test_app_engine_needs_its_project(self, load: Any) -> None:
        with pytest.raises(ValueError, match="GCP_PROJECT"):
            load({"KILLSWITCH_TARGET": "app_engine"})

    @pytest.mark.parametrize("value", ["0", "-0.5", "nan", "inf", "abc", ""])
    def test_a_fraction_that_is_not_positive_and_finite_fails_the_import(
        self, load: Any, value: str
    ) -> None:
        # nan would pause on every message (`cost < budget * nan` is always False).
        with pytest.raises(ValueError, match="PAUSE_AT_FRACTION"):
            load({**DASHBOARD_ENV, "PAUSE_AT_FRACTION": value})

    @pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "abc", ""])
    def test_an_operation_timeout_that_is_not_positive_and_finite_fails_the_import(
        self, load: Any, value: str
    ) -> None:
        with pytest.raises(ValueError, match="APP_ENGINE_OPERATION_TIMEOUT_S"):
            load({**DASHBOARD_ENV, "APP_ENGINE_OPERATION_TIMEOUT_S": value})


class TestNoPause:
    @pytest.mark.parametrize("env", [API_ENV, DASHBOARD_ENV], ids=["api", "dashboard"])
    def test_below_threshold_constructs_no_client_and_says_so(
        self, load: Any, calls: Calls, env: dict[str, str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        load(env).budget_killswitch(_event(cost=4.99, budget=5))
        assert (calls.run_clients, calls.appengine_clients) == (0, 0)
        # The below-threshold probes (docs/deploy-dashboard.md §6 probe 1,
        # docs/deploy-cloud-run.md §9) key on this line; §9 keys on the target token too,
        # to tell a post-#283 revision of the API function from the one it replaced.
        out = capsys.readouterr().out
        assert "under threshold" in out
        assert f"target={env['KILLSWITCH_TARGET']}" in out

    @pytest.mark.parametrize("env", [API_ENV, DASHBOARD_ENV], ids=["api", "dashboard"])
    def test_a_zero_budget_is_reported_and_constructs_no_client(
        self, load: Any, calls: Calls, env: dict[str, str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        load(env).budget_killswitch(_event(cost=100, budget=0))
        assert (calls.run_clients, calls.appengine_clients) == (0, 0)
        assert "MISCONFIGURED" in capsys.readouterr().out

    def test_the_fraction_moves_the_threshold(self, load: Any, calls: Calls) -> None:
        main = load({**DASHBOARD_ENV, "PAUSE_AT_FRACTION": "0.8"})
        main.budget_killswitch(_event(cost=3.99, budget=5))
        assert calls.appengine_clients == 0
        main.budget_killswitch(_event(cost=4.0, budget=5))
        assert calls.appengine_clients == 1


class TestAppEngine:
    """The dashboard's action is to disable the application, never `max_instances: 0`
    (App Engine reads zero as "no cap")."""

    def test_disables_the_app_with_exactly_this_request(
        self, load: Any, calls: Calls, capsys: pytest.CaptureFixture[str]
    ) -> None:
        load({**DASHBOARD_ENV, "APP_ENGINE_OPERATION_TIMEOUT_S": "45"}).budget_killswitch(
            _event(cost=5, budget=5)
        )
        assert calls.appengine_clients == 1
        assert calls.run_clients == 0
        assert calls.appengine_log == [
            ("get_application", "apps/uspv-explore"),
            (
                "update_application",
                {
                    "name": "apps/uspv-explore",
                    "application": {"serving_status": ServingStatus.USER_DISABLED},
                    "update_mask": {"paths": ["serving_status"]},
                },
            ),
            ("result", 45.0),
            # Re-read after the wait: the response is not trusted.
            ("get_application", "apps/uspv-explore"),
        ]
        assert "DISABLED apps/uspv-explore" in capsys.readouterr().out

    def test_an_already_disabled_app_is_not_updated(
        self, load: Any, calls: Calls
    ) -> None:
        calls.app_status = ServingStatus.USER_DISABLED
        load(DASHBOARD_ENV).budget_killswitch(_event(cost=9, budget=5))
        assert calls.appengine_log == [("get_application", "apps/uspv-explore")]

    def test_an_update_that_does_not_disable_raises_and_never_claims_it_did(
        self, load: Any, calls: Calls, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls.status_after_update = ServingStatus.SERVING
        with pytest.raises(RuntimeError, match="serving_status"):
            load(DASHBOARD_ENV).budget_killswitch(_event(cost=5, budget=5))
        assert "DISABLED apps/" not in capsys.readouterr().out


class TestCloudRun:
    """The API's action is unchanged: `max_instance_count = 0` on the service."""

    def test_pauses_the_service(self, load: Any, calls: Calls) -> None:
        load(API_ENV).budget_killswitch(_event(cost=5, budget=5))
        assert calls.run_clients == 1
        assert calls.appengine_clients == 0
        name = "projects/uspv-api/locations/us-west1/services/usvote-api"
        assert [entry[0] for entry in calls.run_log] == ["get_service", "update_service"]
        assert calls.run_log[0][1] == name
        updated = calls.run_log[1][1]
        assert updated.name == name
        assert updated.template.scaling.max_instance_count == 0

    def test_an_already_paused_service_is_not_updated(
        self, load: Any, calls: Calls
    ) -> None:
        calls.service_max_instances = 0
        load(API_ENV).budget_killswitch(_event(cost=9, budget=5))
        assert [entry[0] for entry in calls.run_log] == ["get_service"]
