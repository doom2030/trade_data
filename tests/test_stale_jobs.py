from datetime import datetime, timedelta, timezone

from app.models import CollectJob, CollectJobItem
from collector.job_helper import mark_stale_running_jobs


class TestMarkStaleRunningJobs:
    def test_marks_stale_job_and_running_items(self):
        class FakeScalars:
            def __init__(self, jobs, items_map):
                self.jobs = jobs
                self.items_map = items_map
                self._mode = "jobs"

            def all(self):
                if self._mode == "jobs":
                    return self.jobs
                return self.items_map.get(self._current_job_id, [])

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
