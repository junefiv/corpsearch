import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QWidget, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QListWidget, QDialog, QStackedWidget, QLabel, QTableWidget, QTableWidgetItem, QAbstractItemView
from pykrx import stock
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QMetaType, QMetaObject, Q_ARG
import threading
import time
from queue import Queue
import math
import typing

DART_API_KEY = 'bea2a84f1ed21a05c3bc44c406f4b12f9ba56902'

# STANDARD_TABLE 스타일 정의
STANDARD_TABLE = """
    QTableWidget {
        background-color: white;
        alternate-background-color: #f5f5f5;
        selection-background-color: #0078d7;
        selection-color: white;
        border: 1px solid #d3d3d3;
        gridline-color: #d3d3d3;
    }
    QTableWidget::item {
        padding: 5px;
    }
"""

# 숫자 변환 헬퍼 함수 추가
def convert_to_int(value):
    if isinstance(value, (int, float)):
        return int(value)
    if value is None or value == '' or value == '-':
        return 0
    # 문자열로 변환 후 콤마 제거
    value = str(value).replace(',', '')
    try:
        return int(float(value))
    except ValueError:
        print(f"Warning: 숫자 변환 실패 - '{value}'")
        return 0

def convert_to_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None or value == '' or value == '-':
        return 0.0
    try:
        return float(str(value).replace(',', ''))
    except ValueError:
        print(f"Warning: 숫자 변환 실패 - '{value}'")
        return 0.0

class DataCollectorThread(QThread):
    progress = pyqtSignal(int, int)
    data_processed = pyqtSignal(str, dict)

    def __init__(self, search_term, existing_corp_info, company_codes, api_key, result_widget, search_app):
        super().__init__()
        self.search_term = search_term
        self.existing_corp_info = existing_corp_info
        self.company_codes = company_codes
        self.api_key = api_key
        self.result_widget = result_widget
        self.search_app = search_app
        
        # result_widget을 메인 스레드로 이동
        self.result_widget.moveToThread(QApplication.instance().thread())

        self.required_fields = [
            "corp_info",
            "treasury_info",
            "shareholder_list",
            "issued_share",
            "financial_info",
            "contribution_info"
        ]

    def run(self):
        # 1. 먼저 캐시된 데이터 처리
        cached_companies = [name for name in self.existing_corp_info.keys() 
                           if name != self.search_term and 
                           all(field in self.existing_corp_info[name] for field in self.required_fields)]
        
        # 2. 캐시되지 않은 데이터 식별
        uncached_companies = [name for name in self.existing_corp_info.keys()
                             if name != self.search_term and
                             name not in cached_companies]
        
        total_companies = len(cached_companies) + len(uncached_companies)
        processed = 0

        # 3. 캐시된 데이터 먼저 표시 (하나씩 비동기적으로)
        for company_name in sorted(cached_companies):
            self.data_processed.emit(company_name, self.existing_corp_info[company_name])
            processed += 1
            self.progress.emit(processed, total_companies)
            time.sleep(0.01)  # UI 업데이트를 위한 짧은 딜레이

        # 4. 캐시되지 않은 데이터 처리
        for company_name in sorted(uncached_companies):
            print(f"\n=== {company_name} 기업 정보 수집 시작 ===")
            
            try:
                # 기업 코드 확인
                if company_name in self.company_codes:
                    corp_code = self.company_codes[company_name]['corp_code']
                    stock_code = self.company_codes[company_name].get('stock_code')
                    if stock_code:
                        self.existing_corp_info[company_name]['corp_info']['stock_code'] = stock_code

                # 필요한 정보가 있는지 확인
                missing_fields = []
                for field in self.required_fields:
                    if field == "corp_info":
                        required_corp_info_fields = ["corp_code", "stock_code", "ceo_nm", "jurir_no", "bizr_no", "adres", "hm_url", "est_dt", "induty_code"]
                        if (field not in self.existing_corp_info[company_name] or 
                            not all(f in self.existing_corp_info[company_name][field] for f in required_corp_info_fields)):
                            missing_fields.append(field)
                    else:
                        if field not in self.existing_corp_info[company_name] or not self.existing_corp_info[company_name].get(field):
                            missing_fields.append(field)

                # missing_fields가 있을 때만 API 호출 수행
                if missing_fields:
                    # 기업 기본 정보 업데이트
                    if "corp_info" in missing_fields:
                        company_info_url = "https://opendart.fss.or.kr/api/company.json"
                        company_params = {
                            'crtfc_key': self.api_key,
                            'corp_code': corp_code
                        }
                        company_response = requests.get(company_info_url, params=company_params)
                        if company_response.status_code == 200:
                            company_data = company_response.json()
                            if company_data['status'] == '000':
                                self.existing_corp_info[company_name]["corp_info"].update({
                                    "corp_code": corp_code,
                                    "stock_code": stock_code,
                                    "ceo_nm": company_data.get("ceo_nm"),
                                    "jurir_no": company_data.get("jurir_no"),
                                    "bizr_no": company_data.get("bizr_no"),
                                    "adres": company_data.get("adres"),
                                    "hm_url": company_data.get("hm_url"),
                                    "est_dt": company_data.get("est_dt"),
                                    "induty_code": company_data.get("induty_code")
                                })

                    # treasury_info 수집
                    if "treasury_info" in missing_fields:
                        regular_report = self.search_app.get_latest_regular_disclosure(corp_code)
                        if regular_report:
                            bsns_year = regular_report['rcept_dt'][:4]
                            report_nm = regular_report['report_nm']
                            reprt_code = self.search_app.get_report_code(report_nm)
                            tesstk_url = "https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json"
                            tesstk_params = {
                                'crtfc_key': self.api_key,
                                'corp_code': corp_code,
                                'bsns_year': bsns_year,
                                'reprt_code': reprt_code
                            }
                            tesstk_response = requests.get(tesstk_url, params=tesstk_params)
                            if tesstk_response.status_code == 200:
                                tesstk_data = tesstk_response.json()
                                if tesstk_data['status'] == '000':
                                    treasury_info = {}
                                    
                                    # 실제 보유량 집계
                                    for item in tesstk_data.get('list', []):
                                        acqs_mth2 = item['acqs_mth2']
                                        acqs_mth3 = item['acqs_mth3']
                                        stock_knd = item['stock_knd']
                                        
                                        # 소계나 총계가 아닌 실제 보유량만 집계
                                        if acqs_mth3 not in ['소계', '총계']:
                                            if acqs_mth2 not in treasury_info:
                                                treasury_info[acqs_mth2] = {}
                                            
                                            if stock_knd not in treasury_info[acqs_mth2]:
                                                treasury_info[acqs_mth2][stock_knd] = convert_to_int(item['trmend_qy'])
                                    
                                    # 총계 처리
                                    for item in tesstk_data.get('list', []):
                                        if item['acqs_mth2'] == '총계':
                                            if '총계' not in treasury_info:
                                                treasury_info['총계'] = {}
                                            treasury_info['총계'][item['stock_knd']] = convert_to_int(item['trmend_qy'])
                                    
                                    self.existing_corp_info[company_name]["treasury_info"] = treasury_info

                    # shareholder_list 수집
                    if "shareholder_list" in missing_fields:
                        regular_report = self.search_app.get_latest_regular_disclosure(corp_code)
                        if regular_report:
                            bsns_year = regular_report['rcept_dt'][:4]
                            report_nm = regular_report['report_nm']
                            reprt_code = self.search_app.get_report_code(report_nm)
                            hyslr_url = "https://opendart.fss.or.kr/api/hyslrSttus.json"
                            hyslr_params = {
                                'crtfc_key': self.api_key,
                                'corp_code': corp_code,
                                'bsns_year': bsns_year,
                                'reprt_code': reprt_code
                            }
                            hyslr_response = requests.get(hyslr_url, params=hyslr_params)
                            if hyslr_response.status_code == 200:
                                hyslr_data = hyslr_response.json()
                                if hyslr_data['status'] == '000':
                                    shareholder_list = []
                                    for item in hyslr_data['list']:
                                        shareholder_info = {
                                            'nm': item.get('nm', 'N/A'),
                                            'relate': item.get('relate', 'N/A'),
                                            'trmend_posesn_stock_co': convert_to_int(item.get('trmend_posesn_stock_co')),
                                            'trmend_posesn_stock_qota_rt': convert_to_float(item.get('trmend_posesn_stock_qota_rt'))
                                        }
                                        shareholder_list.append(shareholder_info)
                                    self.existing_corp_info[company_name]["shareholder_list"] = shareholder_list

                    # issued_share 수집
                    if "issued_share" in missing_fields:
                        regular_report = self.search_app.get_latest_regular_disclosure(corp_code)
                        if regular_report:
                            bsns_year = regular_report['rcept_dt'][:4]
                            report_nm = regular_report['report_nm']
                            reprt_code = self.search_app.get_report_code(report_nm)
                            stockTotqySttus_url = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
                            stockTotqySttus_params = {
                                'crtfc_key': self.api_key,
                                'corp_code': corp_code,
                                'bsns_year': bsns_year,
                                'reprt_code': reprt_code
                            }
                            stockTotqySttus_response = requests.get(stockTotqySttus_url, params=stockTotqySttus_params)
                            if stockTotqySttus_response.status_code == 200:
                                stockTotqySttus_data = stockTotqySttus_response.json()
                                if stockTotqySttus_data['status'] == '000':
                                    issued_share = {}
                                    for item in stockTotqySttus_data['list']:
                                        se = item.get('se', 'N/A')
                                        if se not in issued_share:
                                            issued_share[se] = {}
                                        
                                        # 숫자 데이터만 변환 시도
                                        try:
                                            issued_share[se].update({
                                                'istc_totqy': convert_to_int(item.get('istc_totqy')) if not isinstance(item.get('istc_totqy'), str) or item.get('istc_totqy').replace(',', '').isdigit() else item.get('istc_totqy'),
                                            'tesstk_co': convert_to_int(item.get('tesstk_co')) if not isinstance(item.get('tesstk_co'), str) or item.get('tesstk_co').replace(',', '').isdigit() else item.get('tesstk_co'),
                                            'distb_stock_co': convert_to_int(item.get('distb_stock_co')) if not isinstance(item.get('distb_stock_co'), str) or item.get('distb_stock_co').replace(',', '').isdigit() else item.get('distb_stock_co')
                                        })
                                        except Exception as e:
                                            print(f"Warning: 데이터 변환 중 오류 발생 - {e}")
                                            print(f"문제가 된 데이터: {item}")
                                            continue
                                
                                    self.existing_corp_info[company_name]["issued_share"] = issued_share

                    # contribution_info 수집
                    if "contribution_info" in missing_fields:
                        regular_report = self.search_app.get_latest_regular_disclosure(corp_code)
                        if regular_report:
                            bsns_year = regular_report['rcept_dt'][:4]
                            report_nm = regular_report['report_nm']
                            reprt_code = self.search_app.get_report_code(report_nm)
                            otrCprInvstmntSttus_url = "https://opendart.fss.or.kr/api/otrCprInvstmntSttus.json"
                            otrCprInvstmntSttus_params = {
                                'crtfc_key': self.api_key,
                                'corp_code': corp_code,
                                'bsns_year': bsns_year,
                                'reprt_code': reprt_code
                            }
                            otrCprInvstmntSttus_response = requests.get(otrCprInvstmntSttus_url, params=otrCprInvstmntSttus_params)
                            if otrCprInvstmntSttus_response.status_code == 200:
                                otrCprInvstmntSttus_data = otrCprInvstmntSttus_response.json()
                                if otrCprInvstmntSttus_data['status'] == '000':
                                    contribution_info = []
                                    for item in otrCprInvstmntSttus_data['list']:
                                        contribution = {
                                            'inv_prm': item.get('inv_prm', 'N/A'),
                                            'frst_acqs_de': item.get('frst_acqs_de', 'N/A'),
                                            'invstmnt_purps': item.get('invstmnt_purps', 'N/A'),
                                            'trmend_blce_qy': item.get('trmend_blce_qy', '0'),
                                            'trmend_blce_qota_rt': item.get('trmend_blce_qota_rt', '0')
                                        }
                                        contribution_info.append(contribution)
                                    self.existing_corp_info[company_name]["contribution_info"] = contribution_info

                    # financial_info 수집
                    if "financial_info" in missing_fields:
                        current_year = datetime.now().year
                        for year in range(current_year-1, current_year-4, -1):
                            fnlttSinglAcnt_url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
                            fnlttSinglAcnt_params = {
                                'crtfc_key': self.api_key,
                                'corp_code': corp_code,
                                'bsns_year': str(year),
                                'reprt_code': '11011',
                                'fs_div': 'OFS'
                            }
                            fnlttSinglAcnt_response = requests.get(fnlttSinglAcnt_url, params=fnlttSinglAcnt_params)
                            if fnlttSinglAcnt_response.status_code == 200:
                                fnlttSinglAcnt_data = fnlttSinglAcnt_response.json()
                                if fnlttSinglAcnt_data['status'] == '000' and fnlttSinglAcnt_data.get('list'):
                                    financial_info = {
                                        "BS": [],
                                        "IS": [],
                                        "CIS": [],
                                        "CF": [],
                                        "SCE": []
                                    }
                                    for item in fnlttSinglAcnt_data['list']:
                                        financial_item = {
                                            'account_nm': item.get('account_nm'),
                                            'thstrm_amount': convert_to_int(item.get('thstrm_amount')),
                                            'currency': 'KRW'
                                        }
                                        if item.get('sj_div') == 'BS':
                                            financial_info["BS"].append(financial_item)
                                        elif item.get('sj_div') == 'IS':
                                            financial_info["IS"].append(financial_item)
                                        elif item.get('sj_div') == 'CIS':
                                            financial_info["CIS"].append(financial_item)
                                        elif item.get('sj_div') == 'CF':
                                            financial_info["CF"].append(financial_item)
                                        elif item.get('sj_div') == 'SCE':
                                            financial_info["SCE"].append(financial_item)
                                
                                    if any(financial_info.values()):
                                        self.existing_corp_info[company_name]["financial_info"] = financial_info
                                        break

                    # 캐시 파일 업데이트
                    with open('./cache/corp_info.json', 'w', encoding='utf-8') as f:
                        json.dump(self.existing_corp_info, f, ensure_ascii=False, indent=4)

                    # 데이터 수집이 완료되면 시그널 발생
                    self.data_processed.emit(company_name, self.existing_corp_info[company_name])
                    processed += 1
                    self.progress.emit(processed, total_companies)
                    time.sleep(0.01)  # UI 업데이트를 위한 짧은 딜레이
                    print(f"\n=== {company_name} 기업 정보 수집 완료 ===\n")
                
            except Exception as e:
                print(f"Error processing {company_name}: {str(e)}")
                continue

class SearchApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.stack = QStackedWidget()
        self.stack.addWidget(self)  # 검색 화면을 첫 번째 페이지로 추가
        
        # progress_label 추가
        self.progress_label = QLabel('', self)
        layout = self.layout()
        layout.addWidget(self.progress_label)
        
        # existing_corp_info 속성 추가
        self.existing_corp_info = {}
        
        self.required_fields = [
            "corp_info",
            "treasury_info",
            "shareholder_list",
            "issued_share",
            "financial_info",
            "contribution_info"
        ]

    def initUI(self):
        # 레이아웃 설정
        layout = QVBoxLayout()

        # 검색창 생성
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText('검색어를 입력하세요...')
        layout.addWidget(self.search_box)

        # 검색 버튼 생성
        search_button = QPushButton('검색', self)
        layout.addWidget(search_button)

        # 검색 버튼 클릭 시 검색 함수 연결
        search_button.clicked.connect(self.perform_search)

        # 엔터 키 입력 시 검색 함수 연결
        self.search_box.returnPressed.connect(self.perform_search)

        # 레이아웃 설정
        self.setLayout(layout)
        self.setWindowTitle('검색 앱')
        self.show()

    def perform_search(self):
        search_term = self.search_box.text()
        print(f'검색어: {search_term}')

        # 기존 캐시 파일 읽기 (에러 처리 추가)
        try:
            if os.path.exists('./cache/corp_info.json'):
                with open('./cache/corp_info.json', 'r', encoding='utf-8') as f:
                    self.existing_corp_info = json.load(f)
        except json.JSONDecodeError as e:
            print(f"캐시 파일이 손상되었습니다: {e}")
            self.existing_corp_info = {}

        # KOSPI, KOSDAQ 기업 정보 추가 (기존 데이터 유지)
        kospi = stock.get_market_ticker_list(market="KOSPI")
        kosdaq = stock.get_market_ticker_list(market="KOSDAQ")

        # 시장 정보 및 종목 코드 매핑
        market_info = {}
        for ticker in kospi:
            name = stock.get_market_ticker_name(ticker)
            market_info[name] = {"market": "KOSPI", "stock_code": ticker}

        for ticker in kosdaq:
            name = stock.get_market_ticker_name(ticker)
            market_info[name] = {"market": "KOSDAQ", "stock_code": ticker}

        # 검색한 기업이 existing_corp_info에 없으면 초기화
        if search_term not in self.existing_corp_info:
            market_data = market_info.get(search_term, {"market": "N/A", "stock_code": None})
            self.existing_corp_info[search_term] = {
                "corp_info": {
                    "market": market_data["market"],
                    "stock_code": market_data["stock_code"]
                },
                "treasury_info": {},
                "shareholder_list": [],
                "issued_share": {},
                "financial_info": {},
                "contribution_info": []
            }
        elif "market" not in self.existing_corp_info[search_term]["corp_info"]:
            # 이미 존재하는 기업이지만 시장 정보가 없는 경우
            market_data = market_info.get(search_term, {"market": "N/A", "stock_code": None})
            self.existing_corp_info[search_term]["corp_info"]["market"] = market_data["market"]
            self.existing_corp_info[search_term]["corp_info"]["stock_code"] = market_data["stock_code"]

        # 다른 기업들의 시장 정보도 업데이트
        for company_name, market_data in market_info.items():
            if company_name not in self.existing_corp_info:
                self.existing_corp_info[company_name] = {
                    "corp_info": {
                        "market": market_data["market"],
                        "stock_code": market_data["stock_code"]
                    }
                }
            elif "market" not in self.existing_corp_info[company_name]["corp_info"]:
                self.existing_corp_info[company_name]["corp_info"]["market"] = market_data["market"]
                self.existing_corp_info[company_name]["corp_info"]["stock_code"] = market_data["stock_code"]

        api_key = DART_API_KEY
        url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}"
        response = requests.get(url)
        if response.status_code != 200:
            QMessageBox.warning(self, '오류', 'API 요청에 실패했습니다.')
            return

        z = zipfile.ZipFile(io.BytesIO(response.content))
        xml_data = z.read('CORPCODE.xml').decode('utf-8')
        root = ET.fromstring(xml_data)

        # 기업 정보와 corp_code를 저장할 딕셔너리
        company_codes = {}
        
        for company in root.findall('list'):
            corp_name = company.findtext('corp_name')
            corp_code = company.findtext('corp_code')
            stock_code = company.findtext('stock_code')
            if stock_code and stock_code.strip():  # stock_code가 있고 비어있지 않은 경우
                company_codes[corp_name] = {'corp_code': corp_code, 'stock_code': stock_code}
            else:
                company_codes[corp_name] = {'corp_code': corp_code}

        matching_companies = [name for name in self.existing_corp_info if search_term in name]

        if len(matching_companies) == 1:
            search_term = matching_companies[0]
            corp_code = company_codes[search_term]['corp_code']
            stock_code = company_codes[search_term].get('stock_code')
            if stock_code:
                self.existing_corp_info[search_term]['corp_info']['stock_code'] = stock_code
        elif len(matching_companies) > 1:
            search_term = self.select_company(matching_companies)
            if not search_term:
                return
            corp_code = company_codes[search_term]['corp_code']
            stock_code = company_codes[search_term].get('stock_code')
            if stock_code:
                self.existing_corp_info[search_term]['corp_info']['stock_code'] = stock_code
        else:
            QMessageBox.information(self, '검색 결과', '검색어에 해당하는 기업이 없습니다.')
            return

        print(f"Selected company: {search_term}, Using corp_code: {corp_code}")

        # 필요한 정보가 있는지 확인
        if search_term not in self.existing_corp_info:
            self.existing_corp_info[search_term] = {"corp_info": {}}

        missing_fields = []
        for field in self.required_fields:
            # 필드가 없거나 비어있는 경우에만 missing_fields에 추가
            if field not in self.existing_corp_info[search_term] or not self.existing_corp_info[search_term].get(field):
                missing_fields.append(field)

        print(f"Missing fields for {search_term}: {missing_fields}")

        # missing_fields가 있을 때만 API 호출 수행
        if missing_fields:
            print(f"\n=== {search_term} 기업 정보 수집 시작 ===")
            
            # 기업 기본 정보 업데이트
            if "corp_info" in missing_fields:
                print("\n[기업 기본 정보]")
                print("- API: /api/company.json")
                company_info_url = "https://opendart.fss.or.kr/api/company.json"
                company_params = {
                    'crtfc_key': api_key,
                    'corp_code': corp_code
                }
                company_response = requests.get(company_info_url, params=company_params)
                if company_response.status_code == 200:
                    company_data = company_response.json()
                    if company_data['status'] == '000':
                        self.existing_corp_info[search_term]["corp_info"].update({
                            "corp_code": corp_code,
                            "stock_code": stock_code,
                            "ceo_nm": company_data.get("ceo_nm"),
                            "jurir_no": company_data.get("jurir_no"),
                            "bizr_no": company_data.get("bizr_no"),
                            "adres": company_data.get("adres"),
                            "hm_url": company_data.get("hm_url"),
                            "est_dt": company_data.get("est_dt"),
                            "induty_code": company_data.get("induty_code")
                        })

            # treasury_info 수집
            if "treasury_info" in missing_fields:
                print("\n[자기주식 현황]")
                regular_report = self.get_latest_regular_disclosure(corp_code)
                if regular_report:
                    print(f"- 보고서명: {regular_report['report_nm']}")
                    print(f"- 접수일자: {regular_report['rcept_dt']}")
                    print("- API: /api/tesstkAcqsDspsSttus.json")
                    
                    bsns_year = regular_report['rcept_dt'][:4]
                    report_nm = regular_report['report_nm']
                    reprt_code = self.get_report_code(report_nm)
                    tesstk_url = "https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json"
                    tesstk_params = {
                        'crtfc_key': api_key,
                        'corp_code': corp_code,
                        'bsns_year': bsns_year,
                        'reprt_code': reprt_code
                    }
                    tesstk_response = requests.get(tesstk_url, params=tesstk_params)
                    if tesstk_response.status_code == 200:
                        tesstk_data = tesstk_response.json()
                        if tesstk_data['status'] == '000':
                            treasury_info = {}
                            
                            # 실제 보유량 집계
                            for item in tesstk_data.get('list', []):
                                acqs_mth2 = item['acqs_mth2']
                                acqs_mth3 = item['acqs_mth3']
                                stock_knd = item['stock_knd']
                                
                                # 소계나 총계가 아닌 실제 보유량만 집계
                                if acqs_mth3 not in ['소계', '총계']:
                                    if acqs_mth2 not in treasury_info:
                                        treasury_info[acqs_mth2] = {}
                                    
                                    if stock_knd not in treasury_info[acqs_mth2]:
                                        treasury_info[acqs_mth2][stock_knd] = convert_to_int(item['trmend_qy'])
                                    
                            # 총계 처리
                            for item in tesstk_data.get('list', []):
                                if item['acqs_mth2'] == '총계':
                                    if '총계' not in treasury_info:
                                        treasury_info['총계'] = {}
                                    treasury_info['총계'][item['stock_knd']] = convert_to_int(item['trmend_qy'])
                                    
                            self.existing_corp_info[search_term]["treasury_info"] = treasury_info

            # shareholder_list 수집
            if "shareholder_list" in missing_fields:
                print("\n[주주 현황]")
                regular_report = self.get_latest_regular_disclosure(corp_code)
                if regular_report:
                    print(f"- 보고서명: {regular_report['report_nm']}")
                    print(f"- 접수일자: {regular_report['rcept_dt']}")
                    print("- API: /api/hyslrSttus.json")
                    
                    bsns_year = regular_report['rcept_dt'][:4]
                    report_nm = regular_report['report_nm']
                    reprt_code = self.get_report_code(report_nm)
                    hyslr_url = "https://opendart.fss.or.kr/api/hyslrSttus.json"
                    hyslr_params = {
                        'crtfc_key': api_key,
                        'corp_code': corp_code,
                        'bsns_year': bsns_year,
                        'reprt_code': reprt_code
                    }
                    hyslr_response = requests.get(hyslr_url, params=hyslr_params)
                    if hyslr_response.status_code == 200:
                        hyslr_data = hyslr_response.json()
                        if hyslr_data['status'] == '000':
                            shareholder_list = []
                            for item in hyslr_data['list']:
                                shareholder_info = {
                                    'nm': item.get('nm', 'N/A'),
                                    'relate': item.get('relate', 'N/A'),
                                    'trmend_posesn_stock_co': convert_to_int(item.get('trmend_posesn_stock_co')),
                                    'trmend_posesn_stock_qota_rt': convert_to_float(item.get('trmend_posesn_stock_qota_rt'))
                                }
                                shareholder_list.append(shareholder_info)
                            self.existing_corp_info[search_term]["shareholder_list"] = shareholder_list

            # issued_share 수집
            if "issued_share" in missing_fields:
                print("\n[발행주식 현황]")
                regular_report = self.get_latest_regular_disclosure(corp_code)
                if regular_report:
                    print(f"- 보고서명: {regular_report['report_nm']}")
                    print(f"- 접수일자: {regular_report['rcept_dt']}")
                    print("- API: /api/stockTotqySttus.json")
                    
                    bsns_year = regular_report['rcept_dt'][:4]
                    report_nm = regular_report['report_nm']
                    reprt_code = self.get_report_code(report_nm)
                    stockTotqySttus_url = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
                    stockTotqySttus_params = {
                        'crtfc_key': api_key,
                        'corp_code': corp_code,
                        'bsns_year': bsns_year,
                        'reprt_code': reprt_code
                    }
                    stockTotqySttus_response = requests.get(stockTotqySttus_url, params=stockTotqySttus_params)
                    if stockTotqySttus_response.status_code == 200:
                        stockTotqySttus_data = stockTotqySttus_response.json()
                        if stockTotqySttus_data['status'] == '000':
                            issued_share = {}
                            for item in stockTotqySttus_data['list']:
                                se = item.get('se', 'N/A')
                                if se not in issued_share:
                                    issued_share[se] = {}
                                
                                # 숫자 데이터만 변환 시도
                                try:
                                    issued_share[se].update({
                                        'istc_totqy': convert_to_int(item.get('istc_totqy')) if not isinstance(item.get('istc_totqy'), str) or item.get('istc_totqy').replace(',', '').isdigit() else item.get('istc_totqy'),
                                    'tesstk_co': convert_to_int(item.get('tesstk_co')) if not isinstance(item.get('tesstk_co'), str) or item.get('tesstk_co').replace(',', '').isdigit() else item.get('tesstk_co'),
                                    'distb_stock_co': convert_to_int(item.get('distb_stock_co')) if not isinstance(item.get('distb_stock_co'), str) or item.get('distb_stock_co').replace(',', '').isdigit() else item.get('distb_stock_co')
                                })
                                except Exception as e:
                                    print(f"Warning: 데이터 변환 중 오류 발생 - {e}")
                                    print(f"문제가 된 데이터: {item}")
                                    continue
                            
                            self.existing_corp_info[search_term]["issued_share"] = issued_share

            # contribution_info 수집
            if "contribution_info" in missing_fields:
                print("\n[타법인 출자 현황]")
                regular_report = self.get_latest_regular_disclosure(corp_code)
                if regular_report:
                    print(f"- 보고서명: {regular_report['report_nm']}")
                    print(f"- 접수일자: {regular_report['rcept_dt']}")
                    print("- API: /api/otrCprInvstmntSttus.json")
                    
                    bsns_year = regular_report['rcept_dt'][:4]
                    report_nm = regular_report['report_nm']
                    reprt_code = self.get_report_code(report_nm)
                    otrCprInvstmntSttus_url = "https://opendart.fss.or.kr/api/otrCprInvstmntSttus.json"
                    otrCprInvstmntSttus_params = {
                        'crtfc_key': api_key,
                        'corp_code': corp_code,
                        'bsns_year': bsns_year,
                        'reprt_code': reprt_code
                    }
                    otrCprInvstmntSttus_response = requests.get(otrCprInvstmntSttus_url, params=otrCprInvstmntSttus_params)
                    if otrCprInvstmntSttus_response.status_code == 200:
                        otrCprInvstmntSttus_data = otrCprInvstmntSttus_response.json()
                        if otrCprInvstmntSttus_data['status'] == '000':
                            contribution_info = []
                            for item in otrCprInvstmntSttus_data['list']:
                                contribution = {
                                    'inv_prm': item.get('inv_prm', 'N/A'),
                                    'frst_acqs_de': item.get('frst_acqs_de', 'N/A'),
                                    'invstmnt_purps': item.get('invstmnt_purps', 'N/A'),
                                    'trmend_blce_qy': item.get('trmend_blce_qy', '0'),
                                    'trmend_blce_qota_rt': item.get('trmend_blce_qota_rt', '0')
                                }
                                contribution_info.append(contribution)
                            self.existing_corp_info[search_term]["contribution_info"] = contribution_info

            # financial_info 수집 (사업보고서만)
            if "financial_info" in missing_fields:
                print("\n[재무제표 정보]")
                print("- API: /api/fnlttSinglAcntAll.json")
                print("- 사업보고서만 참고")
                current_year = datetime.now().year
                for year in range(current_year-1, current_year-4, -1):
                    print(f"- {year}년 사업보고서 조회 중...")
                    fnlttSinglAcnt_url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
                    fnlttSinglAcnt_params = {
                        'crtfc_key': api_key,
                        'corp_code': corp_code,
                        'bsns_year': str(year),
                        'reprt_code': '11011',
                        'fs_div': 'OFS'
                    }
                    fnlttSinglAcnt_response = requests.get(fnlttSinglAcnt_url, params=fnlttSinglAcnt_params)
                    if fnlttSinglAcnt_response.status_code == 200:
                        fnlttSinglAcnt_data = fnlttSinglAcnt_response.json()
                        if fnlttSinglAcnt_data['status'] == '000' and fnlttSinglAcnt_data.get('list'):
                            print(f"- {year}년 사업보고서 데이터 찾음")
                            financial_info = {
                                "BS": [],
                                "IS": [],
                                "CIS": [],
                                "CF": [],
                                "SCE": []
                            }
                            for item in fnlttSinglAcnt_data['list']:
                                financial_item = {
                                    'account_nm': item.get('account_nm'),
                                    'thstrm_amount': convert_to_int(item.get('thstrm_amount')),
                                    'currency': 'KRW'
                                }
                                if item.get('sj_div') == 'BS':
                                    financial_info["BS"].append(financial_item)
                                elif item.get('sj_div') == 'IS':
                                    financial_info["IS"].append(financial_item)
                                elif item.get('sj_div') == 'CIS':
                                    financial_info["CIS"].append(financial_item)
                                elif item.get('sj_div') == 'CF':
                                    financial_info["CF"].append(financial_item)
                                elif item.get('sj_div') == 'SCE':
                                    financial_info["SCE"].append(financial_item)
                            
                            if any(financial_info.values()):  # 데이터가 하나라도 있으면
                                self.existing_corp_info[search_term]["financial_info"] = financial_info
                                break
                        else:
                            print(f"- {year}년 사업보고서 데이터 없음")
                    else:
                        print(f"- {year}년 사업보고서 API 요청 실패")

            print(f"\n=== {search_term} 기업 정보 수집 완료 ===\n")

        # 캐시 파일 업데이트는 변경사항이 있을 때만 수행
        if missing_fields:
            with open('./cache/corp_info.json', 'w', encoding='utf-8') as f:
                json.dump(self.existing_corp_info, f, ensure_ascii=False, indent=4)

        # 결과 화면으로 전환
        result_widget = ResultWidget(search_term, self.existing_corp_info[search_term])
        self.stack.addWidget(result_widget)
        self.stack.setCurrentWidget(result_widget)

        # 스레드 시작 전에 메타타입 등록
        QMetaType.type("int")
        
        # 나머지 기업들의 정보 수집을 위해 DataCollectorThread 시작
        self.collector_thread = DataCollectorThread(
            search_term,
            self.existing_corp_info,
            company_codes,
            api_key,
            result_widget,
            self
        )
        
        # 시그널 연결 전에 result_widget을 메인 스레드로 이동
        result_widget.moveToThread(QApplication.instance().thread())
        
        self.collector_thread.progress.connect(
            result_widget.update_progress
        )
        self.collector_thread.data_processed.connect(
            result_widget.update_data_table
        )
        self.collector_thread.start()

    def select_company(self, companies):
        dialog = QDialog(self)
        dialog.setWindowTitle('기업 선택')
        layout = QVBoxLayout()

        list_widget = QListWidget(dialog)
        for company in companies:
            list_widget.addItem(company)
        layout.addWidget(list_widget)

        select_button = QPushButton('선택', dialog)
        select_button.clicked.connect(dialog.accept)
        layout.addWidget(select_button)

        dialog.setLayout(layout)
        if dialog.exec_() == QDialog.Accepted:
            return list_widget.currentItem().text()
        return None

    def get_latest_regular_disclosure(self, corp_code):
        api_key = DART_API_KEY
        current_year = datetime.now().year
        current_month = datetime.now().month

        # 보고서 순서 결정
        if current_month < 3:  # 1~2월인 경우
            report_sequence = [
                (current_year-1, '11014'),  # 전년도 3분기
                (current_year-1, '11012'),  # 전년도 반기
                (current_year-1, '11013'),  # 전년도 1분기
                (current_year-2, '11011'),  # 전전년도 사업보고서
            ]
        elif current_month < 5:  # 3~4월인 경우
            report_sequence = [
                (current_year-1, '11011'),  # 전년도 사업보고서
                (current_year-1, '11014'),  # 전년도 3분기
                (current_year-1, '11012'),  # 전년도 반기
                (current_year-1, '11013'),  # 전년도 1분기
            ]
        elif current_month < 8:  # 5~7월인 경우
            report_sequence = [
                (current_year, '11013'),    # 당해 1분기
                (current_year-1, '11011'),  # 전년도 사업보고서
                (current_year-1, '11014'),  # 전년도 3분기
                (current_year-1, '11012'),  # 전년도 반기
            ]
        elif current_month < 11:  # 8~10월인 경우
            report_sequence = [
                (current_year, '11012'),    # 당해 반기
                (current_year, '11013'),    # 당해 1분기
                (current_year-1, '11011'),  # 전년도 사업보고서
                (current_year-1, '11014'),  # 전년도 3분기
            ]
        else:  # 11~12월인 경우
            report_sequence = [
                (current_year, '11014'),    # 당해 3분기
                (current_year, '11012'),    # 당해 반기
                (current_year, '11013'),    # 당해 1분기
                (current_year-1, '11011'),  # 전년도 사업보고서
            ]

        for year, reprt_code in report_sequence:
            url = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={api_key}&corp_code={corp_code}&bgn_de={year}0101&end_de={year}1231&pblntf_ty=A&sort=date&sort_mth=desc&page_no=1&page_count=1"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == '000' and data['list']:
                    return data['list'][0]  # 가장 최근 정기공시 반환
                else:
                    print(f"{year}년 {reprt_code} 보고서 데이터 없음")
            else:
                print("API 요청에 실패했습니다.")
        return None

    def get_report_code(self, report_nm):
        if '분기보고서' in report_nm:
            return '11013'
        elif '반기보고서' in report_nm:
            return '11012'
        elif '사업보고서' in report_nm:
            return '11011'
        elif '3분기보고서' in report_nm:
            return '11014'
        else:
            print("알 수 없는 보고서 유형입니다.")
            return None

    @pyqtSlot(int, int)
    def update_progress(self, current, total):
        self.progress_label.setText(f'데이터 수집 중... ({current}/{total})')
        if current >= total:
            self.progress_label.setText('데이터 수집 완료')

class ShareholderDialog(QDialog):
    def __init__(self, shareholder_list, company_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{company_name} 주주현황")
        self.setMinimumWidth(800)
        
        layout = QVBoxLayout()
        
        # 테이블 위젯 생성
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['주주명', '관계', '보유주식수', '지분율(%)'])
        
        # STANDARD_TABLE 스타일 적용
        table.setStyleSheet(STANDARD_TABLE)
        table.horizontalHeader().setStyleSheet("QHeaderView::section { text-align: center; }")
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # "계" 항목 통합을 위한 처리
        processed_data = []
        total_shares = 0
        total_ratio = 0.0
        
        for shareholder in shareholder_list:
            if shareholder['nm'].endswith('계'):
                total_shares += shareholder['trmend_posesn_stock_co']
                total_ratio += shareholder['trmend_posesn_stock_qota_rt']
            else:
                processed_data.append(shareholder)
        
        # "계" 데이터가 있으면 마지막에 추가
        if total_shares > 0 or total_ratio > 0:
            processed_data.append({
                'nm': '계',
                'relate': '',
                'trmend_posesn_stock_co': total_shares,
                'trmend_posesn_stock_qota_rt': total_ratio
            })
        
        # 데이터 채우기
        table.setRowCount(len(processed_data))
        for row, shareholder in enumerate(processed_data):
            # 각 셀 생성 및 중앙 정렬 적용
            for col, value in enumerate([
                str(shareholder['nm']),
                str(shareholder['relate']),
                f"{shareholder['trmend_posesn_stock_co']:,}",
                f"{shareholder['trmend_posesn_stock_qota_rt']:.2f}"
            ]):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
        
        # 컬럼 너비 자동 조정
        table.resizeColumnsToContents()
        
        layout.addWidget(table)
        self.setLayout(layout)

class ResultWidget(QWidget):
    def __init__(self, company_name, company_data):
        super().__init__()
        self.company_name = company_name
        self.company_data = company_data
        
        # 캐시된 기업 정보 로드
        with open('./cache/corp_info.json', 'r', encoding='utf-8') as f:
            self.all_companies = json.load(f)
        
        # DART API 키 설정
        self.api_key = DART_API_KEY
        
        # 기업 코드 정보 가져오기
        self.company_codes = self.get_company_codes()
        
        self.init_ui()
        self.update_data_table(company_name, company_data)

    def init_ui(self):
        layout = QVBoxLayout()
        
        # 검색한 기업 정보를 표시할 테이블
        standard_table = QTableWidget()
        standard_table.setColumnCount(6)  # 열 개수 증가
        standard_table.setRowCount(1)
        
        # 헤더 설정 수정
        headers = ['기업명', '시장', '자기주식 총계', '종가', '최대주주 지분', '시가총액(억원)']  # 헤더 추가
        standard_table.setHorizontalHeaderLabels(headers)
        
        # 데이터 입력
        corp_info = self.company_data.get('corp_info', {})
        treasury_info = self.company_data.get('treasury_info', {})
        
        # 자기주식 총계 계산 (보통주 + 우선주)
        total_treasury = 0
        if 'treasury_info' in self.company_data and '총계' in treasury_info:
            total_treasury = treasury_info['총계'].get('보통주', 0) + treasury_info['총계'].get('우선주', 0)
        
        # 종가 정보 가져오기
        closing_price = "N/A"
        try:
            stock_code = corp_info.get('stock_code')
            if stock_code:
                stock_code = stock_code.zfill(6)
                today = datetime.now().strftime("%Y%m%d")
                df = stock.get_market_ohlcv_by_date(fromdate=today, todate=today, ticker=stock_code)
                if not df.empty:
                    closing_price = f"{df.iloc[-1]['종가']:,}원"
                else:
                    for i in range(1, 10):
                        previous_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                        df = stock.get_market_ohlcv_by_date(fromdate=previous_date, todate=previous_date, ticker=stock_code)
                        if not df.empty:
                            closing_price = f"{df.iloc[-1]['종가']:,}원"
                            break
        except Exception as e:
            print(f"종가 조회 중 오류 발생: {e}")
            closing_price = "조회 실패"
        
        # 주주 지분율 합계 계산 (계 제외)
        total_share_ratio = 0
        if 'shareholder_list' in self.company_data:
            for shareholder in self.company_data['shareholder_list']:
                if not shareholder['nm'].endswith('계'):
                    total_share_ratio += shareholder['trmend_posesn_stock_qota_rt']

        # 시가총액 계산 추가
        market_cap = "N/A"
        try:
            if closing_price != "N/A" and closing_price != "조회 실패":
                print(f"처리 전 closing_price: {closing_price}, 타입: {type(closing_price)}")
                
                # closing_price의 타입에 따른 처리
                if isinstance(closing_price, (int, float)):
                    price = int(closing_price)
                else:
                    # 문자열인 경우에만 replace 수행
                    price_str = closing_price.replace(',', '').replace('원', '')
                    try:
                        price = int(float(price_str))
                    except ValueError as e:
                        print(f"숫자 변환 실패: {e}, 입력값: {price_str}")
                        price = 0
                
                print(f"변환된 price: {price}")
                # issued_shares 가져오기
                issued_shares = convert_to_int(self.company_data.get('issued_share', {}).get('합계', {}).get('istc_totqy', 0))
                print(f"issued_shares: {issued_shares}")
                
                if issued_shares and price:
                    market_cap = f"{(price * issued_shares) // 100000000:,}"  # 억원 단위로 변환
                    print(f"계산된 market_cap: {market_cap}")
                else:
                    print(f"issued_shares 또는 price가 0: {issued_shares}, {price}")
                    market_cap = "N/A"
        except Exception as e:
            print(f"시가총액 계산 중 오류 발생: {e}")
            print(f"문제가 된 closing_price 타입: {type(closing_price)}, 값: {closing_price}")
            market_cap = "N/A"

        data = [
            self.company_name,
            corp_info.get('market', 'N/A'),
            f"{total_treasury:,}주",
            closing_price,
            '',  # 버튼이 들어갈 자리
            market_cap
        ]
        
        # standard_table에 데이터 삽입
        for col, value in enumerate(data):
            if col != 4:  # 마지막 열(버튼)이 아닌 경우
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                standard_table.setItem(0, col, item)

        # 주주현황 버튼 추가 (지분율 표시 포함)
        button_text = f"{total_share_ratio:.2f}%"
        view_button = QPushButton(button_text)
        view_button.setStyleSheet("text-align: center;")
        view_button.clicked.connect(lambda: self.show_shareholder_dialog(self.company_name, self.company_data))
        standard_table.setCellWidget(0, 4, view_button)
        
        # standard_table 크기 조정
        standard_table.resizeColumnsToContents()
        standard_table.setFixedHeight(standard_table.verticalHeader().length() + 60)
        
        layout.addWidget(standard_table)

        # 진행 상황을 표시할 라벨 추가
        self.progress_label = QLabel('데이터 수집 중...')
        layout.addWidget(self.progress_label)

        # data_table 초기화
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(6)
        self.data_table.setHorizontalHeaderLabels(headers)
        layout.addWidget(self.data_table)

        # 뒤로가기 버튼
        back_button = QPushButton('뒤로가기')
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)

        self.setLayout(layout)

    def go_back(self):
        self.parent().setCurrentIndex(0)  # 첫 번째 페이지(검색 화면)로 돌아가기

    def get_company_codes(self):
        # 기업 코드 정보 가져오기
        api_key = self.api_key
        url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}"
        response = requests.get(url)
        if response.status_code != 200:
            print("API 요청에 실패했습니다.")
            return {}

        z = zipfile.ZipFile(io.BytesIO(response.content))
        xml_data = z.read('CORPCODE.xml').decode('utf-8')
        root = ET.fromstring(xml_data)

        # 기업 정보와 corp_code를 저장할 딕셔너리
        company_codes = {}
        
        for company in root.findall('list'):
            corp_name = company.findtext('corp_name')
            corp_code = company.findtext('corp_code')
            stock_code = company.findtext('stock_code')
            if stock_code and stock_code.strip():  # stock_code가 있고 비어있지 않은 경우
                company_codes[corp_name] = {'corp_code': corp_code, 'stock_code': stock_code}
            else:
                company_codes[corp_name] = {'corp_code': corp_code}

        return company_codes

    @pyqtSlot(str, dict)
    def update_data_table(self, company_name, company_data):
        # 모든 필수 필드가 있는지 확인
        required_fields = [
            "corp_info",
            "treasury_info",
            "shareholder_list",
            "issued_share",
            "financial_info",
            "contribution_info"
        ]
        
        if not all(field in company_data for field in required_fields):
            return

        # 이미 존재하는 행인지 확인
        existing_row = -1
        for row in range(self.data_table.rowCount()):
            if self.data_table.item(row, 0) and self.data_table.item(row, 0).text() == company_name:
                existing_row = row
                break

        if existing_row >= 0:
            # 기존 행 업데이트
            self.update_existing_row(company_name, company_data)
        else:
            # 새 행 추가
            row_position = self.data_table.rowCount()
            self.data_table.insertRow(row_position)
            
            # 자기주식 총계 계산
            total_treasury = 0
            if 'treasury_info' in company_data:
                treasury_info = company_data['treasury_info']
                if isinstance(treasury_info, dict) and '총계' in treasury_info:
                    total_treasury = treasury_info['총계'].get('보통주', 0) + treasury_info['총계'].get('우선주', 0)

            # 종가 정보 가져오기
            closing_price = "N/A"
            try:
                stock_code = company_data.get('corp_info', {}).get('stock_code')
                if stock_code:
                    stock_code = stock_code.zfill(6)
                    today = datetime.now().strftime("%Y%m%d")
                    df = stock.get_market_ohlcv_by_date(fromdate=today, todate=today, ticker=stock_code)
                    if not df.empty:
                        closing_price = f"{df.iloc[-1]['종가']:,}원"
                    else:
                        for i in range(1, 10):
                            previous_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                            df = stock.get_market_ohlcv_by_date(fromdate=previous_date, todate=previous_date, ticker=stock_code)
                            if not df.empty:
                                closing_price = f"{df.iloc[-1]['종가']:,}원"
                                break
            except Exception as e:
                print(f"{company_name} 종가 조회 중 오류 발생: {e}")

            # 주주 지분율 합계 계산 (계 제외)
            total_share_ratio = 0
            if 'shareholder_list' in company_data:
                for shareholder in company_data['shareholder_list']:
                    if not shareholder['nm'].endswith('계'):
                        total_share_ratio += shareholder['trmend_posesn_stock_qota_rt']

            # 시가총액 계산 추가
            market_cap = "N/A"
            try:
                if closing_price != "N/A" and closing_price != "조회 실패":
                    print(f"처리 전 closing_price: {closing_price}, 타입: {type(closing_price)}")
                    
                    # closing_price의 타입에 따른 처리
                    if isinstance(closing_price, (int, float)):
                        price = int(closing_price)
                    else:
                        # 문자열인 경우에만 replace 수행
                        price_str = closing_price.replace(',', '').replace('원', '')
                        try:
                            price = int(float(price_str))
                        except ValueError as e:
                            print(f"숫자 변환 실패: {e}, 입력값: {price_str}")
                            price = 0
                    
                    print(f"변환된 price: {price}")
                    # issued_shares 가져오기
                    issued_shares = convert_to_int(company_data.get('issued_share', {}).get('보통주', {}).get('istc_totqy', 0))
                    print(f"issued_shares: {issued_shares}")
                    
                    if issued_shares and price:
                        market_cap = f"{(price * issued_shares) // 100000000:,}"  # 억원 단위로 변환
                        print(f"계산된 market_cap: {market_cap}")
                    else:
                        print(f"issued_shares 또는 price가 0: {issued_shares}, {price}")
                        market_cap = "N/A"
            except Exception as e:
                print(f"시가총액 계산 중 오류 발생: {e}")
                print(f"문제가 된 closing_price 타입: {type(closing_price)}, 값: {closing_price}")
                market_cap = "N/A"

            # 테이블에 데이터 추가
            items = [
                company_name,
                company_data.get('corp_info', {}).get('market', 'N/A'),
                f"{total_treasury:,}주" if total_treasury > 0 else "0주",
                closing_price,
                '',  # 버튼이 들어갈 자리
                market_cap
            ]
            total_share_ratio = 0
            if 'shareholder_list' in company_data:
                for shareholder in company_data['shareholder_list']:
                    if not shareholder['nm'].endswith('계'):
                        total_share_ratio += shareholder['trmend_posesn_stock_qota_rt']
            # 주주현황 버튼 추가 (지분율 표시 포함)
            button_text = f"{total_share_ratio:.2f}%"
            view_button = QPushButton(button_text)
            view_button.setStyleSheet("text-align: center;")
            view_button.clicked.connect(lambda: self.show_shareholder_dialog(company_name, company_data))

            # 테이블에 데이터 추가
            for col, value in enumerate(items):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.data_table.setItem(row_position, col, item)

            # 주주현황 버튼 추가 (지분율 표시 포함)
            button_text = f"{total_share_ratio:.2f}%"
            view_button = QPushButton(button_text)
            view_button.setStyleSheet("text-align: center;")
            view_button.clicked.connect(lambda: self.show_shareholder_dialog(company_name, company_data))
            self.data_table.setCellWidget(row_position, 4, view_button)

        self.data_table.resizeColumnsToContents()

    def show_shareholder_dialog(self, company_name, company_data):
        if 'shareholder_list' in company_data:
            dialog = ShareholderDialog(company_data['shareholder_list'], company_name, self)
            dialog.exec_()

    def handle_cell_click(self, row, column):
        if column == 4:  # 주주현황 열을 클릭했을 때
            company_name = self.data_table.item(row, 0).text()
            if company_name in self.all_companies:
                self.show_shareholder_dialog(company_name, self.all_companies[company_name])

    @pyqtSlot(int, int)
    def update_progress(self, current, total):
        if hasattr(self, 'progress_label'):
            self.progress_label.setText(f'데이터 수집 중... ({current}/{total})')
            if current >= total:
                self.progress_label.setText('데이터 수집 완료')

    def update_existing_row(self, company_name, company_data):
        # 기존 행을 찾아서 업데이트
        for row in range(self.data_table.rowCount()):
            item = self.data_table.item(row, 0)
            # item이 None이 아닌지 확인
            if item and item.text() == company_name:
                # 자기주식 총계 계산
                total_treasury = 0
                if 'treasury_info' in company_data:
                    treasury_info = company_data['treasury_info']
                    if isinstance(treasury_info, dict) and '총계' in treasury_info:
                        total_treasury = treasury_info['총계'].get('보통주', 0) + treasury_info['총계'].get('우선주', 0)

                # 종가 정보 가져오기
                closing_price = "N/A"
                try:
                    stock_code = company_data.get('corp_info', {}).get('stock_code')
                    if stock_code:
                        stock_code = stock_code.zfill(6)
                        today = datetime.now().strftime("%Y%m%d")
                        df = stock.get_market_ohlcv_by_date(fromdate=today, todate=today, ticker=stock_code)
                        if not df.empty:
                            closing_price = f"{df.iloc[-1]['종가']:,}원"
                        else:
                            for i in range(1, 10):
                                previous_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                                df = stock.get_market_ohlcv_by_date(fromdate=previous_date, todate=previous_date, ticker=stock_code)
                                if not df.empty:
                                    closing_price = f"{df.iloc[-1]['종가']:,}원"
                                    break
                except Exception as e:
                    print(f"{company_name} 종가 조회 중 오류 발생: {e}")

                # 데이터 업데이트 전에 각 셀이 존재하는지 확인
                for col, value in enumerate([
                    company_data.get('corp_info', {}).get('market', 'N/A'),
                    f"{total_treasury:,}주" if total_treasury > 0 else "0주",
                    closing_price
                ]):
                    item = self.data_table.item(row, col + 1)
                    if item is None:
                        item = QTableWidgetItem()
                        self.data_table.setItem(row, col + 1, item)
                    item.setText(str(value))
                break

if __name__ == '__main__':
    app = QApplication(sys.argv)
    search_app = SearchApp()
    search_app.stack.show()
    sys.exit(app.exec_())
