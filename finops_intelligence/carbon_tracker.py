"""
finops_intelligence/carbon_tracker.py
=======================================

CarbonTracker — cloud carbon emissions estimator.

Computes monthly CO2e emissions for cloud workloads using the Cloud Carbon
Footprint (CCF) open-source coefficients dataset.

Emissions Methodology:
    kgCO2e = vCPU_hours * kgCO2e_per_vcpu_hour
           + GB_RAM_hours * kgCO2e_per_gb_ram_hour

Where:
    kgCO2e_per_vcpu_hour = grid_intensity (kgCO2e/kWh)
                           * server_power_per_vcpu (kWh)
                           * PUE (Power Usage Effectiveness)

Coefficients are sourced from the Cloud Carbon Footprint open dataset:
    https://www.cloudcarbonfootprint.org/docs/methodology
    https://github.com/cloud-carbon-footprint/cloud-carbon-footprint
    License: Apache 2.0

The bundled CSV (data/emissions_coefficients.csv) covers ~90 rows across
major AWS, Azure, and GCP regions and instance families.

No new dependencies — uses pandas, numpy (all in requirements.txt).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Coefficients path
# ---------------------------------------------------------------------------

_COEFFICIENTS_PATH = Path(__file__).parent / "data" / "emissions_coefficients.csv"

# Hours in a calendar month (30.4 days average)
_HOURS_PER_MONTH = 730.0

# Default fallback coefficient when region+family not found
_DEFAULT_VCPU_KGC02E_HOUR = 0.000379   # us-east-1 average
_DEFAULT_GB_RAM_KGC02E_HOUR = 0.000047


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WorkloadEmissions:
    """Carbon footprint for a single workload."""

    resource_id: str
    instance_type: str
    region: str
    cloud: str
    instance_family: str
    vcpu: int
    ram_gb: float
    monthly_vcpu_hours: float
    monthly_ram_gb_hours: float
    monthly_kgco2e: float
    monthly_kgco2e_compute: float
    monthly_kgco2e_memory: float
    kgco2e_per_vcpu_hour: float
    kgco2e_per_gb_ram_hour: float
    coefficient_source: str        # 'exact' | 'family_fallback' | 'region_fallback' | 'default'


@dataclass
class RegionAggregate:
    """Carbon footprint aggregated per region."""

    cloud: str
    region: str
    region_display: str
    workload_count: int
    monthly_kgco2e: float
    grid_intensity_gco2_kwh: float
    green_region_alternative: Optional[str] = None
    green_region_savings_kgco2e: Optional[float] = None


@dataclass
class GreenMigrationOpportunity:
    """A specific recommendation to move workloads to a lower-carbon region."""

    resource_id: str
    current_region: str
    target_region: str
    current_monthly_kgco2e: float
    target_monthly_kgco2e: float
    savings_kgco2e_monthly: float
    savings_pct: float
    cloud: str


@dataclass
class CarbonReport:
    """Full carbon footprint report for a fleet of workloads."""

    total_monthly_kgco2e: float
    total_monthly_tonnes_co2e: float
    per_workload: list[WorkloadEmissions] = field(default_factory=list)
    per_region: list[RegionAggregate] = field(default_factory=list)
    top_emitters: list[WorkloadEmissions] = field(default_factory=list)
    green_migration_opportunities: list[GreenMigrationOpportunity] = field(default_factory=list)
    optimization_suggestions: list[str] = field(default_factory=list)
    coefficient_coverage_pct: float = 0.0   # % of workloads matched to exact coefficients

    @property
    def monthly_tco2e(self) -> float:
        return self.total_monthly_tonnes_co2e

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_monthly_kgco2e": round(self.total_monthly_kgco2e, 2),
            "total_monthly_tco2e": round(self.total_monthly_tonnes_co2e, 4),
            "workload_count": len(self.per_workload),
            "top_emitters": [
                {
                    "resource_id": w.resource_id,
                    "instance_type": w.instance_type,
                    "region": w.region,
                    "monthly_kgco2e": round(w.monthly_kgco2e, 4),
                }
                for w in self.top_emitters[:10]
            ],
            "per_region_summary": [
                {
                    "region": r.region,
                    "cloud": r.cloud,
                    "monthly_kgco2e": round(r.monthly_kgco2e, 4),
                    "workload_count": r.workload_count,
                    "green_alternative": r.green_region_alternative,
                    "green_savings_kgco2e": round(r.green_region_savings_kgco2e, 4)
                    if r.green_region_savings_kgco2e else None,
                }
                for r in sorted(self.per_region, key=lambda x: x.monthly_kgco2e, reverse=True)
            ],
            "green_migration_count": len(self.green_migration_opportunities),
            "total_green_migration_savings_kgco2e": round(
                sum(op.savings_kgco2e_monthly for op in self.green_migration_opportunities), 4
            ),
            "optimization_suggestions": self.optimization_suggestions,
            "coefficient_coverage_pct": round(self.coefficient_coverage_pct, 1),
        }


# ---------------------------------------------------------------------------
# Coefficient loader
# ---------------------------------------------------------------------------

class _CoefficientTable:
    """Cached emissions coefficient lookup table."""

    _df: Optional[pd.DataFrame] = None

    @classmethod
    def load(cls) -> pd.DataFrame:
        if cls._df is None:
            cls._df = pd.read_csv(_COEFFICIENTS_PATH, comment="#")
            cls._df["cloud"] = cls._df["cloud"].str.upper()
            cls._df["region"] = cls._df["region"].str.lower()
            cls._df["instance_family"] = cls._df["instance_family"].str.lower()
        return cls._df

    @classmethod
    def lookup(cls, cloud: str, region: str, instance_family: str) -> tuple[float, float, str]:
        """Return (kgCO2e_per_vcpu_hour, kgCO2e_per_gb_ram_hour, source).

        Falls back: exact match -> family fallback -> region fallback -> default.
        """
        df = cls.load()
        cloud_up = cloud.upper()
        region_lo = region.lower()
        family_lo = instance_family.lower()

        # Exact match
        mask = (df["cloud"] == cloud_up) & (df["region"] == region_lo) & (df["instance_family"] == family_lo)
        row = df[mask]
        if not row.empty:
            r = row.iloc[0]
            return float(r["kgCO2e_per_vcpu_hour"]), float(r["kgCO2e_per_gb_ram_hour"]), "exact"

        # Family fallback (same cloud+region, any family)
        mask2 = (df["cloud"] == cloud_up) & (df["region"] == region_lo)
        row2 = df[mask2]
        if not row2.empty:
            vcpu = float(row2["kgCO2e_per_vcpu_hour"].mean())
            ram = float(row2["kgCO2e_per_gb_ram_hour"].mean())
            return vcpu, ram, "family_fallback"

        # Region fallback (same cloud)
        mask3 = df["cloud"] == cloud_up
        row3 = df[mask3]
        if not row3.empty:
            vcpu = float(row3["kgCO2e_per_vcpu_hour"].mean())
            ram = float(row3["kgCO2e_per_gb_ram_hour"].mean())
            return vcpu, ram, "region_fallback"

        return _DEFAULT_VCPU_KGC02E_HOUR, _DEFAULT_GB_RAM_KGC02E_HOUR, "default"

    @classmethod
    def lowest_emission_region(cls, cloud: str, current_region: str) -> Optional[tuple[str, float]]:
        """Return (region_name, kgCO2e_per_vcpu_hour) for the greenest region of this cloud.

        Returns None if only one region available.
        """
        df = cls.load()
        cloud_df = df[df["cloud"] == cloud.upper()]
        if cloud_df.empty:
            return None
        agg = cloud_df.groupby("region")["kgCO2e_per_vcpu_hour"].mean().reset_index()
        agg = agg.sort_values("kgCO2e_per_vcpu_hour")
        best = agg.iloc[0]
        if best["region"] == current_region.lower():
            if len(agg) > 1:
                best = agg.iloc[1]
            else:
                return None
        return str(best["region"]), float(best["kgCO2e_per_vcpu_hour"])


# ---------------------------------------------------------------------------
# CarbonTracker
# ---------------------------------------------------------------------------

class CarbonTracker:
    """Estimates cloud carbon emissions for a fleet of workloads.

    Usage::

        tracker = CarbonTracker()
        report = tracker.estimate(workloads, cloud="AWS")
        print(report.total_monthly_tco2e, "tCO2e/month")
    """

    def __init__(self, cloud: str = "AWS") -> None:
        self._cloud = cloud.upper()

    def estimate(
        self,
        workloads: list[Any],
        cloud: Optional[str] = None,
    ) -> CarbonReport:
        """Estimate monthly carbon emissions for all workloads.

        Args:
            workloads: List of objects with at minimum:
                       resource_id, instance_type, region attrs.
                       Optional: vcpu (int), ram_gb (float), monthly_hours (float).
            cloud: Cloud provider ('AWS', 'Azure', 'GCP'). Falls back to self._cloud.

        Returns:
            CarbonReport with per-workload and per-region breakdowns.
        """
        cloud = (cloud or self._cloud).upper()
        per_workload: list[WorkloadEmissions] = []
        exact_matches = 0

        from .right_sizer import _InstanceCatalog  # lazy import avoids circular dep

        for wl in workloads:
            resource_id = getattr(wl, "resource_id", str(id(wl)))
            instance_type = getattr(wl, "instance_type", "m5.large")
            region = getattr(wl, "region", "us-east-1")

            # Extract instance family
            import re
            m = re.match(r"^([a-z][0-9]+[a-z]*)", instance_type.lower())
            instance_family = m.group(1) if m else "m5"

            # Get spec from catalog if available
            spec = _InstanceCatalog.get(instance_type)
            vcpu = getattr(wl, "vcpu", spec["vcpu"] if spec else 2)
            ram_gb = getattr(wl, "ram_gb", spec["ram_gb"] if spec else 8.0)
            monthly_hours = getattr(wl, "monthly_hours", _HOURS_PER_MONTH)

            vcpu_coeff, ram_coeff, source = _CoefficientTable.lookup(cloud, region, instance_family)
            if source == "exact":
                exact_matches += 1

            monthly_vcpu_hours = vcpu * monthly_hours
            monthly_ram_hours = ram_gb * monthly_hours
            compute_co2e = monthly_vcpu_hours * vcpu_coeff
            memory_co2e = monthly_ram_hours * ram_coeff
            total_co2e = compute_co2e + memory_co2e

            per_workload.append(WorkloadEmissions(
                resource_id=resource_id,
                instance_type=instance_type,
                region=region,
                cloud=cloud,
                instance_family=instance_family,
                vcpu=int(vcpu),
                ram_gb=float(ram_gb),
                monthly_vcpu_hours=round(monthly_vcpu_hours, 2),
                monthly_ram_gb_hours=round(monthly_ram_hours, 2),
                monthly_kgco2e=round(total_co2e, 6),
                monthly_kgco2e_compute=round(compute_co2e, 6),
                monthly_kgco2e_memory=round(memory_co2e, 6),
                kgco2e_per_vcpu_hour=vcpu_coeff,
                kgco2e_per_gb_ram_hour=ram_coeff,
                coefficient_source=source,
            ))

        if not per_workload:
            return CarbonReport(
                total_monthly_kgco2e=0.0,
                total_monthly_tonnes_co2e=0.0,
                optimization_suggestions=["No workloads provided."],
            )

        total_kg = sum(w.monthly_kgco2e for w in per_workload)
        coverage_pct = (exact_matches / len(per_workload) * 100) if per_workload else 0.0

        # Per-region aggregation
        per_region = self._aggregate_regions(per_workload, cloud)

        # Top emitters (by monthly CO2e)
        top_emitters = sorted(per_workload, key=lambda w: w.monthly_kgco2e, reverse=True)[:10]

        # Green migration opportunities
        green_ops = self._compute_green_migrations(per_workload, cloud)

        # Optimization suggestions
        suggestions = self._build_suggestions(per_workload, per_region, green_ops, total_kg)

        return CarbonReport(
            total_monthly_kgco2e=round(total_kg, 4),
            total_monthly_tonnes_co2e=round(total_kg / 1000, 6),
            per_workload=per_workload,
            per_region=per_region,
            top_emitters=top_emitters,
            green_migration_opportunities=green_ops,
            optimization_suggestions=suggestions,
            coefficient_coverage_pct=round(coverage_pct, 1),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _aggregate_regions(
        self, per_workload: list[WorkloadEmissions], cloud: str
    ) -> list[RegionAggregate]:
        df = pd.DataFrame([
            {"cloud": w.cloud, "region": w.region, "monthly_kgco2e": w.monthly_kgco2e}
            for w in per_workload
        ])
        agg = df.groupby(["cloud", "region"]).agg(
            monthly_kgco2e=("monthly_kgco2e", "sum"),
            workload_count=("monthly_kgco2e", "count"),
        ).reset_index()

        result: list[RegionAggregate] = []
        coeff_df = _CoefficientTable.load()
        for _, row in agg.iterrows():
            r_cloud = str(row["cloud"])
            r_region = str(row["region"])
            grid_mask = (coeff_df["cloud"] == r_cloud) & (coeff_df["region"] == r_region.lower())
            grid_row = coeff_df[grid_mask]
            grid_intensity = float(grid_row["grid_intensity_gco2_kwh"].mean()) if not grid_row.empty else 0.0
            region_display = str(grid_row["region_display"].iloc[0]) if not grid_row.empty else r_region

            # Find greener alternative
            best_alt = _CoefficientTable.lowest_emission_region(r_cloud, r_region)
            green_alt = None
            green_savings = None
            if best_alt:
                alt_region, alt_vcpu_coeff = best_alt
                current_vcpu_coeff_mask = (coeff_df["cloud"] == r_cloud) & (coeff_df["region"] == r_region.lower())
                cur_coeff_rows = coeff_df[current_vcpu_coeff_mask]
                cur_avg = float(cur_coeff_rows["kgCO2e_per_vcpu_hour"].mean()) if not cur_coeff_rows.empty else _DEFAULT_VCPU_KGC02E_HOUR
                if cur_avg > 0 and alt_vcpu_coeff < cur_avg * 0.9:  # Only suggest if 10%+ improvement
                    green_alt = alt_region
                    improvement_ratio = 1.0 - (alt_vcpu_coeff / cur_avg)
                    green_savings = float(row["monthly_kgco2e"]) * improvement_ratio

            result.append(RegionAggregate(
                cloud=r_cloud,
                region=r_region,
                region_display=region_display,
                workload_count=int(row["workload_count"]),
                monthly_kgco2e=round(float(row["monthly_kgco2e"]), 4),
                grid_intensity_gco2_kwh=grid_intensity,
                green_region_alternative=green_alt,
                green_region_savings_kgco2e=round(green_savings, 4) if green_savings else None,
            ))
        return sorted(result, key=lambda r: r.monthly_kgco2e, reverse=True)

    def _compute_green_migrations(
        self, per_workload: list[WorkloadEmissions], cloud: str
    ) -> list[GreenMigrationOpportunity]:
        """Identify per-workload migration opportunities to greener regions."""
        ops: list[GreenMigrationOpportunity] = []
        for wl in per_workload:
            best_alt = _CoefficientTable.lowest_emission_region(cloud, wl.region)
            if best_alt is None:
                continue
            alt_region, alt_vcpu_coeff = best_alt
            # Estimate target emissions using alt region coefficient
            ratio = alt_vcpu_coeff / (wl.kgco2e_per_vcpu_hour + 1e-12)
            if ratio >= 0.90:
                continue  # Less than 10% improvement — not worth it
            target_kgco2e = wl.monthly_kgco2e * ratio
            savings = wl.monthly_kgco2e - target_kgco2e
            savings_pct = (savings / wl.monthly_kgco2e * 100) if wl.monthly_kgco2e > 0 else 0.0
            ops.append(GreenMigrationOpportunity(
                resource_id=wl.resource_id,
                current_region=wl.region,
                target_region=alt_region,
                current_monthly_kgco2e=round(wl.monthly_kgco2e, 6),
                target_monthly_kgco2e=round(target_kgco2e, 6),
                savings_kgco2e_monthly=round(savings, 6),
                savings_pct=round(savings_pct, 1),
                cloud=cloud,
            ))
        return sorted(ops, key=lambda o: o.savings_kgco2e_monthly, reverse=True)

    def _build_suggestions(
        self,
        per_workload: list[WorkloadEmissions],
        per_region: list[RegionAggregate],
        green_ops: list[GreenMigrationOpportunity],
        total_kg: float,
    ) -> list[str]:
        suggestions: list[str] = []
        if green_ops:
            top = green_ops[0]
            savings_tco2e = top.savings_kgco2e_monthly / 1000
            suggestions.append(
                f"Migrate workloads from {top.current_region} to {top.target_region} "
                f"to save up to {savings_tco2e:.3f} tCO2e/month "
                f"({top.savings_pct:.0f}% reduction for those workloads)."
            )
        high_intensity = [r for r in per_region if r.grid_intensity_gco2_kwh > 0.0004]
        if high_intensity:
            regions_str = ", ".join(r.region for r in high_intensity[:3])
            suggestions.append(
                f"Regions with high grid carbon intensity (>400 gCO2/kWh): {regions_str}. "
                "Consider migrating batch workloads to lower-carbon regions."
            )
        default_coverage = sum(1 for w in per_workload if w.coefficient_source == "default")
        if default_coverage > 0:
            suggestions.append(
                f"{default_coverage} workloads used default coefficients due to missing region/family data. "
                "Add custom coefficients to data/emissions_coefficients.csv for improved accuracy."
            )
        if total_kg > 50_000:
            suggestions.append(
                f"Total fleet emits {total_kg/1000:.1f} tCO2e/month. "
                "Consider purchasing carbon offsets or purchasing AWS Green Power."
            )
        return suggestions
