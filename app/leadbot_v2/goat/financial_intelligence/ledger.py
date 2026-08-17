from __future__ import annotations

from datetime import date

from .canonical import (
    money,
    stable_hash,
)

from .models import (
    AccountClass,
    AccountingInvariantError,
    BalanceSheet,
    EntityIsolationError,
    IncomeStatement,
    JournalEntry,
    JournalLine,
    TrialBalance,
    ZERO,
    utcnow,
)


class GeneralLedger:
    def __init__(
        self,
        chart,
        *,
        entity_id: str,
    ) -> None:
        if not entity_id.strip():
            raise ValueError(
                "entity_id is required"
            )

        self.chart = chart
        self.entity_id = entity_id

        self._entries: dict[
            str,
            JournalEntry,
        ] = {}

        self._source_index: dict[
            tuple[
                str,
                str,
            ],
            str,
        ] = {}

    def create_entry(
        self,
        *,
        entry_date: date,
        source_type: str,
        source_id: str,
        memo: str,
        lines,
        entity_id: str | None = None,
    ) -> JournalEntry:
        effective_entity = (
            entity_id
            or self.entity_id
        )

        if (
            effective_entity
            != self.entity_id
        ):
            raise EntityIsolationError(
                "journal entry entity does not match ledger entity"
            )

        normalized = []

        for line in lines:
            normalized.append(
                JournalLine(
                    account_code=(
                        line.account_code
                    ),
                    debit=money(
                        line.debit
                    ),
                    credit=money(
                        line.credit
                    ),
                    project_id=(
                        line.project_id
                    ),
                    cost_code=(
                        line.cost_code
                    ),
                    vendor_id=(
                        line.vendor_id
                    ),
                    tax_code=(
                        line.tax_code
                    ),
                    memo=line.memo,
                )
            )

        entry_id = stable_hash(
            {
                "entity_id":
                    effective_entity,
                "entry_date":
                    entry_date,
                "source_type":
                    source_type,
                "source_id":
                    source_id,
                "memo":
                    memo,
                "lines":
                    tuple(
                        normalized
                    ),
            }
        )[:32]

        return JournalEntry(
            entry_id=entry_id,
            entity_id=(
                effective_entity
            ),
            entry_date=entry_date,
            source_type=source_type,
            source_id=source_id,
            memo=memo,
            lines=tuple(
                normalized
            ),
            created_at=utcnow(),
        )

    def post(
        self,
        entry: JournalEntry,
    ) -> JournalEntry:
        if (
            entry.entity_id
            != self.entity_id
        ):
            raise EntityIsolationError(
                "cross-entity journal posting forbidden"
            )

        key = (
            entry.source_type,
            entry.source_id,
        )

        existing_id = (
            self._source_index.get(
                key
            )
        )

        if existing_id:
            existing = self._entries[
                existing_id
            ]

            if (
                existing.entry_id
                == entry.entry_id
            ):
                return existing

            raise AccountingInvariantError(
                "same source attempted with "
                "different accounting"
            )

        if len(
            entry.lines
        ) < 2:
            raise AccountingInvariantError(
                "journal entry requires at least two lines"
            )

        total_debits = ZERO
        total_credits = ZERO

        for line in entry.lines:
            account = self.chart.get(
                line.account_code
            )

            if not account.active:
                raise AccountingInvariantError(
                    f"inactive account: "
                    f"{line.account_code}"
                )

            debit = money(
                line.debit
            )

            credit = money(
                line.credit
            )

            if (
                debit < ZERO
                or credit < ZERO
            ):
                raise AccountingInvariantError(
                    "negative debit/credit forbidden"
                )

            if (
                debit > ZERO
                and credit > ZERO
            ):
                raise AccountingInvariantError(
                    "journal line cannot contain "
                    "both debit and credit"
                )

            if (
                debit == ZERO
                and credit == ZERO
            ):
                raise AccountingInvariantError(
                    "zero journal line forbidden"
                )

            total_debits += debit
            total_credits += credit

        total_debits = money(
            total_debits
        )

        total_credits = money(
            total_credits
        )

        if (
            total_debits
            != total_credits
        ):
            raise AccountingInvariantError(
                f"unbalanced entry: "
                f"debits={total_debits} "
                f"credits={total_credits}"
            )

        self._entries[
            entry.entry_id
        ] = entry

        self._source_index[
            key
        ] = entry.entry_id

        return entry

    def entries(
        self,
    ) -> tuple[
        JournalEntry,
        ...,
    ]:
        return tuple(
            sorted(
                self._entries.values(),
                key=lambda entry: (
                    entry.entry_date,
                    entry.entry_id,
                ),
            )
        )

    def trial_balance(
        self,
    ) -> TrialBalance:
        debits = ZERO
        credits = ZERO

        for entry in (
            self._entries.values()
        ):
            for line in entry.lines:
                debits += money(
                    line.debit
                )
                credits += money(
                    line.credit
                )

        debits = money(
            debits
        )
        credits = money(
            credits
        )

        return TrialBalance(
            total_debits=debits,
            total_credits=credits,
            balanced=(
                debits
                == credits
            ),
        )

    def account_balance(
        self,
        account_code: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        account = self.chart.get(
            account_code
        )

        debit_total = ZERO
        credit_total = ZERO

        for entry in (
            self._entries.values()
        ):
            if (
                start_date
                and entry.entry_date
                < start_date
            ):
                continue

            if (
                end_date
                and entry.entry_date
                > end_date
            ):
                continue

            for line in entry.lines:
                if (
                    line.account_code
                    != account_code
                ):
                    continue

                debit_total += (
                    line.debit
                )
                credit_total += (
                    line.credit
                )

        if (
            account.account_class
            in {
                AccountClass.ASSET,
                AccountClass.COGS,
                AccountClass.EXPENSE,
                AccountClass.OTHER_EXPENSE,
            }
        ):
            return money(
                debit_total
                - credit_total
            )

        return money(
            credit_total
            - debit_total
        )

    def income_statement(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> IncomeStatement:
        revenue = ZERO
        cogs = ZERO
        expense = ZERO
        other_income = ZERO
        other_expense = ZERO

        for account in (
            self.chart.all()
        ):
            balance = self.account_balance(
                account.code,
                start_date=(
                    start_date
                ),
                end_date=(
                    end_date
                ),
            )

            if (
                account.account_class
                is AccountClass.REVENUE
            ):
                revenue += balance

            elif (
                account.account_class
                is AccountClass.COGS
            ):
                cogs += balance

            elif (
                account.account_class
                is AccountClass.EXPENSE
            ):
                expense += balance

            elif (
                account.account_class
                is AccountClass.OTHER_INCOME
            ):
                other_income += balance

            elif (
                account.account_class
                is AccountClass.OTHER_EXPENSE
            ):
                other_expense += balance

        gross_profit = money(
            revenue
            - cogs
        )

        net_income = money(
            gross_profit
            - expense
            + other_income
            - other_expense
        )

        return IncomeStatement(
            revenue=money(
                revenue
            ),
            cogs=money(
                cogs
            ),
            gross_profit=(
                gross_profit
            ),
            operating_expense=money(
                expense
            ),
            other_income=money(
                other_income
            ),
            other_expense=money(
                other_expense
            ),
            net_income=(
                net_income
            ),
        )

    def balance_sheet(
        self,
    ) -> BalanceSheet:
        assets = ZERO
        liabilities = ZERO
        equity = ZERO

        for account in (
            self.chart.all()
        ):
            balance = self.account_balance(
                account.code
            )

            if (
                account.account_class
                is AccountClass.ASSET
            ):
                assets += balance

            elif (
                account.account_class
                is AccountClass.LIABILITY
            ):
                liabilities += balance

            elif (
                account.account_class
                is AccountClass.EQUITY
            ):
                equity += balance

        income = (
            self.income_statement()
            .net_income
        )

        difference = money(
            assets
            - liabilities
            - equity
            - income
        )

        return BalanceSheet(
            assets=money(
                assets
            ),
            liabilities=money(
                liabilities
            ),
            equity=money(
                equity
            ),
            current_period_income=(
                money(
                    income
                )
            ),
            accounting_equation_difference=(
                difference
            ),
            balanced=(
                difference
                == ZERO
            ),
        )

    def bank_postings(
        self,
        bank_account_code: str,
    ):
        self.chart.get(
            bank_account_code
        )

        rows = []

        for entry in (
            self.entries()
        ):
            signed = ZERO

            for line in entry.lines:
                if (
                    line.account_code
                    != bank_account_code
                ):
                    continue

                signed += (
                    line.debit
                    - line.credit
                )

            signed = money(
                signed
            )

            if signed != ZERO:
                rows.append(
                    {
                        "entry_id":
                            entry.entry_id,
                        "entry_date":
                            entry.entry_date,
                        "source_type":
                            entry.source_type,
                        "source_id":
                            entry.source_id,
                        "signed_amount":
                            signed,
                    }
                )

        return tuple(
            rows
        )
