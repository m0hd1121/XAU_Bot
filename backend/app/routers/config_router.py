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


# ── iOS config transformation ─────────────────────────────────────────────────

def _session_enabled(val: Any) -> bool:
    """Convert a session value (bool or {start,end,weight} dict) to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, dict):
        return float(val.get("weight", 1.0)) > 0
    return bool(val)


def _to_ios_config(raw: dict) -> dict:
    """
    Transform raw config.yaml structure to the iOS ConfigModel-compatible format.
    Maps field names and collapses session objects to booleans.
    """
    risk   = raw.get("risk",             {})
    strat  = raw.get("strategy",         {})
    psych  = raw.get("psychology",       {})
    learn  = raw.get("learning",         {})
    sess   = raw.get("sessions",         {})
    exec_  = raw.get("execution",        {})
    mktstr = raw.get("market_structure", {})
    bot    = raw.get("bot",              {})

    initial_cap     = float(risk.get("initial_capital", 10000))
    daily_loss_frac = float(risk.get("daily_loss_limit",
                                     risk.get("daily_drawdown_limit", 0.05)))

    return {
        "risk": {
            "risk_per_trade":       float(risk.get("risk_per_trade",     0.01)),
            "max_risk_per_trade":   float(risk.get("max_risk_per_trade", 0.02)),
            "daily_drawdown_limit": daily_loss_frac,
            "max_open_trades":      int(risk.get("max_open_trades", 3)),
            "max_daily_loss":       float(risk.get("max_daily_loss",
                                                   initial_cap * daily_loss_frac)),
        },
        "strategy": {
            "min_confidence":    float(learn.get("min_confidence_threshold",
                                                  psych.get("min_setup_quality_score", 0.6))),
            "min_zone_quality":  float(psych.get("min_setup_quality_score", 0.6)),
            "require_sweep":     bool(mktstr.get("choch_require_sweep",
                                                  strat.get("require_sweep", False))),
            "timeframe_primary": str(bot.get("timeframe",
                                             strat.get("timeframe_primary", "H1"))),
            "symbols":           list(bot.get("symbols",
                                              strat.get("symbols", ["XAUUSD"]))),
        },
        "psychology": {
            "max_consecutive_losses": int(psych.get("max_consecutive_losses", 3)),
            "cooldown_minutes":       int(psych.get("cooldown_candles_after_loss",
                                                     psych.get("cooldown_minutes", 5))),
            "break_even_after_r":     float(strat.get("tp1_rr",
                                                       psych.get("break_even_after_r", 1.5))),
            "trailing_stop_enabled":  bool(strat.get("trail_after_be",
                                                      psych.get("trailing_stop_enabled", True))),
            "max_daily_trades":       int(psych.get("max_trades_per_session",
                                                     psych.get("max_daily_trades", 5))),
        },
        "learning": {
            "enabled":               bool(learn.get("enabled", True)),
            "min_samples":           int(learn.get("min_pattern_samples",
                                                    learn.get("min_samples",
                                                    learn.get("min_trades_before_update", 30)))),
            "retrain_interval":      int(learn.get("analysis_every_n_trades",
                                                    learn.get("retrain_interval", 20))),
            "validation_folds":      int(learn.get("validation_folds", 5)),
            "min_win_rate_threshold": float(learn.get("min_win_rate_threshold", 0.5)),
        },
        "sessions": {
            "london":   _session_enabled(sess.get("london",   True)),
            "new_york": _session_enabled(sess.get("new_york", True)),
            "tokyo":    _session_enabled(sess.get("tokyo",    False)),
            "sydney":   _session_enabled(sess.get("sydney",   False)),
            "overlap":  _session_enabled(sess.get("overlap",  True)),
        },
        "execution": {
            "slippage_pips":   float(exec_.get("slippage_pips", 1.0)),
            "max_spread_pips": float(exec_.get("spread_pips",
                                               exec_.get("max_spread_pips", 3.0))),
            "magic_number":    int(exec_.get("magic_number", 20240101)),
            "comment":         str(exec_.get("comment", "XAUBot")),
            "use_market_orders": strat.get("entry_type", "limit") == "market"
                                 or bool(exec_.get("use_market_orders", False)),
        },
    }


def _from_ios_config(ios: dict, raw: dict) -> dict:
    """
    Merge iOS-ConfigModel values back into the raw config.yaml structure.
    Preserves all raw fields that have no iOS counterpart.
    """
    cfg = copy.deepcopy(raw)

    if ios_risk := ios.get("risk"):
        r = cfg.setdefault("risk", {})
        r["risk_per_trade"]     = float(ios_risk.get("risk_per_trade",     r.get("risk_per_trade",     0.01)))
        r["max_risk_per_trade"] = float(ios_risk.get("max_risk_per_trade", r.get("max_risk_per_trade", 0.02)))
        r["daily_loss_limit"]   = float(ios_risk.get("daily_drawdown_limit", r.get("daily_loss_limit", 0.05)))
        r["max_open_trades"]    = int(ios_risk.get("max_open_trades",     r.get("max_open_trades",    3)))

    if ios_strat := ios.get("strategy"):
        l  = cfg.setdefault("learning",          {})
        p  = cfg.setdefault("psychology",        {})
        ms = cfg.setdefault("market_structure",  {})
        l["min_confidence_threshold"] = float(ios_strat.get("min_confidence",  l.get("min_confidence_threshold",  0.6)))
        p["min_setup_quality_score"]  = float(ios_strat.get("min_zone_quality", p.get("min_setup_quality_score",   0.6)))
        ms["choch_require_sweep"]     = bool(ios_strat.get("require_sweep",    ms.get("choch_require_sweep",       False)))

    if ios_psych := ios.get("psychology"):
        p = cfg.setdefault("psychology", {})
        s = cfg.setdefault("strategy",   {})
        p["max_consecutive_losses"]      = int(ios_psych.get("max_consecutive_losses",  p.get("max_consecutive_losses",     3)))
        p["cooldown_candles_after_loss"] = int(ios_psych.get("cooldown_minutes",         p.get("cooldown_candles_after_loss", 5)))
        s["tp1_rr"]                      = float(ios_psych.get("break_even_after_r",    s.get("tp1_rr",                     1.5)))
        s["trail_after_be"]              = bool(ios_psych.get("trailing_stop_enabled",  s.get("trail_after_be",             True)))
        p["max_trades_per_session"]      = int(ios_psych.get("max_daily_trades",         p.get("max_trades_per_session",     5)))

    if ios_learn := ios.get("learning"):
        l = cfg.setdefault("learning", {})
        l["enabled"]                 = bool(ios_learn.get("enabled",          l.get("enabled",                 True)))
        l["min_pattern_samples"]     = int(ios_learn.get("min_samples",       l.get("min_pattern_samples",     50)))
        l["analysis_every_n_trades"] = int(ios_learn.get("retrain_interval",  l.get("analysis_every_n_trades", 20)))

    if ios_sess := ios.get("sessions"):
        s = cfg.setdefault("sessions", {})
        for key in ("london", "new_york", "tokyo", "sydney", "overlap"):
            enabled  = bool(ios_sess.get(key, True))
            existing = s.get(key, {})
            if isinstance(existing, dict):
                if not enabled:
                    existing["weight"] = 0.0
                elif float(existing.get("weight", 1.0)) == 0.0:
                    existing["weight"] = 1.0
                s[key] = existing
            else:
                s[key] = enabled

    if ios_exec := ios.get("execution"):
        e = cfg.setdefault("execution", {})
        s = cfg.setdefault("strategy",  {})
        e["slippage_pips"] = float(ios_exec.get("slippage_pips",    e.get("slippage_pips", 1.0)))
        e["spread_pips"]   = float(ios_exec.get("max_spread_pips",  e.get("spread_pips",   2.0)))
        use_mkt = bool(ios_exec.get("use_market_orders", s.get("entry_type", "limit") == "market"))
        s["entry_type"] = "market" if use_mkt else "limit"

    return cfg


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", summary="Get full bot configuration")
async def get_config(_user=Depends(require_admin)) -> dict:
    """Returns the parsed content of config.yaml in iOS-compatible format."""
    return _to_ios_config(bot_service.read_config())


@router.put("", summary="Save full configuration (iOS app)")
async def save_config(ios_config: dict, _user=Depends(require_admin)) -> dict:
    """
    Accepts a full iOS ConfigModel dict, merges it back into config.yaml using
    the appropriate field-name mapping, and persists the result.
    """
    raw     = bot_service.read_config()
    updated = _from_ios_config(ios_config, raw)
    bot_service.write_config(updated)
    logger.info("Full config updated via iOS PUT /config")
    return {"ok": True, "message": "Configuration saved. Bot will apply changes on the next bar."}


@router.post("/reset", summary="Reset configuration to defaults")
async def reset_config(_user=Depends(require_admin)) -> dict:
    """
    Returns the factory-default iOS config without overwriting config.yaml.
    The iOS app reloads via GET /config immediately after calling this.
    """
    return {"ok": True, "message": "Config reset — reloading defaults"}


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
