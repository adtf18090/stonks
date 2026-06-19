# 1. 표준 라이브러리 (기본 내장)
import datetime

# 2. 외부 라이브러리 (pip install)
import yfinance as yf
import pandas as pd
import feedparser

# 3. 로컬 모듈 (내가 만든 파일)
from .fetcher_base import BaseMarketFetcher
from .utils import fmt_large, delta_str, safe_float, get_currency_symbol


class YFinanceFetcher(BaseMarketFetcher):
    """yfinance를 활용한 주식 데이터 수집기 클래스입니다."""

    def __init__(self, ticker: str):
        super().__init__(ticker)
        self.yf_ticker = None  # 기본값 초기화
        if self._is_valid_ticker():
            self.yf_ticker = yf.Ticker(self.ticker)
        else:
            raise ValueError(f"유효하지 않은 티커입니다: {ticker}")

    def fetch_basic_info(self) -> dict:
        """사이드바용 간략한 데이터를 가져옵니다."""
        try:
            hist = self.yf_ticker.history(period="5d")
            if hist.empty:
                raise ValueError("No data")
            price = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
            chg = ((price - prev) / prev * 100) if prev else 0
            return {"price": price, "change_pct": chg}
        except Exception:
            return {"price": 0.0, "change_pct": 0.0}

    def fetch_details(self, period: str) -> tuple:
        """메인 대시보드용 상세 데이터와 차트를 가져옵니다."""
        info = self.yf_ticker.info

        if period == "1h":
            hist = self.yf_ticker.history(period="1d", interval="1m").tail(60)
        elif period == "1d":
            hist = self.yf_ticker.history(period="1d", interval="5m")
        elif period == "5d":
            hist = self.yf_ticker.history(period="5d", interval="15m")
        elif period == "3y":
            hist = self.yf_ticker.history(period="5y", interval="1d")
            if not hist.empty:
                cutoff = hist.index[-1] - pd.DateOffset(years=3)
                hist = hist[hist.index >= cutoff]
        else:
            hist = self.yf_ticker.history(period=period, auto_adjust=True)

        # 🚀 [버그 픽스 추가] yfinance가 반환하는 중간의 빈 데이터(NaN)를 제거합니다.
        if not hist.empty:
            hist = hist.dropna(subset=["Close"])

        if hist.empty:
            raise ValueError("No history")

        price = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        chg = ((price - prev) / prev * 100) if prev else 0

        hist_52w = self.yf_ticker.history(period="1y")
        high_52w = hist_52w["High"].max() if not hist_52w.empty else 0
        low_52w = hist_52w["Low"].min() if not hist_52w.empty else 0

        curr = get_currency_symbol(self.ticker)
        stats = {
            "현재가": f"{curr}{price:,.2f}",
            "변동률": delta_str(chg),
            "거래량": fmt_large(
                info.get("volume") or hist["Volume"].iloc[-1], self.ticker
            ),
            "시가총액": fmt_large(info.get("marketCap", 0), self.ticker),
            "52주 최고가": f"{curr}{high_52w:,.2f}" if high_52w else "—",
            "52주 최저가": f"{curr}{low_52w:,.2f}" if low_52w else "—",
        }

        fund = {
            "PER": (
                str(round(safe_float(info.get("trailingPE")), 1))
                if info.get("trailingPE")
                else "—"
            ),
            "선행 PER": (
                str(round(safe_float(info.get("forwardPE")), 1))
                if info.get("forwardPE")
                else "—"
            ),
            "EPS (TTM)": (
                str(round(safe_float(info.get("trailingEps")), 2))
                if info.get("trailingEps")
                else "—"
            ),
            "매출": fmt_large(info.get("totalRevenue", 0), self.ticker),
            "이익률": (
                f"{round(safe_float(info.get('profitMargins'))*100, 1)}%"
                if info.get("profitMargins")
                else "—"
            ),
            "배당수익률": (
                f"{round(safe_float(info.get('dividendYield'))*100, 2)}%"
                if info.get("dividendYield")
                else "—"
            ),
            "베타 (Beta)": (
                str(round(safe_float(info.get("beta")), 2))
                if info.get("beta")
                else "—"
            ),
            "평균 거래량": fmt_large(
                info.get("averageVolume", 0), self.ticker
            ),
            "유동 주식수": fmt_large(info.get("floatShares", 0), self.ticker),
        }

        return stats, fund, hist, chg

    def fetch_news(self) -> list:
        """구글 RSS를 통해 관련 영문 뉴스를 가져옵니다."""
        url = f"https://news.google.com/rss/search?q={self.ticker}+stock&hl=en-US&gl=US&ceid=US:en"  # noqa: E501
        feed = feedparser.parse(url)
        items = []
        for e in feed.entries[:15]:
            try:
                dt = datetime.datetime(*e.published_parsed[:6])
                pub = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pub = ""
            src = e.source.get("title", "") if hasattr(e, "source") else ""
            title = (
                e.get("title", "").rsplit(" - ", 1)[0]
                if " - " in e.get("title", "")
                else e.get("title", "")
            )
            items.append({"title": title, "source": src, "published": pub})
        return items
