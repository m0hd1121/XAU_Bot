"""
xau_bot.learning
─────────────────
Self-learning subsystem for the XAU/USD price action bot.

Public API:

    from xau_bot.learning import LearningEngine

    engine = LearningEngine(cfg)
    engine.initialize()           # restore persisted state
    ...
    engine.shutdown()             # persist final state

Supporting types re-exported for convenience:
    FeatureVector, ConfidenceBreakdown, RegimeSnapshot
"""

from .learning_engine import LearningEngine
from .feature_extractor import FeatureVector, FeatureExtractor
from .confidence_model import ConfidenceBreakdown
from .regime_detector import RegimeSnapshot, Regime, VolRegime
from .trade_database import TradeDatabase
from .explainability_engine import ExplainabilityEngine

__all__ = [
    "LearningEngine",
    "FeatureVector",
    "FeatureExtractor",
    "ConfidenceBreakdown",
    "RegimeSnapshot",
    "Regime",
    "VolRegime",
    "TradeDatabase",
    "ExplainabilityEngine",
]
