from collector.board_classifier import classify_board, is_st_name, parse_symbol


class TestBoardClassifier:
    def test_sh_main(self):
        assert classify_board("sh.600000") == "sh_main"
        assert classify_board("sh.601318") == "sh_main"
        assert classify_board("sh.603288") == "sh_main"
        assert classify_board("sh.605117") == "sh_main"

    def test_sz_main(self):
        assert classify_board("sz.000001") == "sz_main"
        assert classify_board("sz.001979") == "sz_main"
        assert classify_board("sz.002594") == "sz_main"

    def test_chinext(self):
        assert classify_board("sz.300750") == "chinext"

    def test_star(self):
        assert classify_board("sh.688981") == "star"

    def test_invalid(self):
        assert classify_board("sh.688") is None
        assert classify_board("bj.430047") is None

    def test_st_name(self):
        assert is_st_name("ST康美") is True
        assert is_st_name("*ST海航") is True
        assert is_st_name("贵州茅台") is False

    def test_parse_symbol(self):
        assert parse_symbol("sh.600000") == ("sh.600000", "sh", "600000")
        assert parse_symbol("invalid") is None
