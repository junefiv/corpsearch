import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QWidget, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QListWidget, QDialog
from pykrx import stock
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime

DART_API_KEY = 'bea2a84f1ed21a05c3bc44c406f4b12f9ba56902'

class SearchApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

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

        kospi = stock.get_market_ticker_list(market="KOSPI")
        kosdaq = stock.get_market_ticker_list(market="KOSDAQ")

        corp_info = {}
        for ticker in kospi:
            name = stock.get_market_ticker_name(ticker)
            corp_info[name] = {"corp_info": {"market": "KOSPI"}}

        for ticker in kosdaq:
            name = stock.get_market_ticker_name(ticker)
            corp_info[name] = {"corp_info": {"market": "KOSDAQ"}}

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

            print(f"Processing company: {corp_name}, corp_code: {corp_code}")
            
            # 모든 기업의 corp_code를 저장
            company_codes[corp_name] = corp_code

            if corp_name == search_term:
                print(f"Found company: {corp_name}, corp_code: {corp_code}")
                corp_info[corp_name]["corp_info"].update({
                    "corp_code": corp_code,
                    "stock_code": stock_code
                })

                # 기업 기본 정보 API 호출
                company_info_url = f"https://opendart.fss.or.kr/api/company.json"
                company_params = {
                    'crtfc_key': api_key,
                    'corp_code': corp_code
                }
                company_response = requests.get(company_info_url, params=company_params)
                if company_response.status_code == 200:
                    company_data = company_response.json()
                    if company_data['status'] == '000':
                        corp_info[corp_name]["corp_info"].update({
                            "ceo_nm": company_data.get("ceo_nm"),
                            "jurir_no": company_data.get("jurir_no"),
                            "bizr_no": company_data.get("bizr_no"),
                            "adres": company_data.get("adres"),
                            "hm_url": company_data.get("hm_url"),
                            "est_dt": company_data.get("est_dt"),
                            "induty_code": company_data.get("induty_code")
                        })
                        print(f"{corp_name}의 정보가 성공적으로 업데이트되었습니다.")

                        # 정기공시 정보 가져오기
                        report = self.get_latest_regular_disclosure(corp_code)
                        attempts = 0
                        while not report and attempts < 7:
                            attempts += 1
                            print(f"시도 {attempts}: 정기공시를 찾을 수 없습니다. 다음 보고서를 시도합니다.")
                            report = self.get_latest_regular_disclosure(corp_code)

                        if report:
                            print(f"정기공시를 찾았습니다: {report}")
                            bsns_year = report['rcept_dt'][:4]
                            # report_nm에서 보고서 유형 추출
                            report_nm = report['report_nm']
                            if '분기보고서' in report_nm:
                                reprt_code = '11013'
                            elif '반기보고서' in report_nm:
                                reprt_code = '11012'
                            elif '사업보고서' in report_nm:
                                reprt_code = '11011'
                            elif '3분기보고서' in report_nm:
                                reprt_code = '11014'
                            else:
                                print("알 수 없는 보고서 유형입니다.")
                                return

                            # 자기주식 취득 및 처분 현황
                            tesstk_url = f"https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json"
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
                                    for item in tesstk_data['list']:
                                        acqs_mth2 = item['acqs_mth2']
                                        stock_knd = item['stock_knd']
                                        trmend_qy = item['trmend_qy']
                                        # 쉼표 제거 후 '-' 값을 0으로 변환
                                        trmend_qy = 0 if trmend_qy == '-' else int(trmend_qy.replace(',', ''))
                                        if acqs_mth2 not in treasury_info:
                                            treasury_info[acqs_mth2] = {}
                                        if stock_knd not in treasury_info[acqs_mth2]:
                                            treasury_info[acqs_mth2][stock_knd] = 0
                                        treasury_info[acqs_mth2][stock_knd] += trmend_qy

                                    corp_info[corp_name]["treasury_info"] = treasury_info
                                else:
                                    print("자기주식 취득 및 처분 현황을 찾을 수 없습니다.")
                        
                        # 정기공시 정보 가져오기
                        report = self.get_latest_regular_disclosure(corp_code)
                        attempts = 0
                        while not report and attempts < 7:
                            attempts += 1
                            print(f"시도 {attempts}: 정기공시를 찾을 수 없습니다. 다음 보고서를 시도합니다.")
                            report = self.get_latest_regular_disclosure(corp_code)

                        if report:
                            print(f"정기공시를 찾았습니다: {report}")
                            bsns_year = report['rcept_dt'][:4]
                            # report_nm에서 보고서 유형 추출
                            report_nm = report['report_nm']
                            if '분기보고서' in report_nm:
                                reprt_code = '11013'
                            elif '반기보고서' in report_nm:
                                reprt_code = '11012'
                            elif '사업보고서' in report_nm:
                                reprt_code = '11011'
                            elif '3분기보고서' in report_nm:
                                reprt_code = '11014'
                            else:
                                print("알 수 없는 보고서 유형입니다.")
                                return
                            # 최대주주 현황
                            hyslr_url = f"https://opendart.fss.or.kr/api/hyslrSttus.json"
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
                                            'trmend_posesn_stock_co': 0 if item.get('trmend_posesn_stock_co', '0') == '-' else int(item.get('trmend_posesn_stock_co', '0').replace(',', '')),
                                            'trmend_posesn_stock_qota_rt': 0 if item.get('trmend_posesn_stock_qota_rt', '0') == '-' else float(item.get('trmend_posesn_stock_qota_rt', '0.00'))
                                        }
                                        shareholder_list.append(shareholder_info)
                                    corp_info[corp_name]["shareholder_list"] = shareholder_list
                                else:
                                    print("최대주주 현황을 찾을 수 없습니다.")
                        else:
                            # 값이 없을 경우 0으로 초기화
                            corp_info[corp_name]["treasury_info"] = {'total': 0}
                            print("자기주식 취득 및 처분 현황을 찾을 수 없습니다. 기본값 0으로 설정합니다.")

                        report = self.get_latest_regular_disclosure(corp_code)
                        attempts = 0
                        while not report and attempts < 7:
                            attempts += 1
                            print(f"시도 {attempts}: 정기공시를 찾을 수 없습니다. 다음 보고서를 시도합니다.")
                            report = self.get_latest_regular_disclosure(corp_code)

                        if report:
                            print(f"정기공시를 찾았습니다: {report}")
                            bsns_year = report['rcept_dt'][:4]
                            # report_nm에서 보고서 유형 추출
                            report_nm = report['report_nm']
                            if '분기보고서' in report_nm:
                                reprt_code = '11013'
                            elif '반기보고서' in report_nm:
                                reprt_code = '11012'
                            elif '사업보고서' in report_nm:
                                reprt_code = '11011'
                            elif '3분기보고서' in report_nm:
                                reprt_code = '11014'
                            else:
                                print("알 수 없는 보고서 유형입니다.")
                                return
                        # 주식의 총수 현황 가져오기
                        stock_totqy_url = f"https://opendart.fss.or.kr/api/stockTotqySttus.json"
                        stock_totqy_params = {
                            'crtfc_key': api_key,
                            'corp_code': corp_code,
                            'bsns_year': bsns_year,
                            'reprt_code': reprt_code
                        }
                        stock_totqy_response = requests.get(stock_totqy_url, params=stock_totqy_params)
                        if stock_totqy_response.status_code == 200:
                            stock_totqy_data = stock_totqy_response.json()
                            if stock_totqy_data['status'] == '000':
                                for item in stock_totqy_data['list']:
                                    if item['se'] == '합계':  # '합계' 항목만 사용
                                        issued_share = {
                                            'istc_totqy': 0 if item.get('istc_totqy', '0') == '-' else int(item.get('istc_totqy', '0').replace(',', '')),
                                            'tesstk_co': 0 if item.get('tesstk_co', '0') == '-' else int(item.get('tesstk_co', '0').replace(',', '')),
                                            'distb_stock_co': 0 if item.get('distb_stock_co', '0') == '-' else int(item.get('distb_stock_co', '0').replace(',', ''))
                                        }
                                        corp_info[corp_name]["issued_share"] = issued_share
                            else:
                                print("주식의 총수 현황을 찾을 수 없습니다.")

                        # 가장 최근의 사업보고서 가져오기
                        print(f"Calling get_latest_business_report with corp_code: {corp_code}")  # 디버깅: 호출 전 corp_code 출력
                        business_report = self.get_latest_business_report(corp_code)
                        print(f"Using corp_code for business report: {corp_code}")  # 디버깅: 사업보고서에 사용되는 corp_code 출력
                        attempts = 0
                        while not business_report and attempts < 7:
                            attempts += 1
                            print(f"시도 {attempts}: 정기공시를 찾을 수 없습니다. 다음 보고서를 시도합니다.")
                            business_report = self.get_latest_business_report(corp_code)
                        if business_report:
                            bsns_year = business_report['rcept_dt'][:4]
                            
                            # 재무 정보 가져오기
                            api_key = DART_API_KEY
                            reprt_code = '11011'  # 사업보고서 코드
                            fs_div = 'OFS'  # 재무제표 구분

                            url = f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
                            params = {
                                'crtfc_key': api_key,
                                'corp_code': corp_code,
                                'bsns_year': bsns_year,
                                'reprt_code': reprt_code,
                                'fs_div': fs_div
                            }
                            response = requests.get(url, params=params)
                            if response.status_code == 200:
                                data = response.json()
                                if data['status'] == '000':
                                    financial_info = []
                                    for item in data['list']:
                                        if item['sj_div'] in ['BS', 'IS', 'CF']:
                                            account_info = {
                                                'account_id': item.get('account_id', 'N/A'),
                                                'account_nm': item.get('account_nm', 'N/A'),
                                                'thstrm_amount': item.get('thstrm_amount', '0'),
                                                'currency': item.get('currency', 'N/A')
                                            }
                                            financial_info.append(account_info)
                                    corp_info[corp_name]["financial_info"] = financial_info
                                else:
                                    print("재무 정보를 찾을 수 없습니다.")
                            else:
                                print("API 요청에 실패했습니다.")
                    else:
                        QMessageBox.warning(self, '오류', '기업 기본 정보 API 요청에 실패했습니다.')
                        return

        matching_companies = [name for name in corp_info if search_term in name]

        if len(matching_companies) == 1:
            search_term = matching_companies[0]
            corp_code = company_codes[search_term]  # 선택된 기업의 corp_code 사용
        elif len(matching_companies) > 1:
            search_term = self.select_company(matching_companies)
            if not search_term:
                return
            corp_code = company_codes[search_term]  # 선택된 기업의 corp_code 사용
        else:
            QMessageBox.information(self, '검색 결과', '검색어에 해당하는 기업이 없습니다.')
            return

        print(f"Selected company: {search_term}, Using corp_code: {corp_code}")  # 디버깅: 선택된 기업과 corp_code 출력

        # JSON 파일로 저장
        if not os.path.exists('cache'):
            os.makedirs('cache')

        with open(f'cache/corp_info.json', 'w', encoding='utf-8') as f:
            json.dump(corp_info, f, ensure_ascii=False, indent=4)

        # 가장 최근의 사업보고서 가져오기
        business_report = self.get_latest_business_report(corp_code)
        if business_report:
            bsns_year = business_report['rcept_dt'][:4]
            self.get_financial_info(corp_code, bsns_year)

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

    def get_latest_business_report(self, corp_code):
        print(f"get_latest_business_report called with corp_code: {corp_code}")  # 디버깅: 함수 호출 시 corp_code 출력
        api_key = DART_API_KEY
        current_year = datetime.now().year
        current_month = datetime.now().month

        # 보고서 순서 결정
        if current_month < 3:  # 1~2월인 경우
            report_sequence = [
                (current_year-2, '11011'),  # 전년도 사업보고서
                (current_year-3, '11011'),  # 전전년도 사업보고서
            ]
        else:  # 3월 이후인 경우
            report_sequence = [
                (current_year-1, '11011'),    # 당해 사업보고서
                (current_year-2, '11011'),  # 전년도 사업보고서
            ]

        for year, reprt_code in report_sequence:
            url = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={api_key}&corp_code={corp_code}&bgn_de={year}0101&end_de={year}1231&pblntf_ty=A&sort=date&sort_mth=desc&page_no=1&page_count=100"
            print(f"Requesting URL: {url}")  # 디버깅: 요청 URL 출력
            response = requests.get(url)
            print(f"Response Status Code: {response.status_code}")  # 디버깅: 응답 상태 코드 출력
            if response.status_code == 200:
                data = response.json()
                print(f"Response Data: {data}")  # 디버깅: 응답 데이터 출력
                if data['status'] == '000':
                    for report in data['list']:
                        print(f"Checking report: {report}")  # 디버깅: 각 보고서 출력
                        if 'pblntf_detail_ty' in report and report['pblntf_detail_ty'] == reprt_code:
                            print(f"Found report for year {year} with reprt_code {reprt_code}")  # 디버깅: 보고서 발견
                            return report
                else:
                    print(f"{year}년 사업보고서를 찾을 수 없습니다. Status: {data['status']}")  # 디버깅: 상태 코드 출력
            else:
                print("API 요청에 실패했습니다.")
        return None



if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SearchApp()
    sys.exit(app.exec_())
