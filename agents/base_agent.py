"""
base_agent.py — Abstract base class for all three trading agents.

Lifecycle:
  start() → runs two asyncio tasks:
    1. _heartbeat_loop(): updates agent_state every HEARTBEAT_INTERVAL seconds
    2. _run_loop():       calls run_cycle() repeatedly until stopped

Subclasses implement:
  async def run_cycle(self) -> None  — one unit of work per iteration
  async def on_start(self)           — called once before the run loop
  async def on_stop(self)            — called once after the run loop

Control:
  pause() / resume() — gate the run loop without killing the process
  stop()             — graceful shutdown (sets _stop_event)

Metrics collected automatically:
  - cycle_count, error_count, last_cycle_ms, uptime_seconds
  - Subclasses add domain-specific keys via update_metrics()
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import psutil

from .message_bus import (
    poll, publish,
    CH_SYSTEM, EV_AGENT_PAUSE, EV_AGENT_RESUME, EV_AGENT_STOP,
)
from .shared_db import (
    connect, get_db_path, init_schema,
    upsert_agent_state, get_all_agent_states,
)

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 10.0    # seconds between DB heartbeat writes
CONTROL_POLL_INTERVAL = 5.0  # seconds between control-plane polls
CLEANUP_INTERVAL = 300.0     # seconds between event bus cleanups


class BaseAgent(ABC):
    """
    Abstract base for Agent1, Agent2, Agent3.

    Args:
        agent_id:  "agent1" | "agent2" | "agent3"
        cfg:       full config.yaml dict
        db_path:   override for agents.db location
    """

    def __init__(
        self,
        agent_id: str,
        cfg: dict,
        *,
        db_path: Path | str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.cfg = cfg
        self.db_path = Path(db_path) if db_path else get_db_path(cfg)

        self._status: str = "stopped"
        self._current_task: str = ""
        self._metrics: dict[str, Any] = {
            "cycle_count": 0,
            "error_count": 0,
            "last_cycle_ms": 0.0,
            "uptime_seconds": 0.0,
        }
        self._uptime_start: float = 0.0
        self._stop_event = asyncio.Event()
        self._paused = False
        self._control_hwm: float = 0.0   # high-water mark for control channel

        # Subclasses use this to track their own channel high-water marks
        self._hwm: dict[str, float] = {}

        self.log = logging.getLogger(f"agent.{agent_id}")

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    async def run_cycle(self) -> None:
        """One unit of agent work. Called repeatedly by the run loop."""

    async def on_start(self) -> None:
        """Called once after the DB is initialised, before the run loop."""

    async def on_stop(self) -> None:
        """Called once after the run loop exits."""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialise and run until stopped."""
        init_schema(self.db_path)
        self._uptime_start = time.time()
        self._stop_event.clear()
        self._paused = False
        self._status = "running"
        self._control_hwm = time.time() - 1.0

        await self._set_db_state("running", "starting up")
        self.log.info("Agent %s starting", self.agent_id)

        try:
            await self.on_start()
        except Exception:
            self.log.exception("on_start() failed")
            self._status = "error"
            await self._set_db_state("error", "on_start failed")
            return

        # Install SIGTERM handler for graceful systemd stop
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        await asyncio.gather(
            self._run_loop(),
            self._heartbeat_loop(),
            self._control_loop(),
        )

        try:
            await self.on_stop()
        except Exception:
            self.log.exception("on_stop() failed")

        self._status = "stopped"
        await self._set_db_state("stopped", "")
        self.log.info("Agent %s stopped", self.agent_id)

    async def stop(self) -> None:
        self.log.info("Agent %s stop requested", self.agent_id)
        self._status = "stopping"
        self._stop_event.set()

    async def pause(self) -> None:
        self._paused = True
        self._status = "paused"
        self._current_task = "paused"
        await self._set_db_state("paused", "paused")
        self.log.info("Agent %s paused", self.agent_id)

    async def resume(self) -> None:
        self._paused = False
        self._status = "running"
        await self._set_db_state("running", "resumed")
        self.log.info("Agent %s resumed", self.agent_id)

    # ── Internal loops ────────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        last_cleanup = time.time()
        while not self._stop_event.is_set():
            if self._paused:
                await asyncio.sleep(1.0)
                continue
            t0 = time.time()
            try:
                await self.run_cycle()
                self._metrics["cycle_count"] = self._metrics.get("cycle_count", 0) + 1
            except asyncio.CancelledError:
                break
            except Exception:
                self._metrics["error_count"] = self._metrics.get("error_count", 0) + 1
                self.log.exception("Unhandled error in run_cycle()")
                await asyncio.sleep(5.0)  # back-off on repeated errors
            finally:
                elapsed = (time.time() - t0) * 1000
                self._metrics["last_cycle_ms"] = round(elapsed, 1)

            # Periodic cleanup of expired events
            if time.time() - last_cleanup > CLEANUP_INTERVAL:
                try:
                    from .message_bus import cleanup_expired
                    cleanup_expired(db_path=self.db_path)
                    last_cleanup = time.time()
                except Exception:
                    pass

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            self._metrics["uptime_seconds"] = round(time.time() - self._uptime_start, 0)
            # Add system resource usage
            try:
                proc = psutil.Process(os.getpid())
                self._metrics["cpu_pct"]    = proc.cpu_percent(interval=None)
                self._metrics["mem_mb"]     = round(proc.memory_info().rss / 1_048_576, 1)
            except Exception:
                pass
            with connect(self.db_path) as conn:
                upsert_agent_state(
                    conn,
                    self.agent_id,
                    status=self._status,
                    current_task=self._current_task,
                    metrics=self._metrics,
                    uptime_start=self._uptime_start,
                )
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _control_loop(self) -> None:
        """Listen for system control commands (pause/resume/stop)."""
        while not self._stop_event.is_set():
            try:
                events = poll(
                    [CH_SYSTEM],
                    self._control_hwm,
                    db_path=self.db_path,
                    limit=10,
                )
                for ev in events:
                    payload = ev["payload"]
                    target  = payload.get("target_agent")
                    if target and target != self.agent_id and target != "all":
                        continue
                    etype = ev["event_type"]
                    if etype == EV_AGENT_STOP:
                        await self.stop()
                    elif etype == EV_AGENT_PAUSE:
                        await self.pause()
                    elif etype == EV_AGENT_RESUME:
                        await self.resume()
                    self._control_hwm = max(self._control_hwm, ev["published_at"])
            except Exception:
                pass
            await asyncio.sleep(CONTROL_POLL_INTERVAL)

    # ── Helpers for subclasses ────────────────────────────────────────────────

    def set_task(self, task: str) -> None:
        """Update the current-task string visible in the API / iOS app."""
        self._current_task = task

    def update_metrics(self, updates: dict[str, Any]) -> None:
        self._metrics.update(updates)

    def publish(
        self,
        channel: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int = 3600,
    ) -> str:
        return publish(
            channel, event_type, payload, self.agent_id,
            db_path=self.db_path, ttl_seconds=ttl_seconds,
        )

    def poll_events(
        self,
        channels: list[str],
        *,
        hwm_key: str = "_default",
        limit: int = 50,
        event_types: list[str] | None = None,
    ) -> list[dict]:
        since = self._hwm.get(hwm_key, time.time() - 3600)
        events = poll(
            channels, since,
            db_path=self.db_path,
            limit=limit,
            event_types=event_types,
        )
        if events:
            self._hwm[hwm_key] = max(e["published_at"] for e in events)
        return events

    async def _set_db_state(self, status: str, task: str) -> None:
        self._status = status
        self._current_task = task
        try:
            with connect(self.db_path) as conn:
                upsert_agent_state(
                    conn, self.agent_id,
                    status=status,
                    current_task=task,
                    metrics=self._metrics,
                    uptime_start=self._uptime_start,
                )
        except Exception:
            pass

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status == "running"
