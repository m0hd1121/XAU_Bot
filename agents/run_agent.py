"""
run_agent.py — CLI entry point for launching individual trading agents.

Usage:
    python agents/run_agent.py 1   # Start Agent 1 (Strategy Research)
    python agents/run_agent.py 2   # Start Agent 2 (Market Intelligence)
    python agents/run_agent.py 3   # Start Agent 3 (Live Trader)

The script:
  1. Parses the agent number from sys.argv[1]
  2. Loads config.yaml with ${VAR:-default} env-var expansion
  3. Sets up logging (to logs/agent{N}.log + stdout)
  4. Imports and instantiates the correct agent class
  5. Runs agent.start() under asyncio

SIGTERM is handled gracefully by the BaseAgent signal handler.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

import yaml

# ── Repo root on the path (script can be invoked from anywhere) ───────────────
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Config loader (mirrors load_config() in main.py)
# ─────────────────────────────────────────────────────────────────────────────

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _expand_env_vars(text: str) -> str:
    """Replace ${VAR:-default} placeholders with environment values."""

    def _replace(match: re.Match) -> str:
        var_name, default = match.group(1), match.group(2) or ""
        return os.environ.get(var_name, default)

    return _ENV_VAR_RE.sub(_replace, text)


def load_config(path: Path | str) -> dict:
    """Read a YAML config file, expanding ${VAR:-default} env-var placeholders."""
    raw = Path(path).read_text(encoding="utf-8")
    expanded = _expand_env_vars(raw)
    cfg = yaml.safe_load(expanded)
    return cfg if cfg is not None else {}


# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────


def _setup_logging(agent_num: int, cfg: dict) -> None:
    """Configure root logger: write to logs/agent{N}.log and stdout."""
    log_level_str = (
        cfg.get("logging", {}).get("level")
        or cfg.get("bot", {}).get("log_level")
        or os.environ.get("LOG_LEVEL", "INFO")
    ).upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logs_dir = _REPO_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"agent{agent_num}.log"

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
    ]
    try:
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        handlers.append(file_handler)
    except OSError as exc:
        print(f"Warning: could not open log file {log_file}: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )

    # Quiet noisy third-party loggers
    for noisy in ("yfinance", "urllib3", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# Agent factory
# ─────────────────────────────────────────────────────────────────────────────

_AGENT_META = {
    1: {
        "module": "agents.agent1_researcher",
        "class": "Agent1ResearcherAgent",
        "label": "Agent 1: Strategy Research & Self-Learning",
    },
    2: {
        "module": "agents.agent2_intelligence",
        "class": "Agent2IntelligenceAgent",
        "label": "Agent 2: Market Intelligence & Analysis",
    },
    3: {
        "module": "agents.agent3_trader",
        "class": "Agent3TraderAgent",
        "label": "Agent 3: Live Trader & Risk Manager",
    },
}


def _build_agent(agent_num: int, cfg: dict):
    """Import the agent module and instantiate the agent class."""
    meta = _AGENT_META[agent_num]
    module_name = meta["module"]
    class_name = meta["class"]

    try:
        import importlib
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(
            f"Cannot import {module_name}: {exc}\n"
            f"Make sure the agent class file exists at {module_name.replace('.', '/')}.py"
        ) from exc

    cls = getattr(module, class_name, None)
    if cls is None:
        raise SystemExit(
            f"Class '{class_name}' not found in {module_name}. "
            f"Expected a class named {class_name}."
        )

    agent_id = f"agent{agent_num}"
    return cls(agent_id, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    # ── Parse agent number ────────────────────────────────────────────────────
    if len(sys.argv) < 2:
        print("Usage: python agents/run_agent.py <1|2|3>", file=sys.stderr)
        sys.exit(1)

    try:
        agent_num = int(sys.argv[1])
    except ValueError:
        print(f"Error: agent number must be 1, 2, or 3 — got '{sys.argv[1]}'", file=sys.stderr)
        sys.exit(1)

    if agent_num not in _AGENT_META:
        print(f"Error: unknown agent number {agent_num}. Must be 1, 2, or 3.", file=sys.stderr)
        sys.exit(1)

    # ── Load config ───────────────────────────────────────────────────────────
    config_path = _REPO_ROOT / "config.yaml"
    if not config_path.exists():
        print(f"Error: config.yaml not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(config_path)

    # ── Setup logging ─────────────────────────────────────────────────────────
    _setup_logging(agent_num, cfg)
    log = logging.getLogger(f"run_agent")

    label = _AGENT_META[agent_num]["label"]
    log.info("Starting %s", label)
    log.info("Config: %s", config_path)
    log.info("Repo root: %s", _REPO_ROOT)

    # ── Build and run ─────────────────────────────────────────────────────────
    agent = _build_agent(agent_num, cfg)
    log.info("Instantiated %s as agent%d", type(agent).__name__, agent_num)

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        log.info("%s interrupted by keyboard", label)
    except SystemExit:
        raise
    except Exception:
        log.exception("Fatal error in %s", label)
        sys.exit(1)

    log.info("%s exited cleanly", label)


if __name__ == "__main__":
    main()
