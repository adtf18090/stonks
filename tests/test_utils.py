from stock_dashboard.utils import get_currency_symbol, safe_float


def test_get_currency_symbol_korea():
    # 정상 케이스 1
    assert get_currency_symbol("005930.KS") == "₩"


def test_get_currency_symbol_us():
    # 정상 케이스 2
    assert get_currency_symbol("AAPL") == "$"


def test_safe_float_normal():
    # 정상 케이스 3
    assert safe_float("123.45") == 123.45


def test_safe_float_edge_case():
    # 엣지 케이스 1 (잘못된 입력)
    assert safe_float("abc", default=0.0) == 0.0


def test_safe_float_none():
    # 엣지 케이스 2 (None 입력)
    assert safe_float(None, default=-1.0) == -1.0
