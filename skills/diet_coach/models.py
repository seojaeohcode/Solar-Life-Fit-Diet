"""Pydantic schemas for Solar Diet Master skill.

Ported from diet.md §6.2 — single-user diet journal with reward+policy fields.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class DietMode(str, Enum):
    FAST = "Fast"
    NORMAL = "Normal"
    DEFICIT = "Deficit"


class ActivityMode(str, Enum):
    REST = "Rest"
    ACTIVE = "Active"
    INTENSE = "Intense"


class Phase(str, Enum):
    ONBOARDING = "onboarding"
    FAT_LOSS = "fat_loss"
    PLATEAU = "plateau"
    MAINTENANCE = "maintenance"


class DailyEntry(BaseModel):
    """A single day's diet journal record."""

    date: str = Field(..., description="YYYY-MM-DD")
    weight_kg: float = Field(..., ge=20.0, le=300.0)
    calories_in: Optional[float] = Field(None, ge=0.0)
    steps: Optional[int] = Field(None, ge=0)
    exercises_done: List[str] = Field(default_factory=list)
    exercise_note: str = ""
    sleep_hours: Optional[float] = Field(None, ge=0.0, le=24.0)
    sleep_quality: Optional[float] = Field(None, ge=0.0, le=1.0)
    diet: DietMode = DietMode.NORMAL
    activity: ActivityMode = ActivityMode.ACTIVE
    notes: str = ""
    water_ml: Optional[int] = Field(None, ge=0)

    @field_validator("date")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        date.fromisoformat(v)
        return v


class Journal(BaseModel):
    entries: List[DailyEntry] = Field(default_factory=list)


class ExtractedFields(BaseModel):
    """Solar Chat(JSON schema)로 비정형 일기에서 구조화 추출 — 평가지표: 체중(kg)+식단 키워드."""

    weight_kg: Optional[float] = None
    calories_in: Optional[float] = None
    steps: Optional[int] = None
    sleep_hours: Optional[float] = None
    sleep_quality: Optional[float] = None
    exercises_done: List[str] = Field(default_factory=list)
    exercise_note: str = ""
    notes: str = ""
    diet_keywords: List[str] = Field(
        default_factory=list,
        description="어제 식사에서 읽힌 음식·패턴 키워드(한국어): 예) 야식, 회식, 라면, 샐러드, 닭가슴살, 단식",
    )


class RewardBreakdown(BaseModel):
    """Components of the composite single-step reward (diet.md §5.1)."""

    total: float
    R_weight: float
    R_consistency: float
    R_habit: float
    R_goal: float
    P_risk: float
    R_t: Optional[float] = None
    R_delayed: Optional[float] = None
    ma_window_days: int = 7


class PolicyDecision(BaseModel):
    """Heuristic policy output (diet.md §5.2 — A1~A9)."""

    mode: str  # "safety" | "explore" | "exploit"
    action_id: str  # "A1" .. "A9"
    diet: DietMode
    activity: ActivityMode
    message: str


class ProactiveWarning(BaseModel):
    """A single risk-pattern warning emitted by Proactive Coaching."""

    pattern: str  # e.g. "rapid_weight_loss"
    severity: str  # "info" | "warn" | "alert"
    message: str
    evidence: dict = Field(default_factory=dict)


class NaturalEntryRequest(BaseModel):
    narrative: str = Field(..., min_length=1)
    date: Optional[str] = Field(None, description="YYYY-MM-DD; defaults to today")
    weight_kg: Optional[float] = None  # hint; LLM extracts if missing
    force: bool = False  # override record-window check


class NaturalEntryResponse(BaseModel):
    extracted: ExtractedFields
    saved_entry: DailyEntry
    reward: RewardBreakdown
    policy: PolicyDecision
    phase: Phase
    proactive_warnings: List[ProactiveWarning] = Field(default_factory=list)
    ma_reward_explanation_ko: str = Field(
        default="",
        description="7일 MA 기반 R_weight 해석(에이전트/사용자 투명성·창의성 지표용)",
    )
    extraction_quality_flags: List[str] = Field(
        default_factory=list,
        description="예: weight_regex_crosscheck_ok, diet_keywords_non_empty",
    )


class CoachRequest(BaseModel):
    weight_kg: Optional[float] = None
    narrative: Optional[str] = None
    use_latest: bool = False
    session_caution: str = ""


class CoachResponse(BaseModel):
    coaching_markdown: str
    phase: Phase
    reward_summary: RewardBreakdown
    proactive_warnings: List[ProactiveWarning] = Field(default_factory=list)


class ProgressResponse(BaseModel):
    series: List[dict]  # [{date, weight_kg, ma7}]
    reward: RewardBreakdown
    policy: Optional[PolicyDecision] = None
    phase: Phase
    goal_kg: Optional[float] = None
    ma_reward_explanation_ko: str = ""
