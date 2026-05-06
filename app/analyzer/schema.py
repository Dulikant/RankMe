from typing import Literal
from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    hard_skills: int = Field(ge=0, le=100)
    experience: int = Field(ge=0, le=100)
    domain: int = Field(ge=0, le=100)
    soft_and_education: int = Field(ge=0, le=100)


class MatchingSkill(BaseModel):
    skill: str
    detail: str


class MissingItem(BaseModel):
    skill: str
    evidence: str
    why_matters: str


class WeakPresentation(BaseModel):
    skill: str
    original_text: str
    improved_text: str


class DevelopmentStep(BaseModel):
    action: str
    estimated_hours: int = Field(ge=1, le=80)
    resource: str | None = None


class RewrittenBullet(BaseModel):
    section: Literal["experience", "skills", "summary"]
    text: str
    based_on: str


class GapAnalysisReport(BaseModel):
    match_score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    one_line_verdict: str
    matching_skills: list[MatchingSkill]
    missing_critical: list[MissingItem]
    missing_nice_to_have: list[MissingItem]
    weak_presentation: list[WeakPresentation]
    development_plan: list[DevelopmentStep]
    rewritten_bullets: list[RewrittenBullet]
