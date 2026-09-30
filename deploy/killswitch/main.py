"""Budget kill-switch Cloud Function (E8-S7, #101 / D034; App Engine target #283).

Neither Cloud Run nor App Engine has a native hard cost cap. This function is the
backstop: a GCP **Billing Budget** publishes to a Pub/Sub topic as spend crosses alert
thresholds; this function receives that message and, once spend reaches a configured
fraction of the budget, **pauses one target**. One source, deployed once per target,
each deployment in the target's own project and triggered by that project's own budget
topic (D071):

- ``cloud_run`` (the API, project ``uspv-api``): sets the service's
  ``max_instance_count = 0`` (Cloud Run then serves nothing and bills nothing).
- ``app_engine`` (the dashboard, project ``uspv-explore``): sets the application's
  serving status to ``USER_DISABLED``, which stops its instances and its serving. Never
  ``max_instances: 0``: App Engine reads zero as "no cap", not as "stop".

The target is **required** and the whole configuration is validated at import, so a
misconfigured deployment fails to start instead of failing at the over-threshold moment.

Deploy and un-pause per target: see ``deploy/killswitch/README.md``.

Env:
- ``KILLSWITCH_TARGET``: ``cloud_run`` or ``app_engine`` (required, no default).
- ``GCP_PROJECT``: the target's project (required).
- ``cloud_run`` only: ``CLOUD_RUN_REGION``, ``CLOUD_RUN_SERVICE`` (required).
- ``app_engine`` only: ``APP_ENGINE_OPERATION_TIMEOUT_S`` (optional, default ``120``;
  keep it below the function's own ``--timeout``; the README's deploy sets 300s).
- ``PAUSE_AT_FRACTION`` (optional, default ``1.0`` = pause at 100% of the budget).
"""

from __future__ import annotations

import base64
import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass

import functions_framework
from cloudevents.http import CloudEvent
from google.cloud import appengine_admin_v1, run_v2

CLOUD_RUN = "cloud_run"
APP_ENGINE = "app_engine"
TARGETS = (CLOUD_RUN, APP_ENGINE)

_REQUIRED_ENV = {
    CLOUD_RUN: ("GCP_PROJECT", "CLOUD_RUN_REGION", "CLOUD_RUN_SERVICE"),
    APP_ENGINE: ("GCP_PROJECT",),
}


@dataclass(frozen=True)
class Config:
    target: str
    project: str
    pause_at: float
    cloud_run_region: str | None = None
    cloud_run_service: str | None = None
    app_engine_timeout_s: float = 120.0


def load_config(env: Mapping[str, str]) -> Config:
    """Validate the deployment's env; raise ``ValueError`` naming what is wrong."""
    target = env.get("KILLSWITCH_TARGET", "")
    if target not in TARGETS:
        raise ValueError(
            f"KILLSWITCH_TARGET must be one of {TARGETS}, got {target!r}"
        )
    missing = [k for k in _REQUIRED_ENV[target] if not env.get(k)]
    if missing:
        raise ValueError(f"target {target!r} requires env {missing}")
    # NaN would make every message pause (``cost < budget * nan`` is always False) and
    # infinity would make none, so both are refused along with non-positive values.
    pause_at = _positive_finite(env, "PAUSE_AT_FRACTION", "1.0")
    return Config(
        target=target,
        project=env["GCP_PROJECT"],
        pause_at=pause_at,
        cloud_run_region=env.get("CLOUD_RUN_REGION"),
        cloud_run_service=env.get("CLOUD_RUN_SERVICE"),
        app_engine_timeout_s=_positive_finite(
            env, "APP_ENGINE_OPERATION_TIMEOUT_S", "120"
        ),
    )


def _positive_finite(env: Mapping[str, str], key: str, default: str) -> float:
    raw = env.get(key, default)
    try:
        value = float(raw)
    except ValueError as e:
        raise ValueError(f"{key} must be a number, got {raw!r}") from e
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{key} must be a finite number > 0, got {value}")
    return value


# At import: a bad config fails the deploy's startup, not the over-threshold moment.
CONFIG = load_config(os.environ)


def pause_cloud_run(config: Config) -> None:
    """Set the Cloud Run service's ``max_instance_count`` to 0 (the API's action)."""
    region, service_id = config.cloud_run_region, config.cloud_run_service
    if not (region and service_id):  # load_config guarantees both; narrow for mypy
        raise ValueError("cloud_run needs CLOUD_RUN_REGION and CLOUD_RUN_SERVICE")
    client = run_v2.ServicesClient()
    name = client.service_path(config.project, region, service_id)
    service = client.get_service(name=name)
    if service.template.scaling.max_instance_count == 0:
        print(f"{service_id} already paused (max_instance_count=0); no-op")
        return
    service.template.scaling.max_instance_count = 0
    client.update_service(service=service)
    print(f"PAUSED {service_id} (max_instance_count=0)")


def pause_app_engine(config: Config) -> None:
    """Disable the App Engine application (serving status ``USER_DISABLED``).

    The ``apps.patch`` reference lists only ``authDomain``, ``defaultCookieExpiration``
    and ``iap`` as updatable. That ``servingStatus`` is accepted too is UNVERIFIED until
    #283's over-threshold probe, whose output is to be recorded there. REST fallback:
    ``PATCH https://appengine.googleapis.com/v1/apps/<project>?updateMask=servingStatus``
    with ``{"servingStatus": "USER_DISABLED"}``.
    """
    disabled = appengine_admin_v1.Application.ServingStatus.USER_DISABLED
    name = f"apps/{config.project}"
    client = appengine_admin_v1.ApplicationsClient()
    app = client.get_application(name=name)
    if app.serving_status == disabled:
        print(f"{name} already USER_DISABLED; no-op")
        return
    operation = client.update_application(
        request={
            "name": name,
            "application": {"serving_status": disabled},
            "update_mask": {"paths": ["serving_status"]},
        }
    )
    # Wait, then re-read the app rather than trusting the operation's response, so the
    # log line below is true. A failure raises and the next budget message retries (the
    # already-disabled check above keeps retries idempotent).
    operation.result(timeout=config.app_engine_timeout_s)
    status = client.get_application(name=name).serving_status
    if status != disabled:
        raise RuntimeError(f"{name} update finished with serving_status={status!r}")
    print(f"DISABLED {name} (serving_status=USER_DISABLED)")


_ACTIONS = {CLOUD_RUN: pause_cloud_run, APP_ENGINE: pause_app_engine}


@functions_framework.cloud_event
def budget_killswitch(cloud_event: CloudEvent) -> None:
    """Pause the configured target when billing spend crosses the threshold."""
    payload = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))
    cost = float(payload.get("costAmount", 0))
    budget = float(payload.get("budgetAmount", 0))

    if budget <= 0:
        # A budget set to "last period's spend" reads $0 on a new project: never pauses.
        print(
            f"MISCONFIGURED: budgetAmount={budget} (expected a specified amount > 0); "
            "no-op"
        )
        return
    if cost < budget * CONFIG.pause_at:
        print(
            f"under threshold: cost={cost} budget={budget} frac={CONFIG.pause_at} "
            f"target={CONFIG.target}; no-op"
        )
        return

    print(f"over threshold: cost={cost} >= {CONFIG.pause_at:.0%} of budget={budget}")
    _ACTIONS[CONFIG.target](CONFIG)
