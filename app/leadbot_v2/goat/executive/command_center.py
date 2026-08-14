from __future__ import annotations

import hashlib

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from leadbot_v2.goat.access_control import (
    AuthorizationEngine,
    Permission,
    Principal,
    ResourceContext,
)
from leadbot_v2.goat.data_spine.models import (
    Lead,
    Opportunity,
    Project,
    TERMINAL_OPPORTUNITY_STAGES,
)
from leadbot_v2.goat.data_spine.store import (
    InMemoryDataSpine,
)
from leadbot_v2.goat.finance.project_finance import (
    ProjectFinanceService,
    ProjectFinancialSnapshot,
)
from leadbot_v2.goat.workflow.follow_through import (
    FollowThroughEngine,
)
from leadbot_v2.goat.workforce.sales_ops import (
    SalesOperations,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutiveAuthorizationError(PermissionError):
    pass


class ExecutiveIntegrityError(RuntimeError):
    pass


class ExecutivePriority(str, Enum):
    INFO = "info"
    WATCH = "watch"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationDomain(str, Enum):
    SALES = "sales"
    FOLLOW_THROUGH = "follow_through"
    FINANCE = "finance"
    COLLECTIONS = "collections"
    MARGIN = "margin"
    OPERATIONS = "operations"
    ESTIMATING = "estimating"
    WORKFORCE = "workforce"
    EXECUTIVE = "executive"


@dataclass(frozen=True)
class ExecutiveEvidence:
    source_system: str
    entity_type: str
    entity_id: str
    metric: str
    observed_value: str
    detail: str


@dataclass(frozen=True)
class ExecutiveKPI:
    code: str
    label: str
    value: int
    unit: str
    evidence: tuple[ExecutiveEvidence, ...]

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ExecutiveIntegrityError(
                "KPI code required"
            )

        if not self.evidence:
            raise ExecutiveIntegrityError(
                f"KPI {self.code} has no provenance"
            )


@dataclass(frozen=True)
class ExecutiveRecommendation:
    recommendation_id: str
    domain: RecommendationDomain
    priority: ExecutivePriority
    title: str
    rationale: str
    suggested_action: str
    confidence: float
    evidence: tuple[ExecutiveEvidence, ...]
    advisory_only: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ExecutiveIntegrityError(
                "recommendation confidence must be 0-1"
            )

        if not self.evidence:
            raise ExecutiveIntegrityError(
                "executive recommendation cannot exist "
                "without evidence"
            )

        if not self.advisory_only:
            raise ExecutiveIntegrityError(
                "executive recommendation must remain "
                "advisory until an authorized action "
                "workflow executes it"
            )


@dataclass(frozen=True)
class ExecutiveBrief:
    tenant_id: str
    generated_at: datetime
    source_event_count: int
    kpis: tuple[ExecutiveKPI, ...]
    recommendations: tuple[ExecutiveRecommendation, ...]
    project_financials: tuple[
        ProjectFinancialSnapshot,
        ...
    ]

    @property
    def critical_count(self) -> int:
        return sum(
            1
            for item in self.recommendations
            if item.priority
            == ExecutivePriority.CRITICAL
        )

    @property
    def high_count(self) -> int:
        return sum(
            1
            for item in self.recommendations
            if item.priority
            == ExecutivePriority.HIGH
        )


@dataclass(frozen=True)
class ProjectScenario:
    revenue_delta_cents: int = 0
    cost_delta_cents: int = 0


@dataclass(frozen=True)
class ProjectScenarioResult:
    project_id: str
    baseline_contract_cents: int
    baseline_eac_cents: int
    baseline_gp_cents: int
    baseline_margin_bps: int

    scenario_contract_cents: int
    scenario_eac_cents: int
    scenario_gp_cents: int
    scenario_margin_bps: int

    gp_change_cents: int
    margin_change_bps: int


_PRIORITY_ORDER = {
    ExecutivePriority.CRITICAL: 0,
    ExecutivePriority.HIGH: 1,
    ExecutivePriority.WATCH: 2,
    ExecutivePriority.INFO: 3,
}


class ExecutiveCommandCenter:
    """
    Evidence-driven GOAT executive decision-support layer.

    It may:
      - aggregate verified GOAT operational data
      - identify anomalies and priorities
      - create advisory recommendations
      - model scenarios

    It may NOT:
      - fabricate missing source data
      - transfer money
      - alter contracts
      - change security controls
      - terminate personnel
      - submit bids
      - execute irreversible actions

    Consequential execution belongs to separately authorized workflows.
    """

    def __init__(
        self,
        *,
        spine: InMemoryDataSpine,
        finance: ProjectFinanceService,
        follow_through: FollowThroughEngine,
        sales_operations: SalesOperations,
        authorization: AuthorizationEngine | None = None,
    ) -> None:
        self.spine = spine
        self.finance = finance
        self.follow_through = follow_through
        self.sales_operations = sales_operations
        self.authorization = (
            authorization
            or AuthorizationEngine()
        )

    def _require_executive(
        self,
        *,
        principal: Principal,
        tenant_id: str,
    ) -> None:
        decision = self.authorization.authorize(
            principal,
            Permission.EXECUTIVE_INTELLIGENCE,
            ResourceContext(
                tenant_id=tenant_id,
            ),
        )

        if not decision.allowed:
            raise ExecutiveAuthorizationError(
                decision.reason
            )

    @staticmethod
    def _recommendation_id(
        *,
        domain: RecommendationDomain,
        entity_id: str,
        rule_code: str,
    ) -> str:
        raw = (
            f"{domain.value}|"
            f"{entity_id}|"
            f"{rule_code}"
        ).encode()

        digest = hashlib.sha256(
            raw
        ).hexdigest()[:24]

        return f"exec_{digest}"

    @staticmethod
    def _priority_from_severity(
        severity: str,
    ) -> ExecutivePriority:
        normalized = severity.lower()

        if normalized == "critical":
            return ExecutivePriority.CRITICAL

        if normalized == "high":
            return ExecutivePriority.HIGH

        if normalized in {
            "warning",
            "medium",
            "watch",
        }:
            return ExecutivePriority.WATCH

        return ExecutivePriority.INFO

    @staticmethod
    def _money_evidence(
        *,
        entity_id: str,
        metric: str,
        amount_cents: int,
        detail: str,
    ) -> ExecutiveEvidence:
        return ExecutiveEvidence(
            source_system="goat_financial_spine",
            entity_type="Project",
            entity_id=entity_id,
            metric=metric,
            observed_value=str(amount_cents),
            detail=detail,
        )

    def build_brief(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        now: datetime | None = None,
    ) -> ExecutiveBrief:
        self._require_executive(
            principal=principal,
            tenant_id=tenant_id,
        )

        now = now or utc_now()

        leads = self.spine.list_type(
            tenant_id=tenant_id,
            entity_type=Lead,
        )

        opportunities = self.spine.list_type(
            tenant_id=tenant_id,
            entity_type=Opportunity,
        )

        projects = self.spine.list_type(
            tenant_id=tenant_id,
            entity_type=Project,
        )

        active_opportunities = tuple(
            item
            for item in opportunities
            if item.stage
            not in TERMINAL_OPPORTUNITY_STAGES
        )

        pipeline_value = sum(
            item.estimated_value_cents or 0
            for item in active_opportunities
        )

        won_count = sum(
            1
            for item in opportunities
            if item.stage.value == "won"
        )

        lost_count = sum(
            1
            for item in opportunities
            if item.stage.value == "lost"
        )

        crm_findings = (
            self.follow_through.audit_active_crm(
                tenant_id=tenant_id,
                now=now,
            )
        )

        open_commitments = (
            self.follow_through.open_commitments(
                tenant_id=tenant_id,
            )
        )

        overdue_sales = (
            self.sales_operations.overdue_items(
                tenant_id=tenant_id,
                now=now,
            )
        )

        financial_snapshots: list[
            ProjectFinancialSnapshot
        ] = []

        recommendations: list[
            ExecutiveRecommendation
        ] = []

        for project in projects:
            snapshot = self.finance.snapshot(
                principal=principal,
                tenant_id=tenant_id,
                project_id=project.entity_id,
            )

            financial_snapshots.append(
                snapshot
            )

            for finding in snapshot.findings:
                priority = (
                    self._priority_from_severity(
                        finding.severity
                    )
                )

                evidence = (
                    ExecutiveEvidence(
                        source_system=(
                            "goat_financial_spine"
                        ),
                        entity_type="Project",
                        entity_id=project.entity_id,
                        metric=finding.code,
                        observed_value=str(
                            finding.amount_cents
                            if finding.amount_cents
                            is not None
                            else 0
                        ),
                        detail=finding.message,
                    ),
                )

                recommendations.append(
                    ExecutiveRecommendation(
                        recommendation_id=(
                            self._recommendation_id(
                                domain=(
                                    RecommendationDomain
                                    .FINANCE
                                ),
                                entity_id=(
                                    project.entity_id
                                ),
                                rule_code=(
                                    finding.code
                                ),
                            )
                        ),
                        domain=(
                            RecommendationDomain
                            .FINANCE
                        ),
                        priority=priority,
                        title=(
                            f"Financial risk on "
                            f"{project.name}"
                        ),
                        rationale=finding.message,
                        suggested_action=(
                            "Review project financials, "
                            "validate remaining exposure, "
                            "and assign an accountable "
                            "recovery action."
                        ),
                        confidence=1.0,
                        evidence=evidence,
                    )
                )

            if (
                snapshot.revised_contract_value_cents
                > 0
                and snapshot.projected_margin_bps
                < 2500
            ):
                priority = (
                    ExecutivePriority.CRITICAL
                    if snapshot.projected_margin_bps
                    < 1000
                    else ExecutivePriority.HIGH
                )

                evidence = (
                    self._money_evidence(
                        entity_id=project.entity_id,
                        metric="projected_margin_bps",
                        amount_cents=(
                            snapshot.projected_margin_bps
                        ),
                        detail=(
                            "Current projected gross "
                            "margin basis points."
                        ),
                    ),
                    self._money_evidence(
                        entity_id=project.entity_id,
                        metric=(
                            "projected_gross_profit_cents"
                        ),
                        amount_cents=(
                            snapshot
                            .projected_gross_profit_cents
                        ),
                        detail=(
                            "Current projected gross "
                            "profit."
                        ),
                    ),
                )

                recommendations.append(
                    ExecutiveRecommendation(
                        recommendation_id=(
                            self._recommendation_id(
                                domain=(
                                    RecommendationDomain
                                    .MARGIN
                                ),
                                entity_id=(
                                    project.entity_id
                                ),
                                rule_code=(
                                    "low_projected_margin"
                                ),
                            )
                        ),
                        domain=(
                            RecommendationDomain.MARGIN
                        ),
                        priority=priority,
                        title=(
                            f"Protect margin on "
                            f"{project.name}"
                        ),
                        rationale=(
                            "Projected project gross "
                            "margin is below the GOAT "
                            "executive review threshold."
                        ),
                        suggested_action=(
                            "Review cost-to-complete, "
                            "change-order recovery, "
                            "production performance and "
                            "remaining commitments."
                        ),
                        confidence=1.0,
                        evidence=evidence,
                    )
                )

            if snapshot.ar_outstanding_cents > 0:
                priority = (
                    ExecutivePriority.HIGH
                    if snapshot.ar_outstanding_cents
                    >= 100_000_00
                    else ExecutivePriority.WATCH
                )

                evidence = (
                    self._money_evidence(
                        entity_id=project.entity_id,
                        metric=(
                            "ar_outstanding_cents"
                        ),
                        amount_cents=(
                            snapshot
                            .ar_outstanding_cents
                        ),
                        detail=(
                            "Outstanding owner/customer "
                            "receivable excluding "
                            "retainage."
                        ),
                    ),
                )

                recommendations.append(
                    ExecutiveRecommendation(
                        recommendation_id=(
                            self._recommendation_id(
                                domain=(
                                    RecommendationDomain
                                    .COLLECTIONS
                                ),
                                entity_id=(
                                    project.entity_id
                                ),
                                rule_code=(
                                    "ar_outstanding"
                                ),
                            )
                        ),
                        domain=(
                            RecommendationDomain
                            .COLLECTIONS
                        ),
                        priority=priority,
                        title=(
                            f"Collections follow-up: "
                            f"{project.name}"
                        ),
                        rationale=(
                            "GOAT Financial Spine shows "
                            "an outstanding receivable."
                        ),
                        suggested_action=(
                            "Confirm invoice status, "
                            "customer approval state and "
                            "collection owner."
                        ),
                        confidence=1.0,
                        evidence=evidence,
                    )
                )

        for finding in crm_findings:
            priority = (
                self._priority_from_severity(
                    finding.severity
                )
            )

            evidence = (
                ExecutiveEvidence(
                    source_system=(
                        "goat_follow_through"
                    ),
                    entity_type=(
                        finding.entity_type
                    ),
                    entity_id=(
                        finding.entity_id
                    ),
                    metric="follow_through_finding",
                    observed_value=(
                        finding.reason
                    ),
                    detail=(
                        "Deterministic CRM "
                        "follow-through audit."
                    ),
                ),
            )

            recommendations.append(
                ExecutiveRecommendation(
                    recommendation_id=(
                        self._recommendation_id(
                            domain=(
                                RecommendationDomain
                                .FOLLOW_THROUGH
                            ),
                            entity_id=(
                                finding.entity_id
                            ),
                            rule_code=(
                                finding.reason
                            ),
                        )
                    ),
                    domain=(
                        RecommendationDomain
                        .FOLLOW_THROUGH
                    ),
                    priority=priority,
                    title=(
                        "Prevent opportunity "
                        "follow-through failure"
                    ),
                    rationale=finding.reason,
                    suggested_action=(
                        "Assign a responsible owner "
                        "and a dated next action."
                    ),
                    confidence=1.0,
                    evidence=evidence,
                )
            )

        for item in overdue_sales:
            overdue_seconds = max(
                0,
                int(
                    (
                        now - item.due_at
                    ).total_seconds()
                ),
            )

            priority = (
                ExecutivePriority.HIGH
                if overdue_seconds
                >= 24 * 60 * 60
                else ExecutivePriority.WATCH
            )

            evidence = (
                ExecutiveEvidence(
                    source_system=(
                        "goat_sales_operations"
                    ),
                    entity_type=(
                        item.entity_type
                    ),
                    entity_id=item.entity_id,
                    metric="sales_work_overdue_seconds",
                    observed_value=str(
                        overdue_seconds
                    ),
                    detail=(
                        f"{item.work_type.value} "
                        f"assigned to "
                        f"{item.assigned_to} "
                        "is past SLA."
                    ),
                ),
            )

            recommendations.append(
                ExecutiveRecommendation(
                    recommendation_id=(
                        self._recommendation_id(
                            domain=(
                                RecommendationDomain
                                .SALES
                            ),
                            entity_id=item.item_id,
                            rule_code=(
                                "sales_sla_overdue"
                            ),
                        )
                    ),
                    domain=(
                        RecommendationDomain.SALES
                    ),
                    priority=priority,
                    title=(
                        "Sales SLA requires attention"
                    ),
                    rationale=(
                        "A GOAT sales work item is "
                        "past its required completion "
                        "deadline."
                    ),
                    suggested_action=(
                        "Complete, reassign or "
                        "escalate the sales work item."
                    ),
                    confidence=1.0,
                    evidence=evidence,
                )
            )

        total_contract = sum(
            item.revised_contract_value_cents
            for item in financial_snapshots
        )

        total_eac = sum(
            item.estimate_at_completion_cents
            for item in financial_snapshots
        )

        total_projected_gp = sum(
            item.projected_gross_profit_cents
            for item in financial_snapshots
        )

        total_ar = sum(
            item.ar_outstanding_cents
            for item in financial_snapshots
        )

        total_collected = sum(
            item.collected_cents
            for item in financial_snapshots
        )

        kpis = (
            ExecutiveKPI(
                code="lead_count",
                label="Leads",
                value=len(leads),
                unit="count",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_data_spine"
                        ),
                        entity_type="Lead",
                        entity_id="tenant",
                        metric="lead_count",
                        observed_value=str(
                            len(leads)
                        ),
                        detail=(
                            "Tenant-scoped GOAT lead "
                            "records."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="active_pipeline_value_cents",
                label="Active Pipeline",
                value=pipeline_value,
                unit="cents",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_crm"
                        ),
                        entity_type=(
                            "Opportunity"
                        ),
                        entity_id="tenant",
                        metric=(
                            "active_pipeline_value_cents"
                        ),
                        observed_value=str(
                            pipeline_value
                        ),
                        detail=(
                            "Sum of active opportunity "
                            "estimated values."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="won_opportunity_count",
                label="Won Opportunities",
                value=won_count,
                unit="count",
                evidence=(
                    ExecutiveEvidence(
                        source_system="goat_crm",
                        entity_type="Opportunity",
                        entity_id="tenant",
                        metric=(
                            "won_opportunity_count"
                        ),
                        observed_value=str(
                            won_count
                        ),
                        detail=(
                            "CRM opportunities in WON "
                            "state."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="lost_opportunity_count",
                label="Lost Opportunities",
                value=lost_count,
                unit="count",
                evidence=(
                    ExecutiveEvidence(
                        source_system="goat_crm",
                        entity_type="Opportunity",
                        entity_id="tenant",
                        metric=(
                            "lost_opportunity_count"
                        ),
                        observed_value=str(
                            lost_count
                        ),
                        detail=(
                            "CRM opportunities in LOST "
                            "state."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="open_commitments",
                label="Open Follow-Through",
                value=len(open_commitments),
                unit="count",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_follow_through"
                        ),
                        entity_type="Commitment",
                        entity_id="tenant",
                        metric="open_commitments",
                        observed_value=str(
                            len(open_commitments)
                        ),
                        detail=(
                            "GOAT workflow commitments "
                            "that remain open."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="overdue_sales_items",
                label="Overdue Sales Work",
                value=len(overdue_sales),
                unit="count",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_sales_operations"
                        ),
                        entity_type="QueueItem",
                        entity_id="tenant",
                        metric=(
                            "overdue_sales_items"
                        ),
                        observed_value=str(
                            len(overdue_sales)
                        ),
                        detail=(
                            "Sales work currently past "
                            "its SLA."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="revised_contract_value_cents",
                label="Project Contract Value",
                value=total_contract,
                unit="cents",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_financial_spine"
                        ),
                        entity_type="Project",
                        entity_id="tenant",
                        metric=(
                            "revised_contract_value_cents"
                        ),
                        observed_value=str(
                            total_contract
                        ),
                        detail=(
                            "Aggregate revised contract "
                            "value across projects."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="estimate_at_completion_cents",
                label="Projected Cost at Completion",
                value=total_eac,
                unit="cents",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_financial_spine"
                        ),
                        entity_type="Project",
                        entity_id="tenant",
                        metric=(
                            "estimate_at_completion_cents"
                        ),
                        observed_value=str(
                            total_eac
                        ),
                        detail=(
                            "Aggregate projected project "
                            "cost at completion."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="projected_gross_profit_cents",
                label="Projected Gross Profit",
                value=total_projected_gp,
                unit="cents",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_financial_spine"
                        ),
                        entity_type="Project",
                        entity_id="tenant",
                        metric=(
                            "projected_gross_profit_cents"
                        ),
                        observed_value=str(
                            total_projected_gp
                        ),
                        detail=(
                            "Aggregate projected gross "
                            "profit."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="ar_outstanding_cents",
                label="Outstanding AR",
                value=total_ar,
                unit="cents",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_financial_spine"
                        ),
                        entity_type="Project",
                        entity_id="tenant",
                        metric=(
                            "ar_outstanding_cents"
                        ),
                        observed_value=str(
                            total_ar
                        ),
                        detail=(
                            "Aggregate outstanding "
                            "receivables."
                        ),
                    ),
                ),
            ),

            ExecutiveKPI(
                code="cash_collected_cents",
                label="Collected Revenue",
                value=total_collected,
                unit="cents",
                evidence=(
                    ExecutiveEvidence(
                        source_system=(
                            "goat_financial_spine"
                        ),
                        entity_type="Project",
                        entity_id="tenant",
                        metric=(
                            "cash_collected_cents"
                        ),
                        observed_value=str(
                            total_collected
                        ),
                        detail=(
                            "Aggregate recorded project "
                            "collections."
                        ),
                    ),
                ),
            ),
        )

        recommendations.sort(
            key=lambda item: (
                _PRIORITY_ORDER[
                    item.priority
                ],
                item.domain.value,
                item.recommendation_id,
            )
        )

        brief = ExecutiveBrief(
            tenant_id=tenant_id,
            generated_at=now,
            source_event_count=len(
                self.spine.all_events(
                    tenant_id=tenant_id
                )
            ),
            kpis=kpis,
            recommendations=tuple(
                recommendations
            ),
            project_financials=tuple(
                financial_snapshots
            ),
        )

        self.validate_brief(brief)

        return brief

    @staticmethod
    def validate_brief(
        brief: ExecutiveBrief,
    ) -> None:
        if brief.source_event_count < 0:
            raise ExecutiveIntegrityError(
                "invalid event count"
            )

        for kpi in brief.kpis:
            if not kpi.evidence:
                raise ExecutiveIntegrityError(
                    f"KPI lacks evidence: "
                    f"{kpi.code}"
                )

        for recommendation in (
            brief.recommendations
        ):
            if not recommendation.evidence:
                raise ExecutiveIntegrityError(
                    "recommendation lacks evidence"
                )

            if not (
                0.0
                <= recommendation.confidence
                <= 1.0
            ):
                raise ExecutiveIntegrityError(
                    "invalid confidence"
                )

            if not (
                recommendation.advisory_only
            ):
                raise ExecutiveIntegrityError(
                    "executive recommendation "
                    "cannot directly execute"
                )

    def simulate_project_scenario(
        self,
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        scenario: ProjectScenario,
    ) -> ProjectScenarioResult:
        self._require_executive(
            principal=principal,
            tenant_id=tenant_id,
        )

        baseline = self.finance.snapshot(
            principal=principal,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        scenario_contract = (
            baseline.revised_contract_value_cents
            + scenario.revenue_delta_cents
        )

        scenario_eac = (
            baseline.estimate_at_completion_cents
            + scenario.cost_delta_cents
        )

        if scenario_contract < 0:
            raise ValueError(
                "scenario contract value "
                "cannot be negative"
            )

        if scenario_eac < 0:
            raise ValueError(
                "scenario cost at completion "
                "cannot be negative"
            )

        scenario_gp = (
            scenario_contract
            - scenario_eac
        )

        scenario_margin = (
            scenario_gp * 10_000
            // scenario_contract
            if scenario_contract > 0
            else 0
        )

        return ProjectScenarioResult(
            project_id=project_id,

            baseline_contract_cents=(
                baseline
                .revised_contract_value_cents
            ),

            baseline_eac_cents=(
                baseline
                .estimate_at_completion_cents
            ),

            baseline_gp_cents=(
                baseline
                .projected_gross_profit_cents
            ),

            baseline_margin_bps=(
                baseline.projected_margin_bps
            ),

            scenario_contract_cents=(
                scenario_contract
            ),

            scenario_eac_cents=(
                scenario_eac
            ),

            scenario_gp_cents=(
                scenario_gp
            ),

            scenario_margin_bps=(
                scenario_margin
            ),

            gp_change_cents=(
                scenario_gp
                - baseline
                .projected_gross_profit_cents
            ),

            margin_change_bps=(
                scenario_margin
                - baseline.projected_margin_bps
            ),
        )
