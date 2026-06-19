class BaseMarketFetcher:
    """
    시장 데이터를 가져오는 부모 클래스입니다.
    이 클래스를 상속받아 세부 API 로직을 구현합니다.
    """

    def __init__(self, ticker: str):
        """
        초기화 메서드.
        :param ticker: 주식 티커 심볼
        """
        self.ticker = ticker.upper()

    def fetch_basic_info(self) -> dict:
        """기본 정보(가격, 변동률)를 가져옵니다."""
        raise NotImplementedError("자식 클래스에서 구현해야 합니다.")

    def fetch_details(self, period: str) -> tuple:
        """상세 정보와 차트 데이터를 가져옵니다."""
        raise NotImplementedError("자식 클래스에서 구현해야 합니다.")

    def fetch_news(self) -> list:
        """관련 뉴스 기사를 가져옵니다."""
        raise NotImplementedError("자식 클래스에서 구현해야 합니다.")

    def _is_valid_ticker(self) -> bool:
        """
        티커의 유효성을 검사하는 비공개 메서드입니다.
        :return: 유효하면 True
        """
        return bool(self.ticker and isinstance(self.ticker, str))
