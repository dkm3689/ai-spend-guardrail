from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from cost import get_downgrade_model


class EnforcementMode(str, Enum):
    ALERT_ONLY = "alert-only"
    VISIBLE_DOWNGRADE = "visible-downgrade"
    HARD_CAP = "hard-cap"


@dataclass
class Project:
    id: str
    name: str
    budget_daily: float | None
    budget_monthly: float | None
    enforcement_mode: EnforcementMode
    telegram_chat_id: str | None


@dataclass
class EnforcementDecision:
    blocked: bool = False
    downgraded: bool = False
    original_model: str | None = None
    new_model: str | None = None
    block_reason: str | None = None


def check_enforcement(
    project: Project,
    model: str,
    daily_spend: float,
    monthly_spend: float,
) -> EnforcementDecision:
    checks = []
    if project.budget_daily:
        checks.append((daily_spend, project.budget_daily))
    if project.budget_monthly:
        checks.append((monthly_spend, project.budget_monthly))

    for spend, budget in checks:
        pct = (spend / budget) * 100
        decision = _apply_mode(project, model, pct, budget, spend)
        if decision.blocked or decision.downgraded:
            return decision

    return EnforcementDecision()


def _apply_mode(
    project: Project,
    model: str,
    pct: float,
    budget: float,
    spend: float,
) -> EnforcementDecision:
    if project.enforcement_mode == EnforcementMode.HARD_CAP and pct >= 100:
        return EnforcementDecision(
            blocked=True,
            block_reason=f"Budget exhausted: ${spend:.4f} of ${budget:.2f}",
        )

    if project.enforcement_mode == EnforcementMode.VISIBLE_DOWNGRADE and pct >= 80:
        cheaper = get_downgrade_model(model)
        if cheaper and cheaper != model:
            return EnforcementDecision(
                downgraded=True,
                original_model=model,
                new_model=cheaper,
            )

    return EnforcementDecision()
