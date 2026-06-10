"""
agent1_researcher.py
────────────────────
Strategy Research & Self-Learning Agent for the autonomous XAU/USD trading system.

Responsibilities:
  • Continuously evolves a population of StrategyGenomes via genetic optimisation.
  • Runs a multi-stage validation pipeline (walk-forward + Monte Carlo) on top
    candidates every 5th cycle.
  • Persists every result to strategy_memory for longitudinal analysis.
  • Listens to Agent 3 trade-close feedback and logs outcomes.
  • Optionally auto-promotes validated strategies to live trading when
    agents.agent1.auto_promote is true in config.

Cycle cadence  : ~120 s between cycles (evolution is background work).
Validation gate: every 5th cycle.
Shadow check   : every 20th cycle.

All heavy objects (FitnessEvaluator, WalkForwardValidator, MonteCarloValidator,
GeneticOptimizer) are created in on_start(), not __init__, so that the
constructor is lightweight and the agent can be constructed without side-effects.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from pathlib import Path
from typing import Any

from .base_agent import BaseAgent
from .message_bus import (
    CH_RESEARCH,
    CH_STRATEGY,
    CH_TRADES,
    EV_POPULATION_UPDATE,
    EV_STRATEGY_CANDIDATE,
    EV_STRATEGY_PROMOTED,
    EV_TRADE_CLOSED,
    publish_strategy_candidate,
    publish_strategy_promoted,
)
from .shared_db import (
    connect,
    get_strategy_candidates,
    insert_strategy_memory,
    promote_strategy,
    upsert_strategy_candidate,
)

# Evolution package — all three classes exist in the already-written modules.
from .evolution.fitness_evaluator import FitnessEvaluator, WalkForwardValidator
from .evolution.strategy_genome import StrategyGenome

# GeneticOptimizer and MonteCarloValidator live in the already-written module.
from .evolution.genetic_optimizer import GeneticOptimizer, MonteCarloValidator


# ---------------------------------------------------------------------------
# Sentinel for "no current genome being tracked for feedback"
# ---------------------------------------------------------------------------
_NO_GENOME = ""


class Agent1ResearcherAgent(BaseAgent):
    """
    Strategy Research & Self-Learning Agent.

    Continuously evolves trading strategy parameters via a genetic algorithm
    and validates top candidates through walk-forward and Monte Carlo analysis
    before publishing them for Agent 3 to consume.
    """

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        cfg: dict,
        *,
        db_path: Path | str | None = None,
    ) -> None:
        super().__init__("agent1", cfg, db_path=db_path)

        # Data source used for all backtests.
        self._data_csv_path: str = str(
            cfg.get("data", {}).get("csv_path", "data/XAUUSD_H1.csv")
        )

        # Genetic optimiser settings from config.
        agent1_cfg: dict = cfg.get("agents", {}).get("agent1", {})
        self._population_size: int = int(agent1_cfg.get("population_size", 30))
        self._shadow_mode_bars: int = int(agent1_cfg.get("shadow_mode_bars", 200))

        # Heavy objects — populated in on_start().
        self._evaluator: FitnessEvaluator | None = None
        self._wf_validator: WalkForwardValidator | None = None
        self._mc_validator: MonteCarloValidator | None = None
        self._optimizer: GeneticOptimizer | None = None

        # Cycle counter (drives validation / shadow-mode scheduling).
        self._cycle_count: int = 0

        # High-water mark for Agent 3 trade-feedback polling.
        self._trade_feedback_hwm: float = 0.0

        # Hash of the genome that performed best last cycle (used in
        # _process_trade_feedback to tag memory records).
        self._current_best_genome_hash: str = _NO_GENOME

        # Rolling counters exposed via update_metrics().
        self._validated_count: int = 0
        self._rejected_count: int = 0
        self._promoted_count: int = 0
        self._trade_feedback_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        """Initialise all heavy objects and seed the initial population."""
        self.log.info(
            "Agent 1 initialising — csv=%s  population=%d",
            self._data_csv_path,
            self._population_size,
        )

        # 1. Fitness evaluation infrastructure.
        self._evaluator = FitnessEvaluator(self.cfg, self._data_csv_path)
        self._wf_validator = WalkForwardValidator(self.cfg, self._data_csv_path)
        self._mc_validator = MonteCarloValidator()

        # 2. Genetic optimiser (uses the same evaluator instance).
        self._optimizer = GeneticOptimizer(
            fitness_evaluator=self._evaluator,
            db_path=self.db_path,
            population_size=self._population_size,
        )

        # 3. Seed an initial random population.
        try:
            population = self._optimizer.initialize_population(self.cfg)
            self.log.info(
                "Agent 1 started. Population size: %d",
                len(population),
            )
        except Exception:
            self.log.exception(
                "Failed to initialise population — will retry on first cycle."
            )

        # 4. Initialise the trade-feedback high-water mark.
        self._trade_feedback_hwm = time.time() - 1.0

        # 5. Persist initial metrics so the heartbeat has something to show.
        self.update_metrics(
            {
                "generation": 0,
                "best_score": 0.0,
                "population_size": self._population_size,
                "validated_count": 0,
                "rejected_count": 0,
                "promoted_count": 0,
                "trade_feedback_count": 0,
            }
        )

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------

    async def run_cycle(self) -> None:
        """
        One evolution cycle.

        Structure
        ---------
        Every cycle : run one GA generation.
        Every 5th   : validate top pending candidates.
        Every 20th  : check for shadow-mode / auto-promote candidates.
        End         : consume trade feedback from Agent 3, then sleep 120 s.
        """
        self._cycle_count += 1

        # ── Evolution step (every cycle) ──────────────────────────────
        await self._run_evolution_step()

        # ── Validation pipeline (every 5th cycle) ─────────────────────
        if self._cycle_count % 5 == 0:
            await self._run_validation_pipeline()

        # ── Shadow-mode / auto-promote check (every 20th cycle) ───────
        if self._cycle_count % 20 == 0:
            await self._run_shadow_mode_check()

        # ── Consume trade feedback from Agent 3 ───────────────────────
        await self._consume_trade_feedback()

        # ── Sleep between cycles (evolution runs slowly in background) ─
        await asyncio.sleep(120)

    # ------------------------------------------------------------------
    # Evolution step
    # ------------------------------------------------------------------

    async def _run_evolution_step(self) -> None:
        """Run one generation of the genetic algorithm and publish results."""
        self.set_task("Evolving strategy population")

        if self._optimizer is None:
            self.log.warning("Optimizer not ready; skipping evolution step.")
            return

        try:
            result = self._optimizer.evolve_one_generation()

            self.log.info(
                "Gen %d: best_score=%.3f, avg=%.3f",
                result.generation,
                result.best_fitness.composite_score,
                result.avg_composite_score,
            )

            self._current_best_genome_hash = (
                result.best_genome.genome_hash()
                if result.best_genome is not None
                else _NO_GENOME
            )

            self.update_metrics(
                {
                    "generation": result.generation,
                    "best_score": result.best_fitness.composite_score,
                    "population_size": result.population_size,
                    "validated_count": self._validated_count,
                    "rejected_count": self._rejected_count,
                    "promoted_count": self._promoted_count,
                    "trade_feedback_count": self._trade_feedback_count,
                }
            )

            self.publish(
                CH_RESEARCH,
                EV_POPULATION_UPDATE,
                {
                    "generation": result.generation,
                    "best_score": result.best_fitness.composite_score,
                    "avg_score": result.avg_composite_score,
                    "population_size": result.population_size,
                    "timestamp": time.time(),
                },
            )

        except Exception:
            self.log.exception("Error during evolution step (cycle %d)", self._cycle_count)

    # ------------------------------------------------------------------
    # Validation pipeline
    # ------------------------------------------------------------------

    async def _run_validation_pipeline(self) -> None:
        """
        Full validation pipeline for top pending candidates.

        Stages:
          1. Walk-forward validation.
          2. Monte Carlo simulation (only if walk-forward passed).
          3. Promote to 'validated' or 'rejected' in the DB.
          4. Publish EV_STRATEGY_CANDIDATE for validated genomes.
        """
        self.set_task("Running validation pipeline")
        self.log.info("Cycle %d: starting validation pipeline.", self._cycle_count)

        candidates = self._get_top_candidates()
        if not candidates:
            self.log.info("No pending candidates to validate.")
            return

        for genome_hash, genome, fitness_dict in candidates:
            await self._validate_one_candidate(genome_hash, genome, fitness_dict)

    async def _validate_one_candidate(
        self,
        genome_hash: str,
        genome: StrategyGenome,
        fitness_dict: dict,
    ) -> None:
        """
        Run the full validation pipeline for a single candidate genome.

        Walk-forward is mandatory; Monte Carlo is gated on walk-forward passing.
        A candidate that fails both is marked 'rejected'.
        """
        self.log.info("Validating candidate %s …", genome_hash)

        if self._wf_validator is None or self._mc_validator is None or self._evaluator is None:
            self.log.error("Validators not initialised; cannot validate %s.", genome_hash)
            return

        # ── Stage A: Walk-forward ────────────────────────────────────
        wf_result = None
        try:
            wf_result = self._wf_validator.validate(genome, n_splits=4)
            wf_metrics = {
                "avg_is_score": wf_result.avg_is_score,
                "avg_oos_score": wf_result.avg_oos_score,
                "oos_degradation": wf_result.oos_degradation,
                "passed": wf_result.passed,
                "n_splits": 4,
            }
            try:
                with connect(self.db_path) as conn:
                    insert_strategy_memory(
                        conn,
                        genome_hash,
                        "WALKFORWARD",
                        wf_metrics,
                        passed=wf_result.passed,
                        notes=f"cycle={self._cycle_count}",
                    )
            except Exception:
                self.log.exception(
                    "Failed to persist walk-forward result for %s.", genome_hash
                )

            if wf_result.passed:
                self.log.info(
                    "Walk-forward PASSED for %s: oos=%.3f degradation=%.3f",
                    genome_hash,
                    wf_result.avg_oos_score,
                    wf_result.oos_degradation,
                )
            else:
                self.log.info(
                    "Walk-forward FAILED for %s: oos=%.3f degradation=%.3f",
                    genome_hash,
                    wf_result.avg_oos_score,
                    wf_result.oos_degradation,
                )

        except Exception:
            self.log.exception(
                "Walk-forward validation raised exception for %s.", genome_hash
            )

        # ── Stage B: Monte Carlo (only if WF passed) ──────────────────
        mc_result = None
        mc_passed = False

        if wf_result is not None and wf_result.passed:
            try:
                # We need the raw trade list — run a fresh full-data backtest.
                fresh_fitness = self._evaluator.evaluate(genome)
                trades: list[dict] = fresh_fitness.raw_metrics.get("trades", [])

                mc_result = self._mc_validator.validate(genome, trades)
                mc_passed = mc_result.passed

                mc_metrics = {
                    "median_pnl": mc_result.median_pnl,
                    "percentile_5_pnl": mc_result.percentile_5_pnl,
                    "median_max_dd": mc_result.median_max_dd,
                    "percentile_95_max_dd": mc_result.percentile_95_max_dd,
                    "passed": mc_result.passed,
                    "n_trades_used": len(trades),
                }
                try:
                    with connect(self.db_path) as conn:
                        insert_strategy_memory(
                            conn,
                            genome_hash,
                            "MONTE_CARLO",
                            mc_metrics,
                            passed=mc_result.passed,
                            notes=f"cycle={self._cycle_count}",
                        )
                except Exception:
                    self.log.exception(
                        "Failed to persist Monte Carlo result for %s.", genome_hash
                    )

                if mc_result.passed:
                    self.log.info(
                        "Monte Carlo PASSED for %s: p50_pnl=%.2f p5_pnl=%.2f",
                        genome_hash,
                        mc_result.median_pnl,
                        mc_result.percentile_5_pnl,
                    )
                else:
                    self.log.info(
                        "Monte Carlo FAILED for %s: p50_pnl=%.2f p95_dd=%.2f",
                        genome_hash,
                        mc_result.median_pnl,
                        mc_result.percentile_95_max_dd,
                    )

            except Exception:
                self.log.exception(
                    "Monte Carlo simulation raised exception for %s.", genome_hash
                )
        else:
            self.log.info(
                "Skipping Monte Carlo for %s (walk-forward did not pass).", genome_hash
            )

        # ── Stage C: Update DB status ─────────────────────────────────
        both_passed = (
            wf_result is not None and wf_result.passed and mc_passed
        )

        validation_summary: dict[str, Any] = {}
        if wf_result is not None:
            validation_summary["walkforward"] = {
                "avg_is_score": wf_result.avg_is_score,
                "avg_oos_score": wf_result.avg_oos_score,
                "oos_degradation": wf_result.oos_degradation,
                "passed": wf_result.passed,
            }
        if mc_result is not None:
            validation_summary["monte_carlo"] = {
                "median_pnl": mc_result.median_pnl,
                "percentile_5_pnl": mc_result.percentile_5_pnl,
                "median_max_dd": mc_result.median_max_dd,
                "percentile_95_max_dd": mc_result.percentile_95_max_dd,
                "passed": mc_result.passed,
            }

        new_status = "validated" if both_passed else "rejected"

        try:
            with connect(self.db_path) as conn:
                upsert_strategy_candidate(
                    conn,
                    genome_hash,
                    genome.to_dict(),
                    status=new_status,
                    fitness=fitness_dict,
                    validation=validation_summary,
                    notes=f"validated_cycle={self._cycle_count}",
                )
        except Exception:
            self.log.exception(
                "Failed to update strategy_candidates status for %s.", genome_hash
            )

        # ── Stage D: Publish / count ───────────────────────────────────
        if both_passed:
            self._validated_count += 1
            self.log.info(
                "Candidate %s VALIDATED and ready for shadow mode.", genome_hash
            )
            try:
                publish_strategy_candidate(
                    genome_hash=genome_hash,
                    genome=genome.to_dict(),
                    fitness=fitness_dict,
                    generation=fitness_dict.get("generation", 0),
                    db_path=self.db_path,
                )
            except Exception:
                self.log.exception(
                    "Failed to publish EV_STRATEGY_CANDIDATE for %s.", genome_hash
                )
        else:
            self._rejected_count += 1
            self.log.info(
                "Candidate %s REJECTED (wf_passed=%s, mc_passed=%s).",
                genome_hash,
                wf_result.passed if wf_result else False,
                mc_passed,
            )

        self.update_metrics(
            {
                "validated_count": self._validated_count,
                "rejected_count": self._rejected_count,
            }
        )

    # ------------------------------------------------------------------
    # Shadow mode / auto-promote check
    # ------------------------------------------------------------------

    async def _run_shadow_mode_check(self) -> None:
        """
        Look for validated candidates and optionally promote them to live
        trading if auto_promote is enabled in config.
        """
        self.set_task("Checking shadow mode candidates")
        self.log.info("Cycle %d: running shadow-mode check.", self._cycle_count)

        try:
            with connect(self.db_path) as conn:
                rows = get_strategy_candidates(conn, status="validated", limit=1)
        except Exception:
            self.log.exception("Failed to query validated candidates for shadow check.")
            return

        if not rows:
            self.log.info("No validated candidates awaiting shadow mode.")
            return

        row = rows[0]
        genome_hash: str = row["genome_hash"]
        fitness_dict: dict = row.get("fitness", {})
        validation_summary: dict = row.get("validation", {})

        self.log.info(
            "Candidate %s is ready for shadow mode — awaiting manual approval or auto-promote config.",
            genome_hash,
        )

        auto_promote: bool = bool(
            self.cfg.get("agents", {}).get("agent1", {}).get("auto_promote", False)
        )

        if auto_promote:
            self.log.info(
                "auto_promote=True — promoting candidate %s to live shadow trading.",
                genome_hash,
            )
            try:
                with connect(self.db_path) as conn:
                    promote_strategy(conn, genome_hash)
            except Exception:
                self.log.exception(
                    "Failed to promote strategy %s in DB.", genome_hash
                )
                return

            try:
                publish_strategy_promoted(
                    genome_hash=genome_hash,
                    fitness=fitness_dict,
                    validation_summary=validation_summary,
                    db_path=self.db_path,
                )
            except Exception:
                self.log.exception(
                    "Failed to publish EV_STRATEGY_PROMOTED for %s.", genome_hash
                )

            self._promoted_count += 1
            self.update_metrics({"promoted_count": self._promoted_count})

            self.log.info("Candidate %s promoted successfully.", genome_hash)

        else:
            self.log.info(
                "Manual approval required. Use API or iOS app to promote candidate %s.",
                genome_hash,
            )

    # ------------------------------------------------------------------
    # Trade feedback consumption
    # ------------------------------------------------------------------

    async def _consume_trade_feedback(self) -> None:
        """
        Poll CH_TRADES for EV_TRADE_CLOSED events published by Agent 3 and
        process each one via _process_trade_feedback().
        """
        try:
            events = self.poll_events(
                [CH_TRADES],
                hwm_key="trades",
                limit=50,
                event_types=[EV_TRADE_CLOSED],
            )
            if events:
                self._process_trade_feedback(events)
        except Exception:
            self.log.exception("Error while consuming trade feedback.")

    # ------------------------------------------------------------------
    # Helper: get top pending candidates
    # ------------------------------------------------------------------

    def _get_top_candidates(
        self,
        limit: int = 3,
    ) -> list[tuple[str, StrategyGenome, dict]]:
        """
        Return the top-N pending candidates ordered by composite_score descending.

        Returns a list of (genome_hash, StrategyGenome, fitness_dict) tuples.
        Falls back to an empty list on any DB or parse error.
        """
        try:
            with connect(self.db_path) as conn:
                rows = get_strategy_candidates(conn, status="pending", limit=100)
        except Exception:
            self.log.exception("Failed to query pending strategy candidates.")
            return []

        if not rows:
            return []

        # Sort by composite_score descending; guard against missing keys.
        def _score(row: dict) -> float:
            try:
                return float(row.get("fitness", {}).get("composite_score", 0.0))
            except (TypeError, ValueError):
                return 0.0

        rows.sort(key=_score, reverse=True)
        top_rows = rows[:limit]

        results: list[tuple[str, StrategyGenome, dict]] = []
        for row in top_rows:
            genome_hash: str = row["genome_hash"]
            genome_dict: dict = row.get("genome", {})
            fitness_dict: dict = row.get("fitness", {})
            try:
                genome = StrategyGenome.from_dict(genome_dict)
            except Exception:
                self.log.exception(
                    "Could not reconstruct StrategyGenome from DB row for hash=%s; skipping.",
                    genome_hash,
                )
                continue
            results.append((genome_hash, genome, fitness_dict))

        return results

    # ------------------------------------------------------------------
    # Helper: process trade feedback events
    # ------------------------------------------------------------------

    def _process_trade_feedback(self, events: list[dict]) -> None:
        """
        Process a batch of EV_TRADE_CLOSED events received from Agent 3.

        For loss trades, if we have a current best genome hash tracked we
        insert a LIVE memory record so the genome's live-trade loss rate can be
        analysed during future validation cycles.
        """
        for event in events:
            try:
                payload: dict = event.get("payload", {})
                outcome: str = str(payload.get("outcome", "UNKNOWN")).upper()
                pnl_r: float = float(payload.get("pnl_r", 0.0))
                trade_id: str = str(payload.get("trade_id", ""))

                self.log.info(
                    "Trade feedback: %s  pnl_r=%.2f  trade_id=%s",
                    outcome,
                    pnl_r,
                    trade_id,
                )

                self._trade_feedback_count += 1

                # Tag the current best genome with a live-trade memory entry on losses.
                if outcome == "LOSS" and self._current_best_genome_hash:
                    try:
                        with connect(self.db_path) as conn:
                            insert_strategy_memory(
                                conn,
                                self._current_best_genome_hash,
                                "LIVE",
                                {
                                    "outcome": outcome,
                                    "pnl_r": pnl_r,
                                    "trade_id": trade_id,
                                    "timestamp": payload.get("timestamp", time.time()),
                                },
                                passed=False,
                                notes="live_trade_loss_feedback",
                            )
                    except Exception:
                        self.log.exception(
                            "Failed to insert live loss memory for genome %s.",
                            self._current_best_genome_hash,
                        )

            except Exception:
                self.log.exception(
                    "Error processing trade feedback event: %s", event
                )

        self.update_metrics({"trade_feedback_count": self._trade_feedback_count})
