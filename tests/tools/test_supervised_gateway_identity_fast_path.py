"""Owns-lock fast path for supervised-gateway identity (HAB-1416 / #111922).

``_is_supervised_gateway_process`` used to always call ``get_running_pid``, which
ends in macOS ``psutil create_time`` and could wedge the terminal pre-exec guard
for the full command deadline. When this process already holds the gateway
runtime lock it is the gateway — no kernel process query required.
"""

from __future__ import annotations

import os

import pytest

import tools.process_registry as process_registry


@pytest.fixture
def gateway_env(monkeypatch):
    monkeypatch.setenv("_HERMES_GATEWAY", "1")
    monkeypatch.setenv("HERMES_SUPERVISED_CHILD", "1")


def test_owns_lock_skips_get_running_pid(monkeypatch, gateway_env):
    """Holding the runtime lock is enough; get_running_pid must not be touched."""
    calls: list[str] = []

    monkeypatch.setattr(
        "gateway.restart.is_supervised_gateway_launch",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "gateway.status.owns_gateway_runtime_lock",
        lambda: True,
    )

    def _boom(*_a, **_k):
        calls.append("get_running_pid")
        raise AssertionError("get_running_pid must not run on the owns-lock fast path")

    monkeypatch.setattr("gateway.status.get_running_pid", _boom)

    assert process_registry._is_supervised_gateway_process() is True
    assert calls == []


def test_no_lock_falls_back_to_pid_match(monkeypatch, gateway_env):
    """Without lock ownership, still require live PID ownership."""
    monkeypatch.setattr(
        "gateway.restart.is_supervised_gateway_launch",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "gateway.status.owns_gateway_runtime_lock",
        lambda: False,
    )
    monkeypatch.setattr(
        "gateway.status.get_running_pid",
        lambda *a, **k: os.getpid(),
    )
    assert process_registry._is_supervised_gateway_process() is True

    monkeypatch.setattr(
        "gateway.status.get_running_pid",
        lambda *a, **k: os.getpid() + 1,
    )
    assert process_registry._is_supervised_gateway_process() is False


def test_unsupervised_marker_is_false_even_with_lock(monkeypatch):
    """Inherited _HERMES_GATEWAY alone is not enough without a supervised launch."""
    monkeypatch.setenv("_HERMES_GATEWAY", "1")
    monkeypatch.delenv("HERMES_SUPERVISED_CHILD", raising=False)
    monkeypatch.setattr(
        "gateway.restart.is_supervised_gateway_launch",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "gateway.status.owns_gateway_runtime_lock",
        lambda: True,
    )
    assert process_registry._is_supervised_gateway_process() is False


def test_no_gateway_env_short_circuits(monkeypatch):
    monkeypatch.delenv("_HERMES_GATEWAY", raising=False)
    assert process_registry._is_supervised_gateway_process() is False
