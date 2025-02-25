import sys
import os
from cx_Freeze import setup, Executable
import PyQt5
import pykrx

# PyQt5 플러그인 경로 찾기
qt_path = os.path.dirname(PyQt5.__file__)
platform_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms')
styles_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'styles')

build_exe_options = {
    "packages": [
        "pykrx",  # pykrx 패키지 전체를 포함
        "os", 
        "sys",
        "PyQt5",
        "requests",
        "datetime",
        "json",
        "zipfile",
        "xml.etree.ElementTree",
        "queue",
        "threading",
        "math",
        "typing",
        "re",
        "io",
        "time",
        "certifi",
        "idna",
        "urllib3",
        "chardet",
        "bs4",  # pykrx가 사용하는 BeautifulSoup
        "pandas",  # pykrx 의존성
        "numpy",   # pandas 의존성
        "matplotlib",  # matplotlib 추가
        "matplotlib.pyplot",  # pyplot 명시적 추가
        "matplotlib.backends",  # matplotlib 백엔드
    ],
    "excludes": [
        "PyQt5.QtQml",
        "PyQt5.QtQuick",
        "PyQt5.QtNetwork",
        "tkinter",
        "notebook",
        "scipy",
    ],
    "include_files": [
        ("treasury_search_logo.ico", "treasury_search_logo.ico"),
        ("cache", "cache"),
    ],
    "include_msvcr": True,
}

# PyQt5 플러그인 경로가 존재하는 경우에만 추가
if os.path.exists(platform_path):
    build_exe_options["include_files"].append((platform_path, "platforms"))
if os.path.exists(styles_path):
    build_exe_options["include_files"].append((styles_path, "styles"))

base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name="디지털대성 기업서치 서비스",
    version="1.0",
    description="Stock Analysis Program",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "searchbot2.py",
            base=base,
            target_name="디지털대성_기업서치_서비스.exe",
            icon="treasury_search_logo.ico",
            copyright="DigitalDaesung"
        )
    ]
)