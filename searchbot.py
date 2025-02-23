from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, 
                           QTextEdit, QHBoxLayout, QLabel, QLineEdit, QStackedWidget,
                           QMessageBox, QTableWidget, QHeaderView, QTableWidgetItem,
                           QDialog, QRadioButton, QButtonGroup, QHBoxLayout, QGridLayout,
                           QScrollArea)
import sys
import json
from pykrx import stock
from datetime import datetime, timedelta
import os
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
import math
import requests
import zipfile
import xml.etree.ElementTree as ET
import io
import time

def get_currently_trading_companies():
    # KOSPI와 KOSDAQ의 현재 거래 가능한 종목 코드 목록을 가져옵니다.
    kospi_tickers = stock.get_market_ticker_list(market="KOSPI")
    kosdaq_tickers = stock.get_market_ticker_list(market="KOSDAQ")
    
    # 두 시장의 종목 코드를 합칩니다.
    all_tickers = kospi_tickers + kosdaq_tickers
    
    # 종목 코드와 종목명을 딕셔너리로 저장합니다.
    trading_companies = {}
    for ticker in all_tickers:
        name = stock.get_market_ticker_name(ticker)
        trading_companies[name] = ticker
    
    return trading_companies

def get_ticker_price(corp_name, stock_code):
    """
    주어진 종목코드의 날짜별 종가를 출력하고 최근 종가를 반환합니다.
    Args:
        corp_name (str): 회사명
        stock_code (str): 종목코드
        
    Returns:
        int: 최근 종가 (실패시 0 반환)
    """
    try:
        # 오늘 날짜
        end_date = datetime.now().strftime("%Y%m%d")
        # 20일 전 날짜 (주말/공휴일 고려)
        start_date = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
        
        # 주가 데이터 조회
        df = stock.get_market_ohlcv_by_date(
            fromdate=start_date,
            todate=end_date,
            ticker=stock_code
        )
        
        # 데이터가 존재하면 날짜별 종가 출력
        if not df.empty:
            print(f"\n{corp_name}({stock_code})의 날짜별 종가:")
            for date, row in df.iterrows():
                print(f"{date.strftime('%Y-%m-%d')}: {int(row['종가']):,}원")
            return int(df.iloc[-1]["종가"])
            
    except Exception as e:
        print(f"{corp_name}({stock_code}) 주가 조회 실패: {str(e)}")
    
    return 0

class SearchThread(QThread):
    search_completed = pyqtSignal(str, dict, int)  # 검색 완료 시 신호

    def __init__(self, corp_name, corps):
        super().__init__()
        self.corp_name = corp_name
        self.corps = corps

    def run(self):
        # 검색 작업 수행
        corp_info = self.corps[self.corp_name]
        corp_code = corp_info['corp_code']
        stock_code = corp_info['stock_code']
        
        # 주가 가져오기
        current_price = get_ticker_price(self.corp_name, stock_code)
        
        # 자기주식 정보 가져오기
        self.get_treasury_stock(corp_code, self.corp_name, self.corps)
        
        # 검색 완료 신호 발송
        self.search_completed.emit(self.corp_name, self.corps, current_price)

    def get_treasury_stock(self, corp_code, corp_name, corps):
        API_KEY = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
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

        # 기본값으로 0 설정
        treasury_stock = {
            "직접취득": 0,
            "신탁계약취득": 0,
            "기타취득": 0
        }

        latest_data = None
        
        for year, reprt_code in report_sequence:
            if latest_data:
                break
            
            url = "https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json"
            params = {
                "crtfc_key": API_KEY,
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": reprt_code
            }
            
            try:
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == '000' and data.get('list'):
                        latest_data = data
                        print(f"{corp_name}: {year}년 {reprt_code} 보고서에서 데이터 찾음")
                        break
                    else:
                        print(f"{corp_name}: {year}년 {reprt_code} 보고서 데이터 없음")
            except Exception as e:
                print(f"{corp_name} API 요청 오류: {str(e)}")
                continue

        if latest_data:
            for item in latest_data.get('list', []):
                acqs_mth2 = item.get('acqs_mth2', '')
                trmend_qy = item.get('trmend_qy', '0')
                
                # 모든 주식 종류에 대해 합계 계산
                if acqs_mth2 == '직접취득':
                    amount = int(trmend_qy.replace(',', '')) if trmend_qy != '-' else 0
                    treasury_stock['직접취득'] += amount
                elif acqs_mth2 == '신탁계약에 의한취득':
                    amount = int(trmend_qy.replace(',', '')) if trmend_qy != '-' else 0
                    treasury_stock['신탁계약취득'] += amount
                elif acqs_mth2 == '기타취득':
                    amount = int(trmend_qy.replace(',', '')) if trmend_qy != '-' else 0
                    treasury_stock['기타취득'] += amount
        else:
            print(f"{corp_name}: 자기주식 데이터 없음, 0으로 설정")
            
        print(f"{corp_name} 자기주식 데이터: {treasury_stock}")
        # treasury_stock 정보 저장
        corps[corp_name]["treasury_stock"] = treasury_stock
        
        # 캐시 즉시 저장
        with open('cache/corp_info.json', 'w', encoding='utf-8') as f:
            json.dump(corps, f, ensure_ascii=False, indent=4)
        
        # 다음 함수 호출
        self.get_financial_info(corp_code, corp_name, corps)
        
    def get_financial_info(self, corp_code, corp_name, corps):
        try:
            if os.path.exists('cache/corp_info.json'):
                with open('cache/corp_info.json', 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                if corp_name in cached_data and "finance_info" in cached_data[corp_name]:
                    print(f"{corp_name}: 캐시된 재무제표 데이터 사용")
                    corps[corp_name]["finance_info"] = cached_data[corp_name]["finance_info"]
                    
                    # 캐시 즉시 저장
                    with open('cache/corp_info.json', 'w', encoding='utf-8') as f:
                        json.dump(corps, f, ensure_ascii=False, indent=4)
                    
                    # 발행주식 총수 정보 가져오기
                    self.get_stock_amount(corp_code, corp_name, corps)
                    return
        except Exception as e:
            print(f"캐시 파일 읽기 오류: {str(e)}")
        
        API_KEY = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
        current_year = datetime.now().year
        
        # 가장 최근 사업보고서(11011) 찾기
        latest_data = None
        found_year = None
        
        for year in range(current_year, current_year-4, -1):
            url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
            params = {
                "crtfc_key": API_KEY,
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": "11011",
                "fs_div": "OFS"
            }
            
            try:
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == '000':
                        latest_data = data
                        found_year = year
                        print(f"{corp_name}: {year}년 사업보고서 재무제표 데이터 찾음")
                        break
                    else:
                        print(f"{corp_name}: {year}년 사업보고서 재무제표 데이터 없음")
            except Exception as e:
                print(f"{corp_name} 재무제표 API 요청 오류: {str(e)}")
                continue
        
        if latest_data:
            # 재무제표 정보를 저장할 딕셔너리
            finance_info = {}
            
            # 재무상태표, 손익계산서 등의 데이터 처리
            for item in latest_data.get('list', []):
                sj_nm = item.get('sj_nm', '')  # 재무제표 종류
                account_nm = item.get('account_nm', '')  # 계정ID
                
                # 당기/전기/전전기 금액
                thstrm_amount = item.get('thstrm_amount', '0')  # 당기금액
                frmtrm_amount = item.get('frmtrm_amount', '0')  # 전기금액
                bfefrmtrm_amount = item.get('bfefrmtrm_amount', '0')  # 전전기금액
                
                # 음수 처리 및 정수 변환 함수
                def parse_amount(amount):
                    try:
                        if amount.startswith('-'):
                            return -int(amount[1:].replace(',', ''))
                        return int(amount.replace(',', ''))
                    except (ValueError, AttributeError):
                        return 0
                
                # 각 기간별 금액을 정수로 변환
                thstrm = parse_amount(thstrm_amount)
                frmtrm = parse_amount(frmtrm_amount)
                bfefrmtrm = parse_amount(bfefrmtrm_amount)
                
                # 재무제표 종류별로 구분하여 저장
                if sj_nm not in finance_info:
                    finance_info[sj_nm] = {}
                
                # account_detail를 키로 사용하고, 주석으로 계정명 포함
                finance_info[sj_nm][account_nm] = {
                    "당기": thstrm,
                    "전기": frmtrm,
                    "전전기": bfefrmtrm
                }
            
            print(f"{corp_name} 재무제표 데이터 저장 완료")
            corps[corp_name]["finance_info"] = finance_info
            
            # 캐시 즉시 저장
            with open('cache/corp_info.json', 'w', encoding='utf-8') as f:
                json.dump(corps, f, ensure_ascii=False, indent=4)
            
            # 발행주식 총수 정보 가져오기
            self.get_stock_amount(corp_code, corp_name, corps)
            
        else:
            print(f"{corp_name}: 재무제표 데이터를 찾을 수 없음")
            corps[corp_name]["finance_info"] = {}
            self.get_stock_amount(corp_code, corp_name, corps)

    def get_stock_amount(self, corp_code, corp_name, corps):
        API_KEY = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
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

        stock_amount = 0
        
        for year, reprt_code in report_sequence:
            if stock_amount > 0:
                break
            
            url = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
            params = {
                "crtfc_key": API_KEY,
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": reprt_code
            }

            try:
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == '000' and data.get('list'):
                        for item in data.get('list', []):
                            if item.get('istc_totqy'):
                                try:
                                    stock_amount = int(item['istc_totqy'].replace(',', ''))
                                    print(f"{corp_name}: {year}년 {reprt_code} 보고서에서 발행주식 총수 찾음")
                                    break
                                except (ValueError, AttributeError):
                                    continue
                    else:
                        print(f"{corp_name}: {year}년 {reprt_code} 보고서 발행주식 총수 데이터 없음")
            except Exception as e:
                print(f"{corp_name} 발행주식 총수 API 요청 오류: {str(e)}")
                continue

        print(f"{corp_name} 발행주식 총수: {stock_amount}")
        corps[corp_name]["stock_amount"] = stock_amount
        
        # 캐시 즉시 저장
        with open('cache/corp_info.json', 'w', encoding='utf-8') as f:
            json.dump(corps, f, ensure_ascii=False, indent=4)
        
        # 최대주주 정보 가져오기
        self.get_shareholders_info(corp_code, corp_name, corps)

    def get_shareholders_info(self, corp_code, corp_name, corps):
        try:
            if os.path.exists('cache/corp_info.json'):
                with open('cache/corp_info.json', 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    if corp_name in cached_data and "shareholders_info" in cached_data[corp_name]:
                        print(f"{corp_name}: 캐시된 최대주주 정보 사용")
                        corps[corp_name]["shareholders_info"] = cached_data[corp_name]["shareholders_info"]
                        # 캐시된 정보를 사용할 경우 바로 다음 함수 호출
                        self.get_company_info(corp_code, corp_name, corps)
                        return  # 여기서 함수 종료

            # 캐시된 정보가 없을 경우에만 API 호출
            API_KEY = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
            current_year = datetime.now().year
            current_month = datetime.now().month

            # report_sequence는 get_stock_amount와 동일한 로직 사용
            if current_month < 3:  # 1~2월인 경우
                report_sequence = [(current_year-1, '11014'), (current_year-1, '11012'),
                                 (current_year-1, '11013'), (current_year-2, '11011')]
            elif current_month < 5:
                report_sequence = [(current_year-1, '11011'), (current_year-1, '11014'),
                                 (current_year-1, '11012'), (current_year-1, '11013')]
            elif current_month < 8:
                report_sequence = [(current_year, '11013'), (current_year-1, '11011'),
                                 (current_year-1, '11014'), (current_year-1, '11012')]
            elif current_month < 11:
                report_sequence = [(current_year, '11012'), (current_year, '11013'),
                                 (current_year-1, '11011'), (current_year-1, '11014')]
            else:
                report_sequence = [(current_year, '11014'), (current_year, '11012'),
                                 (current_year, '11013'), (current_year-1, '11011')]

            shareholders_dict = {}  # 주주별 정보를 임시 저장할 딕셔너리
            latest_data = None  # latest_data 변수 초기화

            for year, reprt_code in report_sequence:
                if latest_data:
                    break

                url = "https://opendart.fss.or.kr/api/hyslrSttus.json"
                params = {
                    "crtfc_key": API_KEY,
                    "corp_code": corp_code,
                    "bsns_year": str(year),
                    "reprt_code": reprt_code
                }

                try:
                    response = requests.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('status') == '000' and data.get('list'):
                            latest_data = data
                            print(f"{corp_name}: {year}년 {reprt_code} 보고서에서 최대주주 정보 찾음")
                            
                            # 주주 정보 추출 및 저장
                            for item in data.get('list', []):
                                name = item.get('nm', '')
                                relation = item.get('relate', '')
                                stock_type = item.get('stock_knd', '')
                                shares = item.get('trmend_posesn_stock_co', '0').replace(',', '')
                                ownership_ratio = item.get('trmend_posesn_stock_qota_rt', '0')

                                # 주주 이름과 관계로 고유 키 생성
                                shareholder_key = f"{name}_{relation}"

                                # 해당 주주의 정보가 없으면 새로 생성
                                if shareholder_key not in shareholders_dict:
                                    shareholders_dict[shareholder_key] = {
                                        "name": name,
                                        "relation": relation,
                                        "stocks": {}
                                    }

                                # 주식 종류별 정보 추가
                                shareholders_dict[shareholder_key]["stocks"][stock_type] = {
                                    "shares": shares,
                                    "ownership_ratio": ownership_ratio
                                }
                            break
                        else:
                            print(f"{corp_name}: {year}년 {reprt_code} 보고서 최대주주 데이터 없음")
                except Exception as e:
                    print(f"{corp_name} 최대주주 정보 API 요청 오류: {str(e)}")
                    continue

            # 딕셔너리를 리스트로 변환
            shareholders_info = list(shareholders_dict.values())
            print(f"{corp_name} 최대주주 정보 저장 완료")
            corps[corp_name]["shareholders_info"] = shareholders_info
            
            # 캐시 즉시 저장
            with open('cache/corp_info.json', 'w', encoding='utf-8') as f:
                json.dump(corps, f, ensure_ascii=False, indent=4)
            
            # 기업개황 정보 가져오기
            self.get_company_info(corp_code, corp_name, corps)

        except Exception as e:
            print(f"캐시 파일 읽기 오류: {str(e)}")
            # 에러 발생시에도 다음 함수 호출
            self.get_company_info(corp_code, corp_name, corps)

    def get_company_info(self, corp_code, corp_name, corps):
        try:
            print(f"{corp_name}: get_company_info 함수 시작")
            
            # 캐시 확인
            if os.path.exists('cache/corp_info.json'):
                with open('cache/corp_info.json', 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    if corp_name in cached_data and "corp_status" in cached_data[corp_name]:
                        print(f"{corp_name}: 캐시된 기업개황 정보 사용")
                        corps[corp_name]["corp_status"] = cached_data[corp_name]["corp_status"]
                        return

            print(f"{corp_name}: 기업개황 정보 API 호출")
            API_KEY = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
            url = f"https://opendart.fss.or.kr/api/company.json?crtfc_key={API_KEY}&corp_code={corp_code}"
            
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == '000':
                    # KRRS API를 사용하여 업종명 가져오기
                    induty_code = data.get('induty_code', '')
                    industry_name = self.get_industry_name(induty_code)
                    
                    # corp_status 정보 저장
                    corps[corp_name]["corp_status"] = {
                        "induty_code": induty_code,
                        "industry_name": industry_name,
                        "c_nm": data.get('corp_name', ''),
                        "hm_url": data.get('hm_url', ''),
                        "ceo_nm": data.get('ceo_nm', '')
                    }
                    
                    # 캐시 업데이트
                    if os.path.exists('cache/corp_info.json'):
                        with open('cache/corp_info.json', 'r', encoding='utf-8') as f:
                            cached_data = json.load(f)
                        cached_data[corp_name]["corp_status"] = corps[corp_name]["corp_status"]
                        with open('cache/corp_info.json', 'w', encoding='utf-8') as f:
                            json.dump(cached_data, f, ensure_ascii=False, indent=4)
                else:
                    print(f"{corp_name}: 기업개황 정보를 찾을 수 없음")
                    corps[corp_name]["corp_status"] = {
                        "induty_code": "",
                        "industry_name": "",
                        "c_nm": "",
                        "hm_url": "",
                        "ceo_nm": ""
                    }
                    
        except Exception as e:
            print(f"{corp_name} 기업개황 API 요청 오류: {str(e)}")
            corps[corp_name]["corp_status"] = {
                "induty_code": "",
                "industry_name": "",
                "c_nm": "",
                "hm_url": "",
                "ceo_nm": ""
            }

    def get_industry_name(self, induty_code):
        """KRRS API를 사용하여 업종 코드를 기반으로 업종명을 반환"""
        API_KEY = "MzQwY2E0ZTEyNzk4ZWI3NGVhOGM5NDhiYjYxMTAxNmI="  # 본인의 API 키 입력
        url = f"https://api.krrs.or.kr/industry_code?apiKey={API_KEY}&induty_code={induty_code}"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if "industry_name" in data:
                    return data["industry_name"]
                else:
                    return "업종 정보 없음"
            else:
                return f"API 요청 실패: {response.status_code}"
        except Exception as e:
            return f"오류 발생: {str(e)}"

    def go_back(self):
        self.stack.setCurrentIndex(0)

    def save_corp_codes(self):
        API_KEY = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
        url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={API_KEY}"
        
        try:
            response = requests.get(url)
            if response.status_code != 200:
                QMessageBox.warning(self, '오류', 'API 요청에 실패했습니다.')
                return
                
            z = zipfile.ZipFile(io.BytesIO(response.content))
            xml_data = z.read('CORPCODE.xml').decode('utf-8')
            root = ET.fromstring(xml_data)
            
            # 현재 거래 가능한 기업 목록 가져오기
            trading_companies = get_currently_trading_companies()
            
            corps = {}
            for company in root.findall('list'):
                stock_code = company.findtext('stock_code')
                corp_name = company.findtext('corp_name')
                corp_code = company.findtext('corp_code')
                
                # 현재 거래 가능한 기업만 포함
                if stock_code and stock_code.strip() and corp_name in trading_companies:
                    # KOSPI와 KOSDAQ 시장을 직접 확인
                    if stock_code in stock.get_market_ticker_list(market="KOSPI"):
                        market = "KOSPI"
                    elif stock_code in stock.get_market_ticker_list(market="KOSDAQ"):
                        market = "KOSDAQ"
                    else:
                        market = "Unknown"  # 알 수 없는 경우

                    corps[corp_name] = {
                        "corp_code": corp_code,
                        "stock_code": stock_code,
                        "market": market
                    }
            
            if not os.path.exists('cache'):
                os.makedirs('cache')
            
            with open('cache/corp_info.json', 'w', encoding='utf-8') as f:
                json.dump(corps, f, ensure_ascii=False, indent=4)
            
        except Exception as e:
            QMessageBox.warning(self, '오류', f'오류가 발생했습니다: {str(e)}')
    
    def update_header_table(self, company_name, corps, current_price):
        corp_info = corps[company_name]
        
        # 재무 정보
        finance_info = corp_info.get('finance_info', {})
        bs_info = finance_info.get('재무상태표', {})
        is_info = finance_info.get('포괄손익계산서', {})
        
        # 자기주식 정보
        treasury_info = corp_info.get('treasury_stock', {})
        direct_treasury = treasury_info.get('직접취득', 0)
        trust_treasury = treasury_info.get('신탁계약취득', 0)
        other_treasury = treasury_info.get('기타취득', 0)
        
        # 계산
        self_treasury = direct_treasury + trust_treasury + other_treasury
        direct_other = direct_treasury + other_treasury
        direct_treasury_shares = direct_treasury * current_price
        trust_treasury_shares = trust_treasury * current_price
        other_treasury_shares = other_treasury * current_price
        direct_other_shares = direct_other * current_price
        self_treasury_shares = self_treasury * current_price
        
        # 재무제표 데이터 가져오기
        revenue = is_info.get('매출액', {}).get('당기', 0)
        operating_profit = is_info.get('영업이익', {}).get('당기', 0)
        net_income = is_info.get('당기순이익', {}).get('당기', 0)
        equity = bs_info.get('자본총계', {}).get('당기', 0)
        stock_amount = corp_info.get('stock_amount', 0)
        
        # 비율 계산
        opm = (operating_profit / revenue * 100) if revenue else 0
        eps = net_income / stock_amount if stock_amount else 0
        bps = equity / stock_amount if stock_amount else 0
        per = current_price / eps if eps else 0
        pbr = current_price / bps if bps else 0
        
        # 재무비율 분석 결과 계산
        profitability_result, profitability_details = self.calculate_profitability(is_info, bs_info, company_name)
        safety_result, safety_details = self.calculate_safety(bs_info, is_info, company_name)
        activity_result, activity_details = self.calculate_activity(is_info, bs_info, company_name)
        growth_result, growth_details = self.calculate_growth(is_info, company_name)
        
        # header_table에 데이터 입력
        row_data = [
            company_name,  # 기업명
            "KOSPI" if len(corp_info.get('stock_code', '')) == 6 else "KOSDAQ",  # 상장시장
            f"{current_price:,}원",  # 주가
            f"{direct_treasury_shares/100000000:.2f}억원",  # 직접취득 총액
            f"{other_treasury_shares/100000000:.2f}억원",  # 기타취득 총액
            f"{direct_other_shares/100000000:.2f}억원",  # 직접+기타 총액
            f"{trust_treasury_shares/100000000:.2f}억원",  # 신탁계약취득 총액
            f"{self_treasury_shares/100000000:.2f}억원",  # 자사주 총액
            f"-%",  # 취득가능지분율
            f"{revenue/100000000:,.0f}억원",  # 매출액
            f"{operating_profit/100000000:,.0f}억원({opm:.1f}%)",  # 영업이익(영업이익률)
            profitability_result,  # 수익성
            safety_result,  # 안전성
            activity_result,  # 활동성
            growth_result,  # 성장성
            f"{eps:,.0f}원",  # EPS
            f"{per:.2f}배",  # PER
            f"{bps:,.0f}원",  # BPS
            f"{pbr:.2f}배"  # PBR
        ]
        
        # header_table에 데이터 입력 및 가운데 정렬
        for col, value in enumerate(row_data):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            self.header_table.setItem(0, col, item)

        # header_table에 툴팁 설정
        profitability_item = QTableWidgetItem(profitability_result)
        profitability_item.setToolTip(profitability_details)
        profitability_item.setTextAlignment(Qt.AlignCenter)
        self.header_table.setItem(0, 11, profitability_item)
        
        safety_item = QTableWidgetItem(safety_result)
        safety_item.setToolTip(safety_details)
        safety_item.setTextAlignment(Qt.AlignCenter)
        self.header_table.setItem(0, 12, safety_item)
        
        activity_item = QTableWidgetItem(activity_result)
        activity_item.setToolTip(activity_details)
        activity_item.setTextAlignment(Qt.AlignCenter)
        self.header_table.setItem(0, 13, activity_item)
        
        growth_item = QTableWidgetItem(growth_result)
        growth_item.setToolTip(growth_details)
        growth_item.setTextAlignment(Qt.AlignCenter)
        self.header_table.setItem(0, 14, growth_item)

   
    def process_search_queue(self):
        """검색 대기열에서 하나씩 처리"""
        if not self.search_queue:
            self.search_timer.stop()
            print("모든 기업 검색 완료")
            return
        
        try:
            corp_name = self.search_queue.pop(0)  # 대기열에서 첫 번째 기업 가져오기
            print(f"검색 중: {corp_name} (남은 기업: {len(self.search_queue)}개)")
            
            self.search_input.setText(corp_name)
            self.search_company()
            

            
        except Exception as e:
            print(f"기업 검색 중 오류 발생: {str(e)}")
            if self.search_queue:
                return
            else:
                self.search_timer.stop()

    def closeEvent(self, event):
        """프로그램 종료 시 타이머 정리"""
        self.search_timer.stop()
        super().closeEvent(event)

    def calculate_profitability(self, is_info, bs_info, company_name):
        try:
            # 재무상태표(bs_info) 항목 가져오기
            total_liabilities = 0
            for key in bs_info.keys():
                if '부채총계' in key:
                    total_liabilities = bs_info[key].get('당기', 0)
                    break

            equity = 0
            for key in bs_info.keys():
                if '자기자본' in key or '자본총계' in key:
                    equity = bs_info[key].get('당기', 1)  # 0으로 나누는 것을 방지
                    break

            current_assets = 0
            for key in bs_info.keys():
                if '유동자산' in key:
                    current_assets = bs_info[key].get('당기', 0)
                    break

            current_liabilities = 0
            for key in bs_info.keys():
                if '유동부채' in key:
                    current_liabilities = bs_info[key].get('당기', 1)  # 0으로 나누는 것을 방지
                    break

            inventory = 0
            for key in bs_info.keys():
                if '재고자산' in key:
                    inventory = bs_info[key].get('당기', 0)
                    break

            # 손익계산서(is_info) 항목 가져오기
            operating_profit = 0
            for key in is_info.keys():
                if '영업이익' in key:
                    operating_profit = is_info[key].get('당기', 0)
                    break

            financial_cost = 0
            for key in is_info.keys():
                if '금융비용' in key or '이자비용' in key:
                    financial_cost = is_info[key].get('당기', 1)  # 0으로 나누는 것을 방지
                    break

            revenue = 0
            for key in is_info.keys():
                if '매출액' in key:
                    revenue = is_info[key].get('당기', 0)
                    break

            cost_of_sales = 0
            for key in is_info.keys():
                if '매출원가' in key:
                    cost_of_sales = is_info[key].get('당기', 0)
                    break

            total_assets = 0
            for key in bs_info.keys():
                if '자산총계' in key:
                    total_assets = bs_info[key].get('당기', 1)  # 0으로 나누는 것을 방지
                    break

            accounts_receivable = 0
            for key in bs_info.keys():
                if '매출채권' in key:
                    accounts_receivable = bs_info[key].get('당기', 1)  # 0으로 나누는 것을 방지
                    break

            # 성장성 지표를 위한 전기 데이터
            revenue_prev = 0
            for key in is_info.keys():
                if '매출액' in key:
                    revenue_prev = is_info[key].get('전기', 0)
                    break

            operating_profit_prev = 0
            for key in is_info.keys():
                if '영업이익' in key:
                    operating_profit_prev = is_info[key].get('전기', 0)
                    break

            net_income = 0
            for key in is_info.keys():
                if '당기순이익' in key or '당기순이익(손실)' in key:  # 당기순이익(손실)도 포함되도록 수정
                    net_income = is_info[key].get('당기', 0)
                    break

            net_income_prev = 0
            for key in is_info.keys():
                if '당기순이익' in key or '당기순손실' in key:  # 당기순이익(손실)도 포함되도록 수정
                    net_income_prev = is_info[key].get('전기', 0)
                    break

            # 수익성 비율 계산
            gpm = (cost_of_sales / revenue * 100) if revenue else 0  # 매출총이익률
            opm = (operating_profit / revenue * 100) if revenue else 0  # 영업이익률
            npm = (net_income / revenue * 100) if revenue else 0  # 순이익률
            roa = (net_income / total_assets * 100) if total_assets else 0  # ROA
            roe = (net_income / equity * 100) if equity else 0  # ROE
            
            
            
            # 각 지표 점수 계산
            def get_score(value, thresholds):
                if value > thresholds[0]: return 5  # 매우 좋음
                elif value > thresholds[1]: return 4  # 좋음
                elif value > thresholds[2]: return 3  # 보통
                elif value > thresholds[3]: return 2  # 나쁨
                else: return 1  # 매우 나쁨
            
            gpm_score = get_score(gpm, [50, 40, 30, 20])
            opm_score = get_score(opm, [20, 10, 5, 1])
            npm_score = get_score(npm, [15, 10, 5, 1])
            roa_score = get_score(roa, [10, 5, 2, 1])
            roe_score = get_score(roe, [20, 10, 5, 1])
            
            # 평균 점수 계산 및 등급 결정
            avg_score = (gpm_score + opm_score + npm_score + roa_score + roe_score) / 5
            avg_score = math.ceil(avg_score)  # 소수점 올림
            
            profitability_grade = {
                5: "매우좋음",
                4: "좋음",
                3: "보통",
                2: "나쁨",
                1: "매우나쁨"
            }[avg_score]
            
            # 수익성 지표 계산 결과를 툴팁으로 표시하기 위한 상세 정보 생성
            profitability_details = (
                f"<div style='background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc; border-radius: 5px;'>"
                f"<div style='color: #2c3e50; font-weight: bold; margin-bottom: 5px;'>[{company_name}]</div>"
                f"<div style='color: #34495e;'>"
                f"<div>매출총이익률: <span style='color: #e74c3c;'>{gpm:.2f}%</span></div>"
                f"<div>영업이익률: <span style='color: #e74c3c;'>{opm:.2f}%</span></div>"
                f"<div>순이익률: <span style='color: #e74c3c;'>{npm:.2f}%</span></div>"
                f"<div>총자산이익률(ROA): <span style='color: #e74c3c;'>{roa:.2f}%</span></div>"
                f"<div>자기자본이익률(ROE): <span style='color: #e74c3c;'>{roe:.2f}%</span></div>"
                f"</div></div>"
            )
            
            profitability_grade = f"{profitability_grade}"
            return profitability_grade, profitability_details
        except Exception as e:
            print(f"{company_name} 수익성 지표 계산 중 오류 발생: {str(e)}")
            return "계산불가", ""

    def calculate_safety(self, bs_info, is_info, company_name):
        try:
            # 재무상태표 항목 가져오기
            total_liabilities = bs_info.get('부채총계', {}).get('당기', 0)
            equity = bs_info.get('자기자본', {}).get('당기', 1)  # 0으로 나누는 것을 방지
            current_assets = bs_info.get('유동자산', {}).get('당기', 0)
            current_liabilities = bs_info.get('유동부채', {}).get('당기', 1)  # 0으로 나누는 것을 방지
            inventory = bs_info.get('재고자산', {}).get('당기', 0)
            
            # 손익계산서 항목 가져오기
            operating_profit = is_info.get('영업이익', {}).get('당기', 0)
            financial_cost = is_info.get('금융비용', {}).get('당기', 1)  # 0으로 나누는 것을 방지
            
            # 안전성 비율 계산
            debt_ratio = (total_liabilities / equity * 100) if equity else 0  # 부채비율
            current_ratio = (current_assets / current_liabilities * 100) if current_liabilities else 0  # 유동비율
            quick_ratio = ((current_assets - inventory) / current_liabilities * 100) if current_liabilities else 0  # 당좌비율
            interest_coverage = (operating_profit / financial_cost) if financial_cost else 0  # 이자보상배율
            
            # 각 지표 점수 계산
            def get_safety_score(value, thresholds, reverse=False):
                if reverse:
                    if value < thresholds[0]: return 5  # 매우 좋음
                    elif value < thresholds[1]: return 4  # 좋음
                    elif value < thresholds[2]: return 3  # 보통
                    elif value < thresholds[3]: return 2  # 나쁨
                    else: return 1  # 매우 나쁨
                else:
                    if value > thresholds[0]: return 5  # 매우 좋음
                    elif value > thresholds[1]: return 4  # 좋음
                    elif value > thresholds[2]: return 3  # 보통
                    elif value > thresholds[3]: return 2  # 나쁨
                    else: return 1  # 매우 나쁨
            
            debt_score = get_safety_score(debt_ratio, [50, 100, 150, 200], reverse=True)
            current_score = get_safety_score(current_ratio, [200, 150, 100, 50])
            quick_score = get_safety_score(quick_ratio, [150, 100, 70, 50])
            interest_score = get_safety_score(interest_coverage, [10, 5, 2, 1])
            
            # 평균 점수 계산 및 등급 결정
            avg_score = (debt_score + current_score + quick_score + interest_score) / 4
            avg_score = math.ceil(avg_score)  # 소수점 올림
            
            safety_grade = {
                5: "매우좋음",
                4: "좋음",
                3: "보통",
                2: "나쁨",
                1: "매우나쁨"
            }[avg_score]
            
            # 안전성 지표 계산 결과를 툴팁으로 표시하기 위한 상세 정보 생성
            safety_details = (
                f"<div style='background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc; border-radius: 5px;'>"
                f"<div style='color: #2c3e50; font-weight: bold; margin-bottom: 5px;'>[{company_name}]</div>"
                f"<div style='color: #34495e;'>"
                f"<div>부채비율: <span style='color: #e74c3c;'>{debt_ratio:.2f}%</span></div>"
                f"<div>유동비율: <span style='color: #e74c3c;'>{current_ratio:.2f}%</span></div>"
                f"<div>당좌비율: <span style='color: #e74c3c;'>{quick_ratio:.2f}%</span></div>"
                f"<div>이자보상배율: <span style='color: #e74c3c;'>{interest_coverage:.2f}배</span></div>"
                f"</div></div>"
            )
            
            safety_grade = f"{safety_grade}"
            return safety_grade, safety_details
        except Exception as e:
            print(f"{company_name} 안전성 지표 계산 중 오류 발생: {str(e)}")
            return "계산불가", ""

    def calculate_activity(self, is_info, bs_info, company_name):
        try:
            # 손익계산서 항목 가져오기
            revenue = is_info.get('매출액', {}).get('당기', 0)
            cost_of_sales = is_info.get('매출원가', {}).get('당기', 0)
            
            # 재무상태표 항목 가져오기
            total_assets = bs_info.get('자산총계', {}).get('당기', 1)  # 0으로 나누는 것을 방지
            accounts_receivable = bs_info.get('매출채권및기타채권', {}).get('당기', 1)  # 0으로 나누는 것을 방지
            inventory = bs_info.get('재고자산', {}).get('당기', 1)  # 0으로 나누는 것을 방지
            
            # 활동성 비율 계산
            asset_turnover = revenue / total_assets if total_assets else 0  # 총자산회전율
            receivable_turnover = revenue / accounts_receivable if accounts_receivable else 0  # 매출채권회전율
            inventory_turnover = cost_of_sales / inventory if inventory else 0  # 재고자산회전율
            
            
            
            # 각 지표 점수 계산
            def get_activity_score(value, thresholds):
                if value > thresholds[0]: return 5  # 매우 좋음
                elif value > thresholds[1]: return 4  # 좋음
                elif value > thresholds[2]: return 3  # 보통
                elif value > thresholds[3]: return 2  # 나쁨
                else: return 1  # 매우 나쁨
            
            asset_score = get_activity_score(asset_turnover, [1.5, 1.0, 0.5, 0.3])
            receivable_score = get_activity_score(receivable_turnover, [12, 6, 4, 2])
            inventory_score = get_activity_score(inventory_turnover, [8, 5, 3, 2])
            
            # 평균 점수 계산 및 등급 결정
            avg_score = (asset_score + receivable_score + inventory_score) / 3
            avg_score = math.ceil(avg_score)  # 소수점 올림
            
            activity_grade = {
                5: "매우좋음",
                4: "좋음",
                3: "보통",
                2: "나쁨",
                1: "매우나쁨"
            }[avg_score]
            
            # 활동성 지표 계산 결과를 툴팁으로 표시하기 위한 상세 정보 생성
            activity_details = (
                f"<div style='background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc; border-radius: 5px;'>"
                f"<div style='color: #2c3e50; font-weight: bold; margin-bottom: 5px;'>[{company_name}]</div>"
                f"<div style='color: #34495e;'>"
                f"<div>총자산회전율: <span style='color: #e74c3c;'>{asset_turnover:.2f}회</span></div>"
                f"<div>매출채권회전율: <span style='color: #e74c3c;'>{receivable_turnover:.2f}회</span></div>"
                f"<div>재고자산회전율: <span style='color: #e74c3c;'>{inventory_turnover:.2f}회</span></div>"
                f"</div></div>"
            )
            
            activity_grade = f"{activity_grade}"
            return activity_grade, activity_details
        except Exception as e:
            print(f"{company_name} 활동성 지표 계산 중 오류 발생: {str(e)}")
            return "계산불가", ""

    def calculate_growth(self, is_info, company_name):
        try:
            # 손익계산서 항목 가져오기 (당기/전기)
            revenue_current = is_info.get('매출액', {}).get('당기', 0)
            revenue_prev = is_info.get('매출액', {}).get('전기', 0)
            
            operating_profit_current = is_info.get('영업이익', {}).get('당기', 0)
            operating_profit_prev = is_info.get('영업이익', {}).get('전기', 0)
            
            net_income_current = is_info.get('당기순이익', {}).get('당기', 0)
            net_income_prev = is_info.get('당기순이익', {}).get('전기', 0)
            
            # 증가율 계산
            def calculate_growth_rate(current, prev):
                if prev and prev != 0:  # 전기 값이 존재하고 0이 아닌 경우
                    return ((current - prev) / abs(prev)) * 100  # abs를 사용하여 음수 처리
                return 0
            
            revenue_growth = calculate_growth_rate(revenue_current, revenue_prev)
            operating_profit_growth = calculate_growth_rate(operating_profit_current, operating_profit_prev)
            net_income_growth = calculate_growth_rate(net_income_current, net_income_prev)
            
            
            
            # 각 지표 점수 계산
            def get_growth_score(value):
                if value > 20: return 5  # 매우 좋음
                elif value > 10: return 4  # 좋음
                elif value > 5: return 3  # 보통
                elif value > 0: return 2  # 나쁨
                else: return 1  # 매우 나쁨
            
            revenue_score = get_growth_score(revenue_growth)
            operating_profit_score = get_growth_score(operating_profit_growth)
            net_income_score = get_growth_score(net_income_growth)
            
            # 평균 점수 계산 및 등급 결정
            avg_score = (revenue_score + operating_profit_score + net_income_score) / 3
            avg_score = math.ceil(avg_score)  # 소수점 올림
            
            growth_grade = {
                5: "매우좋음",
                4: "좋음",
                3: "보통",
                2: "나쁨",
                1: "매우나쁨"
            }[avg_score]
            
            # 성장성 지표 계산 결과를 툴팁으로 표시하기 위한 상세 정보 생성
            growth_details = (
                f"<div style='background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc; border-radius: 5px;'>"
                f"<div style='color: #2c3e50; font-weight: bold; margin-bottom: 5px;'>[{company_name}]</div>"
                f"<div style='color: #34495e;'>"
                f"<div>매출액증가율: <span style='color: #e74c3c;'>{revenue_growth:.2f}%</span></div>"
                f"<div>영업이익증가율: <span style='color: #e74c3c;'>{operating_profit_growth:.2f}%</span></div>"
                f"<div>순이익증가율: <span style='color: #e74c3c;'>{net_income_growth:.2f}%</span></div>"
                f"</div></div>"
            )
            
            growth_grade = f"{growth_grade}"
            return growth_grade, growth_details
        except Exception as e:
            print(f"{company_name} 성장성 지표 계산 중 오류 발생: {str(e)}")
            return "계산불가", ""
