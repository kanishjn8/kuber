from __future__ import annotations

import socket
import subprocess
from contextlib import AbstractContextManager
from time import monotonic, sleep


class SandboxPortForwards(AbstractContextManager["SandboxPortForwards"]):
    """Own host access to Kafka and Redis during a reference-sandbox run."""

    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[str]] = []

    def __enter__(self) -> SandboxPortForwards:
        self.processes = [
            self._start("service/kafka", "19092:29092"),
            self._start("service/redis", "16379:6379"),
        ]
        self._wait_for_port(19092)
        self._wait_for_port(16379)
        return self

    def __exit__(self, *_: object) -> None:
        for process in self.processes:
            process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self.processes = []

    @staticmethod
    def _start(resource: str, mapping: str) -> subprocess.Popen[str]:
        return subprocess.Popen(
            (
                "kubectl",
                "--context",
                "kind-kuber",
                "-n",
                "kuber-sandbox",
                "port-forward",
                resource,
                mapping,
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _wait_for_port(self, port: int) -> None:
        deadline = monotonic() + 20
        while monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    return
            except OSError:
                if any(process.poll() is not None for process in self.processes):
                    errors = "\n".join(
                        process.stderr.read() for process in self.processes if process.stderr
                    )
                    raise RuntimeError(
                        f"sandbox port-forward stopped unexpectedly: {errors.strip()}"
                    ) from None
                sleep(0.2)
        raise TimeoutError(f"timed out waiting for sandbox port {port}")
