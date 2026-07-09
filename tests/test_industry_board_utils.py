from collector.industry_board_utils import letter_bucket, normalize_em_code, pinyin_initial


class TestPinyinInitial:
    def test_chinese_name(self):
        assert pinyin_initial("半导体") == "B"
        assert pinyin_initial("白酒") == "B"
        assert pinyin_initial("银行") == "Y"
        assert pinyin_initial("证券") == "Z"

    def test_ascii_prefix(self):
        assert pinyin_initial("IT服务") == "I"

    def test_empty(self):
        assert pinyin_initial("") == "#"


class TestLetterBucket:
    def test_buckets(self):
        assert letter_bucket("B") == "A~E"
        assert letter_bucket("F") == "F~J"
        assert letter_bucket("L") == "K~O"
        assert letter_bucket("Q") == "P~T"
        assert letter_bucket("Y") == "U~Z"
        assert letter_bucket("#") == "U~Z"


class TestNormalizeEmCode:
    def test_shanghai(self):
        assert normalize_em_code("600519") == "sh.600519"

    def test_shenzhen(self):
        assert normalize_em_code("000001") == "sz.000001"
        assert normalize_em_code("300750") == "sz.300750"

    def test_star(self):
        assert normalize_em_code("688981") == "sh.688981"

    def test_skip_beijing(self):
        assert normalize_em_code("830799") is None

    def test_already_prefixed(self):
        assert normalize_em_code("sh.600000") == "sh.600000"
        assert normalize_em_code("SZ.000001") == "sz.000001"
