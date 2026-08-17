from __future__ import annotations

from .models import (
    AccountClass,
    AccountingInvariantError,
    ChartAccount,
)


class ChartOfAccounts:
    def __init__(
        self,
    ) -> None:
        self._accounts: dict[
            str,
            ChartAccount,
        ] = {}

    def add(
        self,
        account: ChartAccount,
    ) -> None:
        if (
            account.code
            in self._accounts
        ):
            raise AccountingInvariantError(
                f"duplicate account code: "
                f"{account.code}"
            )

        self._accounts[
            account.code
        ] = account

    def get(
        self,
        code: str,
    ) -> ChartAccount:
        try:
            return self._accounts[
                code
            ]
        except KeyError as exc:
            raise AccountingInvariantError(
                f"unknown account: "
                f"{code}"
            ) from exc

    def exists(
        self,
        code: str,
    ) -> bool:
        return (
            code
            in self._accounts
        )

    def all(
        self,
    ):
        return tuple(
            sorted(
                self._accounts.values(),
                key=lambda account:
                    account.code,
            )
        )


def default_construction_chart(
) -> ChartOfAccounts:
    chart = ChartOfAccounts()

    rows = (
        ("1000", "Operating Checking", AccountClass.ASSET),
        ("1010", "Savings / Tax Reserve", AccountClass.ASSET),
        ("1020", "Payroll Reserve", AccountClass.ASSET),
        ("1030", "Project Mobilization Reserve", AccountClass.ASSET),
        ("1100", "Accounts Receivable", AccountClass.ASSET),
        ("1200", "Undeposited Funds", AccountClass.ASSET),
        ("1300", "Materials Inventory", AccountClass.ASSET),
        ("1400", "Prepaid Expenses", AccountClass.ASSET),
        ("1500", "Vehicles and Equipment", AccountClass.ASSET),
        ("1510", "Tools", AccountClass.ASSET),
        ("1600", "Land / Real Estate", AccountClass.ASSET),

        ("2000", "Accounts Payable", AccountClass.LIABILITY),
        ("2100", "Credit Card Payable", AccountClass.LIABILITY),
        ("2200", "Sales / Use Tax Payable", AccountClass.LIABILITY),
        ("2300", "Payroll Liabilities", AccountClass.LIABILITY),
        ("2400", "Loans Payable", AccountClass.LIABILITY),
        ("2500", "Accrued Expenses", AccountClass.LIABILITY),

        ("3000", "Owner Capital", AccountClass.EQUITY),
        ("3100", "Retained Earnings", AccountClass.EQUITY),
        ("3200", "Owner Distributions", AccountClass.EQUITY),

        ("4000", "Construction Revenue", AccountClass.REVENUE),
        ("4100", "Approved Change Order Revenue", AccountClass.REVENUE),
        ("4200", "Service Revenue", AccountClass.REVENUE),

        ("5000", "Direct Materials", AccountClass.COGS),
        ("5010", "Concrete", AccountClass.COGS),
        ("5020", "Reinforcing Steel", AccountClass.COGS),
        ("5030", "Aggregates", AccountClass.COGS),
        ("5040", "Forms / Lumber", AccountClass.COGS),
        ("5050", "Embedded Materials", AccountClass.COGS),
        ("5100", "Direct Labor", AccountClass.COGS),
        ("5200", "Subcontractors", AccountClass.COGS),
        ("5300", "Job Equipment", AccountClass.COGS),
        ("5400", "Freight / Hauling", AccountClass.COGS),

        ("6000", "General and Administrative", AccountClass.EXPENSE),
        ("6100", "Marketing / Advertising", AccountClass.EXPENSE),
        ("6200", "Insurance", AccountClass.EXPENSE),
        ("6300", "Legal / Professional", AccountClass.EXPENSE),
        ("6400", "Vehicle / Fuel", AccountClass.EXPENSE),
        ("6500", "Interest Expense", AccountClass.OTHER_EXPENSE),
        ("6600", "Taxes / Licenses / Permits", AccountClass.EXPENSE),
        ("6700", "Software / Technology", AccountClass.EXPENSE),
        ("6800", "Office / Administrative", AccountClass.EXPENSE),
        ("6900", "Unclassified Review", AccountClass.EXPENSE),

        ("7000", "Other Income", AccountClass.OTHER_INCOME),
    )

    for code, name, account_class in rows:
        chart.add(
            ChartAccount(
                code=code,
                name=name,
                account_class=(
                    account_class
                ),
            )
        )

    return chart
