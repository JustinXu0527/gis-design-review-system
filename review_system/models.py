from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DesignObject(BaseModel):
    """Unified engineering object parsed from GIS design deliverables."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    name: str
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    calculation: str
    actual_value: float | str | None = None
    threshold: float | str | None = None
    unit: str = ""
    object_ids: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RiskFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    category: str
    level: str
    description: str
    impact: str
    recommendation: str
    priority: int
    clause: dict[str, Any]
    evidence: ReviewEvidence
    geometry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        item = self.model_dump(mode="json")
        item["evidence"] = self.evidence.to_dict()
        return item
