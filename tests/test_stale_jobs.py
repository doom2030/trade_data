from datetime import datetime, timedelta, timezone

from app.models import CollectJob, CollectJobItem
from collector.job_helper import fail_interrupted_running_jobs, mark_stale_running_jobs


class TestMarkStaleRunningJobs:
    def test_marks_stale_job_and_running_items(self):
        stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
        job = CollectJob(id=1, job_type="daily_update", status="running", started_at=stale_time)
        item = CollectJobItem(id=10, job_id=1, status="running")

        class FakeSession:
            def __init__(self):
                self.job = job
                self.item = item

            def scalars(self, query):
                class Result:
                    def __init__(self, outer):
                        self.outer = outer

                    def all(self):
                        q = str(query).lower()
                        if "collect_job_item" in q:
                            return [self.outer.item]
                        return [self.outer.job]

                return Result(self)

            def flush(self):
                pass

        session = FakeSession()
        count = mark_stale_running_jobs(session, stale_minutes=60)
        assert count == 1
        assert job.status == "failed"
        assert item.status == "failed"


class TestFailInterruptedRunningJobs:
    def test_fails_all_running_when_grace_zero(self):
        job = CollectJob(
            id=1,
            job_type="backfill_kline",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        item = CollectJobItem(id=10, job_id=1, status="running")

        class FakeSession:
            def scalars(self, query):
                class Result:
                    def all(self):
                        q = str(query).lower()
                        if "collect_job_item" in q:
                            return [item]
                        return [job]

                return Result()

            def flush(self):
                pass

        count = fail_interrupted_running_jobs(FakeSession(), grace_seconds=0)
        assert count == 1
        assert job.status == "failed"
        assert item.status == "failed"

    def test_skips_recent_jobs_within_grace(self):
        job = CollectJob(
            id=1,
            job_type="daily_update",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        class FakeSession:
            def scalars(self, query):
                class Result:
                    def all(self):
                        return [job]

                return Result()

            def flush(self):
                pass

        count = fail_interrupted_running_jobs(FakeSession(), grace_seconds=300)
        assert count == 0
        assert job.status == "running"
