"""
GUI 모듈: 화면을 그리고 사용자 입력을 처리하는 프레젠테이션 로직만 담당합니다.

데이터 수집 및 처리는 `fetcher_yfinance.py`와 `utils.py`에 위임하여
단일 책임 원칙(SRP, Single Responsibility Principle)을 준수합니다.

사용 예시:
    >>> from gui import StockDashboard
    >>> app = StockDashboard()
    >>> # app.mainloop()  # GUI 이벤트 루프 실행 (테스트 시 생략)
"""

import matplotlib.pyplot as plt
from .fetcher_yfinance import YFinanceFetcher
from .utils import (
    search_stock_ticker,
    get_currency_symbol,
    delta_color,
    delta_str,
)
import matplotlib.gridspec as gridspec
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import threading
import time
import datetime
import pandas as pd
import numpy as np
import warnings  # 경고 메시지 제어용

import matplotlib

# Tkinter에 Matplotlib 차트를 임베딩하기 위해 백엔드 설정
matplotlib.use("TkAgg")

# 한글 폰트 및 마이너스 폰트 깨짐 방지 설정
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


# ─── Palette (색상 팔레트: 매직 넘버를 상수화하여 가독성 향상) ────────────────
BG = "#0D0D0F"
SURFACE = "#141417"
BORDER = "#1E1E24"
MUTED = "#2A2A33"
TEXT_PRI = "#F0F0F5"
TEXT_SEC = "#6B6B80"
ACCENT = "#4F8EF7"
GREEN = "#2ECC71"
RED = "#E74C3C"
CHART_LINE = "#4F8EF7"
CHART_FILL = "#1A2840"

# CustomTkinter 기본 테마 설정
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# 초기 관심 종목 상수
DEFAULT_WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "005930.KS"]


class StockDashboard(ctk.CTk):
    """
    주식 대시보드의 메인 화면을 구성하는 GUI 클래스입니다.
    
    `customtkinter.CTk`를 상속받아 메인 윈도우를 생성하며, 
    각 UI 컴포넌트의 배치와 사용자 상호작용, 백그라운드 데이터 업데이트를 관리합니다.

    :ivar selected_ticker: 현재 선택된 주식 종목의 티커 (ctk.StringVar)
    :ivar watchlist: 현재 사용자의 관심 종목 리스트 (list)
    :ivar ticker_data: 종목별 최신 데이터를 캐싱하는 딕셔너리 (dict)
    :ivar auto_update: 자동 업데이트 활성화 여부 (tk.BooleanVar)
    
    사용 예시:
        >>> dashboard = StockDashboard()
        >>> type(dashboard.watchlist)
        <class 'list'>
    """

    def __init__(self):
        """StockDashboard 인스턴스를 초기화하고 기본 UI 레이아웃을 구성합니다."""
        super().__init__()
        
        # 1. 메인 윈도우 설정
        self.title("주식 시장 대시보드")
        self.geometry("1440x900")
        self.minsize(1200, 720)
        self.configure(fg_color=BG)

        # 2. 상태(State) 관리 변수 초기화
        self.selected_ticker = ctk.StringVar(value="AAPL")
        self.watchlist = list(DEFAULT_WATCHLIST)
        self.ticker_data: dict = {}

        # API 호출을 줄이기 위한 종목명 캐싱
        self.ticker_names = {
            "AAPL": "Apple",
            "TSLA": "Tesla",
            "NVDA": "NVIDIA",
            "MSFT": "Microsoft",
            "005930.KS": "삼성전자",
        }

        # 3. 차트 컨트롤 및 설정용 Tkinter 변수
        self.period_var = ctk.StringVar(value="1mo")
        self.chart_type_var = ctk.StringVar(value="라인 차트")
        self.show_sma = tk.BooleanVar(value=False)
        self.show_vol = tk.BooleanVar(value=False)
        self.auto_update = tk.BooleanVar(value=True)
        self.update_interval = tk.IntVar(value=60)

        # 차트 렌더링을 위한 캔버스 및 데이터 상태
        self._chart_canvas = None
        self.current_hist = pd.DataFrame()

        # 차트 클릭(인터랙션) 관련 상태 저장 리스트
        self.click_points = []
        self.click_artists = []
        self.ax = None
        self.ax_vol = None

        # 4. 이벤트 바인딩 (ESC 키를 누르면 차트 측정 포인트 초기화)
        self.bind("<Escape>", lambda e: self._clear_chart_points())

        # 5. UI 빌드 및 데이터 스레드 시작
        self._build_layout()
        self._start_data_thread()

    # ── Layout (레이아웃 구성) ───────────────────────────────────────────────
    def _build_layout(self):
        """
        메인 윈도우의 그리드 레이아웃(Grid Layout)을 설정하고 
        각 구역(상단바, 사이드바, 메인 패널)을 생성하는 비공개 메서드입니다.
        """
        self.grid_columnconfigure(0, weight=0, minsize=210)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        
        self._build_topbar()
        self._build_sidebar()
        self._build_main()

    # ── Top bar (상단 바) ──────────────────────────────────────────────────
    def _build_topbar(self):
        """화면 상단의 검색바, 설정 버튼, 연결 상태 배지 및 시계를 생성합니다."""
        bar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=54)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        # 로고 타이틀
        ctk.CTkLabel(
            bar,
            text="◈  시장 동향",
            font=ctk.CTkFont("Malgun Gothic", 15, weight="bold"),
            text_color=ACCENT,
        ).grid(row=0, column=0, padx=20, sticky="w")

        # 중앙: 검색창 및 설정 버튼 영역
        center = ctk.CTkFrame(bar, fg_color="transparent")
        center.grid(row=0, column=1, pady=10)

        ef = ctk.CTkFrame(center, fg_color=MUTED, corner_radius=7)
        ef.grid(row=0, column=0, padx=5)
        
        # 검색 엔트리 (엔터 키 입력 시 추가 로직 실행)
        self.add_entry = ctk.CTkEntry(
            ef,
            placeholder_text="종목명 또는 티커 검색...",
            font=ctk.CTkFont("Malgun Gothic", 12),
            fg_color="transparent",
            border_width=0,
            text_color=TEXT_PRI,
            width=200,
            height=28,
        )
        self.add_entry.grid(row=0, column=0, padx=(10, 4))
        self.add_entry.bind("<Return>", self._add_ticker)
        
        # 추가 버튼
        ctk.CTkButton(
            ef,
            text="＋",
            width=30,
            height=28,
            font=ctk.CTkFont("Arial", 14),
            fg_color=ACCENT,
            hover_color="#3a72d4",
            corner_radius=5,
            command=lambda: self._add_ticker(None),
        ).grid(row=0, column=1, padx=(0, 4))

        # 설정 창 오픈 버튼
        ctk.CTkButton(
            center,
            text="⚙️ 설정",
            width=60,
            height=28,
            font=ctk.CTkFont("Malgun Gothic", 12),
            fg_color=MUTED,
            hover_color=BORDER,
            text_color=TEXT_PRI,
            command=self._open_settings,
        ).grid(row=0, column=1, padx=5)

        # 우측: 연결 상태 및 시계
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, padx=20, sticky="e")
        self.src_badge = ctk.CTkLabel(
            right,
            text="● 연결됨",
            font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
            text_color=GREEN,
        )
        self.src_badge.grid(row=0, column=0, padx=(0, 12))
        
        self.clock_lbl = ctk.CTkLabel(
            right,
            text="",
            font=ctk.CTkFont("Malgun Gothic", 12),
            text_color=TEXT_SEC,
        )
        self.clock_lbl.grid(row=0, column=1)
        self._tick_clock() # 시계 업데이트 루프 시작

    def _tick_clock(self):
        """1초마다 상단바의 현재 시간을 업데이트하는 재귀(after) 메서드입니다."""
        self.clock_lbl.configure(
            text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        )
        self.after(1000, self._tick_clock)

    def _open_settings(self):
        """
        모달(Toplevel) 설정 창을 엽니다. 
        차트 타입(라인/캔들) 및 데이터 자동 업데이트 주기를 설정할 수 있습니다.
        """
        top = ctk.CTkToplevel(self)
        top.title("설정")
        top.geometry("320x300")
        top.configure(fg_color=SURFACE)
        top.transient(self) # 메인 윈도우 위에 표시
        top.grab_set()      # 모달 포커스 고정

        # --- 차트 설정 섹션 ---
        ctk.CTkLabel(
            top,
            text="차트 표시 설정",
            font=ctk.CTkFont("Malgun Gothic", 14, weight="bold"),
            text_color=TEXT_PRI,
        ).pack(pady=(20, 10))
        
        seg = ctk.CTkSegmentedButton(
            top,
            values=["라인 차트", "캔들 차트"],
            variable=self.chart_type_var,
            font=ctk.CTkFont("Malgun Gothic", 12),
            command=lambda v: self._refresh_chart_only(),
        )
        seg.pack(pady=5)

        # --- 업데이트 설정 섹션 ---
        ctk.CTkLabel(
            top,
            text="데이터 업데이트 설정",
            font=ctk.CTkFont("Malgun Gothic", 14, weight="bold"),
            text_color=TEXT_PRI,
        ).pack(pady=(20, 10))
        
        ctk.CTkCheckBox(
            top,
            text="자동 업데이트 켜기",
            variable=self.auto_update,
            font=ctk.CTkFont("Malgun Gothic", 12),
        ).pack(pady=5)

        # UI 문자열 <-> 초(seconds) 단위 매핑 헬퍼 함수
        def set_interval(choice):
            mapping = {"10초": 10, "30초": 30, "1분": 60, "5분": 300}
            self.update_interval.set(mapping.get(choice, 60))

        interval_frame = ctk.CTkFrame(top, fg_color="transparent")
        interval_frame.pack(pady=5)
        
        ctk.CTkLabel(
            interval_frame,
            text="업데이트 주기: ",
            font=ctk.CTkFont("Malgun Gothic", 12),
        ).pack(side="left", padx=5)

        current_sec = self.update_interval.get()
        reverse_mapping = {10: "10초", 30: "30초", 60: "1분", 300: "5분"}
        interval_menu = ctk.CTkOptionMenu(
            interval_frame,
            values=["10초", "30초", "1분", "5분"],
            command=set_interval,
        )
        interval_menu.set(reverse_mapping.get(current_sec, "1분"))
        interval_menu.pack(side="left")

        ctk.CTkButton(
            top,
            text="닫기",
            width=100,
            command=top.destroy,
            fg_color=MUTED,
            hover_color=BORDER,
        ).pack(pady=(20, 0))

    # ── Sidebar (사이드바) ──────────────────────────────────────────────────
    def _build_sidebar(self):
        """좌측의 관심 종목(Watchlist) 패널을 구성합니다."""
        self.sidebar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(1, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text="관심 종목 (WATCHLIST)",
            font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
            text_color=TEXT_SEC,
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        
        # 종목이 많아질 경우를 대비한 스크롤 프레임 사용
        self.watch_scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", corner_radius=0
        )
        self.watch_scroll.grid(row=1, column=0, sticky="nsew")
        self.watch_scroll.grid_columnconfigure(0, weight=1)
        
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        """관심 종목 리스트의 UI를 갱신합니다. 기존 위젯을 삭제하고 다시 그립니다."""
        for w in self.watch_scroll.winfo_children():
            w.destroy()
        for i, sym in enumerate(self.watchlist):
            self._sidebar_card(sym, i)

    def _sidebar_card(self, sym: str, idx: int):
        """
        단일 종목 카드를 생성하여 사이드바에 배치합니다.

        :param sym: 주식 종목의 티커 심볼 (예: 'AAPL')
        :param idx: UI 상에 배치될 그리드 행 인덱스
        """
        data = self.ticker_data.get(sym, {})
        price = data.get("price", 0.0)
        chg = data.get("change_pct", 0.0)
        active = (sym == self.selected_ticker.get())
        name = self.ticker_names.get(sym, sym)
        curr = get_currency_symbol(sym)

        # 카드 배경 (선택된 종목은 강조색 적용)
        card = ctk.CTkFrame(
            self.watch_scroll,
            fg_color=MUTED if active else "transparent",
            corner_radius=7,
            cursor="hand2",
        )
        card.grid(row=idx, column=0, padx=10, pady=3, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        card.bind("<Button-1>", lambda e, s=sym: self._select_ticker(s))

        # 카드 상단 (종목명, 삭제 버튼)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, padx=10, pady=(8, 2), sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        sym_lbl = ctk.CTkLabel(
            top,
            text=name,
            font=ctk.CTkFont("Malgun Gothic", 13, weight="bold"),
            text_color=ACCENT if active else TEXT_PRI,
            cursor="hand2",
        )
        sym_lbl.grid(row=0, column=0, sticky="w")
        sym_lbl.bind("<Button-1>", lambda e, s=sym: self._select_ticker(s))

        rm = ctk.CTkLabel(
            top,
            text="×",
            font=ctk.CTkFont("Arial", 16),
            text_color=TEXT_SEC,
            cursor="hand2",
        )
        rm.grid(row=0, column=1, sticky="e")
        rm.bind("<Button-1>", lambda e, s=sym: self._remove_ticker(s))

        # 카드 하단 (가격, 등락률)
        bot = ctk.CTkFrame(card, fg_color="transparent")
        bot.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        
        ctk.CTkLabel(
            bot,
            text=f"{curr}{price:,.2f}" if price else "—",
            font=ctk.CTkFont("Courier", 13, weight="bold"),
            text_color=TEXT_PRI,
        ).grid(row=0, column=0, sticky="w")
        
        ctk.CTkLabel(
            bot,
            text=delta_str(chg) if price else "",
            font=ctk.CTkFont("Courier", 11),
            text_color=delta_color(chg),
        ).grid(row=0, column=1, padx=(8, 0), sticky="w")

    # ── Main panel (메인 패널) ──────────────────────────────────────────────
    def _build_main(self):
        """우측 메인 패널(헤더 정보, 차트, 하단 지표/뉴스)의 레이아웃을 구성합니다."""
        self.main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main.grid(row=1, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        
        # 화면 비율(row weight) 조정: 차트 영역을 조금 더 크게 할당
        self.main.grid_rowconfigure(1, weight=3)
        self.main.grid_rowconfigure(2, weight=2)
        
        self._build_hero_stats()
        self._build_chart_panel()
        self._build_bottom_row()

    def _build_hero_stats(self):
        """메인 패널 최상단에 핵심 요약 정보(가격, 시총, 거래량 등) 영역을 만듭니다."""
        self.hero = ctk.CTkFrame(self.main, fg_color="transparent")
        self.hero.grid(row=0, column=0, padx=20, pady=(16, 0), sticky="ew")
        self.hero.grid_columnconfigure(tuple(range(6)), weight=1)

        self.ticker_header = ctk.CTkLabel(
            self.hero,
            text="Apple",
            font=ctk.CTkFont("Malgun Gothic", 28, weight="bold"),
            text_color=TEXT_PRI,
        )
        self.ticker_header.grid(
            row=0, column=0, columnspan=6, padx=5, pady=(0, 10), sticky="w"
        )

        self.stat_lbls = {}
        # 반복문 활용하여 유사한 구조의 통계 카드들을 동적 생성 (DRY 원칙 적용)
        stat_keys = ["현재가", "변동률", "거래량", "시가총액", "52주 최고가", "52주 최저가"]
        for i, key in enumerate(stat_keys):
            card = ctk.CTkFrame(self.hero, fg_color=SURFACE, corner_radius=8)
            card.grid(row=1, column=i, padx=5, sticky="ew", ipady=8)
            card.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(
                card,
                text=key,
                font=ctk.CTkFont("Malgun Gothic", 10, weight="bold"),
                text_color=TEXT_SEC,
            ).grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
            
            val = ctk.CTkLabel(
                card,
                text="—",
                font=ctk.CTkFont("Courier", 16, weight="bold"),
                text_color=TEXT_PRI,
            )
            val.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
            self.stat_lbls[key] = val

    # ── Chart (차트 설정 및 오버레이 옵션) ──────────────────────────────────
    def _build_chart_panel(self):
        """
        주가 차트 및 제어 버튼(기간 선택, SMA, 거래량 토글) 영역을 구성합니다.
        Matplotlib 차트가 삽입될 컨테이너를 포함합니다.
        """
        self.chart_frame = ctk.CTkFrame(
            self.main, fg_color=SURFACE, corner_radius=10
        )
        self.chart_frame.grid(row=1, column=0, padx=20, pady=12, sticky="nsew")
        self.chart_frame.grid_columnconfigure(0, weight=1)
        self.chart_frame.grid_rowconfigure(1, weight=1)

        # 차트 제어부 (상단)
        ctrl = ctk.CTkFrame(self.chart_frame, fg_color="transparent")
        ctrl.grid(row=0, column=0, padx=16, pady=(12, 0), sticky="ew")
        ctrl.grid_columnconfigure(2, weight=1)

        # 기간 선택 버튼 생성
        btn_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="w")
        self.period_btns = {}
        periods = [
            ("1시간", "1h"), ("1일", "1d"), ("1주일", "5d"), 
            ("1개월", "1mo"), ("3개월", "3mo"), ("1년", "1y"), 
            ("3년", "3y"), ("5년", "5y")
        ]
        
        for j, (label, val) in enumerate(periods):
            btn = ctk.CTkButton(
                btn_frame,
                text=label,
                width=46,
                height=26,
                font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
                fg_color=ACCENT if val == "1mo" else MUTED,
                hover_color="#3a72d4",
                corner_radius=5,
                command=lambda v=val: self._change_period(v),
            )
            btn.grid(row=0, column=j, padx=2)
            self.period_btns[val] = btn

        # 보조 지표 체크박스
        cb_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        cb_frame.grid(row=0, column=1, padx=15, sticky="w")
        
        ctk.CTkCheckBox(
            cb_frame,
            text="SMA (5,20,60)",
            variable=self.show_sma,
            font=ctk.CTkFont("Malgun Gothic", 11),
            text_color=TEXT_SEC,
            command=self._refresh_chart_only,
        ).grid(row=0, column=0, padx=5)
        
        ctk.CTkCheckBox(
            cb_frame,
            text="거래량",
            variable=self.show_vol,
            font=ctk.CTkFont("Malgun Gothic", 11),
            text_color=TEXT_SEC,
            command=self._refresh_chart_only,
        ).grid(row=0, column=1, padx=5)

        # 차트 측정 포인트 초기화 버튼 (기본적으로 숨김 처리)
        self.clear_btn = ctk.CTkButton(
            ctrl,
            text="초기화 (ESC)",
            width=80,
            height=26,
            font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
            fg_color=RED,
            hover_color="#c0392b",
            corner_radius=5,
            command=self._clear_chart_points,
        )
        self.clear_btn.grid(row=0, column=3, padx=(0, 10), sticky="e")
        self.clear_btn.grid_remove()

        # 수동 업데이트 버튼
        self.refresh_btn = ctk.CTkButton(
            ctrl,
            text="🔄 수동 고침",
            width=90,
            height=26,
            font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
            fg_color=MUTED,
            hover_color=BORDER,
            text_color=TEXT_PRI,
            corner_radius=5,
            command=self._force_update_async,
        )
        self.refresh_btn.grid(row=0, column=4, sticky="e")

        # Matplotlib 차트가 삽입될 컨테이너
        self.chart_container = ctk.CTkFrame(
            self.chart_frame, fg_color="transparent", corner_radius=0
        )
        self.chart_container.grid(
            row=1, column=0, sticky="nsew", padx=8, pady=(4, 8)
        )
        self.chart_container.grid_propagate(False)

        self.loading_lbl = ctk.CTkLabel(
            self.chart_container,
            text="차트 불러오는 중…",
            font=ctk.CTkFont("Malgun Gothic", 12),
            text_color=TEXT_SEC,
        )
        self.loading_lbl.pack(expand=True)

    def _refresh_chart_only(self):
        """API 재호출 없이 현재 캐시된 데이터를 기반으로 차트만 다시 그립니다."""
        if not self.current_hist.empty:
            self._draw_chart(self.current_hist)

    def _draw_chart(self, hist: pd.DataFrame):
        """
        Pandas DataFrame 데이터를 받아 Matplotlib 차트를 생성하고 Tkinter 캔버스에 임베딩합니다.

        :param hist: 'Open', 'High', 'Low', 'Close', 'Volume' 등의 컬럼을 포함한 시계열 DataFrame.
        """
        self._clear_chart_points()
        self.current_hist = hist

        # 기존 캔버스 정리
        if self._chart_canvas:
            self._chart_canvas.get_tk_widget().destroy()
            self._chart_canvas = None
        for w in self.chart_container.winfo_children():
            w.destroy()

        if hist is None or hist.empty:
            ctk.CTkLabel(
                self.chart_container,
                text="차트 데이터가 없습니다.",
                font=ctk.CTkFont("Malgun Gothic", 12),
                text_color=TEXT_SEC,
            ).pack(expand=True)
            return

        # Figure 초기화 (어두운 테마에 맞춤)
        fig = Figure(figsize=(6, 3.5), dpi=100)
        fig.patch.set_facecolor(SURFACE)

        # 거래량 표시 여부에 따른 GridSpec 레이아웃 분기
        gs = gridspec.GridSpec(4, 1, hspace=0.1)
        if self.show_vol.get():
            self.ax = fig.add_subplot(gs[0:3, 0])
            self.ax_vol = fig.add_subplot(gs[3, 0], sharex=self.ax)
            self.ax_vol.set_facecolor(SURFACE)
            plt.setp(self.ax.get_xticklabels(), visible=False)
        else:
            self.ax = fig.add_subplot(gs[:, 0])
            self.ax_vol = None

        self.ax.set_facecolor(SURFACE)

        df = hist.copy()
        dates = df.index.to_pydatetime()
        df["DateNum"] = mdates.date2num(dates)
        closes = df["Close"].values

        is_candle = self.chart_type_var.get() == "캔들 차트"

        # 라인 차트 vs 캔들스틱 차트 분기 처리
        if is_candle:
            dx = np.median(np.diff(df["DateNum"])) * 0.7
            if np.isnan(dx) or dx == 0:
                dx = 0.5
            up = df[df.Close >= df.Open]
            down = df[df.Close < df.Open]
            
            # 캔들스틱 - 고가/저가 선 그리기
            self.ax.vlines(up["DateNum"], up.Low, up.High, color=GREEN, linewidth=1, zorder=3)
            self.ax.vlines(down["DateNum"], down.Low, down.High, color=RED, linewidth=1, zorder=3)
            
            # 캔들스틱 - 시가/종가 몸통 그리기
            self.ax.bar(up["DateNum"], up.Close - up.Open, width=dx, bottom=up.Open, color=GREEN, zorder=3)
            self.ax.bar(down["DateNum"], down.Open - down.Close, width=dx, bottom=down.Close, color=RED, zorder=3)
        else:
            # 라인 차트 영역 채우기
            self.ax.fill_between(
                dates, closes, closes.min() * 0.998, color=CHART_FILL, alpha=0.7, zorder=1
            )
            self.ax.plot(dates, closes, color=CHART_LINE, linewidth=1.6, zorder=3)

        # 단순이동평균(SMA) 오버레이
        if self.show_sma.get():
            for w, c in [(5, "#f1c40f"), (20, "#9b59b6"), (60, "#e67e22")]:
                sma = df["Close"].rolling(window=w).mean()
                self.ax.plot(dates, sma, color=c, linewidth=1.2, label=f"SMA {w}", zorder=2)
            self.ax.legend(
                loc="upper left", fontsize=7, framealpha=0.5,
                facecolor=SURFACE, edgecolor=BORDER, labelcolor=TEXT_PRI,
            )

        # 최고가 및 최저가 텍스트 주석(Annotation) 표시
        curr = get_currency_symbol(self.selected_ticker.get())
        i_max, i_min = closes.argmax(), closes.argmin()
        
        self.ax.annotate(
            f"{curr}{closes[i_max]:,.2f}",
            xy=(dates[i_max], closes[i_max]), xytext=(0, 8),
            textcoords="offset points", color=GREEN, fontsize=8, ha="center",
        )
        self.ax.annotate(
            f"{curr}{closes[i_min]:,.2f}",
            xy=(dates[i_min], closes[i_min]), xytext=(0, -14),
            textcoords="offset points", color=RED, fontsize=8, ha="center",
        )

        # 축 및 격자 스타일 설정
        self.ax.tick_params(colors=TEXT_SEC, labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(BORDER)
        self.ax.set_xlim(dates[0], dates[-1])
        self.ax.yaxis.set_label_position("right")
        self.ax.yaxis.tick_right()
        self.ax.grid(axis="y", color=BORDER, linewidth=0.5, alpha=0.6)
        self.ax.grid(axis="x", color="none")

        # 거래량(Volume) 서브플롯 렌더링
        if self.ax_vol:
            dx_vol = np.median(np.diff(df["DateNum"])) * 0.8
            if np.isnan(dx_vol) or dx_vol == 0:
                dx_vol = 0.5
            colors = [GREEN if c >= o else RED for c, o in zip(df["Close"], df["Open"])]
            
            self.ax_vol.bar(df["DateNum"], df["Volume"], width=dx_vol, color=colors, alpha=0.8)
            self.ax_vol.tick_params(colors=TEXT_SEC, labelsize=7)
            for spine in self.ax_vol.spines.values():
                spine.set_edgecolor(BORDER)
            self.ax_vol.yaxis.set_label_position("right")
            self.ax_vol.yaxis.tick_right()
            self.ax_vol.grid(axis="y", color=BORDER, linewidth=0.5, alpha=0.6)
            self.ax_vol.grid(axis="x", color="none")

            def vol_fmt(x, pos):
                """거래량 단위 포맷팅 헬퍼 함수"""
                if x >= 1e6: return f"{x*1e-6:.1f}M"
                elif x >= 1e3: return f"{x*1e-3:.0f}K"
                return f"{x:.0f}"

            from matplotlib.ticker import FuncFormatter
            self.ax_vol.yaxis.set_major_formatter(FuncFormatter(vol_fmt))

        # X축 날짜 포맷팅 (조회 기간에 따라 동적 변경)
        bottom_ax = self.ax_vol if self.ax_vol else self.ax
        period = self.period_var.get()
        if period in ("1h", "1d", "5d"):
            bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        elif period in ("1mo", "3mo"):
            bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter("%m월 %d일"))
        else:
            bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter("%y년 %m월"))

        fig.autofmt_xdate(rotation=0, ha="center")
        if not self.show_vol.get():
            fig.tight_layout(pad=1.2)

        # Matplotlib Figure를 Tkinter 위젯으로 변환 및 이벤트 바인딩
        self._chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_container)
        self._chart_canvas.mpl_connect("button_press_event", self._on_chart_click)
        self._chart_canvas.draw()
        
        w = self._chart_canvas.get_tk_widget()
        w.configure(bg=SURFACE, highlightthickness=0)
        w.pack(fill=tk.BOTH, expand=True)

    def _on_chart_click(self, event):
        """
        차트 클릭 시 발생하는 콜백 메서드입니다. 
        두 점을 클릭하면 등락률과 차이를 시각적으로 계산하여 보여줍니다.

        :param event: Matplotlib 마우스 클릭 이벤트 객체
        """
        if not event.inaxes or self.current_hist.empty:
            return
        if event.inaxes != self.ax:
            return
        if event.button != 1:  # 좌클릭만 허용
            return

        if len(self.click_points) == 2:
            self._clear_chart_points()

        # 가장 가까운 데이터 포인트 찾기
        dates_num = mdates.date2num(self.current_hist.index.to_pydatetime())
        idx = np.argmin(np.abs(dates_num - event.xdata))
        px = dates_num[idx]
        py = self.current_hist["Close"].iloc[idx]
        p_date = self.current_hist.index[idx]
        curr = get_currency_symbol(self.selected_ticker.get())
        
        period = self.period_var.get()
        fmt_str = "%m-%d %H:%M" if period in ("1h", "1d", "5d") else "%y-%m-%d"
        date_str = p_date.strftime(fmt_str)

        self.click_points.append((px, py, p_date))
        
        # 클릭한 지점에 점 찍기
        (dot,) = self.ax.plot(px, py, marker="o", color="white", markersize=6, zorder=6)
        self.click_artists.append(dot)

        # 첫 번째 클릭 시 가격 표시, 두 번째 클릭 시 차이/등락률 계산 표시
        if len(self.click_points) == 1:
            txt = f"{curr}{py:,.2f}\n{date_str}"
            ann = self.ax.annotate(
                txt, xy=(px, py), xytext=(0, 15), textcoords="offset points",
                ha="center", va="bottom", color=TEXT_PRI, fontsize=9, weight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=BORDER, alpha=0.85),
                zorder=6,
            )
            self.click_artists.append(ann)
            self.clear_btn.grid()
        elif len(self.click_points) == 2:
            p1_x, p1_y, _ = self.click_points[0]
            p2_x, p2_y, _ = self.click_points[1]
            (line,) = self.ax.plot(
                [p1_x, p2_x], [p1_y, p2_y], color="white", linestyle="--", linewidth=1.5, zorder=5
            )
            self.click_artists.append(line)
            
            diff = p2_y - p1_y
            pct_change = (diff / p1_y) * 100 if p1_y != 0 else 0
            sign = "+" if diff >= 0 else ""
            color = GREEN if diff >= 0 else RED
            txt = f"{sign}{curr}{diff:,.2f} ({sign}{pct_change:.2f}%)"
            
            ann = self.ax.annotate(
                txt, xy=(p2_x, p2_y), xytext=(0, -20), textcoords="offset points",
                ha="center", va="top", color=color, fontsize=10, weight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=BORDER, alpha=0.9),
                zorder=6,
            )
            self.click_artists.append(ann)
            
        self._chart_canvas.draw()

    def _clear_chart_points(self):
        """차트 위에 그려진 사용자 클릭 마커 및 측정 선을 모두 지웁니다."""
        if not self.click_artists:
            return
        for artist in self.click_artists:
            artist.remove()
        self.click_artists.clear()
        self.click_points.clear()
        
        if self._chart_canvas:
            self._chart_canvas.draw()
        self.clear_btn.grid_remove()

    # ── Bottom row (하단 패널) ──────────────────────────────────────────────
    def _build_bottom_row(self):
        """기본 지표(Fundamentals)와 최신 뉴스 패널을 담는 하단 영역을 구성합니다."""
        row = ctk.CTkFrame(self.main, fg_color="transparent")
        row.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="nsew")
        row.grid_columnconfigure((0, 1), weight=1)
        row.grid_rowconfigure(0, weight=1)
        
        self._build_fundamentals(row)
        self._build_news_panel(row)

    def _build_fundamentals(self, parent):
        """PER, EPS, 시가총액 등 기본 분석 지표 표를 생성합니다."""
        frame = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10)
        frame.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            frame,
            text="기본 지표 (FUNDAMENTALS)",
            font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
            text_color=TEXT_SEC,
        ).grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")
        
        sf = ctk.CTkScrollableFrame(frame, fg_color="transparent", corner_radius=0)
        sf.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        sf.grid_columnconfigure((0, 1), weight=1)
        self.fund_scroll = sf

        self.fund_rows = []
        fund_keys = [
            "PER", "선행 PER", "EPS (TTM)", "매출", "이익률",
            "배당수익률", "베타 (Beta)", "평균 거래량", "유동 주식수"
        ]
        
        for i, key in enumerate(fund_keys):
            ctk.CTkLabel(
                sf, text=key, font=ctk.CTkFont("Malgun Gothic", 12), text_color=TEXT_SEC,
            ).grid(row=i, column=0, padx=12, pady=4, sticky="w")
            
            val = ctk.CTkLabel(
                sf, text="—", font=ctk.CTkFont("Courier", 12), text_color=TEXT_PRI,
            )
            val.grid(row=i, column=1, padx=12, pady=4, sticky="e")
            
            # 리스트 아이템 사이 구분선
            sep = ctk.CTkFrame(sf, fg_color=BORDER, height=1)
            sep.grid(row=i, column=0, columnspan=2, padx=8, pady=(0, 0), sticky="ew")
            self.fund_rows.append((key, val))

    def _build_news_panel(self, parent):
        """해당 종목과 관련된 최신 뉴스 기사 리스트 영역을 구성합니다."""
        frame = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10)
        frame.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            hdr,
            text="최신 뉴스 (LATEST NEWS)",
            font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
            text_color=TEXT_SEC,
        ).grid(row=0, column=0, sticky="w")
        
        self.news_status = ctk.CTkLabel(
            hdr,
            text="● 대기중",
            font=ctk.CTkFont("Malgun Gothic", 10, weight="bold"),
            text_color=TEXT_SEC,
        )
        self.news_status.grid(row=0, column=1, sticky="e")

        sf = ctk.CTkScrollableFrame(frame, fg_color="transparent", corner_radius=0)
        sf.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        sf.grid_columnconfigure(0, weight=1)
        self.news_scroll = sf

    def _populate_news(self, items: list):
        """
        뉴스 데이터를 UI에 반영합니다.

        :param items: [{'title': '...', 'source': '...', 'published': '...'}, ...] 형태의 리스트
        """
        for w in self.news_scroll.winfo_children():
            w.destroy()
            
        if not items:
            ctk.CTkLabel(
                self.news_scroll,
                text="뉴스 불러오는 중…",
                font=ctk.CTkFont("Malgun Gothic", 12),
                text_color=TEXT_SEC,
                wraplength=340,
            ).grid(row=0, column=0, padx=12, pady=12)
            return
            
        for i, item in enumerate(items[:14]):
            card = ctk.CTkFrame(
                self.news_scroll,
                fg_color=MUTED if i % 2 == 0 else "transparent", # 홀짝 배경색 교차 적용
                corner_radius=6,
            )
            card.grid(row=i, column=0, padx=6, pady=2, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(
                card,
                text=item.get("title", ""),
                font=ctk.CTkFont("Malgun Gothic", 12),
                text_color=TEXT_PRI,
                wraplength=360,
                justify="left",
                anchor="w",
            ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")
            
            meta = "  ·  ".join(filter(None, [item.get("source"), item.get("published")]))
            ctk.CTkLabel(
                card,
                text=meta,
                font=ctk.CTkFont("Malgun Gothic", 10),
                text_color=TEXT_SEC,
                anchor="w",
            ).grid(row=1, column=0, padx=10, pady=(0, 6), sticky="w")

    # ── 데이터 수집 및 업데이트 스레드 (Threading) ─────────────────────────
    def _start_data_thread(self):
        """네트워크 I/O로 인한 GUI 멈춤(Freezing) 현상을 막기 위해 백그라운드 데몬 스레드를 실행합니다."""
        threading.Thread(target=self._data_loop, daemon=True).start()

    def _force_update(self):
        """전체 종목 및 현재 선택된 종목의 상세 데이터를 동기적으로 갱신합니다."""
        self.after(
            0, lambda: self.src_badge.configure(text="● 갱신 중...", text_color=ACCENT)
        )
        self._fetch_all_tickers()
        sym = self.selected_ticker.get()
        self._fetch_detail(sym)
        self._fetch_news(sym)

    def _force_update_async(self):
        """수동 업데이트 버튼 클릭 시 기존 스레드와 충돌하지 않도록 비동기로 업데이트를 실행합니다."""
        threading.Thread(target=self._force_update, daemon=True).start()

    def _data_loop(self):
        """설정된 주기마다 데이터를 자동 갱신하는 무한 루프 메서드입니다. (데몬 스레드에서 실행)"""
        self._force_update()  # 최초 1회 실행
        last_update_time = time.time()

        while True:
            time.sleep(1)  # 1초마다 상태 확인 (CPU 점유율 낭비 방지)
            if self.auto_update.get():
                current_time = time.time()
                # 설정된 주기(초)가 지났으면 업데이트 실행
                if (current_time - last_update_time) >= self.update_interval.get():
                    self._force_update()
                    last_update_time = time.time()
            else:
                # 자동 업데이트가 꺼져있을 때는 기준 시간만 현재 시간으로 초기화
                last_update_time = time.time()

    def _fetch_all_tickers(self):
        """관심 종목에 등록된 모든 주식의 기본 정보(현재가 등)를 가져와 사이드바를 업데이트합니다."""
        failed_any = False
        for sym in list(self.watchlist):
            fetcher = YFinanceFetcher(sym)
            data = fetcher.fetch_basic_info()
            if data["price"] == 0.0:
                failed_any = True
            self.ticker_data[sym] = data
            
        # UI 업데이트는 반드시 메인 스레드(after 메서드)에서 수행해야 안전함
        self.after(0, self._refresh_sidebar)
        
        badge = "● 실시간" if not failed_any else "○ 일부 연결 실패"
        col = GREEN if not failed_any else RED
        self.after(0, lambda: self.src_badge.configure(text=badge, text_color=col))

    def _fetch_detail(self, sym: str):
        """
        특정 종목의 상세 정보 및 차트 기록(Historical Data)을 조회합니다.

        :param sym: 조회할 종목 티커 심볼
        """
        try:
            fetcher = YFinanceFetcher(sym)
            stats, fund, hist, chg = fetcher.fetch_details(self.period_var.get())
            chg_col = delta_color(chg)
            self.after(0, lambda: self._update_detail_ui(sym, stats, fund, hist, chg_col))
        except Exception:
            # 실패 시 예외 처리: 하이픈(-)으로 빈칸 처리
            empty_keys_stats = ["현재가", "변동률", "거래량", "시가총액", "52주 최고가", "52주 최저가"]
            empty_stats = {k: "—" for k in empty_keys_stats}
            empty_keys_fund = ["PER", "선행 PER", "EPS (TTM)", "매출", "이익률", "배당수익률", "베타 (Beta)", "평균 거래량", "유동 주식수"]
            empty_fund = {k: "—" for k in empty_keys_fund}
            
            self.after(0, lambda: self._update_detail_ui(sym, empty_stats, empty_fund, pd.DataFrame(), TEXT_PRI))

    def _update_detail_ui(self, sym: str, stats: dict, fund: dict, hist: pd.DataFrame, chg_col: str):
        """
        API에서 수집한 상세 데이터를 바탕으로 메인 패널 위젯 값을 변경합니다.
        
        :param sym: 종목 티커
        :param stats: 핵심 요약 통계 딕셔너리
        :param fund: 펀더멘탈(기본지표) 딕셔너리
        :param hist: 차트 렌더링을 위한 과거 주가 데이터
        :param chg_col: 등락률에 따른 색상 (RED/GREEN)
        """
        name = self.ticker_names.get(sym, sym)
        self.ticker_header.configure(text=name)
        
        for key, lbl in self.stat_lbls.items():
            col = chg_col if key == "변동률" else TEXT_PRI
            lbl.configure(text=stats.get(key, "—"), text_color=col)
            
        for key, val_lbl in self.fund_rows:
            val_lbl.configure(text=fund.get(key, "—"))
            
        self._draw_chart(hist)

    def _fetch_news(self, sym: str):
        """해당 종목의 뉴스 데이터를 가져옵니다."""
        try:
            fetcher = YFinanceFetcher(sym)
            items = fetcher.fetch_news()
            self.after(0, lambda: self._populate_news(items))
            self.after(0, lambda: self.news_status.configure(text="● 실시간", text_color=GREEN))
        except Exception:
            self.after(0, lambda: self._show_news_error())

    def _show_news_error(self):
        """뉴스 로드 실패 시 에러 메시지를 표시합니다."""
        for w in self.news_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.news_scroll,
            text="뉴스를 불러올 수 없습니다.",
            font=ctk.CTkFont("Malgun Gothic", 12),
            text_color=RED,
        ).grid(row=0, column=0, padx=12, pady=12)
        self.news_status.configure(text="○ 오류", text_color=RED)

    # ── 상호작용 (버튼 및 입력 이벤트) ──────────────────────────────────────
    def _select_ticker(self, sym: str):
        """
        사용자가 관심 종목 목록에서 특정 종목을 클릭했을 때 호출됩니다.
        선택된 종목을 변경하고 UI 갱신을 스레드에 위임합니다.

        :param sym: 선택한 종목 티커
        """
        if self.selected_ticker.get() == sym:
            return  # 동일 종목 중복 클릭 방지
            
        self.selected_ticker.set(sym)
        self._refresh_sidebar()
        
        # 차트 로딩 애니메이션 표시
        if self._chart_canvas:
            self._chart_canvas.get_tk_widget().destroy()
            self._chart_canvas = None
        for w in self.chart_container.winfo_children():
            w.destroy()
            
        ctk.CTkLabel(
            self.chart_container,
            text="차트 불러오는 중…",
            font=ctk.CTkFont("Malgun Gothic", 12),
            text_color=TEXT_SEC,
        ).pack(expand=True)

        # 독립된 스레드에서 데이터 패치
        threading.Thread(target=self._fetch_detail, args=(sym,), daemon=True).start()
        threading.Thread(target=self._fetch_news, args=(sym,), daemon=True).start()

    def _change_period(self, period: str):
        """
        차트 조회 기간을 변경합니다.

        :param period: '1mo', '1y' 등의 기간 문자열
        """
        self.period_var.set(period)
        
        # 버튼 색상 활성화 처리
        for p, btn in self.period_btns.items():
            btn.configure(fg_color=ACCENT if p == period else MUTED)
            
        sym = self.selected_ticker.get()
        threading.Thread(target=self._fetch_detail, args=(sym,), daemon=True).start()

    def _add_ticker(self, event):
        """
        검색창에 입력된 검색어(회사명 또는 티커)를 검증하고 관심 종목에 추가합니다.
        
        :param event: Tkinter 이벤트 객체 (엔터 키 입력 등)
        """
        query = self.add_entry.get().strip()
        if not query:
            return

        self.add_entry.delete(0, "end")
        self.add_entry.configure(placeholder_text="검색 중...")

        def validate_and_add():
            """입력값을 검증하고 API를 통해 실제 존재하는 종목인지 확인하는 래퍼 함수 (스레드용)"""
            try:
                # utils.py의 하이브리드 검색기 활용 (책임 분리)
                sym, name = search_stock_ticker(query)
                if not sym:
                    raise ValueError("검색 결과 없음")

                if sym in self.watchlist:
                    self.after(0, lambda: self.add_entry.configure(placeholder_text="이미 추가된 종목입니다"))
                    time.sleep(1)
                    self.after(0, lambda: self.add_entry.configure(placeholder_text="종목명 또는 티커 검색..."))
                    return

                self.ticker_names[sym] = name
                self.watchlist.append(sym)
                self._fetch_all_tickers()
                
                self.after(0, self._refresh_sidebar)
                self.after(0, lambda: self.add_entry.configure(placeholder_text="종목명 또는 티커 검색..."))
                
            except Exception:
                # 오류 발생 시 사용자에게 팝업 피드백 제공
                self.after(
                    0, lambda: messagebox.showerror(
                        "종목 검색 실패",
                        f"'{query}'에 대한 종목을 찾을 수 없습니다.\n정확한 기업명이나 티커를 입력해주세요.",
                    )
                )
                self.after(0, lambda: self.add_entry.configure(placeholder_text="종목명 또는 티커 검색..."))

        threading.Thread(target=validate_and_add, daemon=True).start()

    def _remove_ticker(self, sym: str):
        """
        관심 종목 리스트에서 특정 종목을 제거합니다.

        :param sym: 삭제할 종목의 티커
        """
        if sym in self.watchlist:
            self.watchlist.remove(sym)
            # 만약 현재 보고 있던 종목을 삭제했다면, 리스트의 첫 번째 종목으로 자동 전환
            if self.selected_ticker.get() == sym and self.watchlist:
                self._select_ticker(self.watchlist[0])
            else:
                self._refresh_sidebar()


def main():
    """모듈을 직접 실행할 경우 대시보드 앱을 구동하는 메인 함수입니다."""
    app = StockDashboard()
    app.mainloop()


if __name__ == "__main__":
    main()