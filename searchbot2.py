import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QWidget, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QListWidget, QDialog, QStackedWidget, QLabel, QTableWidget, QTableWidgetItem
from pykrx import stock
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import threading
import time
from queue import Queue
import math

DART_API_KEY = 'bea2a84f1ed21a05c3bc44c406f4b12f9ba56902'

# 숫자 변환 헬퍼 함수 추가
def convert_to_int(value):
    if value is None or value == '' or value == '-':
        return 0
    return int(value.replace(',', ''))

def convert_to_float(value):
    if value is None or value == '' or value == '-':
        return 0.0
    return float(value.replace(',', ''))

class DataCollectorThread(QThread):
    data_ready = pyqtSignal(str, dict)
    progress = pyqtSignal(int, int)  # 현재 진행 상황, 전체 기업 수

    def __init__(self, company_name, companies, api_key):
        super().__init__()
        self.company_name = company_name
        self.companies = companies
        self.api_key = api_key
        self.api_semaphore = threading.Semaphore(100)  # API 호출 제한을 위한 세마포어
        self.api_queue = Queue()

    def run(self):
        total_companies = len(self.companies)
        processed = 0

        # API 호출 제한 관리를 위한 스레드
        def api_rate_limiter():
            while True:
                if not self.api_queue.empty():
                    self.api_semaphore.acquire()
                    time.sleep(0.6)  # 1분에 100회 제한을 고려하여 0.6초 간격
                    self.api_semaphore.release()
                else:
                    time.sleep(0.1)

        limiter_thread = threading.Thread(target=api_rate_limiter, daemon=True)
        limiter_thread.start()

        def process_company(company_name, corp_info):
            try:
                # API 호출이 필요한 작업을 수행
                company_data = self.collect_company_data(company_name, corp_info)
                if company_data:
                    self.data_ready.emit(company_name, company_data)
            except Exception as e:
                print(f"Error processing {company_name}: {e}")

        threads = []
        batch_size = 10  # 동시에 처리할 기업 수

        # 기업들을 배치로 나누어 처리
        company_items = list(self.companies.items())
        for i in range(0, len(company_items), batch_size):
            batch = company_items[i:i + batch_size]
            current_threads = []
            
            for company_name, corp_info in batch:
                if company_name != self.company_name:  # 이미 처리된 기업 제외
                    thread = threading.Thread(
                        target=process_company,
                        args=(company_name, corp_info)
                    )
                    thread.start()
                    current_threads.append(thread)
                    threads.append(thread)

            # 현재 배치의 모든 스레드가 완료될 때까지 대기
            for thread in current_threads:
                thread.join()
            
            processed += len(batch)
            self.progress.emit(processed, total_companies)

        # 모든 스레드가 완료될 때까지 대기
        for thread in threads:
            thread.join()

    def collect_company_data(self, company_name, corp_info):
        # API 호출 전에 큐에 추가
        self.api_queue.put(1)
        
        result = {
            "corp_info": corp_info,
            "treasury_info": {"총계": {"보통주": 0, "우선주": 0}},
        }

        try:
            # 주식 코드로 종가 정보 조회
            stock_code = corp_info.get('stock_code')
            if stock_code:
                stock_code = stock_code.zfill(6)
                today = datetime.now().strftime("%Y%m%d")
                df = stock.get_market_ohlcv_by_date(fromdate=today, todate=today, ticker=stock_code)
                if not df.empty:
                    result["closing_price"] = df.iloc[-1]['종가']
                else:
                    for i in range(1, 10):
                        previous_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                        df = stock.get_market_ohlcv_by_date(fromdate=previous_date, todate=previous_date, ticker=stock_code)
                        if not df.empty:
                            result["closing_price"] = df.iloc[-1]['종가']
                            break

            # 자기주식 정보 수집
            corp_code = corp_info.get('corp_code')
            if corp_code:
                regular_report = self.get_latest_regular_disclosure(corp_code)
                if regular_report:
                    bsns_year = regular_report['rcept_dt'][:4]
                    reprt_code = self.get_report_code(regular_report['report_nm'])
                    
                    tesstk_url = "https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json"
                    tesstk_params = {
                        'crtfc_key': self.api_key,
                        'corp_code': corp_code,
                        'bsns_year': bsns_year,
                        'reprt_code': reprt_code
                    }
                    self.api_queue.put(1)  # API 호출 제한 관리
                    tesstk_response = requests.get(tesstk_url, params=tesstk_params)
                    if tesstk_response.status_code == 200:
                        tesstk_data = tesstk_response.json()
                        if tesstk_data['status'] == '000':
                            treasury_info = {
                                "직접취득": {"보통주": 0, "우선주": 0},
                                "신탁계약에 의한취득": {"보통주": 0, "우선주": 0},
                                "기타취득": {"보통주": 0, "우선주": 0},
                                "총계": {"보통주": 0, "우선주": 0}
                            }
                            if 'list' in tesstk_data and tesstk_data['list']:
                                for item in tesstk_data['list']:
                                    acqs_mth2 = item['acqs_mth2']
                                    if acqs_mth2 == '-':
                                        acqs_mth2 = '기타취득'
                                    
                                    stock_knd = item['stock_knd']
                                    if stock_knd == '-':
                                        stock_knd = '보통주'
                                    
                                    trmend_qy = convert_to_int(item.get('trmend_qy'))
                                    
                                    if acqs_mth2 in treasury_info and stock_knd in treasury_info[acqs_mth2]:
                                        treasury_info[acqs_mth2][stock_knd] = trmend_qy
                                        treasury_info["총계"][stock_knd] += trmend_qy
                            
                            result["treasury_info"] = treasury_info

            return result
        except Exception as e:
            print(f"Error collecting data for {company_name}: {e}")
            return None

    def get_latest_regular_disclosure(self, corp_code):
        api_key = self.api_key
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
            self.api_queue.put(1)  # API 호출 제한 관리
            url = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={api_key}&corp_code={corp_code}&bgn_de={year}0101&end_de={year}1231&pblntf_ty=A&sort=date&sort_mth=desc&page_no=1&page_count=1"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == '000' and data['list']:
                    return data['list'][0]  # 가장 최근 정기공시 반환
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
            return None

class SearchApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.stack = QStackedWidget()
        self.stack.addWidget(self)  # 검색 화면을 첫 번째 페이지로 추가

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

        # 기존 캐시 파일 읽기
        existing_corp_info = {}
        if os.path.exists('./cache/corp_info.json'):
            with open('./cache/corp_info.json', 'r', encoding='utf-8') as f:
                existing_corp_info = json.load(f)

        # KOSPI, KOSDAQ 기업 정보 추가 (기존 데이터 유지)
        kospi = stock.get_market_ticker_list(market="KOSPI")
        kosdaq = stock.get_market_ticker_list(market="KOSDAQ")

        for ticker in kospi:
            name = stock.get_market_ticker_name(ticker)
            if name not in existing_corp_info:
                existing_corp_info[name] = {"corp_info": {"market": "KOSPI"}}

        for ticker in kosdaq:
            name = stock.get_market_ticker_name(ticker)
            if name not in existing_corp_info:
                existing_corp_info[name] = {"corp_info": {"market": "KOSDAQ"}}

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

        matching_companies = [name for name in existing_corp_info if search_term in name]

        if len(matching_companies) == 1:
            search_term = matching_companies[0]
            corp_code = company_codes[search_term]['corp_code']
            stock_code = company_codes[search_term].get('stock_code')
            if stock_code:
                existing_corp_info[search_term]['corp_info']['stock_code'] = stock_code
        elif len(matching_companies) > 1:
            search_term = self.select_company(matching_companies)
            if not search_term:
                return
            corp_code = company_codes[search_term]['corp_code']
            stock_code = company_codes[search_term].get('stock_code')
            if stock_code:
                existing_corp_info[search_term]['corp_info']['stock_code'] = stock_code
        else:
            QMessageBox.information(self, '검색 결과', '검색어에 해당하는 기업이 없습니다.')
            return

        print(f"Selected company: {search_term}, Using corp_code: {corp_code}")

        # 필요한 정보가 있는지 확인
        if search_term not in existing_corp_info:
            existing_corp_info[search_term] = {"corp_info": {}}

        required_fields = [
            "corp_info",
            "treasury_info",
            "shareholder_list",
            "issued_share",
            "financial_info",
            "contribution_info"
        ]

        missing_fields = []
        for field in required_fields:
            # 필드가 없거나 비어있는 경우에만 missing_fields에 추가
            if field not in existing_corp_info[search_term] or not existing_corp_info[search_term].get(field):
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
                        existing_corp_info[search_term]["corp_info"].update({
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
                            treasury_info = {
                                "직접취득": {"보통주": 0, "우선주": 0},
                                "신탁계약에 의한취득": {"보통주": 0, "우선주": 0},
                                "기타취득": {"보통주": 0, "우선주": 0},
                                "총계": {"보통주": 0, "우선주": 0}
                            }
                            if 'list' in tesstk_data and tesstk_data['list']:
                                for item in tesstk_data['list']:
                                    acqs_mth2 = item['acqs_mth2']
                                    if acqs_mth2 == '-':
                                        acqs_mth2 = '기타취득'
                                    
                                    stock_knd = item['stock_knd']
                                    if stock_knd == '-':
                                        stock_knd = '보통주'
                                    
                                    trmend_qy = convert_to_int(item.get('trmend_qy'))
                                    
                                    if acqs_mth2 in treasury_info and stock_knd in treasury_info[acqs_mth2]:
                                        treasury_info[acqs_mth2][stock_knd] = trmend_qy
                                        treasury_info["총계"][stock_knd] += trmend_qy
                                
                            existing_corp_info[search_term]["treasury_info"] = treasury_info

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
                            existing_corp_info[search_term]["shareholder_list"] = shareholder_list

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
                                issued_share[se].update({
                                    'istc_totqy': convert_to_int(item.get('istc_totqy')),
                                    'now_to_totqy': convert_to_int(item.get('now_to_totqy')),
                                    'distb_stock_co': convert_to_int(item.get('distb_stock_co'))
                                })
                            existing_corp_info[search_term]["issued_share"] = issued_share

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
                            existing_corp_info[search_term]["contribution_info"] = contribution_info

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
                                existing_corp_info[search_term]["financial_info"] = financial_info
                                break  # 데이터를 찾았으므로 루프 종료
                        else:
                            print(f"- {year}년 사업보고서 데이터 없음")
                    else:
                        print(f"- {year}년 사업보고서 API 요청 실패")

            print(f"\n=== {search_term} 기업 정보 수집 완료 ===\n")

        # 캐시 파일 업데이트는 변경사항이 있을 때만 수행
        if missing_fields:
            if not os.path.exists('./cache'):
                os.makedirs('./cache')
            with open('./cache/corp_info.json', 'w', encoding='utf-8') as f:
                json.dump(existing_corp_info, f, ensure_ascii=False, indent=4)

        # 결과 화면으로 전환
        result_widget = ResultWidget(search_term, existing_corp_info[search_term])
        self.stack.addWidget(result_widget)
        self.stack.setCurrentWidget(result_widget)

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

class ResultWidget(QWidget):
    def __init__(self, company_name, company_data):
        super().__init__()
        self.company_name = company_name
        self.company_data = company_data
        self.data_table = None
        self.progress_label = None
        self.initUI()
        self.start_data_collection()

    def initUI(self):
        layout = QVBoxLayout()
        
        # 검색한 기업 정보를 표시할 테이블
        standard_table = QTableWidget()
        standard_table.setColumnCount(5)
        standard_table.setRowCount(1)
        
        # 헤더 설정
        headers = ['기업명', '시장', '자기주식 총계', '종가', '']
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
        
        data = [
            self.company_name,
            corp_info.get('market', 'N/A'),
            f"{total_treasury:,}주",
            closing_price,
            ''
        ]
        
        # standard_table에 데이터 삽입
        for col, value in enumerate(data):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            standard_table.setItem(0, col, item)
        
        # standard_table 크기 조정
        standard_table.resizeColumnsToContents()
        standard_table.setFixedHeight(standard_table.verticalHeader().length() + 60)
        
        layout.addWidget(standard_table)

        # 진행 상황을 표시할 라벨 추가
        self.progress_label = QLabel('데이터 수집 중...')
        layout.addWidget(self.progress_label)

        # data_table 초기화
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(5)
        self.data_table.setHorizontalHeaderLabels(headers)
        layout.addWidget(self.data_table)

        # 뒤로가기 버튼
        back_button = QPushButton('뒤로가기')
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)

        self.setLayout(layout)

    def go_back(self):
        self.parent().setCurrentIndex(0)  # 첫 번째 페이지(검색 화면)로 돌아가기

    def start_data_collection(self):
        # 캐시된 기업 정보 로드
        with open('./cache/corp_info.json', 'r', encoding='utf-8') as f:
            all_companies = json.load(f)

        # 데이터 수집 스레드 시작
        self.collector_thread = DataCollectorThread(
            self.company_name,
            all_companies,
            DART_API_KEY
        )
        self.collector_thread.data_ready.connect(self.update_data_table)
        self.collector_thread.progress.connect(self.update_progress)
        self.collector_thread.start()

    def update_data_table(self, company_name, company_data):
        row_position = self.data_table.rowCount()
        self.data_table.insertRow(row_position)

        # 테이블에 데이터 추가
        items = [
            company_name,
            company_data['corp_info'].get('market', 'N/A'),
            f"{company_data['treasury_info']['총계']['보통주'] + company_data['treasury_info']['총계']['우선주']:,}주",
            f"{company_data.get('closing_price', 'N/A'):,}원" if company_data.get('closing_price') else 'N/A',
            ''
        ]

        for col, value in enumerate(items):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            self.data_table.setItem(row_position, col, item)

        self.data_table.resizeColumnsToContents()

    def update_progress(self, current, total):
        self.progress_label.setText(f'데이터 수집 중... ({current}/{total})')
        if current >= total:
            self.progress_label.setText('데이터 수집 완료')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    search_app = SearchApp()
    search_app.stack.show()
    sys.exit(app.exec_())
