"""
utils.py

이 모듈은 대시보드 프로젝트에서 공통으로 사용되는 도우미(Helper) 함수들을 제공합니다.
숫자 포맷팅, 색상 결정, 외부 API를 이용한 종목 검색 등의 '단일 책임'을 가지는
유틸리티 함수들이 포함되어 있어 코드의 중복을 방지하고 DRY(Don't Repeat Yourself) 원칙을 준수합니다.
"""

import urllib.request
import urllib.parse
import json


def get_currency_symbol(sym: str) -> str:
    """
    주식 티커에 따른 통화 기호를 반환합니다.

    :param sym: 주식 티커 심볼 (예: 'AAPL', '005930.KS')
    :return: 한국 주식의 경우 '₩', 그 외 해외 주식은 '$' 문자열을 반환합니다.

    >>> get_currency_symbol("005930.KS")
    '₩'
    >>> get_currency_symbol("AAPL")
    '$'
    """
    # 한국 코스피(.KS)나 코스닥(.KQ)으로 끝나는 경우 원화 기호 사용
    return "₩" if sym.endswith(".KS") or sym.endswith(".KQ") else "$"


def fmt_large(n: float, sym: str) -> str:
    """
    큰 숫자를 읽기 쉬운 문자열(M: 백만, B: 십억, T: 조)로 포맷팅합니다.
    통화 기호도 함께 덧붙여 반환합니다.

    :param n: 변환할 숫자 (시가총액, 거래량 등)
    :param sym: 주식 티커 심볼 (통화 기호 판별용)
    :return: 단위가 적용된 깔끔한 금액 문자열

    >>> fmt_large(1500000, "AAPL")
    '$1.50M'
    >>> fmt_large(0, "TSLA")
    '—'
    """
    try:
        n = float(n or 0)
        if n == 0:
            return "—"
            
        curr = get_currency_symbol(sym)
        
        # 큰 단위부터 순차적으로 검사하여 포맷팅
        if n >= 1e12:
            return f"{curr}{n/1e12:.2f}T"
        if n >= 1e9:
            return f"{curr}{n/1e9:.2f}B"
        if n >= 1e6:
            return f"{curr}{n/1e6:.2f}M"
            
        return f"{curr}{n:,.0f}"
    except Exception:
        # 데이터가 비정상적인 경우 빈 칸(-) 표시 (Fail-safe)
        return "—"


def delta_color(v: float) -> str:
    """
    변동률 값에 따라 UI에 적용할 색상(HEX 코드)을 반환합니다.

    :param v: 등락률 또는 변동 금액 수치
    :return: 양수(상승)면 초록색, 음수(하락)면 빨간색의 16진수 색상 코드

    >>> delta_color(1.5)
    '#2ECC71'
    >>> delta_color(-0.5)
    '#E74C3C'
    """
    return "#2ECC71" if v >= 0 else "#E74C3C"


def delta_str(v: float) -> str:
    """
    변동률 수치를 직관적인 방향 기호(▲/▼)가 포함된 문자열로 포맷팅합니다.

    :param v: 등락 변동률 (예: 2.34, -1.5)
    :return: 상승/하락 기호와 소수점 둘째 자리까지 표시된 문자열

    >>> delta_str(2.34)
    '▲ 2.34%'
    >>> delta_str(-1.50)
    '▼ 1.50%'
    """
    sign = "▲" if v >= 0 else "▼"
    # abs()를 사용해 음수 기호(-)를 제거하고 사용자 지정 기호로 대체
    return f"{sign} {abs(v):.2f}%"


def safe_float(v, default=0.0) -> float:
    """
    다양한 타입의 입력값을 안전하게 float 타입으로 변환합니다.
    변환 불가능한 값(None, 잘못된 문자열 등)이 들어오면 에러를 내지 않고 기본값을 반환합니다.

    :param v: float으로 변환할 데이터
    :param default: 변환 실패 시 반환할 기본값 (기본값: 0.0)
    :return: 변환된 float 값 또는 기본값

    >>> safe_float("3.14")
    3.14
    >>> safe_float(None, 0.0)
    0.0
    >>> safe_float("invalid_string", -1.0)
    -1.0
    """
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def search_stock_ticker(query: str):
    """
    한국 주식은 네이버 금융 API로, 해외 주식은 야후 API로 검색하는 하이브리드 검색기입니다.
    사용자가 종목명이나 티커를 모호하게 입력해도 정확한 야후 파이낸스 티커를 찾아줍니다.

    :param query: 사용자 입력 검색어 (예: "삼성전자", "Apple", "NVDA")
    :return: (티커 심볼, 종목명) 형태의 튜플. 검색 실패 시 (None, None) 반환.

    >>> ticker, name = search_stock_ticker("AAPL")
    >>> ticker == "AAPL"
    True
    """
    
    # 1. 한국 주식 (네이버 금융 자동완성 API 활용)
    try:
        # 네이버 검색 API는 한글(euc-kr) 인코딩을 요구합니다.
        encoded_query = urllib.parse.quote(query.encode("euc-kr"))
        naver_url = f"https://ac.finance.naver.com/ac?q={encoded_query}&q_enc=euc-kr&st=111&r_format=json&r_enc=utf-8"  # noqa: E501
        
        # 봇 차단을 막기 위해 일반 브라우저처럼 User-Agent 헤더 추가
        req = urllib.request.Request(
            naver_url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            items = data.get("items", [[]])[0]
            
            # 검색 결과가 존재할 경우
            if items:
                name, code, market = items[0][0], items[0][1], items[0][2]
                # 야후 파이낸스에서 인식할 수 있도록 한국 주식의 시장 접미사를 붙여 반환
                if market == "KOSPI":
                    return f"{code}.KS", name
                elif market == "KOSDAQ":
                    return f"{code}.KQ", name
    except Exception:
        # 한국 주식 검색 실패 시 시스템을 멈추지 않고 바로 아래의 해외 주식 검색으로 넘어갑니다.
        pass

    # 2. 해외 주식 (야후 파이낸스 검색 API 활용)
    try:
        safe_query = urllib.parse.quote(query)
        yahoo_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={safe_query}"  # noqa: E501
        
        req = urllib.request.Request(
            yahoo_url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            
            for q in data.get("quotes", []):
                # 옵션, 파생상품 등 불필요한 결과물을 제외하고 주식(EQUITY) 및 ETF만 필터링
                if q.get("quoteType") in ("EQUITY", "ETF"):
                    return q.get("symbol"), q.get(
                        "shortname", q.get("longname", query)
                    )
    except Exception:
        # 야후 검색도 실패 시 마지막 fallback 로직으로 이동합니다.
        pass

    # 양쪽 API 모두 검색 결과가 없거나 타임아웃 발생 시
    return None, None