from __future__ import annotations

import os
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from kubernetes.client.exceptions import ApiException

from reference_workload.tracked_kube_client import TrackedKubeClient

app = FastAPI(title="Kuber reference workload")
NAMESPACE = os.getenv("POD_NAMESPACE", "kuber-sandbox")
SERVICE_ID = os.getenv("SERVICE_ID", "payment-service")


@lru_cache(maxsize=1)
def kube() -> TrackedKubeClient:
    return TrackedKubeClient(NAMESPACE, SERVICE_ID)


def _forbidden(exc: ApiException) -> HTTPException:
    return HTTPException(
        status_code=exc.status or 500, detail=exc.reason or "Kubernetes API failure"
    )


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def config() -> dict[str, object]:
    try:
        return {"data": kube().read_config_map("app-config")}
    except ApiException as exc:
        raise _forbidden(exc) from exc


@app.get("/secret")
def secret() -> dict[str, object]:
    try:
        return {"keys": sorted(kube().read_secret("payment-secret"))}
    except ApiException as exc:
        raise _forbidden(exc) from exc


@app.get("/pods")
def pods() -> dict[str, object]:
    try:
        return {"pods": kube().list_pods()}
    except ApiException as exc:
        raise _forbidden(exc) from exc


@app.post("/reconcile/{name}")
def reconcile(name: str) -> dict[str, str | None]:
    try:
        kube().create_job(name)
        found = kube().get_job(name)
        kube().delete_job(name)
        return {"job": found, "status": "reconciled"}
    except ApiException as exc:
        raise _forbidden(exc) from exc


@app.post("/leader-election")
def leader_election() -> dict[str, str]:
    try:
        return {"status": kube().renew_leader_lease("kuber-reference-leader")}
    except ApiException as exc:
        raise _forbidden(exc) from exc


@app.get("/profile")
def profile() -> dict[str, object]:
    """Exercise the normal Kubernetes behavior declared for this service."""

    try:
        if SERVICE_ID == "api-gateway":
            return {"service": SERVICE_ID, "config": kube().read_config_map("app-config")}
        if SERVICE_ID == "auth-service":
            return {
                "service": SERVICE_ID,
                "config": kube().read_config_map("app-config"),
                "secret_keys": sorted(kube().read_secret("auth-secret")),
            }
        if SERVICE_ID == "order-service":
            return {"service": SERVICE_ID, "config": kube().read_config_map("app-config")}
        if SERVICE_ID == "payment-service":
            return {
                "service": SERVICE_ID,
                "config": kube().read_config_map("app-config"),
                "secret_keys": sorted(kube().read_secret("payment-secret")),
                "pods": kube().list_pods(),
            }
        if SERVICE_ID == "worker-service":
            return {"service": SERVICE_ID, "config": kube().read_config_map("app-config")}
        raise HTTPException(status_code=500, detail=f"unknown SERVICE_ID {SERVICE_ID}")
    except ApiException as exc:
        raise _forbidden(exc) from exc


@app.post("/rare-workflow")
def rare_workflow() -> dict[str, str | None]:
    """Owner-declared worker path intentionally absent from warmup evidence."""

    if SERVICE_ID != "worker-service":
        raise HTTPException(status_code=404, detail="rare workflow belongs to worker-service")
    return reconcile("kuber-worker-smoke")
