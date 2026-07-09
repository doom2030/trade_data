from datetime import date

from app.models import QualityCheckResult
from collector.quality_check import resolve_quality_checks


class TestResolveQualityChecks:
    def _check(
        self,
        *,
        symbol: str = "sh.600000",
        frequency: str = "day",
        adjust_flag: str | None = "forward",
        start_date: date | None = date(2024, 1, 10),
        end_date: date | None = date(2024, 1, 10),
        status: str = "open",
    ) -> QualityCheckResult:
        return QualityCheckResult(
            symbol=symbol,
            frequency=frequency,
            adjust_flag=adjust_flag,
            start_date=start_date,
            end_date=end_date,
            check_type="missing_kline",
            severity="error",
            status=status,
        )

    def test_resolves_only_matching_scope(self):
        matching = self._check()
        other_date = self._check(start_date=date(2024, 2, 1), end_date=date(2024, 2, 1))
        other_adjust = self._check(adjust_flag="none")
        already_resolved = self._check(status="resolved")

        class FakeSession:
            def __init__(self, checks):
                self.checks = checks

            def scalars(self, query):
                class Result:
                    def __init__(self, outer):
                        self.outer = outer

                    def all(self):
                        symbol = "sh.600000"
                        frequency = "day"
                        adjust_flag = "forward"
                        start_date = date(2024, 1, 1)
                        end_date = date(2024, 1, 31)
                        resolved = []
                        for check in self.outer.checks:
                            if check.status != "open":
                                continue
                            if check.symbol != symbol or check.frequency != frequency:
                                continue
                            if adjust_flag and check.adjust_flag != adjust_flag:
                                continue
                            if start_date and end_date:
                                if not check.start_date or check.start_date > end_date:
                                    continue
                                if check.end_date and check.end_date < start_date:
                                    continue
                            resolved.append(check)
                        return resolved

                return Result(self)

        session = FakeSession([matching, other_date, other_adjust, already_resolved])
        resolve_quality_checks(
            session,
            "sh.600000",
            "day",
            "forward",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert matching.status == "resolved"
        assert other_date.status == "open"
        assert other_adjust.status == "open"
        assert already_resolved.status == "resolved"
