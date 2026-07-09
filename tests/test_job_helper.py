




class TestFinalizeJobLogic:
    def test_all_success(self):
        total_items = 2
        failed_items = 0
        skipped_items = 0
        effective = total_items - skipped_items
        fail_rate = failed_items / effective if effective else 0
        assert fail_rate == 0

    def test_partial_success(self):
        total_items = 20
        failed_items = 1
        skipped_items = 0
        fail_rate = failed_items / (total_items - skipped_items)
        assert 0 < fail_rate <= 0.05

    def test_all_skipped(self):
        total_items = 2
        skipped_items = 2
        effective = total_items - skipped_items
        assert effective == 0
