from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import os


REQUIRED_MODULES = (
    "leadbot_v2.core.models",
    "leadbot_v2.core.pipeline",
    "leadbot_v2.discovery.brave_v2",
    "leadbot_v2.enrichment.signals",
    "leadbot_v2.intelligence.geography",
    "leadbot_v2.intelligence.intent_ensemble",
    "leadbot_v2.intelligence.intent_rules",
    "leadbot_v2.intelligence.intent_context",
    "leadbot_v2.intelligence.intent_fusion",
    "leadbot_v2.qualification.evidence",
)


@dataclass
class IntegrityIssue:
    component: str
    severity: str
    message: str


@dataclass
class IntegrityReport:
    healthy: bool = True
    issues: list[IntegrityIssue] = field(default_factory=list)

    def add(
        self,
        component: str,
        severity: str,
        message: str,
    ) -> None:
        self.issues.append(
            IntegrityIssue(
                component=component,
                severity=severity,
                message=message,
            )
        )

        if severity.upper() in {"ERROR", "CRITICAL"}:
            self.healthy = False


class SystemIntegrityGuardian:
    def check_imports(self, report: IntegrityReport) -> None:
        for module in REQUIRED_MODULES:
            try:
                importlib.import_module(module)
            except Exception as exc:
                report.add(
                    module,
                    "CRITICAL",
                    f"import failed: {exc!r}",
                )

    def check_environment(self, report: IntegrityReport) -> None:
        if not os.getenv("BRAVE_API_KEY"):
            report.add(
                "environment",
                "ERROR",
                "BRAVE_API_KEY missing",
            )

    def run(self) -> IntegrityReport:
        report = IntegrityReport()

        self.check_imports(report)
        self.check_environment(report)

        return report


class IntegrityFailure(RuntimeError):
    pass


def format_report(report: IntegrityReport) -> str:
    lines = [
        f"HEALTHY: {report.healthy}",
        f"ISSUES: {len(report.issues)}",
    ]

    for issue in report.issues:
        lines.append(
            f"[{issue.severity}] "
            f"{issue.component}: "
            f"{issue.message}"
        )

    return "\n".join(lines)


def require_healthy_system() -> IntegrityReport:
    guardian = SystemIntegrityGuardian()
    report = guardian.run()

    if not report.healthy:
        raise IntegrityFailure(
            "LeadBot V2 startup blocked by integrity failure:\n"
            + format_report(report)
        )

    return report
