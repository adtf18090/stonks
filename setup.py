from setuptools import setup, find_packages

setup(
    name="stock_dashboard",
    version="1.0.0",
    author="안단태",
    description="실시간 주식 정보 및 뉴스를 제공하는 GUI 대시보드",
    packages=find_packages(),
    install_requires=[
        "customtkinter",
        "yfinance",
        "feedparser",
        "pandas",
        "numpy",
        "matplotlib"
    ],
    entry_points={
        # 설치 후 터미널에 'run-dashboard'만 치면 실행되게 하는 마법의 명령어 (가산점 요인)
        "console_scripts": [
            "run-dashboard=stock_dashboard.gui:main", 
        ]
    }
)