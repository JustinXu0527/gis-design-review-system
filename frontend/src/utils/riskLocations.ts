import type { Geometry, RiskFinding, RiskLevel } from "@/types";
import type { RiskCountSummary } from "@/utils/format";

export interface RiskLocation {
  id: string;
  objectIds: string[];
  geometry?: Geometry | null;
  level: RiskLevel;
  risks: RiskFinding[];
}

const levelOrder: Record<string, number> = { high: 3, medium: 2, low: 1, unknown: 0 };

export function higherRiskLevel(current: RiskLevel, candidate: RiskLevel): RiskLevel {
  return (levelOrder[String(candidate)] || 0) > (levelOrder[String(current)] || 0) ? candidate : current;
}

export function groupRisksByLocation(risks: RiskFinding[] = []): RiskLocation[] {
  const groups = new Map<string, RiskLocation>();
  for (const risk of risks) {
    const objectIds = [...(risk.evidence?.object_ids || [])].filter(Boolean).sort();
    const key = objectIds.length
      ? `object:${objectIds.join("|")}`
      : risk.geometry
        ? `geometry:${JSON.stringify(risk.geometry)}`
        : `unlocated:${risk.id}`;
    const existing = groups.get(key);
    if (existing) {
      existing.risks.push(risk);
      existing.level = higherRiskLevel(existing.level, risk.level);
      if (!existing.geometry && risk.geometry) existing.geometry = risk.geometry;
      continue;
    }
    groups.set(key, {
      id: key,
      objectIds,
      geometry: risk.geometry,
      level: risk.level || "unknown",
      risks: [risk],
    });
  }
  return [...groups.values()];
}

export function riskLocationCounts(risks: RiskFinding[] = [], locatableOnly = false): RiskCountSummary {
  const locations = groupRisksByLocation(risks).filter((location) => !locatableOnly || Boolean(location.geometry));
  return locations.reduce<RiskCountSummary>(
    (acc, location) => {
      const level = String(location.level || "unknown");
      acc.total += 1;
      acc[level] = (acc[level] || 0) + 1;
      return acc;
    },
    { total: 0, high: 0, medium: 0, low: 0, unknown: 0 },
  );
}
