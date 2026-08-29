from __future__ import annotations

import os
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from kubernetes.client.exceptions import ApiException

from src.tracked_kube_client import TrackedKubeClient

app = FastAPI(title="Kuber payment-controller demo")
NAMESPACE = os.getenv("POD_NAMESPACE", "kuber-demo")


@lru_cache(maxsize=1)
def kube() -> TrackedKubeClient:
    return TrackedKubeClient(NAMESPACE)


def _forbidden(exc: ApiException) -> HTTPException:
    return HTTPException(status_code=exc.status or 500, detail=exc.reason or "Kubernetes API failure")


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
        return {"status": kube().renew_leader_lease("payment-controller")}
    except ApiException as exc:
        raise _forbidden(exc) from exc

