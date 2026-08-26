"""Rule-based anomaly detector."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ..models import DetectorResult, FeatureVector, Rule, RuleCondition

logger = logging.getLogger(__name__)


class RuleDetector:
    """Evaluates feature vectors against predefined rules.

    Rules are loaded from YAML files and support operators:
    >, <, >=, <=, ==, increased
    """

    name = "rule"

    def __init__(self, rules_path: str = "./rules/"):
        self.rules: list[Rule] = []
        self._load_rules(rules_path)

    def _load_rules(self, rules_path: str) -> None:
        """Load rules from all YAML files in the rules directory."""
        rules_dir = Path(rules_path)
        if not rules_dir.exists():
            logger.warning("Rules directory not found: %s", rules_path)
            return

        for yaml_file in rules_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                for rule_data in data.get("rules", []):
                    condition = rule_data.pop("condition", {})
                    rule_data["condition"] = RuleCondition(**condition)
                    rule = Rule(**rule_data)
                    self.rules.append(rule)
                    logger.info("Loaded rule: %s (%s)", rule.id, rule.name)
            except Exception as e:
                logger.error("Failed to load rules from %s: %s", yaml_file, e)

    def evaluate(self, feature_vector: FeatureVector) -> list[DetectorResult]:
        """Evaluate feature vector against all matching enabled rules.

        Returns a list of results since multiple rules can match one metric.
        """
        results: list[DetectorResult] = []

        for rule in self.rules:
            if not rule.enabled:
                continue

            # Check if rule applies to this metric
            if rule.metric != feature_vector.metric:
                continue

            is_anomaly = self._evaluate_condition(
                rule.condition, feature_vector.current_value
            )

            if is_anomaly:
                results.append(
                    DetectorResult(
                        is_anomaly=True,
                        detector=self.name,
                        severity=rule.severity,
                        score=1.0,
                        confidence=1.0,
                        details={
                            "rule_id": rule.id,
                            "rule_name": rule.name,
                            "operator": rule.condition.operator,
                            "threshold": rule.condition.threshold,
                            "current_value": feature_vector.current_value,
                            "category": rule.category,
                        },
                    )
                )

        return results

    def _evaluate_condition(
        self, condition: RuleCondition, current_value: float
    ) -> bool:
        """Evaluate a single rule condition against the current value."""
        op = condition.operator
        threshold = condition.threshold

        if op == ">" and threshold is not None:
            return current_value > threshold
        elif op == "<" and threshold is not None:
            return current_value < threshold
        elif op == ">=" and threshold is not None:
            return current_value >= threshold
        elif op == "<=" and threshold is not None:
            return current_value <= threshold
        elif op == "==" and threshold is not None:
            return current_value == threshold
        elif op == "increased" and condition.min_increase is not None:
            return current_value >= condition.min_increase
        else:
            logger.warning("Unknown operator: %s", op)
            return False

    def add_rule(self, rule: Rule) -> None:
        """Add a rule dynamically (for API-created rules)."""
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        original_len = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < original_len

    def get_rules(self) -> list[Rule]:
        """Return all loaded rules."""
        return self.rules
