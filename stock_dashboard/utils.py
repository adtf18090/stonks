import urllib.request
import urllib.parse
import json


def get_currency_symbol(sym: str) -> str:
    """
    주식 티커에 따른 통화 기호를 반환합니다.

    :param sym: 주식 티커 심볼
    :return: 통화 기호 문자열 ('₩' 또는 '$')

    >>> get_currency_symbol("005930.KS")
    '₩'
    >>> get_currency_symbol("AAPL")
    '$'
    """
    return "₩" if sym.endswith(".KS") or sym.endswith(".KQ") else "$"


def fmt_large(n: float, sym: str) -> str:
    """
    큰 숫자를 읽기 쉬운 문자열(M, B, T)로 포맷팅합니다.

    :param n: 변환할 숫자
    :param sym: 주식 티커 심볼
    :return: 단위가 적용된 금액 문자열

    >>> fmt_large(1500000, "AAPL")
    '$1.50M'
    """
    try:
        n = float(n or 0)
        if n == 0:
            return "—"
        curr = get_currency_symbol(sym)
        if n >= 1e12:
            return f"{curr}{n/1e12:.2f}T"
        if n >= 1e9:
            return f"{curr}{n/1e9:.2f}B"
        if n >= 1e6:
            return f"{curr}{n/1e6:.2f}M"
        return f"{curr}{n:,.0f}"
    except Exception:
        return "—"


def delta_color(v: float) -> str:
    """변동률에 따른 색상을 반환합니다."""
    return "#2ECC71" if v >= 0 else "#E74C3C"


def delta_str(v: float) -> str:
    """변동률 문자열을 생성합니다."""
    sign = "▲" if v >= 0 else "▼"
    return f"{sign} {abs(v):.2f}%"


def safe_float(v, default=0.0) -> float:
    """안전하게 float으로 변환합니다."""
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def search_stock_ticker(query: str):
    """
    한국 주식은 네이버 금융 API로, 해외 주식은 야후 API로 검색하는 하이브리드 검색기.

    :param query: 사용자 입력 검색어
    :return: (티커, 종목명) 튜플
    """
    try:
        encoded_query = urllib.parse.quote(query.encode("euc-kr"))
        naver_url = f"https://ac.finance.naver.com/ac?q={encoded_query}&q_enc=euc-kr&st=111&r_format=json&r_enc=utf-8"  # noqa: E501
        req = urllib.request.Request(
            naver_url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            items = data.get("items", [[]])[0]
            if items:
                name, code, market = items[0][0], items[0][1], items[0][2]
                if market == "KOSPI":
                    return f"{code}.KS", name
                elif market == "KOSDAQ":
                    return f"{code}.KQ", name
    except Exception:
        pass

    try:
        safe_query = urllib.parse.quote(query)
        yahoo_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={safe_query}"  # noqa: E501
        req = urllib.request.Request(
            yahoo_url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            for q in data.get("quotes", []):
                if q.get("quoteType") in ("EQUITY", "ETF"):
                    return q.get("symbol"), q.get(
                        "shortname", q.get("longname", query)
                    )
    except Exception:
        pass

    return None, None
