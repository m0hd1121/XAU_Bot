"""
psychology_layer.py
────────────────────
Simulates disciplined trader psychology to prevent the most common
behavioural errors that destroy trading accounts:

  • Revenge trading after losses
  • Overtrading / impulsive entries
  • Ignoring cooldown periods
  • Forcing trades in poor market conditions
  • Increasing size after losses (gambler's fallacy)

All rules are applied as a filter gate: every potential entry must pass
through PsychologyLayer.approve() before reaching execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PsychologyState:
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    trades_today: int = 0
    trades_this_session: int = 0
    last_loss_bar: int = -1
    last_trade_bar: int = -1
    in_cooldown: bool = False
    cooldown_until_bar: int = -1
    size_modifier: float = 1.0
    session_trade_count: dict = field(default_factory=dict)
    halted_by_psychology: bool = False
    halt_reason: str = ""


@dataclass
class PsychologyVerdict:
    approved: bool
    reason: str
    size_modifier: float = 1.0   # Multiply risk_per_trade by this value


class PsychologyLayer:
    """
    Stateful psychology filter that wraps around the strategy engine.
    Call `approve(setup, current_bar)` for every candidate entry.
    Call `record_outcome()` after each trade closes.
    """

    def __init__(self, cfg: dict) -> None:
        pc = cfg.get("psychology", {})

        self._max_consec_losses: int       = pc.get("max_consecutive_losses", 3)
        self._loss_size_reduction: float   = pc.get("loss_streak_size_reduction", 0.5)
        self._cooldown_after_loss: int     = pc.get("cooldown_candles_after_loss", 3)
        self._cooldown_after_kill: int     = pc.get("cooldown_candles_after_kill", 48)
        self._min_quality: float           = pc.get("min_setup_quality_score", 0.6)
        self._max_per_session: int         = pc.get("max_trades_per_session", 2)
        self._revenge_detection: bool      = pc.get("revenge_trade_detection", True)

        self._state = PsychologyState()

    # ── Public API ──────────────────────────────────────────────────────────

    def approve(
        self,
        setup_quality: float,
        current_bar: int,
        session: str,
        setup_direction: str,
        last_trade_direction: Optional[str] = None,
        last_trade_was_loss: bool = False,
    ) -> PsychologyVerdict:
        """
        Returns a PsychologyVerdict. If approved=False, trade must be skipped.
        size_modifier adjusts risk_per_trade when psychology warrants caution.
        """
        s = self._state

        # ── Halted ──────────────────────────────────────────────────────────
        if s.halted_by_psychology:
            return PsychologyVerdict(False, f"psychology_halt: {s.halt_reason}")

        # ── Cooldown enforcement ─────────────────────────────────────────────
        if s.in_cooldown and current_bar < s.cooldown_until_bar:
            remaining = s.cooldown_until_bar - current_bar
            return PsychologyVerdict(
                False, f"cooldown_active ({remaining} bars remaining)"
            )
        elif s.in_cooldown and current_bar >= s.cooldown_until_bar:
            s.in_cooldown = False
            logger.debug("Cooldown lifted at bar %d", current_bar)

        # ── Setup quality gate ───────────────────────────────────────────────
        if setup_quality < self._min_quality:
            return PsychologyVerdict(
                False, f"quality_too_low ({setup_quality:.2f} < {self._min_quality})"
            )

        # ── Revenge trade detection ──────────────────────────────────────────
        if self._revenge_detection and last_trade_was_loss:
            if (last_trade_direction is not None and
                    setup_direction == last_trade_direction and
                    s.last_loss_bar >= 0 and
                    current_bar - s.last_loss_bar <= self._cooldown_after_loss + 2):
                return PsychologyVerdict(
                    False,
                    "revenge_trade_blocked (same direction immediately after loss)"
                )

        # ── Session trade limit ──────────────────────────────────────────────
        session_count = s.session_trade_count.get(session, 0)
        if session_count >= self._max_per_session:
            return PsychologyVerdict(
                False,
                f"session_limit ({session_count}/{self._max_per_session} trades in '{session}')"
            )

        # ── Consecutive loss size reduction ──────────────────────────────────
        modifier = 1.0
        if s.consecutive_losses >= self._max_consec_losses:
            modifier = self._loss_size_reduction
            logger.info(
                "Psychology: %d consecutive losses — size reduced to %.0f%%",
                s.consecutive_losses, modifier * 100
            )

        return PsychologyVerdict(approved=True, reason="ok", size_modifier=modifier)

    def record_win(self, bar: int, session: str) -> None:
        s = self._state
        s.consecutive_losses = 0
        s.consecutive_wins  += 1
        s.last_trade_bar     = bar
        s.trades_today      += 1
        s.session_trade_count[session] = s.session_trade_count.get(session, 0) + 1
        s.size_modifier = 1.0
        logger.debug("Psychology: WIN recorded. Streak: %d wins", s.consecutive_wins)

    def record_loss(self, bar: int, session: str) -> None:
        s = self._state
        s.consecutive_wins  = 0
        s.consecutive_losses += 1
        s.last_loss_bar      = bar
        s.last_trade_bar     = bar
        s.trades_today      += 1
        s.session_trade_count[session] = s.session_trade_count.get(session, 0) + 1

        # Apply cooldown
        s.in_cooldown = True
        s.cooldown_until_bar = bar + self._cooldown_after_loss
        logger.info(
            "Psychology: LOSS recorded. Streak=%d. Cooldown until bar %d.",
            s.consecutive_losses, s.cooldown_until_bar
        )

        # After extended loss streak, apply size reduction
        if s.consecutive_losses >= self._max_consec_losses:
            s.size_modifier = self._loss_size_reduction
            logger.warning(
                "Psychology: %d consecutive losses — operating at %.0f%% size",
                s.consecutive_losses, s.size_modifier * 100
            )

        # If far too many consecutive losses, consider halting
        if s.consecutive_losses >= self._max_consec_losses * 2:
            s.halted_by_psychology = True
            s.halt_reason = f"extreme_loss_streak ({s.consecutive_losses} losses)"
            logger.critical("Psychology HALT: extreme loss streak of %d", s.consecutive_losses)

    def reset_session_count(self, session: str) -> None:
        self._state.session_trade_count[session] = 0

    def reset_daily(self) -> None:
        self._state.trades_today = 0
        self._state.session_trade_count = {}

    def reset_halt(self) -> None:
        self._state.halted_by_psychology = False
        self._state.halt_reason = ""
        self._state.consecutive_losses = 0

    def apply_kill_cooldown(self, current_bar: int) -> None:
        """Called when the RiskManager kill-switch fires."""
        s = self._state
        s.in_cooldown = True
        s.cooldown_until_bar = current_bar + self._cooldown_after_kill
        logger.warning("Psychology: kill-switch cooldown until bar %d", s.cooldown_until_bar)

    @property
    def size_modifier(self) -> float:
        return self._state.size_modifier

    @property
    def consecutive_losses(self) -> int:
        return self._state.consecutive_losses

    @property
    def state(self) -> PsychologyState:
        return self._state
