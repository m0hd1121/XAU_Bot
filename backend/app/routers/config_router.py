"""
routers/config_router.py
─────────────────────────
Configuration management endpoints.

GET  /config          — return full parsed config.yaml
GET  /config/schema   — return allowed sections + key descriptions
PUT  /config/section  — update one config section, validate, write back, return diff
POST /config/reload   — signal bot to reload config (writes a flag file)
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.security import require_admin
from app.config import settings
from app.services.bot_service import bot_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Allowed configurable sections + their key types ──────────────────────────

_ALLOWED_SECTIONS: dict[str, dict[str, type]] = {
    "risk": {
        "initial_capital": float,
        "risk_per_trade": float,
        "max_risk_per_trade": float,
        "daily_loss_limit": float,
        "max_drawdown_kill": float,
        "min_reward_to_risk": float,
        "max_open_trades": int,
        "volatility_lookback": int,
        "volatility_scale_factor": float,
    },
    "strategy": {
        "require_htf_bias": bool,
        "require_session_window": bool,
        "entry_type": str,
        "limit_entry_buffer_pct": float,
        "sl_buffer_pips": float,
        "partial_tp_pct": float,
        "tp1_rr": float,
        "tp2_rr": float,
        "use_break_even": bool,
        "trail_after_be": bool,
        "trail_step_pct": float,
    },
    "psychology": {
        "max_consecutive_losses": int,
        "loss_streak_size_reduction": float,
        "cooldown_candles_after_loss": int,
        "cooldown_candles_after_kill": int,
        "min_setup_quality_score": float,
        "max_trades_per_session": int,
        "revenge_trade_detection": bool,
    },
    "learning": {
        "enabled": bool,
        "analysis_every_n_trades": int,
        "min_trades_before_update": int,
        "adaptive_threshold": bool,
        "min_confidence_threshold": float,
        "min_pattern_samples": int,
        "decay_halflife": int,
    },
    "execution": {
        "spread_pips": float,
        "slippage_pips": float,
        "slippage_model": str,
        "commission_per_lot": float,
        "min_lot": float,
        "max_lot": float,
        "lot_step": float,
    },
    "market_structure": {
        "swing_lookback": int,
        "bos_confirmation_candles": int,
        "choch_require_sweep": bool,
        "liquidity_equal_threshold": float,
        "inducement_lookback": int,
        "zone_merge_threshold": float,
        "zone_max_age_candles": int,
        "min_zone_impulse_ratio": float,
    },
    "logging": {
        "level": str,
        "log_to_file": bool,
    },
}

# Sections that require bot restart to take effect
_RESTART_REQUIRED = {"risk", "strategy", "market_structure", "execution"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class UpdateSectionRequest(BaseModel):
    section: str
    values: dict[str, Any]


class ConfigUpdateResponse(BaseModel):
    ok: bool
    section: str
    diff: dict[str, Any]
    restart_required: bool
    message: str = ""


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_section(section: str, values: dict) -> list[str]:
    """Return a list of validation error messages (empty = valid)."""
    errors: list[str] = []
    schema = _ALLOWED_SECTIONS.get(section, {})

    for key, val in values.items():
        if key not in schema:
            errors.append(f"Unknown key '{key}' in section '{section}'")
            continue
        expected_type = schema[key]
        if expected_type is float and isinstance(val, int):
            continue  # int coerces to float — OK
        if not isinstance(val, expected_type):
            errors.append(
                f"Key '{key}' expects {expected_type.__name__}, got {type(val).__name__}"
            )

    # Domain-specific range checks
    if section == "risk":
        if "risk_per_trade" in values and not (0.001 <= values["risk_per_trade"] <= 0.05):
            errors.append("risk_per_trade must be between 0.001 and 0.05 (0.1%–5%)")
        if "daily_loss_limit" in values and not (0.01 <= values["daily_loss_limit"] <= 0.10):
            errors.append("daily_loss_limit must be between 0.01 and 0.10")
        if "min_reward_to_risk" in values and values["min_reward_to_risk"] < 1.0:
            errors.append("min_reward_to_risk must be >= 1.0")
    if section == "learning":
        if "min_confidence_threshold" in values and not (0.0 <= values["min_confidence_threshold"] <= 1.0):
            errors.append("min_confidence_threshold must be between 0.0 and 1.0")

    return errors


def _compute_diff(old: dict, new: dict) -> dict:
    diff: dict[str, Any] = {}
    for k, v in new.items():
        if k not in old or old[k] != v:
            diff[k] = {"before": old.get(k), "after": v}
    return diff


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", summary="Get full bot configuration")
async def get_config(_user=Depends(require_admin)) -> dict:
    """Returns the parsed content of config.yaml."""
    return bot_service.read_config()


@router.get("/schema", summary="List configurable sections and their keys")
async def get_schema(_user=Depends(require_admin)) -> dict:
    return {
        section: {
            "keys": {k: v.__name__ for k, v in keys.items()},
            "restart_required": section in _RESTART_REQUIRED,
        }
        for section, keys in _ALLOWED_SECTIONS.items()
    }


@router.put("/section", response_model=ConfigUpdateResponse, summary="Update a config section")
async def update_section(
    req: UpdateSectionRequest,
    _user=Depends(require_admin),
) -> ConfigUpdateResponse:
    """
    Validates the provided values against the schema, writes the config back to
    disk, and returns a diff of what changed.  The bot reads config changes on
    its next bar unless restart_required is True.
    """
    if req.section not in _ALLOWED_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Section '{req.section}' is not configurable via API. "
                   f"Allowed: {sorted(_ALLOWED_SECTIONS.keys())}",
        )

    errors = _validate_section(req.section, req.values)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": errors},
        )

    current_cfg = bot_service.read_config()
    old_section = copy.deepcopy(current_cfg.get(req.section, {}))
    updated_cfg = bot_service.update_config_section(req.section, req.values)
    diff = _compute_diff(old_section, updated_cfg.get(req.section, {}))
    restart_needed = req.section in _RESTART_REQUIRED

    logger.info("Config section updated section=%s diff=%s", req.section, diff)
    return ConfigUpdateResponse(
        ok=True,
        section=req.section,
        diff=diff,
        restart_required=restart_needed,
        message=(
            "Configuration saved. Restart the bot for changes to take effect."
            if restart_needed
            else "Configuration saved. Bot will apply changes on the next bar."
        ),
    )


@router.post("/reload", summary="Signal bot to reload configuration")
async def reload_config(_user=Depends(require_admin)) -> dict:
    """
    Writes a .reload_config flag file that the bot checks each bar.
    For sections that require restart, use POST /bot/restart instead.
    """
    reload_flag = settings.bot_root / ".reload_config"
    reload_flag.touch()
    return {"ok": True, "detail": "Reload signal sent — bot will apply on next bar"}
