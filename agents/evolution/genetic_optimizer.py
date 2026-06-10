"""
genetic_optimizer.py
────────────────────
GeneticOptimizer — drives a population-based search over the StrategyGenome
parameter space, guided by FitnessEvaluator.composite_score.

Operators:
  Tournament selection — prevents premature convergence
  Uniform crossover    — each gene independently drawn from either parent
  Gaussian mutation    — each gene perturbed by +/- 10–30% of its range

MonteCarloValidator — stress-tests a genome by shuffling trade order n_simulations
times and computing distribution of cumulative PnL and maximum drawdown.

Usage (async context not required — optimizer is synchronous):
    optimizer = GeneticOptimizer(evaluator, db_path=Path("data/agents.db"))
    population = optimizer.initialize_population(base_cfg)
    for gen in range(50):
        gen_result = optimizer.evolve_one_generation()
        print(gen_result.best_fitness.composite_score)
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GenerationResult:
    """Summary of one completed GA generation."""
    generation: int
    best_genome: "StrategyGenome"           # type: ignore[name-defined]
    best_fitness: "FitnessResult"           # type: ignore[name-defined]
    population_size: int
    avg_composite_score: float
    new_candidates_validated: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class MonteCarloResult:
    """Distribution statistics from shuffled-trade Monte Carlo simulation."""
    median_pnl: float
    percentile_5_pnl: float            # worst-case PnL at 95% confidence
    percentile_95_pnl: float
    median_max_dd: float
    percentile_95_max_dd: float
    passed: bool                        # True if p5_pnl > -2000 and p95_dd < 25%


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _percentile(sorted_values: list[float], pct: float) -> float:
    """Return the pct-th percentile from an already-sorted list."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = (pct / 100.0) * (n - 1)
    lo  = int(idx)
    hi  = lo + 1
    if hi >= n:
        return sorted_values[-1]
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _compute_max_drawdown(cumulative_pnls: list[float]) -> float:
    """
    Compute maximum drawdown percentage from a cumulative PnL sequence.
    Returns the maximum peak-to-trough decline expressed as a percentage of
    the peak value at the time the drawdown occurred.
    """
    if not cumulative_pnls:
        return 0.0
    peak          = cumulative_pnls[0]
    max_dd_pct    = 0.0
    for v in cumulative_pnls:
        if v > peak:
            peak = v
        if peak > 1e-10:
            dd_pct = (peak - v) / peak * 100.0
        else:
            # When peak is zero or negative, use absolute dollar drawdown
            dd_pct = max(0.0, peak - v)
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
    return max_dd_pct


# ─────────────────────────────────────────────────────────────────────────────
# MonteCarloValidator
# ─────────────────────────────────────────────────────────────────────────────

class MonteCarloValidator:
    """
    Stress-test a genome by shuffling the observed trade sequence and
    recomputing PnL distribution and max drawdown for each shuffle.

    Parameters
    ----------
    seed : int | None
        Optional RNG seed for reproducibility.
    """

    PASS_P5_PNL   = -2000.0    # 5th-percentile PnL must be above this ($)
    PASS_P95_DD   = 25.0       # 95th-percentile max drawdown must be below this (%)

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def validate(
        self,
        genome: "StrategyGenome",           # type: ignore[name-defined]
        trades: list[dict],
        n_simulations: int = 500,
    ) -> MonteCarloResult:
        """
        Shuffle trade order n_simulations times; collect PnL and max-DD
        distributions; return MonteCarloResult.
        """
        if not trades:
            return MonteCarloResult(
                median_pnl=0.0,
                percentile_5_pnl=0.0,
                percentile_95_pnl=0.0,
                median_max_dd=0.0,
                percentile_95_max_dd=0.0,
                passed=False,
            )

        base_pnls = [float(t.get("pnl", 0.0)) for t in trades]
        sim_total_pnls: list[float] = []
        sim_max_dds:    list[float] = []

        for _ in range(n_simulations):
            shuffled = list(base_pnls)
            self._rng.shuffle(shuffled)

            # Build cumulative PnL curve
            cumulative: list[float] = []
            running = 0.0
            for p in shuffled:
                running += p
                cumulative.append(running)

            sim_total_pnls.append(running)
            sim_max_dds.append(_compute_max_drawdown(cumulative))

        sim_total_pnls.sort()
        sim_max_dds.sort()

        median_pnl    = _percentile(sim_total_pnls, 50.0)
        p5_pnl        = _percentile(sim_total_pnls, 5.0)
        p95_pnl       = _percentile(sim_total_pnls, 95.0)
        median_dd     = _percentile(sim_max_dds, 50.0)
        p95_dd        = _percentile(sim_max_dds, 95.0)

        passed = (p5_pnl > self.PASS_P5_PNL) and (p95_dd < self.PASS_P95_DD)

        logger.debug(
            "MonteCarlo[%d sims] P5_PnL=%.2f  P95_PnL=%.2f  P95_DD=%.2f%%  passed=%s",
            n_simulations, p5_pnl, p95_pnl, p95_dd, passed,
        )

        return MonteCarloResult(
            median_pnl=round(median_pnl, 2),
            percentile_5_pnl=round(p5_pnl, 2),
            percentile_95_pnl=round(p95_pnl, 2),
            median_max_dd=round(median_dd, 4),
            percentile_95_max_dd=round(p95_dd, 4),
            passed=passed,
        )


# ─────────────────────────────────────────────────────────────────────────────
# GeneticOptimizer
# ─────────────────────────────────────────────────────────────────────────────

class GeneticOptimizer:
    """
    Population-based genetic algorithm optimiser over the StrategyGenome space.

    Parameters
    ----------
    fitness_evaluator : FitnessEvaluator
        Evaluator instance (already configured with base_cfg + csv_path).
    db_path : Path
        SQLite agents.db path — validated genomes are persisted here.
    population_size : int
        Target population count (including elites).
    elite_size : int
        Number of top genomes carried forward unchanged each generation.
    tournament_size : int
        Candidate pool size for tournament selection.
    mutation_rate : float
        Probability (0–1) that any individual parameter is mutated.
    crossover_rate : float
        Probability (0–1) that two parents produce offspring via crossover
        rather than direct copy.
    seed : int | None
        Optional RNG seed.
    """

    def __init__(
        self,
        fitness_evaluator: "FitnessEvaluator",   # type: ignore[name-defined]
        db_path: Path,
        population_size: int = 30,
        elite_size: int = 5,
        tournament_size: int = 3,
        mutation_rate: float = 0.15,
        crossover_rate: float = 0.70,
        seed: int | None = None,
    ) -> None:
        from .fitness_evaluator import FitnessEvaluator  # noqa: F401 — for type guard

        self._evaluator      = fitness_evaluator
        self._db_path        = Path(db_path)
        self.population_size = population_size
        self.elite_size      = min(elite_size, population_size)
        self.tournament_size = max(2, tournament_size)
        self.mutation_rate   = mutation_rate
        self.crossover_rate  = crossover_rate
        self._rng            = random.Random(seed)

        # State
        # Each element: (StrategyGenome, FitnessResult | None)
        self.population: list[tuple["StrategyGenome", Optional["FitnessResult"]]] = []  # type: ignore[name-defined]
        self.generation_number: int = 0

        # Ensure DB schema exists
        self._init_db()

    # ── Public API ──────────────────────────────────────────────────────────

    def initialize_population(self, base_cfg: dict) -> list["StrategyGenome"]:  # type: ignore[name-defined]
        """
        Seed the initial population:
          1. One genome extracted from base_cfg (the "current production" strategy)
          2. Any previously validated genomes from agents.db (status='validated')
          3. Random genomes to fill up to population_size

        Returns the list of genomes (also stored in self.population).
        """
        from .strategy_genome import StrategyGenome

        genomes: list[StrategyGenome] = []

        # 1. Base config genome
        base_genome = StrategyGenome.from_cfg(base_cfg)
        genomes.append(base_genome)
        logger.debug("Population seed: added base_cfg genome %s", base_genome.genome_hash())

        # 2. Previously validated genomes from agents.db
        try:
            from ..shared_db import connect, get_strategy_candidates
            with connect(self._db_path) as conn:
                candidates = get_strategy_candidates(conn, status="validated", limit=self.population_size)
            for c in candidates:
                try:
                    g = StrategyGenome.from_dict(c["genome"])
                    genomes.append(g)
                    logger.debug("Population seed: loaded validated genome %s from db", g.genome_hash())
                except Exception as exc:
                    logger.debug("Skipping malformed db genome: %s", exc)
        except Exception as exc:
            logger.warning("Could not load validated genomes from db: %s", exc)

        # 3. Fill remainder with random genomes
        while len(genomes) < self.population_size:
            genomes.append(StrategyGenome.random(self._rng))

        # Trim to population_size (in case db returned many)
        genomes = genomes[:self.population_size]

        # Build population with no fitness yet (will be evaluated in evolve_one_generation)
        self.population = [(g, None) for g in genomes]
        self.generation_number = 0

        logger.debug(
            "Population initialised: %d genomes (%d from db, %d random)",
            len(genomes),
            min(len(genomes) - 1, self.population_size),
            max(0, self.population_size - len(genomes)),
        )
        return genomes

    def evolve_one_generation(self) -> GenerationResult:
        """
        One full GA cycle:
          1. Evaluate any unevaluated genomes in the current population
          2. Sort by composite_score (desc)
          3. Elites pass through unchanged
          4. Remainder is filled via tournament selection + crossover + mutation
          5. Return GenerationResult summary

        The population is updated in-place: self.population always reflects
        the *current* generation after this call.
        """
        from .strategy_genome import StrategyGenome
        from .fitness_evaluator import FitnessResult

        self.generation_number += 1
        logger.debug("=== Generation %d — evaluating population ===", self.generation_number)

        # ── Step 1: evaluate unevaluated genomes ───────────────────────────
        new_validated = 0
        evaluated_population: list[tuple[StrategyGenome, FitnessResult]] = []

        for genome, fitness in self.population:
            if fitness is None:
                fitness = self._evaluator.evaluate(genome)
                if fitness.passed_minimum:
                    new_validated += 1
                    self.persist_candidate(genome, fitness, self.generation_number)
                logger.debug(
                    "Gen %d | Evaluated %s → score=%.4f passed=%s",
                    self.generation_number, genome.genome_hash(),
                    fitness.composite_score, fitness.passed_minimum,
                )
            evaluated_population.append((genome, fitness))

        # ── Step 2: sort by composite_score descending ─────────────────────
        evaluated_population.sort(key=lambda x: x[1].composite_score, reverse=True)

        best_genome, best_fitness = evaluated_population[0]
        scores = [f.composite_score for _, f in evaluated_population]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        logger.debug(
            "Gen %d | Best=%.4f  Avg=%.4f  NewValidated=%d",
            self.generation_number, best_fitness.composite_score,
            avg_score, new_validated,
        )

        # ── Step 3: build next generation ──────────────────────────────────
        next_population: list[tuple[StrategyGenome, Optional[FitnessResult]]] = []

        # Elites carry through with their fitness scores (no re-evaluation needed)
        for i in range(min(self.elite_size, len(evaluated_population))):
            next_population.append(evaluated_population[i])

        # Fill remainder
        while len(next_population) < self.population_size:
            parent1 = self.tournament_select(evaluated_population, self.tournament_size)
            parent2 = self.tournament_select(evaluated_population, self.tournament_size)

            if self._rng.random() < self.crossover_rate:
                child1, child2 = self.crossover(parent1, parent2)
            else:
                child1, child2 = parent1, parent2

            child1 = self.mutate(child1)
            child2 = self.mutate(child2)

            next_population.append((child1, None))
            if len(next_population) < self.population_size:
                next_population.append((child2, None))

        self.population = next_population[:self.population_size]

        return GenerationResult(
            generation=self.generation_number,
            best_genome=best_genome,
            best_fitness=best_fitness,
            population_size=len(self.population),
            avg_composite_score=round(avg_score, 6),
            new_candidates_validated=new_validated,
            timestamp=time.time(),
        )

    def mutate(self, genome: "StrategyGenome") -> "StrategyGenome":  # type: ignore[name-defined]
        """
        Gaussian-style mutation: each parameter perturbed with probability
        mutation_rate by a random fraction (10–30%) of its valid range.
        Boolean fields are flipped with mutation_rate probability.
        Returns a new clamped genome.
        """
        from .strategy_genome import StrategyGenome, _BOUNDS, _INT_FIELDS, _BOOL_FIELDS

        d = genome.to_dict()

        for fname, (lo, hi) in _BOUNDS.items():
            if self._rng.random() > self.mutation_rate:
                continue
            param_range = float(hi) - float(lo)
            # Perturbation magnitude: uniformly drawn between 10% and 30% of range
            magnitude = self._rng.uniform(0.10, 0.30) * param_range
            # Direction: +/-
            delta = magnitude * (1 if self._rng.random() < 0.5 else -1)

            if fname in _INT_FIELDS:
                d[fname] = int(round(float(d[fname]) + delta))
            else:
                d[fname] = float(d[fname]) + delta

        for fname in _BOOL_FIELDS:
            if self._rng.random() < self.mutation_rate:
                d[fname] = not bool(d[fname])

        return StrategyGenome.from_dict(d).clamp()

    def crossover(
        self,
        parent1: "StrategyGenome",  # type: ignore[name-defined]
        parent2: "StrategyGenome",  # type: ignore[name-defined]
    ) -> "tuple[StrategyGenome, StrategyGenome]":  # type: ignore[name-defined]
        """
        Uniform crossover: each parameter is independently assigned from
        either parent1 or parent2 with 50/50 probability.
        Produces two children.
        """
        from .strategy_genome import StrategyGenome

        d1 = parent1.to_dict()
        d2 = parent2.to_dict()
        c1: dict = {}
        c2: dict = {}

        for key in d1:
            if self._rng.random() < 0.5:
                c1[key] = d1[key]
                c2[key] = d2[key]
            else:
                c1[key] = d2[key]
                c2[key] = d1[key]

        child1 = StrategyGenome.from_dict(c1).clamp()
        child2 = StrategyGenome.from_dict(c2).clamp()
        return child1, child2

    def tournament_select(
        self,
        population: list[tuple["StrategyGenome", "FitnessResult"]],  # type: ignore[name-defined]
        k: int,
    ) -> "StrategyGenome":  # type: ignore[name-defined]
        """
        Draw k random candidates from the population (with replacement) and
        return the genome with the highest composite_score.
        """
        if not population:
            raise ValueError("tournament_select called on empty population")

        k = min(k, len(population))
        candidates = self._rng.choices(population, k=k)
        winner = max(candidates, key=lambda x: x[1].composite_score)
        return winner[0]

    def persist_candidate(
        self,
        genome: "StrategyGenome",   # type: ignore[name-defined]
        fitness: "FitnessResult",   # type: ignore[name-defined]
        generation: int,
    ) -> None:
        """
        Persist a genome + fitness to agents.db strategy_candidates table via
        shared_db.upsert_strategy_candidate.
        """
        from ..shared_db import connect, upsert_strategy_candidate

        fitness_dict = {
            "expectancy":        fitness.expectancy,
            "profit_factor":     fitness.profit_factor,
            "sharpe_ratio":      fitness.sharpe_ratio,
            "sortino_ratio":     fitness.sortino_ratio,
            "max_drawdown_pct":  fitness.max_drawdown_pct,
            "win_rate":          fitness.win_rate,
            "total_trades":      fitness.total_trades,
            "stability_score":   fitness.stability_score,
            "recovery_factor":   fitness.recovery_factor,
            "composite_score":   fitness.composite_score,
        }

        try:
            with connect(self._db_path) as conn:
                upsert_strategy_candidate(
                    conn,
                    genome_hash=genome.genome_hash(),
                    genome=genome.to_dict(),
                    status="validated",
                    fitness=fitness_dict,
                    generation=generation,
                )
            logger.debug(
                "Persisted genome %s (gen=%d, score=%.4f)",
                genome.genome_hash(), generation, fitness.composite_score,
            )
        except Exception as exc:
            logger.warning("Failed to persist genome %s: %s", genome.genome_hash(), exc)

    # ── Internal ────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Ensure agents.db schema is initialised."""
        try:
            from ..shared_db import init_schema
            init_schema(self._db_path)
        except Exception as exc:
            logger.warning("Could not initialise agents.db schema: %s", exc)
