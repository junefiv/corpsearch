import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QWidget, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QListWidget, QDialog, QStackedWidget, QLabel, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QHBoxLayout
from pykrx import stock
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QMetaType, QMetaObject, Q_ARG, QTextCodec
from PyQt5.QtGui import QColor, QFont, QFontMetrics
import threading
import time
from queue import Queue
import math
import typing
import re
import traceback
import tempfile

if not os.path.exists('logs'):
    os.makedirs('logs')

def get_cache_dir():
    try:
        if getattr(sys, 'frozen', False):
            # exe 실행 시에는 실행 파일이 있는 디렉토리의 cache 폴더 사용
            base_dir = os.path.dirname(sys.executable)
        else:
            # 일반 파이썬 실행 시에는 스크립트 파일이 있는 디렉토리의 cache 폴더 사용
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        cache_dir = os.path.join(base_dir, 'cache')
        
        # 캐시 디렉토리가 없으면 생성
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            
        return cache_dir
        
    except Exception as e:
        # 권한 문제 등으로 생성 실패 시 사용자 임시 디렉토리 사용
        temp_cache_dir = os.path.join(tempfile.gettempdir(), 'searchbot_cache')
        if not os.path.exists(temp_cache_dir):
            os.makedirs(temp_cache_dir)
        return temp_cache_dir

# 2. 캐시 디렉토리 생성
cache_dir = get_cache_dir()
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

# 3. 캐시 파일 경로 설정
cache_file = os.path.join(get_cache_dir(), 'corp_info.json')

DART_API_KEY = '91226718b5a46f417a86d2cf0c0c16df49ecc36c'


# STANDARD_TABLE 스타일 정의
STANDARD_TABLE = """
    QTableWidget {
        background-color: white;
        alternate-background-color: #f5f5f5ㄷ;
        selection-background-color: #0078d7;ㄴㄴㄴㄴ
        selection-color: white;
        border: 1px solid #d3d3d3;
        gridline-color: #d3d3d3;
    }
    QTableWidget::item {
        padding: 5px;
    }
"""
class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, text):
        super().__init__(text)
    def __lt__(self, other):
        def parse(text):
            try:
                # 쉼표 제거
                text = text.replace(',', '')
                # 정규표현식을 사용하여 숫자(정수 또는 실수)를 추출
                match = re.search(r"[-+]?[0-9]*\.?[0-9]+", text)
                if match:
                    return float(match.group())
                else:
                    return 0.0
            except ValueError:
                return 0.0
        self_val = parse(self.text())
        other_val = parse(other.text())
        return self_val < other_val

# 숫자 변환 헬퍼 함수 수정
def convert_to_int(value):
    if isinstance(value, (int, float)):
        return int(value)
    if value is None or value == '' or value == '-' or value == '보통주' or value == '우선주':
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
    if value is None or value == '' or value == '-' or value == '보통주' or value == '우선주':
        return 0.0
    try:
        return float(str(value).replace(',', ''))
    except ValueError:
        print(f"Warning: 숫자 변환 실패 - '{value}'")
        return 0.0

class DataCollector:
    def __init__(self, api_key):
        self.api_key = api_key

    def collect_company_data(self, company_name, corp_code, existing_corp_info, missing_fields):
        """기업 데이터 수집을 위한 공통 로직"""
        try:
            print(f"\n=== {company_name} 데이터 수집 시작 ===")
            found_valid_data = False
            
            # corp_info 필드 체크 로직 수정
            if "corp_info" in missing_fields or not all(field in existing_corp_info[company_name].get("corp_info", {}) 
                for field in ["corp_code", "ceo_nm", "jurir_no", "bizr_no", "adres", "hm_url", "est_dt", "induty_code"]):
                print(f"\n[{company_name} - 기업 정보]")
                # 기존 corp_info 데이터 보존
                existing_corp_info_data = existing_corp_info[company_name].get("corp_info", {})
                
                company_info_url = "https://opendart.fss.or.kr/api/company.json"
                company_params = {
                    'crtfc_key': self.api_key,
                    'corp_code': corp_code
                }
                company_response = requests.get(company_info_url, params=company_params)
                if company_response.status_code == 200:
                    company_data = company_response.json()
                    if company_data['status'] == '000':
                        # 기존 데이터와 새로운 데이터 병합
                        existing_corp_info_data.update({
                            "corp_code": corp_code,
                            "ceo_nm": company_data.get("ceo_nm"),
                            "jurir_no": company_data.get("jurir_no"),
                            "bizr_no": company_data.get("bizr_no"),
                            "adres": company_data.get("adres"),
                            "hm_url": company_data.get("hm_url"),
                            "est_dt": company_data.get("est_dt"),
                            "induty_code": company_data.get("induty_code")
                        })
                        # 업데이트된 데이터 저장
                        existing_corp_info[company_name]["corp_info"] = existing_corp_info_data
                        print(f"기업 정보 저장 완료: {existing_corp_info[company_name]['corp_info']}")
            
            if "treasury_info" in missing_fields:
                print(f"\n[{company_name} - 자사주 현황]")
                found_data = False
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
                    if found_data:
                        break
                        
                    print(f"- {year}년 {reprt_code} 보고서 조회 중...")
                    tesstk_url = "https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json"
                    tesstk_params = {
                        'crtfc_key': self.api_key,
                        'corp_code': corp_code,
                        'bsns_year': str(year),
                        'reprt_code': reprt_code
                    }
                    
                    tesstk_response = requests.get(tesstk_url, params=tesstk_params)
                    if tesstk_response.status_code == 200:
                        tesstk_data = tesstk_response.json()
                        if tesstk_data['status'] == '000' and tesstk_data.get('list'):
                            treasury_info = {}
                            has_data = False
                            
                            # 실제 보유량 집계
                            for item in tesstk_data.get('list', []):
                                acqs_mth2 = item.get('acqs_mth2')
                                stock_knd = item.get('stock_knd')
                                qty = convert_to_int(item.get('trmend_qy', '0'))
                                
                                # 유효한 데이터인 경우에만 처리
                                if acqs_mth2 not in ['-', None] and stock_knd not in ['-', None]:
                                    has_data = True
                                    if acqs_mth2 not in treasury_info:
                                        treasury_info[acqs_mth2] = {}
                                    treasury_info[acqs_mth2][stock_knd] = qty
                            
                            if has_data:
                                existing_corp_info[company_name]["treasury_info"] = treasury_info
                                found_valid_data = True
                                print(f"{year}년 {reprt_code} 보고서에서 자기주식 정보를 찾았습니다.")
                                break
            
            if not found_valid_data:
                print("모든 보고서에서 자기주식 정보를 찾지 못했습니다.")
                existing_corp_info[company_name]["treasury_info"] = {
                    "직접취득": {"보통주": 0, "우선주": 0},
                    "신탁계약에 의한취득": {"보통주": 0, "우선주": 0},
                    "기타취득": {"보통주": 0, "우선주": 0},
                    "총계": {"보통주": 0, "우선주": 0}
                }

            if "shareholder_list" in missing_fields:
                print(f"\n[{company_name} - 최대주주주 현황]")
                found_data = False
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
                    if found_data:
                        break
                        
             
                    print(f"- {year}년 {reprt_code} 보고서 조회 중...")
                    hyslr_url = "https://opendart.fss.or.kr/api/hyslrSttus.json"
                    hyslr_params = {
                        'crtfc_key': self.api_key,
                        'corp_code': corp_code,
                        'bsns_year': str(year),
                        'reprt_code': reprt_code
                    }
                    
                    try:
                        hyslr_response = requests.get(hyslr_url, params=hyslr_params)
                        if hyslr_response.status_code == 200:
                            hyslr_data = hyslr_response.json()
                            if hyslr_data['status'] == '000' and hyslr_data.get('list'):
                                shareholder_list = []
                                has_valid_data = False
                                
                                for item in hyslr_data['list']:
                                    # 필수 필드가 모두 있는지 확인
                                    if all(item.get(field) is not None for field in ['nm', 'relate', 'trmend_posesn_stock_co', 'trmend_posesn_stock_qota_rt']):
                                        has_valid_data = True
                                        nm = item.get('nm', 'N/A')
                                        
                                        # 주주별로 데이터 통합
                                        existing_shareholder = next((s for s in shareholder_list if s['nm'] == nm), None)
                                        if existing_shareholder:
                                            # 기존 주주의 경우 주식수와 지분율 합산
                                            existing_shareholder['trmend_posesn_stock_co'] += convert_to_int(item.get('trmend_posesn_stock_co', '0'))
                                            existing_shareholder['trmend_posesn_stock_qota_rt'] += convert_to_float(item.get('trmend_posesn_stock_qota_rt', '0'))
                                        else:
                                            # 새로운 주주 추가
                                            shareholder_info = {
                                                'nm': nm,
                                                'relate': item.get('relate', 'N/A'),
                                                'trmend_posesn_stock_co': convert_to_int(item.get('trmend_posesn_stock_co', '0')),
                                                'trmend_posesn_stock_qota_rt': convert_to_float(item.get('trmend_posesn_stock_qota_rt', '0'))
                                            }
                                            shareholder_list.append(shareholder_info)
                                
                                if has_valid_data:
                                    print(f"- {year}년 {reprt_code} 보고서에서 주주 정보를 찾았습니다.")
                                    existing_corp_info[company_name]["shareholder_list"] = shareholder_list
                                    found_data = True
                                    break
                                else:
                                    print(f"- {year}년 {reprt_code} 보고서에 유효한 주주 정보가 없습니다.")
                    except Exception as e:
                        print(f"- API 호출 중 오류 발생: {str(e)}")
                        continue
            
            if not found_data:
                print("- 모든 보고서에서 주주 정보를 찾지 못했습니다.")
                existing_corp_info[company_name]["shareholder_list"] = []

            if "issued_share" in missing_fields:
                print(f"\n[{company_name} - 총주식 발행 현황]")
                found_valid_data = False
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
                    if found_valid_data:
                        break
                        
                    print(f"- {year}년 {reprt_code} 보고서 조회 중...")
                    stockTotqySttus_url = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
                    stockTotqySttus_params = {
                        'crtfc_key': self.api_key,
                        'corp_code': corp_code,
                        'bsns_year': str(year),
                        'reprt_code': reprt_code
                    }
                    
                    try:
                        stockTotqySttus_response = requests.get(stockTotqySttus_url, params=stockTotqySttus_params)
                        if stockTotqySttus_response.status_code == 200:
                            stockTotqySttus_data = stockTotqySttus_response.json()
                            if stockTotqySttus_data['status'] == '000' and stockTotqySttus_data.get('list'):
                                issued_share = {}
                                total_istc_totqy = 0
                                
                                for item in stockTotqySttus_data['list']:
                                    se = item.get('se', 'N/A')
                                    if se == '합계':  # API에 이미 존재하는 합계 행이면 건너뛰기
                                        continue
                                    istc_totqy = item.get('istc_totqy', '0')
                                    tesstk_co = item.get('tesstk_co', '0')
                                    distb_stock_co = item.get('distb_stock_co', '0')
                                    
                                    # '-' 값을 '0'으로 변환
                                    istc_totqy = '0' if istc_totqy == '-' else istc_totqy
                                    tesstk_co = '0' if tesstk_co == '-' else tesstk_co
                                    distb_stock_co = '0' if distb_stock_co == '-' else distb_stock_co
                                    
                                    converted_istc_totqy = convert_to_int(istc_totqy)
                                    total_istc_totqy += converted_istc_totqy
                                    
                                    if se not in issued_share:
                                        issued_share[se] = {}
                                    
                                    issued_share[se].update({
                                        'istc_totqy': converted_istc_totqy,
                                        'tesstk_co': convert_to_int(tesstk_co),
                                        'distb_stock_co': convert_to_int(distb_stock_co)
                                    })
                                
                                # 발행주식 총수가 0이 아닌 경우에만 데이터로 인정
                                if total_istc_totqy > 0:
                                    # 합계 데이터 추가
                                    issued_share['합계'] = {
                                        'istc_totqy': total_istc_totqy,
                                        'tesstk_co': sum(data.get('tesstk_co', 0) for key, data in issued_share.items() if key != '합계'),
                                        'distb_stock_co': sum(data.get('distb_stock_co', 0) for key, data in issued_share.items() if key != '합계')
                                    }
                                    existing_corp_info[company_name]["issued_share"] = issued_share
                                    found_valid_data = True
                                    print(f"- {year}년 {reprt_code} 보고서에서 유효한 발행주식 정보를 찾았습니다.")
                                    print(f"- 발행주식 총수: {total_istc_totqy:,}주")
                                    break
                                else:
                                    print(f"- {year}년 {reprt_code} 보고서의 발행주식 총수가 0입니다. 다음 보고서 확인...")
                                
                    except Exception as e:
                        print(f"- API 호출 중 오류 발생: {str(e)}")
                        continue
                        
                    if found_valid_data:
                        break
            
            if not found_valid_data:
                print("- 모든 보고서에서 유효한 발행주식 정보를 찾지 못했습니다.")
                existing_corp_info[company_name]["issued_share"] = {
                    "보통주": {
                        "istc_totqy": 0,
                        "tesstk_co": 0,
                        "distb_stock_co": 0
                    },
                    "합계": {
                        "istc_totqy": 0,
                        "tesstk_co": 0,
                        "distb_stock_co": 0
                    }
                }

            if "contribution_info" in missing_fields:
                print(f"\n[{company_name} - 출자 현황]")
                found_data = False
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
                    if found_data:
                        break
                        
                   
                    print(f"- {year}년 {reprt_code} 보고서 조회 중...")
                    otrCprInvstmntSttus_url = "https://opendart.fss.or.kr/api/otrCprInvstmntSttus.json"
                    otrCprInvstmntSttus_params = {
                        'crtfc_key': self.api_key,
                        'corp_code': corp_code,
                        'bsns_year': str(year),
                        'reprt_code': reprt_code
                    }
                    
                    try:
                        otrCprInvstmntSttus_response = requests.get(otrCprInvstmntSttus_url, params=otrCprInvstmntSttus_params)
                        if otrCprInvstmntSttus_response.status_code == 200:
                            otrCprInvstmntSttus_data = otrCprInvstmntSttus_response.json()
                            if otrCprInvstmntSttus_data['status'] == '000' and otrCprInvstmntSttus_data.get('list'):
                                contribution_info = []
                                has_valid_data = False
                                
                                for item in otrCprInvstmntSttus_data['list']:
                                    # 필수 필드가 모두 있는지 확인
                                    if all(item.get(field) not in [None, '-'] for field in ['inv_prm', 'invstmnt_purps', 'trmend_blce_qota_rt']):
                                        has_valid_data = True
                                        contribution = {
                                            'inv_prm': item.get('inv_prm', 'N/A'),
                                            'invstmnt_purps': item.get('invstmnt_purps', 'N/A'),
                                            'trmend_blce_qota_rt': convert_to_float(item.get('trmend_blce_qota_rt', '0'))
                                        }
                                        contribution_info.append(contribution)
                                
                                if has_valid_data:
                                    print(f"- {year}년 {reprt_code} 보고서에서 출자 정보를 찾았습니다.")
                                    existing_corp_info[company_name]["contribution_info"] = contribution_info
                                    found_data = True
                                    break
                                else:
                                    print(f"- {year}년 {reprt_code} 보고서에 유효한 출자 정보가 없습니다.")
                    except Exception as e:
                        print(f"- API 호출 중 오류 발생: {str(e)}")
                        continue
            
            if not found_data:
                print("- 모든 보고서에서 출자 정보를 찾지 못했습니다.")
                existing_corp_info[company_name]["contribution_info"] = []

            if "financial_info" in missing_fields:
                print(f"\n[{company_name} - 재무제표 정보]")
                print("- API: /api/fnlttSinglAcntAll.json")
                print("- 사업보고서만 참고")
                found_data = False
                current_year = datetime.now().year
                for year in range(current_year-1, current_year-4, -1):
                    if found_data:
                        break
                    print(f"- {year}년 사업보고서 조회 중...")
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
                            print(f"- {year}년 사업보고서 데이터 찾음")
                            financial_info = {
                                "BS": [], 
                                "CIS": [],
                                "IS": [],
                                "CF": [],
                            }
                            for item in fnlttSinglAcnt_data['list']:
                                financial_item = {
                                    'account_id': item.get('account_id'),
                                    'thstrm_amount': convert_to_int(item.get('thstrm_amount')),
                                    'currency': 'KRW'
                                }
                                if item.get('sj_div') == 'BS':
                                    financial_item['frmtrm_amount'] = convert_to_int(item.get('frmtrm_amount'))
                                    financial_info["BS"].append(financial_item)           
                                elif item.get('sj_div') == 'CIS':
                                    financial_item['frmtrm_amount'] = convert_to_int(item.get('frmtrm_amount'))
                                    financial_info["CIS"].append(financial_item)
                                elif item.get('sj_div') == 'IS':
                                    financial_item['frmtrm_amount'] = convert_to_int(item.get('frmtrm_amount'))
                                    financial_info["IS"].append(financial_item)
                                elif item.get('sj_div') == 'CF':
                                    financial_item['frmtrm_amount'] = convert_to_int(item.get('frmtrm_amount'))
                                    financial_info["CF"].append(financial_item)

                        
                            if any(financial_info.values()):
                                existing_corp_info[company_name]["financial_info"] = financial_info
                                found_data = True
                                break

            print(f"\n=== {company_name} 데이터 수집 완료 ===\n")
            return True
        except Exception as e:
            print(f"Error collecting data for {company_name}: {str(e)}")
            return False

    def _get_latest_regular_disclosure(self, corp_code, reprt_code):
        current_year = datetime.now().year
        current_month = datetime.now().month

        report_years = range(current_year-1, current_year-4, -1)
        report_codes = ['11011', '11013', '11012', '11014']

        for year in report_years:
            url = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={self.api_key}&corp_code={corp_code}&bgn_de={year}0101&end_de={year}1231&pblntf_ty=A&sort=date&sort_mth=desc&page_no=1&page_count=100"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == '000' and data['list']:
                    for report in data['list']:
                        report_type = {
                            '11011': '사업보고서',
                            '11013': '1분기보고서',
                            '11012': '반기보고서',
                            '11014': '3분기보고서'
                        }
                        if report_type[reprt_code] in report['report_nm']:
                            print(f"{year}년 {report_type[reprt_code]} 찾음: {report['report_nm']}")
                            return report
            else:
                print(f"{year}년 {reprt_code} API 요청 실패")
        
        print("사용 가능한 보고서를 찾지 못했습니다")
        return None

class DataCollectorThread(QThread):
    progress = pyqtSignal(int, int)
    data_processed = pyqtSignal(str, dict)

    def __init__(self, search_term, existing_corp_info, company_codes, api_key, result_widget, parent=None):
        super().__init__(parent)
        self.search_term = search_term
        self.existing_corp_info = existing_corp_info
        self.company_codes = company_codes
        self.api_key = api_key
        self.result_widget = result_widget
        self.processed = 0
        self.total_companies = len(existing_corp_info)
        self.required_fields = [
            "corp_info",
            "treasury_info",
            "shareholder_list",
            "issued_share",
            "financial_info",
            "contribution_info"
        ]

    def run(self):
        collector = DataCollector(self.api_key)
        
        # 캐시된 기업과 미캐시된 기업 분리
        cached_companies = [name for name in self.existing_corp_info.keys() 
                           if name != 'timestamp' and  # timestamp 키 제외
                           all(field in self.existing_corp_info[name] and self.existing_corp_info[name][field] 
                               for field in self.required_fields)]
        
        uncached_companies = [name for name in self.existing_corp_info.keys()
                            if name != self.search_term and
                            name not in cached_companies]
        
        # 캐시된 데이터 먼저 표시
        for company_name in sorted(cached_companies):
            print(f"\n캐시된 데이터 로드: {company_name}")
            self.data_processed.emit(company_name, self.existing_corp_info[company_name])
            self._update_progress(company_name)
        
        # 새로운 데이터 수집 및 표시
        for company_name in sorted(uncached_companies):
            # company_codes에 해당 기업이 있는지 확인
            if company_name not in self.company_codes:
                print(f"회사 코드를 찾을 수 없음: {company_name}")
                continue
                
            missing_fields = self._get_missing_fields(company_name)
            if missing_fields:
                print(f"\n새로운 데이터 수집 시작: {company_name}")
                print(f"수집할 필드: {missing_fields}")
                
                # 기업 정보가 없는 경우 기본 구조 초기화
                if company_name not in self.existing_corp_info:
                    self.existing_corp_info[company_name] = {
                        "corp_info": {},
                        "treasury_info": {},
                        "shareholder_list": [],
                        "issued_share": {},
                        "financial_info": {},
                        "contribution_info": []
                    }
                
                # 데이터 수집
                success = collector.collect_company_data(
                    company_name,
                    self.company_codes[company_name]['corp_code'],
                    self.existing_corp_info,
                    missing_fields
                )
                
                if success:
                    print(f"{company_name} 데이터 수집 성공")
                    self.data_processed.emit(company_name, self.existing_corp_info[company_name])
                else:
                    print(f"{company_name} 데이터 수집 실패")
            
            self._update_progress(company_name)
            time.sleep(0.1)  # API 호출 간격 조절

    def _get_missing_fields(self, company_name):
        missing_fields = []
        company_data = self.existing_corp_info.get(company_name, {})
        
        for field in self.required_fields:
            if field not in company_data or not company_data[field]:
                missing_fields.append(field)
                print(f"{company_name}의 {field} 필드 누락")
        
        return missing_fields

    def _update_progress(self, company_name):
        self.processed += 1
        self.progress.emit(self.processed, self.total_companies)
        
       
        cache_file = os.path.join(get_cache_dir(), 'corp_info.json')
        
        print(f"저장할 데이터: {self.existing_corp_info[company_name]}")
        
        try:
            # 현재 timestamp 가져오기
            current_timestamp = int(time.time())
            
            # 기존 캐시 파일이 있는 경우
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    
                # timestamp 확인
                if 'timestamp' in cached_data:
                    # 일주일(7일 = 604800초)이 지났는지 확인
                    if current_timestamp - cached_data['timestamp'] > 604800:
                        # 캐시 파일 삭제
                        os.remove(cache_file)
                        # 새로운 데이터와 timestamp 저장
                        self.existing_corp_info['timestamp'] = current_timestamp
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            json.dump(self.existing_corp_info, f, ensure_ascii=False, indent=4)
                    else:
                        # 일주일이 지나지 않았으면 기존 데이터 유지하고 company_name에 해당하는 데이터만 업데이트
                        cached_data[company_name] = self.existing_corp_info[company_name]
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            json.dump(cached_data, f, ensure_ascii=False, indent=4)
                else:
                    # timestamp가 없는 경우 새로 추가
                    self.existing_corp_info['timestamp'] = current_timestamp
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(self.existing_corp_info, f, ensure_ascii=False, indent=4)
            else:
                # 캐시 파일이 없는 경우 새로 생성
                self.existing_corp_info['timestamp'] = current_timestamp
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.existing_corp_info, f, ensure_ascii=False, indent=4)
                
            print(f"데이터 저장 완료: {cache_file}")
        except Exception as e:
            print(f"데이터 저장 중 오류 발생: {str(e)}")

class SearchApp(QWidget):
    # 시그널 정의 추가
    data_processed = pyqtSignal(str, dict)
    progress = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        # 한글 설정 추가
        QApplication.setStyle("Fusion")
        font = QApplication.font()
        font.setFamily("Malgun Gothic")  # 한글 폰트 설정
        QApplication.setFont(font)
        
        # 초기 윈도우 크기 설정 (카카오톡 PC 버전 크기와 유사하게)
   
        
        # company_codes 초기화
        self.company_codes = {}
        
        # DART API를 통해 기업 코드 정보 가져오기
        try:
            api_key = DART_API_KEY
            url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}"
            response = requests.get(url)
            
            if response.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(response.content))
                xml_data = z.read('CORPCODE.xml').decode('utf-8')
                root = ET.fromstring(xml_data)
                
                for company in root.findall('list'):
                    corp_name = company.findtext('corp_name')
                    corp_code = company.findtext('corp_code')
                    stock_code = company.findtext('stock_code')
                    if stock_code and stock_code.strip():  # stock_code가 있고 비어있지 않은 경우
                        self.company_codes[corp_name] = {'corp_code': corp_code, 'stock_code': stock_code}
                    else:
                        self.company_codes[corp_name] = {'corp_code': corp_code}
            else:
                print("기업 코드 정보를 가져오는데 실패했습니다.")
        except Exception as e:
            print(f"기업 코드 초기화 중 오류 발생: {str(e)}")
        
        self.initUI()
        self.stack = QStackedWidget()
        self.stack.addWidget(self)

        window_width = 400
        window_height = 600
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - window_width) // 2
        y = (screen.height() - window_height) // 2
        # 윈도우 최대화 설정
        self.stack.setGeometry(x, y, window_width, window_height)
        self.stack.show()
        
        self.progress_label = QLabel('', self)
        layout = self.layout()
        layout.addWidget(self.progress_label)
        
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
        # 메인 레이아웃
        layout = QVBoxLayout()
        
        # 중앙 정렬을 위한 여백 추가
        layout.addStretch()
        
        # 검색 위젯들을 담을 컨테이너
        search_container = QWidget()
        search_layout = QVBoxLayout(search_container)
        
        # 제목 라벨 생성 및 스타일 설정
        title_label = QLabel("자사주 스왑딜 대상기업 검색기")
        title_label.setAlignment(Qt.AlignCenter)
        font = title_label.font()
        font.setPointSize(14)  # 폰트 크기 설정
        font.setBold(True)     # 볼드체 설정
        title_label.setFont(font)
        search_layout.addWidget(title_label, alignment=Qt.AlignCenter)
        
        # 제목과 검색창 사이 간격 추가
        search_layout.addSpacing(50)  # 간격을 50으로 증가
        
        # 배경색 설정
        self.setStyleSheet
        
        # 검색창 생성 및 스타일 설정
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText('검색어를 입력하세요...')
        self.search_box.setFixedWidth(300)
        self.search_box.setFixedHeight(40)
        self.search_box.setStyleSheet("""
            QLineEdit {
                border: 2px solid #A0A0A0;
                border-radius: 20px;
                padding: 0 15px;
                background-color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #4A90E2;
                background-color: #FFFFFF;
            }
            QLineEdit::placeholder {
                color: #999999;
            }
        """)
        search_layout.addWidget(self.search_box, alignment=Qt.AlignCenter)

        # 검색 버튼 생성 및 스타일 설정
        search_button = QPushButton('검색')
        search_button.setFixedWidth(100)
        search_button.setFixedHeight(30)
        search_button.setStyleSheet("""
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
            QPushButton:pressed {
                background-color: #2E6DA4;
            }
        """)
        search_layout.addWidget(search_button, alignment=Qt.AlignCenter)

        # 검색 버튼 클릭 시 검색 함수 연결
        search_button.clicked.connect(self.perform_search)
        
        # 엔터 키 입력 시 검색 함수 연결
        self.search_box.returnPressed.connect(self.perform_search)

        # 컨테이너를 메인 레이아웃에 추가
        layout.addWidget(search_container, alignment=Qt.AlignCenter)
        
        # 하단 여백 추가
        layout.addStretch()

        self.setLayout(layout)

    def perform_search(self):
        search_term = self.search_box.text().strip()
        
        # 검색 실행 시 윈도우 최대화
        self.stack.showMaximized()
        
        # 캐시 파일 체크 및 로드
        cache_file = os.path.join(get_cache_dir(), 'corp_info.json')  # 수정된 부분
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    
                # timestamp 확인
                if 'timestamp' in cached_data:
                    current_timestamp = int(time.time())
                    timestamp = cached_data.pop('timestamp')  # timestamp 제거 후 저장
                    # 일주일이 지났는지 확인
                    if current_timestamp - timestamp > 604800:
                        # 캐시 파일 삭제
                        os.remove(cache_file)
                        self.existing_corp_info = {}
                    else:
                        # 캐시된 데이터 사용 (timestamp 제외)
                        self.existing_corp_info = cached_data
            except Exception as e:
                print(f"캐시 파일 로드 중 오류 발생: {str(e)}")
                self.existing_corp_info = {}
        
        # 한글 인코딩 처리
        try:
            search_term = search_term.encode('utf-8').decode('utf-8')
        except UnicodeEncodeError:
            QMessageBox.warning(self, '검색 오류', '올바른 회사명을 입력해주세요.')
            return
        
        if not search_term:
            QMessageBox.warning(self, '검색 오류', '회사명을 입력해주세요.')
            return
        
        # company_codes에서 키를 찾을 때 예외 처리
        try:
            corp_code = self.company_codes[search_term]['corp_code']
        except KeyError:
            QMessageBox.warning(self, '검색 오류', f'"{search_term}" 회사를 찾을 수 없습니다.')
            return
        
        print(f'검색어: {search_term}')

        # processed 변수 초기화 추가
        processed = 0
        total_companies = 1  # 현재는 한 회사만 처리하므로 1로 설정

        # 현재 연도 가져오기 추가
        current_year = datetime.now().year

        # 현재 스크립트 경로 가져오기
        cache_dir = get_cache_dir()  # get_cache_dir() 함수 사용
        cache_file = os.path.join(cache_dir, 'corp_info.json')
        


        # 기존 캐시 파일 읽기
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.existing_corp_info = json.load(f)
        except Exception as e:
            print(f"캐시 파일 로드 중 오류 발생: {str(e)}")
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

        collector = DataCollector(DART_API_KEY)
        if missing_fields:
            success = collector.collect_company_data(
                search_term, 
                corp_code, 
                self.existing_corp_info, 
                missing_fields
            )
            if not success:
                QMessageBox.warning(self, '오류', '데이터 수집 중 오류가 발생했습니다.')
                return

        result_widget = ResultWidget(search_term, self.existing_corp_info[search_term])
        self.stack.addWidget(result_widget)
        self.stack.setCurrentWidget(result_widget)

        QMetaType.type("int")
        
        self.collector_thread = DataCollectorThread(
            search_term,
            self.existing_corp_info,
            company_codes,
            DART_API_KEY,
            result_widget,
            self
        )
        
        result_widget.moveToThread(QApplication.instance().thread())
        
        self.collector_thread.progress.connect(result_widget.update_progress)
        self.collector_thread.data_processed.connect(result_widget.update_data_table)
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

    def get_latest_regular_disclosure(self, corp_code, reprt_code):
        api_key = DART_API_KEY
        current_year = datetime.now().year
        current_month = datetime.now().month

        # 보고서 코드: 사업보고서(11011), 반기보고서(11012), 1분기보고서(11013), 3분기보고서(11014)
        report_years = range(current_year-1, current_year-4, -1)  # 최근 3년
        report_codes = ['11011', '11013', '11012', '11014']  # 연간, 1분기, 반기, 3분기 순서

        for year in report_years:
            for reprt_code in report_codes:
                url = f"https://opendart.fss.or.kr/api/list.json?crtfc_key={api_key}&corp_code={corp_code}&bgn_de={year}0101&end_de={year}1231&pblntf_ty=A&sort=date&sort_mth=desc&page_no=1&page_count=100"
                response = requests.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == '000' and data['list']:
                        # 해당 연도의 보고서 찾기
                        for report in data['list']:
                            report_type = {
                                '11011': '사업보고서',
                                '11013': '1분기보고서',
                                '11012': '반기보고서',
                                '11014': '3분기보고서'
                            }
                            if report_type[reprt_code] in report['report_nm']:
                                print(f"{year}년 {report_type[reprt_code]} 찾음: {report['report_nm']}")
                                return report
                else:
                    print(f"{year}년 {reprt_code} API 요청 실패")
                
        print("사용 가능한 보고서를 찾지 못했습니다")
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
        if hasattr(self, 'progress_label'):
            self.progress_label.setText(f'데이터 수집 중... ({current}/{total})')
            if current >= total:
                self.progress_label.setText('데이터 수집 완료')

class ContributionDialog(QDialog):
    def __init__(self, contribution_info, company_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{company_name} 출자현황")
        self.setMinimumWidth(800)
        
        layout = QVBoxLayout()
        
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['출자회사명', '출자목적', '취득지분율(%)'])
        
        table.setStyleSheet(STANDARD_TABLE)
        table.horizontalHeader().setStyleSheet("QHeaderView::section { text-align: center; }")
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 데이터 처리
        table.setRowCount(len(contribution_info))
        
        for row, contribution in enumerate(contribution_info):
            for col, value in enumerate([
                str(contribution['inv_prm']),
                str(contribution['invstmnt_purps']),
                f"{contribution['trmend_blce_qota_rt']:.2f}"
            ]):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        self.setLayout(layout)

                
class CompanyInfoDialog(QDialog):
    def __init__(self, corp_info, company_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{company_name} 기업정보")
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout()
        
        # 정보 표시를 위한 테이블 위젯
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(['항목', '내용'])
        
        table.setStyleSheet(STANDARD_TABLE)
        table.horizontalHeader().setStyleSheet("QHeaderView::section { text-align: center; }")
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 표시할 정보 매핑
        info_mapping = {
            '시장': 'market',
            '종목코드': 'stock_code',
            '법인코드': 'corp_code',
            '대표이사': 'ceo_nm',
            '법인등록번호': 'jurir_no',
            '사업자등록번호': 'bizr_no',
            '주소': 'adres',
            '홈페이지': 'hm_url',
            '설립일': 'est_dt',
            '업종코드': 'induty_code'
        }
        
        # 데이터 채우기
        table.setRowCount(len(info_mapping))
        for row, (label, key) in enumerate(info_mapping.items()):
            # 항목 열
            item_label = QTableWidgetItem(label)
            item_label.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, item_label)
            
            # 내용 열
            value = corp_info.get(key, 'N/A')
            if key == 'hm_url' and value != 'N/A':
                # URL인 경우 클릭 가능한 링크로 생성
                link_label = QLabel()
                link_label.setText(f'<a href="http://{value}">{value}</a>')
                link_label.setOpenExternalLinks(True)
                link_label.setAlignment(Qt.AlignCenter)
                table.setCellWidget(row, 1, link_label)
            else:
                # 일반 텍스트인 경우
                if key == 'est_dt' and value != 'N/A':
                    # 설립일 형식 변경 (YYYYMMDD -> YYYY-MM-DD)
                    value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
                item_value = QTableWidgetItem(str(value))
                item_value.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, 1, item_value)
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        self.setLayout(layout)
        
class ShareholderDialog(QDialog):
    def __init__(self, shareholder_list, company_name, issued_total, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{company_name} 주주현황")
        self.setMinimumWidth(800)
        
        layout = QVBoxLayout()
        
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['주주명', '관계', '보유주식수', '지분율(%)'])
        
        table.setStyleSheet(STANDARD_TABLE)
        table.horizontalHeader().setStyleSheet("QHeaderView::section { text-align: center; }")
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 데이터 처리
        total_shares = 0
        total_ratio = 0.0
        processed_data = []
        
        for shareholder in shareholder_list:
            if not shareholder['nm'].endswith('계'):
                processed_data.append(shareholder)
                total_shares += shareholder['trmend_posesn_stock_co']
         
        
        # 데이터 채우기
        table.setRowCount(len(processed_data) + 1)  # +1 for total row
        for row, shareholder in enumerate(processed_data):
            computed_ratio = (shareholder['trmend_posesn_stock_co'] / issued_total) * 100 if issued_total else 0.0
            for col, value in enumerate([
                str(shareholder['nm']),
                str(shareholder['relate']),
                f"{shareholder['trmend_posesn_stock_co']:,}",
                f"{computed_ratio:.2f}"
            ]):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
        
        # 합계 행 추가
        total_row = len(processed_data)
        total_ratio = (total_shares / issued_total) * 100 if issued_total else 0.0
        for col, value in enumerate(['합계', '', f"{total_shares:,}", f"{total_ratio:.2f}"]):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(QColor('blue'))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            table.setItem(total_row, col, item)
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        self.setLayout(layout)

class TreasuryDialog(QDialog):
    def __init__(self, treasury_info, company_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{company_name} 자기주식 현황")
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout()
        
        table = QTableWidget()
        
        # 총계에서 주식 종류 가져오기
        stock_types = []
        if '총계' in treasury_info:
            stock_types = list(treasury_info['총계'].keys())
        
        # 테이블 컬럼 설정 (구분 + 주식종류 개수 + 계)
        table.setColumnCount(len(stock_types) + 2)  # 구분 열 1개 + 주식종류 개수 + 계 1개
        
        # 헤더 레이블 설정
        headers = ['구분'] + stock_types + ['계']
        table.setHorizontalHeaderLabels(headers)
        
        table.setStyleSheet(STANDARD_TABLE)
        table.horizontalHeader().setStyleSheet("QHeaderView::section { text-align: center; }")
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 데이터 처리
        categories = {
            '직접취득+기타취득': ['직접취득', '기타취득'],
            '직접취득+기타취득 합계': ['직접취득', '기타취득'],
            '신탁계약에 의한취득': ['신탁계약에 의한취득'],
            '총계': ['총계']
        }
        
        table.setRowCount(len(categories))
        
        for row, (label, category_list) in enumerate(categories.items()):
            # 구분 열
            item = QTableWidgetItem(label)
            item.setTextAlignment(Qt.AlignCenter)
            if '합계' in label or label == '총계':
                item.setForeground(QColor('blue'))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            table.setItem(row, 0, item)
            
            # 각 주식 종류별 합계 계산
            stock_totals = {stock_type: 0 for stock_type in stock_types}
            
            for category in category_list:
                if category in treasury_info:
                    for stock_type in stock_types:
                        if stock_type in treasury_info[category]:
                            stock_totals[stock_type] += convert_to_int(treasury_info[category][stock_type])
            
            # 각 주식 종류별 데이터 입력
            total_sum = 0
            for col, stock_type in enumerate(stock_types, start=1):
                value = stock_totals[stock_type]
                total_sum += value
                
                item = QTableWidgetItem(f"{value:,}")
                item.setTextAlignment(Qt.AlignCenter)
                if '합계' in label or label == '총계':
                    item.setForeground(QColor('blue'))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(row, col, item)
            
            # 계 열
            total_item = QTableWidgetItem(f"{total_sum:,}")
            total_item.setTextAlignment(Qt.AlignCenter)
            if '합계' in label or label == '총계':
                total_item.setForeground(QColor('blue'))
                font = total_item.font()
                font.setBold(True)
                total_item.setFont(font)
            table.setItem(row, len(stock_types) + 1, total_item)
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        self.setLayout(layout)


class ResultWidget(QWidget):
    def __init__(self, search_term, company_data):
        super().__init__()
        # 한글 설정 추가
        font = QApplication.font()
        font.setFamily("Malgun Gothic")  # 한글 폰트 설정
        QApplication.setFont(font)
        
        self.search_term = search_term
        self.company_data = company_data
        self.existing_corp_info = {search_term: company_data}
        self.required_fields = [
            "corp_info",
            "treasury_info",
            "shareholder_list",
            "issued_share",
            "financial_info",
            "contribution_info"
        ]
        
        self.init_ui()
        self.update_data_table(search_term, company_data)

    def calculate_market_cap(self, closing_price, company_data):
        try:
            if closing_price != "N/A" and closing_price != "조회 실패":
                if isinstance(closing_price, (int, float)):
                    price = int(closing_price)
                else:
                    price_str = closing_price.replace(',', '').replace('원', '')
                    try:
                        price = int(float(price_str))
                    except ValueError as e:
                        print(f"숫자 변환 실패: {e}, 입력값: {price_str}")
                        return "N/A"
                
                issued_shares = 0
                if 'issued_share' in company_data:
                    if '합계' in company_data['issued_share']:
                        issued_shares = convert_to_int(company_data['issued_share']['합계'].get('istc_totqy', 0))
                    else:
                        issued_shares = convert_to_int(company_data['issued_share'].get('보통주', {}).get('istc_totqy', 0)) + \
                                      convert_to_int(company_data['issued_share'].get('우선주', {}).get('istc_totqy', 0))
                
                if issued_shares and price:
                    market_cap = (price * issued_shares / 100000000)
                    # 천단위 구분 기호를 추가하고 소수점 두 자리까지 표시
                    return f"{market_cap:,.2f}억원"
                else:
                    print(f"시가총액 계산 실패 - 주가: {price}, 발행주식수: {issued_shares}")
                    return "N/A"
        except Exception as e:
            print(f"시가총액 계산 중 오류 발생: {e}")
            return "N/A"

    def calculate_shareholder_ratio(self, shareholder_list, company_name):
        try:
            # 분자: 모든 주주의 trmend_posesn_stock_co의 합계
            numerator = sum(convert_to_int(shareholder.get('trmend_posesn_stock_co', 0))
                            for shareholder in shareholder_list)
            
            # 해당 회사의 데이터에서 발행주식 총수 가져오기
            denominator = convert_to_int(self.existing_corp_info.get(company_name, {})
                                    .get('issued_share', {})
                                    .get('합계', {})
                                    .get('istc_totqy', 0))
            
            print(f"[{company_name}] 주요주주 총수: {numerator}, 발행주식총수: {denominator}")
            
            if denominator == 0:
                return "N/A"
                
            ratio = (numerator / denominator) * 100
            return f"{ratio:.2f}%"
        except Exception as e:
            print(f"[{company_name}] 주주 지분율 계산 중 오류 발생: {e}")
            return "N/A"

    def calculate_total_treasury(self):
        try:
            treasury_info = self.company_data.get('treasury_info', {})
            total_treasury = 0
            
            # 총계가 있는 경우
            if '총계' in treasury_info:
                total_treasury = sum(convert_to_int(value) for value in treasury_info['총계'].values())
            else:
                # 각 항목별로 합산
                for category in ['직접취득', '신탁계약에 의한취득', '기타취득']:
                    if category in treasury_info:
                        total_treasury += sum(convert_to_int(value) for value in treasury_info[category].values())
                        
            
            return total_treasury
        except Exception as e:
            print(f"자기주식 총계 계산 중 오류 발생: {e}")
            return 0
    def calculate_total_treasury_amount(self, company_data=None):
        try:
            # company_data가 전달되지 않으면 현재 검색된 기업의 데이터 사용
            if company_data is None:
                company_data = self.company_data
            
            # 해당 기업의 자사주 총계 계산
            treasury_info = company_data.get('treasury_info', {})
            total_treasury = 0
            
            if '총계' in treasury_info:
                total_treasury = sum(convert_to_int(value) for value in treasury_info['총계'].values())
            else:
                for category in ['직접취득', '신탁계약에 의한취득', '기타취득']:
                    if category in treasury_info:
                        total_treasury += sum(convert_to_int(value) for value in treasury_info[category].values())
            
            # 해당 기업의 종가 조회
            stock_code = company_data.get('corp_info', {}).get('stock_code')
            if not stock_code:
                return f"{total_treasury:,}주"
                
            stock_code = stock_code.zfill(6)
            today = datetime.now().strftime("%Y%m%d")
            
            # 종가 조회
            df = stock.get_market_ohlcv_by_date(fromdate=today, todate=today, ticker=stock_code)
            if not df.empty:
                closing_price = df.iloc[-1]['종가']
            else:
                # 오늘 데이터가 없으면 최근 10일간 데이터 확인
                for i in range(1, 10):
                    previous_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                    df = stock.get_market_ohlcv_by_date(fromdate=previous_date, todate=previous_date, ticker=stock_code)
                    if not df.empty:
                        closing_price = df.iloc[-1]['종가']
                        break
                else:
                    return f"{total_treasury:,}주"
            
            # 총액 계산 (자사주 * 종가)
            total_amount = total_treasury * closing_price
            total_amount_billion = round(total_amount / 100000000, 2)
            
            # 자사주 수와 총액을 함께 표시
            return f"{total_amount_billion:,.2f}억원"
            
        except Exception as e:
            print(f"자사주 총액 계산 중 오류 발생: {e}")
            return f"{total_treasury:,}주"

    def init_ui(self):
        layout = QVBoxLayout()
        
        # standard_table 설정
        standard_table = QTableWidget()
        standard_table.setColumnCount(16)
        standard_table.setRowCount(1)
        standard_table.verticalHeader().setVisible(False)
        standard_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        # 헤더에 '출자현황' 추가
        headers = ['기업명', '자사주총액', '최대주주 지분', '시가총액', '출자현황', '자본총계', '이익잉여금', '매출', '영업이익', '당기순이익', '영업활동 현금흐름', '현금성자산', '성장성', '안정성', '수익성', '효율성']
        standard_table.setHorizontalHeaderLabels(headers)
        
        font_metrics = QFontMetrics(standard_table.font())
        shareholder_width = font_metrics.horizontalAdvance('가나다라마바사사')
        contribution_width = font_metrics.horizontalAdvance('가나다라마마')
        indicator_width = font_metrics.horizontalAdvance('가나다라')
        cashflow_width = font_metrics.horizontalAdvance('가나다라마바사아자차차')
        
        # 열 너비 설정
        column_widths = [100, 120, shareholder_width, 120, contribution_width, 120, 120, 100, 100, 100, cashflow_width, 120, indicator_width, indicator_width, indicator_width, indicator_width]
        
        # 전체 테이블 너비 계산
        total_width = sum(column_widths)
        standard_table.setMinimumWidth(total_width)
        
        # 높이만 고정
        standard_table.setFixedHeight(standard_table.verticalHeader().length() + 60)
        layout.addWidget(standard_table)
        
        # 필터링 UI 추가
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)  # 수평 방향 간격 설정
        
        # 필터 라벨
        filter_label = QLabel("자사주총액 필터 (±%):")
        filter_layout.addWidget(filter_label)
        
        # 필터 입력 박스
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("퍼센티지 입력")
        self.filter_input.setFixedWidth(100)
        self.filter_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_input)
        
        # 필터 초기화 버튼
        reset_button = QPushButton("필터 초기화")
        reset_button.clicked.connect(self.reset_filter)
        filter_layout.addWidget(reset_button)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        layout.setSpacing(5)  # 수직 방향 간격 설정

        # data_table 설정
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(16)
        self.data_table.verticalHeader().setVisible(False)  # 세로 헤더(순번) 숨기기
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.data_table.setHorizontalHeaderLabels(headers)
        self.data_table.setSortingEnabled(True)
        
        # data_table 열 너비 설정
        for i, width in enumerate(column_widths):
            self.data_table.setColumnWidth(i, width)
        for i, width in enumerate(column_widths):
            standard_table.setColumnWidth(i, width)
        
        # 주주 지분율 계산
        shareholder_ratio = self.calculate_shareholder_ratio(self.company_data.get('shareholder_list', []), self.search_term)
        
        # 출자현황 개수 계산
        contribution_count = len(self.company_data.get('contribution_info', []))
        
        # 자본총계 계산
        equity_amount = 0
        financial_info = self.company_data.get('financial_info', {})
        if 'BS' in financial_info:
            for item in financial_info['BS']:
                if item.get('account_id') == 'ifrs-full_Equity':
                    equity_amount = item.get('thstrm_amount', 0)
                    break
        
        # 이익잉여금 계산
        retainedEarnings_amount = 0
        financial_info = self.company_data.get('financial_info', {})
        if 'BS' in financial_info:
            for item in financial_info['BS']:
                if item.get('account_id') == 'ifrs-full_RetainedEarnings':
                    retainedEarnings_amount = item.get('thstrm_amount', 0)
                    break
                    
        # 매출액 계산
        revenue_amount = 0
        financial_info = self.company_data.get('financial_info', {})
        if 'CIS' in financial_info:
            for item in financial_info['CIS']:
                if item.get('account_id') == 'ifrs-full_Revenue':
                    revenue_amount = item.get('thstrm_amount', 0)
                    break
                
        # 영업이익 계산
        operating_profit_amount = 0
        financial_info = self.company_data.get('financial_info', {})
        if 'CIS' in financial_info:
            for item in financial_info['CIS']:
                if item.get('account_id') == 'dart_OperatingIncomeLoss':
                    operating_profit_amount = item.get('thstrm_amount', 0)
                    break
        
        # 당기순이익 계산
        net_profit_amount = 0
        financial_info = self.company_data.get('financial_info', {})
        if 'CIS' in financial_info:
            for item in financial_info['CIS']:
                if item.get('account_id') == 'ifrs-full_ProfitLoss':
                    net_profit_amount = item.get('thstrm_amount', 0)
                    break
        
        # 영업활동 현금흐름 계산산
        operating_cash_flow_amount = 0
        financial_info = self.company_data.get('financial_info', {})
        if 'CF' in financial_info:
            for item in financial_info['CF']:
                if item.get('account_id') == 'ifrs-full_CashFlowsFromUsedInOperatingActivities':
                    operating_cash_flow_amount = item.get('thstrm_amount', 0)
                    break
        
        # 현금성자산 계산
        cash_and_cash_equivalents_amount = 0
        financial_info = self.company_data.get('financial_info', {})
        if 'CF' in financial_info:
            for item in financial_info['CF']:
                if item.get('account_id') == 'dart_CashAndCashEquivalentsAtEndOfPeriodCf':
                    cash_and_cash_equivalents_amount = item.get('thstrm_amount', 0)
                    break
                 
        # BS 관련 변수
        liabilities_amount = 0  # 부채총계
        equity_amount = 0  # 자본총계
        equity_prev_amount = 0  # 전년 자기자본
        current_assets = 0  # 유동자산
        current_liabilities = 0  # 유동부채
        inventories = 0  # 재고자산
        total_assets = 0  # 총자산
        total_assets_prev = 0  # 전년 총자산
        trade_receivables = 0  # 매출채권
        
        # CIS 관련 변수
        operating_income = 0  # 영업이익
        operating_income_prev = 0  # 전년 영업이익
        finance_costs = 0  # 이자비용
        revenue = 0  # 매출액
        revenue_prev = 0  # 전년 매출액
        gross_profit = 0  # 매출총이익
        net_income = 0  # 당기순이익
        net_income_prev = 0  # 전년 당기순이익

        financial_info = self.company_data.get('financial_info', {})
        
        # BS 항목 처리
        if 'BS' in financial_info:
            for item in financial_info['BS']:
                if item.get('account_id') == 'ifrs-full_Liabilities':
                    liabilities_amount = item.get('thstrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_Equity':
                    equity_amount = item.get('thstrm_amount', 0)
                    equity_prev_amount = item.get('frmtrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_CurrentAssets':
                    current_assets = item.get('thstrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_CurrentLiabilities':
                    current_liabilities = item.get('thstrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_Inventories':
                    inventories = item.get('thstrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_Assets':
                    total_assets = item.get('thstrm_amount', 0)
                    total_assets_prev = item.get('frmtrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_TradeAndOtherCurrentReceivables':
                    trade_receivables = item.get('thstrm_amount', 0)

        # CIS(손익계산서) 항목 처리
        if 'CIS' in financial_info:
            for item in financial_info['CIS']:
                if item.get('account_id') == 'dart_OperatingIncomeLoss':
                    operating_income = item.get('thstrm_amount', 0)
                    operating_income_prev = item.get('frmtrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_FinanceCosts':
                    finance_costs = item.get('thstrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_Revenue':
                    revenue = item.get('thstrm_amount', 0)
                    revenue_prev = item.get('frmtrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_GrossProfit':
                    gross_profit = item.get('thstrm_amount', 0)
                elif item.get('account_id') == 'ifrs-full_ProfitLoss':
                    net_income = item.get('thstrm_amount', 0)
                    net_income_prev = item.get('frmtrm_amount', 0)
        
        liabilities_amount = int(liabilities_amount)  # 부채총계
        equity_amount = int(equity_amount)  # 자본총계
        equity_prev_amount = int(equity_prev_amount)  # 전년 자기자본
        current_assets = int(current_assets)  # 유동자산
        current_liabilities = int(current_liabilities)  # 유동부채
        inventories = int(inventories)  # 재고자산
        total_assets = int(total_assets)  # 총자산
        total_assets_prev = int(total_assets_prev)  # 전년 총자산
        trade_receivables = int(trade_receivables)  # 매출채권

        operating_income = int(operating_income)  # 영업이익
        operating_income_prev = int(operating_income_prev)  # 전년 영업이익
        finance_costs = int(finance_costs)  # 이자비용
        revenue = int(revenue)  # 매출액
        revenue_prev = int(revenue_prev)  # 전년 매출액
        gross_profit = int(gross_profit)  # 매출총이익
        net_income = int(net_income)  # 당기순이익
        net_income_prev = int(net_income_prev)  # 전년 당기순이익
        
        
        # 안전성
        self.debt_ratio = round((liabilities_amount / equity_amount * 100), 2) if equity_amount != 0 else None  # 부채비율 (%)
        self.current_ratio = round((current_assets / current_liabilities * 100), 2) if current_liabilities != 0 else None  # 유동비율 (%)
        self.quick_ratio = round(((current_assets - inventories) / current_liabilities * 100), 2) if current_liabilities != 0 else None  # 당좌비율 (%)
        self.interest_coverage_ratio = round((operating_income / finance_costs), 2) if finance_costs != 0 else None  # 이자보상배율 (배)

        # 효율성
        self.asset_turnover = round((revenue / total_assets), 2) if total_assets != 0 else None  # 총자산회전율 (회)
        self.equity_turnover = round((revenue / equity_amount), 2) if equity_amount != 0 else None  # 자기자본회전율 (회)
        self.receivables_turnover = round((revenue / trade_receivables), 2) if trade_receivables != 0 else None  # 매출채권회전율 (회)
        self.inventory_turnover = round((revenue / inventories), 2) if inventories != 0 else None  # 재고자산회전율 (회)

        # 수익성
        self.gross_profit_margin = round((gross_profit / revenue * 100), 2) if revenue != 0 else None  # 매출총이익률 (%)
        self.operating_profit_margin = round((operating_income / revenue * 100), 2) if revenue != 0 else None  # 영업이익률 (%)
        self.net_profit_margin = round((net_income / revenue * 100), 2) if revenue != 0 else None  # 순이익률 (%)
        self.roe = round((net_income / equity_amount * 100), 2) if equity_amount != 0 else None  # ROE (%)
        self.roa = round((net_income / total_assets * 100), 2) if total_assets != 0 else None  # ROA (%)

        # 성장성
        self.revenue_growth = round(((revenue / revenue_prev - 1) * 100), 2) if revenue_prev != 0 else None  # 매출액 성장률 (%)
        self.operating_income_growth = round(((operating_income / operating_income_prev - 1) * 100), 2) if operating_income_prev != 0 else None  # 영업이익 성장률 (%)
        self.net_income_growth = round(((net_income / net_income_prev - 1) * 100), 2) if net_income_prev != 0 else None  # 당기순이익 성장률 (%)
        self.asset_growth = round(((total_assets / total_assets_prev - 1) * 100), 2) if total_assets_prev != 0 else None  # 총자산 증가율 (%)
        self.equity_growth = round(((equity_amount / equity_prev_amount - 1) * 100), 2) if equity_prev_amount != 0 else None  # 자기자본 증가율 (%)

        # 점수 계산
        self.growth_scores = {
            'revenue': self.calculate_growth_score(self.revenue_growth, "revenue"),
            'operating_income': self.calculate_growth_score(self.operating_income_growth, "operating_income"),
            'net_income': self.calculate_growth_score(self.net_income_growth, "net_income"),
            'asset': self.calculate_growth_score(self.asset_growth, "asset"),
            'equity': self.calculate_growth_score(self.equity_growth, "equity")
        }

        self.stability_scores = {
            'debt': self.calculate_stability_score(self.debt_ratio, "debt"),
            'current': self.calculate_stability_score(self.current_ratio, "current"),
            'quick': self.calculate_stability_score(self.quick_ratio, "quick"),
            'interest': self.calculate_stability_score(self.interest_coverage_ratio, "interest")
        }

        self.profitability_scores = {
            'operating': self.calculate_profitability_score(self.operating_profit_margin, "operating"),
            'net': self.calculate_profitability_score(self.net_profit_margin, "net"),
            'gross': self.calculate_profitability_score(self.gross_profit_margin, "gross"),
            'roe': self.calculate_profitability_score(self.roe, "roe"),
            'roa': self.calculate_profitability_score(self.roa, "roa")
        }

        self.efficiency_scores = {
            'asset': self.calculate_efficiency_score(self.asset_turnover, "asset"),
            'equity': self.calculate_efficiency_score(self.equity_turnover, "equity"),
            'receivables': self.calculate_efficiency_score(self.receivables_turnover, "receivables"),
            'inventory': self.calculate_efficiency_score(self.inventory_turnover, "inventory")
        }

      
        growth_scores_valid = [score for score in self.growth_scores.values() if score > 0]  # 0은 N/A를 의미
        stability_scores_valid = [score for score in self.stability_scores.values() if score > 0]
        profitability_scores_valid = [score for score in self.profitability_scores.values() if score > 0]
        efficiency_scores_valid = [score for score in self.efficiency_scores.values() if score > 0]

        # 유효한 점수가 있는 경우에만 평균 계산, 없으면 "N/A" 반환
        growth_avg = f"{sum(growth_scores_valid) / len(growth_scores_valid):.1f}" if growth_scores_valid else "N/A"
        stability_avg = f"{sum(stability_scores_valid) / len(stability_scores_valid):.1f}" if stability_scores_valid else "N/A"
        profitability_avg = f"{sum(profitability_scores_valid) / len(profitability_scores_valid):.1f}" if profitability_scores_valid else "N/A"
        efficiency_avg = f"{sum(efficiency_scores_valid) / len(efficiency_scores_valid):.1f}" if efficiency_scores_valid else "N/A"
        
        # 데이터 입력
        data = [
            self.search_term,
            self.calculate_total_treasury_amount(),
            self.calculate_shareholder_ratio(self.company_data.get('shareholder_list', []), self.search_term),
            self.calculate_market_cap(self.get_closing_price(), self.company_data),
            f"{contribution_count}개",
            f"{equity_amount / 100000000:,.2f}억원",  # 자본총계 포맷 수정
            f"{retainedEarnings_amount / 100000000:,.2f}억원", #이익잉여금금
            f"{revenue_amount / 100000000:,.2f}억원", #매출액
            f"{operating_profit_amount / 100000000:,.2f}억원", #영업이익
            f"{net_profit_amount / 100000000:,.2f}억원", #당기순이익
            f"{operating_cash_flow_amount / 100000000:,.2f}억원", #영업활동 현금흐름
            f"{cash_and_cash_equivalents_amount / 100000000:,.2f}억원", #현금성자산
            f"{growth_avg}점" if growth_avg != "N/A" else "N/A",
            f"{stability_avg}점" if stability_avg != "N/A" else "N/A",
            f"{profitability_avg}점" if profitability_avg != "N/A" else "N/A",
            f"{efficiency_avg}점" if efficiency_avg != "N/A" else "N/A"
        ]
        
        for col, value in enumerate(data):
            if col in [2, 3, 4, 5, 6]:
                item = NumericTableWidgetItem(str(value))
            else:
                item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            if col == 0:  # 기업명 열
                
                font = item.font()
                
                item.setFont(font)
                item.setToolTip("클릭하여 기업 정보 보기")
            elif col == 4:  # 최대주주 지분 열
                
                font = item.font()
              
                item.setFont(font)
                item.setToolTip("클릭하여 상세 정보 보기")
            elif col == 6:  # 출자현황 열
                
                font = item.font()
                
                
                item.setFont(font)
                item.setToolTip("클릭하여 출자현황 보기")
            standard_table.setItem(0, col, item)
        
        # standard_table 클릭 이벤트 연결
        standard_table.cellClicked.connect(self.handle_cell_click)
        
        # data_table인 경우
        self.data_table.cellClicked.connect(self.handle_cell_click)
        
        # standard_table 크기 조정
        # standard_table.resizeColumnsToContents()
        standard_table.setFixedHeight(standard_table.verticalHeader().length() + 60)
        
        layout.addWidget(standard_table)

        # 진행 상황을 표시할 라벨 추가
        self.progress_label = QLabel('데이터 수집 중...')
        layout.addWidget(self.progress_label)

        # 필터링된 데이터를 저장할 딕셔너리 추가
        self.filtered_companies = {}

        # data_table 추가
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
        # search_term과 동일한 기업은 data_table에 추가하지 않음
        if company_name == self.search_term:
            return
        
        # 필터가 적용된 상태에서 새로운 데이터 추가 시 필터 조건 확인
        if self.filter_input.text():
            try:
                percentage = float(self.filter_input.text())
                standard_amount = self.parse_amount(self.calculate_total_treasury_amount())
                new_amount = self.parse_amount(self.calculate_total_treasury_amount(company_data))
                
                min_amount = standard_amount * (100 - percentage) / 100
                max_amount = standard_amount * (100 + percentage) / 100
                
                if not (min_amount <= new_amount <= max_amount):
                    self.filtered_companies[company_name] = False
                    return
            except ValueError:
                pass
        
        # existing_corp_info 업데이트
        self.existing_corp_info[company_name] = company_data
        
        print(f"\n테이블 업데이트: {company_name}")
        self.data_table.setSortingEnabled(False)
        
        # 새로운 행 추가
        row = self.data_table.rowCount()
        self.data_table.insertRow(row)
        
        try:
            # 해당 기업의 자기주식 총계 계산
            treasury_info = company_data.get('treasury_info', {})
            total_treasury = 0
            if '총계' in treasury_info:
                total_treasury = sum(convert_to_int(value) for value in treasury_info['총계'].values())
            else:
                for category in ['직접취득', '신탁계약에 의한취득', '기타취득']:
                    if category in treasury_info:
                        total_treasury += sum(convert_to_int(value) for value in treasury_info[category].values())
                        
            
            # 해당 기업의 종가 조회
            stock_code = company_data.get('corp_info', {}).get('stock_code')
            if not stock_code:
                return

            stock_code = stock_code.zfill(6)
            today = datetime.now().strftime("%Y%m%d")
            
            # 오늘 종가 조회
            df = stock.get_market_ohlcv_by_date(fromdate=today, todate=today, ticker=stock_code)
            if not df.empty:
                closing_price = f"{df.iloc[-1]['종가']:,}원"
            else:
                # 오늘 데이터가 없으면 최근 10일간 데이터 확인
                for i in range(1, 10):
                    previous_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                    df = stock.get_market_ohlcv_by_date(fromdate=previous_date, todate=previous_date, ticker=stock_code)
                    if not df.empty:
                        closing_price = f"{df.iloc[-1]['종가']:,}원"
                        break

            # 출자현황 개수 계산
            contribution_count = len(company_data.get('contribution_info', []))
            # 자본총계 계산
            equity_amount = 0
            financial_info = company_data.get('financial_info', {})
            if 'BS' in financial_info:
                for item in financial_info['BS']:
                    if item.get('account_id') == 'ifrs-full_Equity':
                        equity_amount = item.get('thstrm_amount', 0)
                        break
                    
            # 자본총계 계산
            equity_amount = 0
            financial_info = company_data.get('financial_info', {})
            if 'BS' in financial_info:
                for item in financial_info['BS']:
                    if item.get('account_id') == 'ifrs-full_Equity':
                        equity_amount = item.get('thstrm_amount', 0)
                        break
            
            # 이익잉여금 계산
            retainedEarnings_amount = 0
            financial_info = company_data.get('financial_info', {})
            if 'BS' in financial_info:
                for item in financial_info['BS']:
                    if item.get('account_id') == 'ifrs-full_RetainedEarnings':
                        retainedEarnings_amount = item.get('thstrm_amount', 0)
                        break
                        
            # 매출액 계산
            revenue_amount = 0
            financial_info = company_data.get('financial_info', {})
            if 'CIS' in financial_info:
                for item in financial_info['CIS']:
                    if item.get('account_id') == 'ifrs-full_Revenue':
                        revenue_amount = item.get('thstrm_amount', 0)
                        break
            if revenue_amount == 0 and 'IS' in financial_info:  # CIS에서 못찾은 경우 IS에서 검색
                for item in financial_info['IS']:
                    if item.get('account_id') == 'ifrs-full_Revenue':
                        revenue_amount = item.get('thstrm_amount', 0)
                        break
                    
            # 영업이익 계산
            operating_profit_amount = 0
            if 'CIS' in financial_info:
                for item in financial_info['CIS']:
                    if item.get('account_id') == 'dart_OperatingIncomeLoss':
                        operating_profit_amount = item.get('thstrm_amount', 0)
                        break
            if operating_profit_amount == 0 and 'IS' in financial_info:  # CIS에서 못찾은 경우 IS에서 검색
                for item in financial_info['IS']:
                    if item.get('account_id') == 'dart_OperatingIncomeLoss':
                        operating_profit_amount = item.get('thstrm_amount', 0)
                        break
            
            # 당기순이익 계산
            net_profit_amount = 0
            if 'CIS' in financial_info:
                for item in financial_info['CIS']:
                    if item.get('account_id') == 'ifrs-full_ProfitLoss':
                        net_profit_amount = item.get('thstrm_amount', 0)
                        break
            if net_profit_amount == 0 and 'IS' in financial_info:  # CIS에서 못찾은 경우 IS에서 검색
                for item in financial_info['IS']:
                    if item.get('account_id') == 'ifrs-full_ProfitLoss':
                        net_profit_amount = item.get('thstrm_amount', 0)
                        break
            
            # 영업활동 현금흐름 계산
            operating_cash_flow_amount = 0
            if 'CF' in financial_info:
                for item in financial_info['CF']:
                    if item.get('account_id') == 'ifrs-full_CashFlowsFromUsedInOperatingActivities':
                        operating_cash_flow_amount = item.get('thstrm_amount', 0)
                        break
            
            # 영업활동 현금흐름 계산산
            operating_cash_flow_amount = 0
            financial_info = company_data.get('financial_info', {})
            if 'CF' in financial_info:
                for item in financial_info['CF']:
                    if item.get('account_id') == 'ifrs-full_CashFlowsFromUsedInOperatingActivities':
                        operating_cash_flow_amount = item.get('thstrm_amount', 0)
                        break
            
            # 현금성자산 계산
            cash_and_cash_equivalents_amount = 0
            financial_info = company_data.get('financial_info', {})
            if 'CF' in financial_info:
                for item in financial_info['CF']:
                    if item.get('account_id') == 'dart_CashAndCashEquivalentsAtEndOfPeriodCf':
                        cash_and_cash_equivalents_amount = item.get('thstrm_amount', 0)
                        break
                    
            # BS 관련 변수
            liabilities_amount = 0  # 부채총계
            equity_amount = 0  # 자본총계
            equity_prev_amount = 0  # 전년 자기자본
            current_assets = 0  # 유동자산
            current_liabilities = 0  # 유동부채
            inventories = 0  # 재고자산
            total_assets = 0  # 총자산
            total_assets_prev = 0  # 전년 총자산
            trade_receivables = 0  # 매출채권
            
            # CIS 관련 변수
            operating_income = 0  # 영업이익
            operating_income_prev = 0  # 전년 영업이익
            finance_costs = 0  # 이자비용
            revenue = 0  # 매출액
            revenue_prev = 0  # 전년 매출액
            gross_profit = 0  # 매출총이익
            net_income = 0  # 당기순이익
            net_income_prev = 0  # 전년 당기순이익

            financial_info = company_data.get('financial_info', {})
            
            # BS 항목 처리
            if 'BS' in financial_info:
                for item in financial_info['BS']:
                    if item.get('account_id') == 'ifrs-full_Liabilities':
                        liabilities_amount = item.get('thstrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_Equity':
                        equity_amount = item.get('thstrm_amount', 0)
                        equity_prev_amount = item.get('frmtrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_CurrentAssets':
                        current_assets = item.get('thstrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_CurrentLiabilities':
                        current_liabilities = item.get('thstrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_Inventories':
                        inventories = item.get('thstrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_Assets':
                        total_assets = item.get('thstrm_amount', 0)
                        total_assets_prev = item.get('frmtrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_TradeAndOtherCurrentReceivables':
                        trade_receivables = item.get('thstrm_amount', 0)

            # CIS(손익계산서) 항목 처리
            if 'CIS' in financial_info:
                for item in financial_info['CIS']:
                    if item.get('account_id') == 'dart_OperatingIncomeLoss':
                        operating_income = item.get('thstrm_amount', 0)
                        operating_income_prev = item.get('frmtrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_FinanceCosts':
                        finance_costs = item.get('thstrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_Revenue':
                        revenue = item.get('thstrm_amount', 0)
                        revenue_prev = item.get('frmtrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_GrossProfit':
                        gross_profit = item.get('thstrm_amount', 0)
                    elif item.get('account_id') == 'ifrs-full_ProfitLoss':
                        net_income = item.get('thstrm_amount', 0)
                        net_income_prev = item.get('frmtrm_amount', 0)
            
            liabilities_amount = int(liabilities_amount)  # 부채총계
            equity_amount = int(equity_amount)  # 자본총계
            equity_prev_amount = int(equity_prev_amount)  # 전년 자기자본
            current_assets = int(current_assets)  # 유동자산
            current_liabilities = int(current_liabilities)  # 유동부채
            inventories = int(inventories)  # 재고자산
            total_assets = int(total_assets)  # 총자산
            total_assets_prev = int(total_assets_prev)  # 전년 총자산
            trade_receivables = int(trade_receivables)  # 매출채권

            operating_income = int(operating_income)  # 영업이익
            operating_income_prev = int(operating_income_prev)  # 전년 영업이익
            finance_costs = int(finance_costs)  # 이자비용
            revenue = int(revenue)  # 매출액
            revenue_prev = int(revenue_prev)  # 전년 매출액
            gross_profit = int(gross_profit)  # 매출총이익
            net_income = int(net_income)  # 당기순이익
            net_income_prev = int(net_income_prev)  # 전년 당기순이익
            
            
            # 안전성
            self.debt_ratio = round((liabilities_amount / equity_amount * 100), 2) if equity_amount != 0 else None  # 부채비율 (%)
            self.current_ratio = round((current_assets / current_liabilities * 100), 2) if current_liabilities != 0 else None  # 유동비율 (%)
            self.quick_ratio = round(((current_assets - inventories) / current_liabilities * 100), 2) if current_liabilities != 0 else None  # 당좌비율 (%)
            self.interest_coverage_ratio = round((operating_income / finance_costs), 2) if finance_costs != 0 else None  # 이자보상배율 (배)

            # 효율성
            self.asset_turnover = round((revenue / total_assets), 2) if total_assets != 0 else None  # 총자산회전율 (회)
            self.equity_turnover = round((revenue / equity_amount), 2) if equity_amount != 0 else None  # 자기자본회전율 (회)
            self.receivables_turnover = round((revenue / trade_receivables), 2) if trade_receivables != 0 else None  # 매출채권회전율 (회)
            self.inventory_turnover = round((revenue / inventories), 2) if inventories != 0 else None  # 재고자산회전율 (회)

            # 수익성
            self.gross_profit_margin = round((gross_profit / revenue * 100), 2) if revenue != 0 else None  # 매출총이익률 (%)
            self.operating_profit_margin = round((operating_income / revenue * 100), 2) if revenue != 0 else None  # 영업이익률 (%)
            self.net_profit_margin = round((net_income / revenue * 100), 2) if revenue != 0 else None  # 순이익률 (%)
            self.roe = round((net_income / equity_amount * 100), 2) if equity_amount != 0 else None  # ROE (%)
            self.roa = round((net_income / total_assets * 100), 2) if total_assets != 0 else None  # ROA (%)

            # 성장성
            self.revenue_growth = round(((revenue / revenue_prev - 1) * 100), 2) if revenue_prev != 0 else None  # 매출액 성장률 (%)
            self.operating_income_growth = round(((operating_income / operating_income_prev - 1) * 100), 2) if operating_income_prev != 0 else None  # 영업이익 성장률 (%)
            self.net_income_growth = round(((net_income / net_income_prev - 1) * 100), 2) if net_income_prev != 0 else None  # 당기순이익 성장률 (%)
            self.asset_growth = round(((total_assets / total_assets_prev - 1) * 100), 2) if total_assets_prev != 0 else None  # 총자산 증가율 (%)
            self.equity_growth = round(((equity_amount / equity_prev_amount - 1) * 100), 2) if equity_prev_amount != 0 else None  # 자기자본 증가율 (%)

            # 점수 계산
            self.growth_scores = {
                'revenue': self.calculate_growth_score(self.revenue_growth, "revenue"),
                'operating_income': self.calculate_growth_score(self.operating_income_growth, "operating_income"),
                'net_income': self.calculate_growth_score(self.net_income_growth, "net_income"),
                'asset': self.calculate_growth_score(self.asset_growth, "asset"),
                'equity': self.calculate_growth_score(self.equity_growth, "equity")
            }

            self.stability_scores = {
                'debt': self.calculate_stability_score(self.debt_ratio, "debt"),
                'current': self.calculate_stability_score(self.current_ratio, "current"),
                'quick': self.calculate_stability_score(self.quick_ratio, "quick"),
                'interest': self.calculate_stability_score(self.interest_coverage_ratio, "interest")
            }

            self.profitability_scores = {
                'operating': self.calculate_profitability_score(self.operating_profit_margin, "operating"),
                'net': self.calculate_profitability_score(self.net_profit_margin, "net"),
                'gross': self.calculate_profitability_score(self.gross_profit_margin, "gross"),
                'roe': self.calculate_profitability_score(self.roe, "roe"),
                'roa': self.calculate_profitability_score(self.roa, "roa")
            }

            self.efficiency_scores = {
                'asset': self.calculate_efficiency_score(self.asset_turnover, "asset"),
                'equity': self.calculate_efficiency_score(self.equity_turnover, "equity"),
                'receivables': self.calculate_efficiency_score(self.receivables_turnover, "receivables"),
                'inventory': self.calculate_efficiency_score(self.inventory_turnover, "inventory")
            }

            # 각 지표의 평균 점수 계산
         
            
            growth_scores_valid = [score for score in self.growth_scores.values() if score > 0]  # 0은 N/A를 의미
            stability_scores_valid = [score for score in self.stability_scores.values() if score > 0]
            profitability_scores_valid = [score for score in self.profitability_scores.values() if score > 0]
            efficiency_scores_valid = [score for score in self.efficiency_scores.values() if score > 0]

            # 유효한 점수가 있는 경우에만 평균 계산, 없으면 "N/A" 반환
            growth_avg = f"{sum(growth_scores_valid) / len(growth_scores_valid):.1f}" if growth_scores_valid else "N/A"
            stability_avg = f"{sum(stability_scores_valid) / len(stability_scores_valid):.1f}" if stability_scores_valid else "N/A"
            profitability_avg = f"{sum(profitability_scores_valid) / len(profitability_scores_valid):.1f}" if profitability_scores_valid else "N/A"
            efficiency_avg = f"{sum(efficiency_scores_valid) / len(efficiency_scores_valid):.1f}" if efficiency_scores_valid else "N/A"

            # 데이터 리스트 생성
            data_list = [
                company_name,
                self.calculate_total_treasury_amount(company_data),  # 각 기업별 데이터 전달
                self.calculate_shareholder_ratio(company_data.get('shareholder_list', []), company_name),
                self.calculate_market_cap(closing_price, company_data),
                f"{contribution_count}개",  # 출자현황 개수 추가
                f"{equity_amount / 100000000:,.2f}억원",  # 자본총계 포맷 수정
                f"{retainedEarnings_amount / 100000000:,.2f}억원", #이익잉여금금
                f"{revenue_amount / 100000000:,.2f}억원", #매출액
                f"{operating_profit_amount / 100000000:,.2f}억원", #영업이익
                f"{net_profit_amount / 100000000:,.2f}억원", #당기순이익
                f"{operating_cash_flow_amount / 100000000:,.2f}억원", #영업활동 현금흐름
                f"{cash_and_cash_equivalents_amount / 100000000:,.2f}억원", #현금성자산,
                f"{growth_avg}점" if growth_avg != "N/A" else "N/A",
                f"{stability_avg}점" if stability_avg != "N/A" else "N/A",
                f"{profitability_avg}점" if profitability_avg != "N/A" else "N/A",
                f"{efficiency_avg}점" if efficiency_avg != "N/A" else "N/A"
            ]
            
            # 데이터 업데이트 후 셀 스타일 적용
            for col, value in enumerate(data_list):
                # 숫자 데이터가 포함된 열은 NumericTableWidgetItem 사용
                if col in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]:  # 숫자 데이터를 포함하는 모든 열
                    # 숫자만 추출하여 저장
                    if isinstance(value, str):
                        numeric_value = ''.join(filter(lambda x: x.isdigit() or x == '.', value.replace(',', '')))
                        try:
                            numeric_value = float(numeric_value)
                        except ValueError:
                            numeric_value = 0
                    else:
                        numeric_value = value
                        
                    new_item = NumericTableWidgetItem(str(value))
                    new_item.setData(Qt.UserRole, numeric_value)  # 정렬을 위한 실제 숫자 값 저장
                else:
                    new_item = QTableWidgetItem(str(value))
                
                new_item.setTextAlignment(Qt.AlignCenter)
                
                # 스타일링 적용 (기업명, 최대주주 지분, 출자현황 열 등)
                if col == 0:  # 기업명 열
                  
                    font = new_item.font()
                
                    new_item.setFont(font)
                    new_item.setToolTip("클릭하여 기업 정보 보기")
                elif col == 2:  # 최대주주 지분 열
                  
                    font = new_item.font()
                 
                    new_item.setFont(font)
                    new_item.setToolTip("클릭하여 상세 정보 보기")
                elif col == 4:  # 출자현황 열
                   
                    font = new_item.font()
           
                    new_item.setFont(font)
                    new_item.setToolTip("클릭하여 출자현황 보기")
                
                self.data_table.setItem(row, col, new_item)
            self.data_table.setSortingEnabled(True)
            
            print(f"{company_name} 테이블 업데이트 완료")
            
            # 필터가 적용된 상태라면 필터 조건에 따라 행 숨김 처리
            if self.filter_input.text() and not self.filtered_companies.get(company_name, True):
                self.data_table.setRowHidden(row, True)
            
            # ... rest of the code ...
        except Exception as e:
            print(f"테이블 업데이트 중 오류 발생 ({company_name}): {str(e)}")

    def show_shareholder_dialog(self, company_name, company_data):
        if 'shareholder_list' in company_data:
            dialog = ShareholderDialog(company_data['shareholder_list'], company_name, self)
            dialog.exec_()

    def handle_cell_click(self, row, column):
        clicked_table = self.sender()
        company_name = clicked_table.item(row, 0).text()  # 첫 번째 열에서 회사명 가져오기
        
        # standard_table인 경우
        if clicked_table == self.findChild(QTableWidget):  # 첫 번째 테이블
            company_data = self.company_data
        # data_table인 경우
        else:
            company_data = self.existing_corp_info.get(company_name)
            
        if column == 0:  # 기업명 열을 클릭했을 때
            if company_data and 'corp_info' in company_data:
                dialog = CompanyInfoDialog(company_data['corp_info'], company_name, self)
                dialog.exec_()
        elif column == 1: 
            if company_data and 'treasury_info' in company_data:
                dialog = TreasuryDialog(company_data['treasury_info'], company_name, self)
                dialog.exec_()
        elif column == 2:  # 최대주주 지분 열을 클릭했을 때
            if company_data and 'shareholder_list' in company_data:
                # 발행주식 총수 계산
                issued_total = 0
                if 'issued_share' in company_data and '합계' in company_data['issued_share']:
                    issued_total = convert_to_int(company_data['issued_share']['합계'].get('istc_totqy', 0))
                
                dialog = ShareholderDialog(company_data['shareholder_list'], company_name, issued_total, self)
                dialog.exec_()
        elif column == 4:  # 출자현황 열을 클릭했을 때
            if company_data and 'contribution_info' in company_data:
                dialog = ContributionDialog(company_data['contribution_info'], company_name, self)
                dialog.exec_()
        elif column >= 12 and column <= 15:  # 성장성, 안정성, 수익성, 효율성 열
            metrics_type = {
                12: 'growth',
                13: 'stability',
                14: 'profitability',
                15: 'efficiency'
            }.get(column)
            
            if metrics_type:
                dialog = FinancialMetricsDialog(metrics_type, None, company_name, self)
                dialog.exec_()

    @pyqtSlot(int, int)
    def update_progress(self, current, total):
        if hasattr(self, 'progress_label'):
            self.progress_label.setText(f'데이터 수집 중... ({current}/{total})')
            if current >= total:
                self.progress_label.setText('데이터 수집 완료')

    def get_closing_price(self):
        try:
            stock_code = self.company_data.get('corp_info', {}).get('stock_code')
            if not stock_code:
                return "N/A"

            stock_code = stock_code.zfill(6)
            today = datetime.now().strftime("%Y%m%d")
            
            # 오늘 종가 조회
            df = stock.get_market_ohlcv_by_date(fromdate=today, todate=today, ticker=stock_code)
            if not df.empty:
                return f"{df.iloc[-1]['종가']:,}원"
            
            # 오늘 데이터가 없으면 최근 10일간 데이터 확인
            for i in range(1, 10):
                previous_date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                df = stock.get_market_ohlcv_by_date(fromdate=previous_date, todate=previous_date, ticker=stock_code)
                if not df.empty:
                    return f"{df.iloc[-1]['종가']:,}원"
            
            return "조회 실패"
            
        except Exception as e:
            print(f"종가 조회 중 오류 발생: {e}")
            return "조회 실패"

    def calculate_growth_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "revenue":
            if value >= 30: return 10
            elif value >= 25: return 9
            elif value >= 20: return 8
            elif value >= 15: return 7
            elif value >= 10: return 6
            elif value >= 5: return 5
            elif value >= 1: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "operating_income":
            if value >= 40: return 10
            elif value >= 30: return 9
            elif value >= 20: return 8
            elif value >= 15: return 7
            elif value >= 10: return 6
            elif value >= 5: return 5
            elif value >= 1: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "net_income":
            if value >= 50: return 10
            elif value >= 40: return 9
            elif value >= 30: return 8
            elif value >= 20: return 7
            elif value >= 10: return 6
            elif value >= 5: return 5
            elif value >= 1: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "asset":
            if value >= 25: return 10
            elif value >= 20: return 9
            elif value >= 15: return 8
            elif value >= 10: return 7
            elif value >= 5: return 6
            elif value >= 1: return 5
            elif value >= 0: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "equity":
            if value >= 20: return 10
            elif value >= 15: return 9
            elif value >= 10: return 8
            elif value >= 7: return 7
            elif value >= 5: return 6
            elif value >= 1: return 5
            elif value >= 0: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1

    def calculate_stability_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "debt":
            if value <= 50: return 10
            elif value <= 70: return 9
            elif value <= 90: return 8
            elif value <= 110: return 7
            elif value <= 130: return 6
            elif value <= 150: return 5
            elif value <= 180: return 4
            elif value <= 210: return 3
            elif value <= 250: return 2
            else: return 1
        
        elif indicator_type == "current":
            if value >= 200: return 10
            elif value >= 180: return 9
            elif value >= 150: return 8
            elif value >= 130: return 7
            elif value >= 110: return 6
            elif value >= 90: return 5
            elif value >= 70: return 4
            elif value >= 50: return 3
            elif value >= 30: return 2
            else: return 1
        
        elif indicator_type == "quick":
            if value >= 180: return 10
            elif value >= 150: return 9
            elif value >= 120: return 8
            elif value >= 100: return 7
            elif value >= 80: return 6
            elif value >= 60: return 5
            elif value >= 40: return 4
            elif value >= 20: return 3
            elif value >= 10: return 2
            else: return 1
        
        elif indicator_type == "interest":
            if value >= 10: return 10
            elif value >= 8: return 9
            elif value >= 6: return 8
            elif value >= 4: return 7
            elif value >= 3: return 6
            elif value >= 2: return 5
            elif value >= 1.5: return 4
            elif value >= 1: return 3
            elif value >= 0.5: return 2
            else: return 1

    def calculate_profitability_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "operating":
            if value >= 30: return 10
            elif value >= 25: return 9
            elif value >= 20: return 8
            elif value >= 15: return 7
            elif value >= 10: return 6
            elif value >= 7: return 5
            elif value >= 4: return 4
            elif value >= 1: return 3
            elif value >= 0: return 2
            else: return 1
        
        elif indicator_type == "net":
            if value >= 25: return 10
            elif value >= 20: return 9
            elif value >= 15: return 8
            elif value >= 10: return 7
            elif value >= 7: return 6
            elif value >= 4: return 5
            elif value >= 2: return 4
            elif value >= 0: return 3
            elif value >= -3: return 2
            else: return 1
        
        elif indicator_type == "gross":
            if value >= 60: return 10
            elif value >= 50: return 9
            elif value >= 40: return 8
            elif value >= 35: return 7
            elif value >= 30: return 6
            elif value >= 25: return 5
            elif value >= 20: return 4
            elif value >= 15: return 3
            elif value >= 10: return 2
            else: return 1
        
        elif indicator_type == "roe":
            if value >= 25: return 10
            elif value >= 20: return 9
            elif value >= 15: return 8
            elif value >= 12: return 7
            elif value >= 10: return 6
            elif value >= 7: return 5
            elif value >= 4: return 4
            elif value >= 1: return 3
            elif value >= 0: return 2
            else: return 1
        
        elif indicator_type == "roa":
            if value >= 15: return 10
            elif value >= 12: return 9
            elif value >= 10: return 8
            elif value >= 8: return 7
            elif value >= 6: return 6
            elif value >= 4: return 5
            elif value >= 2: return 4
            elif value >= 1: return 3
            elif value >= 0: return 2
            else: return 1

    def calculate_efficiency_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "asset":
            if value >= 2.5: return 10
            elif value >= 2.0: return 9
            elif value >= 1.5: return 8
            elif value >= 1.2: return 7
            elif value >= 1.0: return 6
            elif value >= 0.8: return 5
            elif value >= 0.6: return 4
            elif value >= 0.4: return 3
            elif value >= 0.2: return 2
            else: return 1
        
        elif indicator_type == "equity":
            if value >= 5.0: return 10
            elif value >= 4.0: return 9
            elif value >= 3.0: return 8
            elif value >= 2.5: return 7
            elif value >= 2.0: return 6
            elif value >= 1.5: return 5
            elif value >= 1.0: return 4
            elif value >= 0.8: return 3
            elif value >= 0.5: return 2
            else: return 1
        
        elif indicator_type == "receivables":
            if value >= 20.0: return 10
            elif value >= 15.0: return 9
            elif value >= 12.0: return 8
            elif value >= 10.0: return 7
            elif value >= 8.0: return 6
            elif value >= 6.0: return 5
            elif value >= 4.0: return 4
            elif value >= 2.0: return 3
            elif value >= 1.0: return 2
            else: return 1
        
        elif indicator_type == "inventory":
            if value >= 12.0: return 10
            elif value >= 10.0: return 9
            elif value >= 8.0: return 8
            elif value >= 6.0: return 7
            elif value >= 5.0: return 6
            elif value >= 4.0: return 5
            elif value >= 3.0: return 4
            elif value >= 2.0: return 3
            elif value >= 1.0: return 2
            else: return 1

    def apply_filter(self):
        filter_text = self.filter_input.text().strip()
        
        # 필터가 비어있으면 모든 행 표시
        if not filter_text:
            for row in range(self.data_table.rowCount()):
                self.data_table.setRowHidden(row, False)
                if self.data_table.item(row, 0):
                    company_name = self.data_table.item(row, 0).text()
                    self.filtered_companies[company_name] = True
            return
        
        try:
            percentage = float(filter_text)
            standard_amount = self.parse_amount(self.calculate_total_treasury_amount())
            
            for row in range(self.data_table.rowCount()):
                if self.data_table.item(row, 1):  # 자사주총액 열 확인
                    company_name = self.data_table.item(row, 0).text()
                    amount_str = self.data_table.item(row, 1).text()
                    amount = self.parse_amount(amount_str)
                    
                    min_amount = standard_amount * (100 - percentage) / 100
                    max_amount = standard_amount * (100 + percentage) / 100
                    
                    show_row = min_amount <= amount <= max_amount
                    self.data_table.setRowHidden(row, not show_row)
                    self.filtered_companies[company_name] = show_row
                    
        except ValueError:
            # 숫자가 아닌 입력의 경우 모든 행 표시
            for row in range(self.data_table.rowCount()):
                self.data_table.setRowHidden(row, False)
                if self.data_table.item(row, 0):
                    company_name = self.data_table.item(row, 0).text()
                    self.filtered_companies[company_name] = True

    def reset_filter(self):
        self.filter_input.clear()
        self.filtered_companies.clear()
        # 모든 행 표시
        for row in range(self.data_table.rowCount()):
            self.data_table.setRowHidden(row, False)

    def parse_amount(self, amount_str):
        try:
            # "억원" 제거하고 숫자만 추출
            return float(amount_str.replace('억원', '').replace(',', ''))
        except:
            return 0

class FinancialMetricsDialog(QDialog):
    def __init__(self, metrics_type, metrics_data, company_name, parent=None):
        super().__init__(parent)
        # 현재 선택된 행의 회사 데이터를 복사하여 저장
        self.company_data = parent.existing_corp_info.get(company_name, {}).copy()
        self.metrics_type = metrics_type
        
        self.setWindowTitle(f"{company_name} {self.get_korean_title(metrics_type)} 상세")
        self.setMinimumWidth(600)
        
        # 재무 지표 계산
        self.calculate_financial_metrics()
        
        layout = QVBoxLayout()
        
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['지표명', '값', '점수'])
        
        table.setStyleSheet(STANDARD_TABLE)
        table.horizontalHeader().setStyleSheet("QHeaderView::section { text-align: center; }")
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 지표별 데이터 매핑
        metrics_mapping = self.get_metrics_mapping(metrics_type)
        table.setRowCount(len(metrics_mapping))
        
        row = 0
        for metric_name, (value, score) in metrics_mapping.items():
            # 지표명
            name_item = QTableWidgetItem(metric_name)
            name_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, name_item)
            
            # 값
            value_str = f"{value:.2f}" if value is not None else "N/A"
            if value is not None:
                if metrics_type in ['growth', 'stability', 'profitability']:
                    value_str += "%"
                elif metrics_type == 'efficiency':
                    value_str += "회"
            value_item = QTableWidgetItem(value_str)
            value_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, value_item)
            
            # 점수
            score_str = f"{score:.1f}점" if score is not None else "N/A"
            score_item = QTableWidgetItem(score_str)
            score_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 2, score_item)
            
            row += 1
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        self.setLayout(layout)

    def get_metrics_mapping(self, metrics_type):
        if metrics_type == 'growth':
            return {
                '매출액 성장률': (self.revenue_growth, self.growth_scores.get('revenue')),
                '영업이익 성장률': (self.operating_income_growth, self.growth_scores.get('operating_income')),
                '당기순이익 성장률': (self.net_income_growth, self.growth_scores.get('net_income')),
                '총자산 증가율': (self.asset_growth, self.growth_scores.get('asset')),
                '자기자본 증가율': (self.equity_growth, self.growth_scores.get('equity'))
            }
        elif metrics_type == 'stability':
            return {
                '부채비율': (self.debt_ratio, self.stability_scores.get('debt')),
                '유동비율': (self.current_ratio, self.stability_scores.get('current')),
                '당좌비율': (self.quick_ratio, self.stability_scores.get('quick')),
                '이자보상배율': (self.interest_coverage_ratio, self.stability_scores.get('interest'))
            }
        elif metrics_type == 'profitability':
            return {
                '매출총이익률': (self.gross_profit_margin, self.profitability_scores.get('gross')),
                '영업이익률': (self.operating_profit_margin, self.profitability_scores.get('operating')),
                '순이익률': (self.net_profit_margin, self.profitability_scores.get('net')),
                'ROE': (self.roe, self.profitability_scores.get('roe')),
                'ROA': (self.roa, self.profitability_scores.get('roa'))
            }
        elif metrics_type == 'efficiency':
            return {
                '총자산회전율': (self.asset_turnover, self.efficiency_scores.get('asset')),
                '자기자본회전율': (self.equity_turnover, self.efficiency_scores.get('equity')),
                '매출채권회전율': (self.receivables_turnover, self.efficiency_scores.get('receivables')),
                '재고자산회전율': (self.inventory_turnover, self.efficiency_scores.get('inventory'))
            }
        return {}

    def calculate_growth_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "revenue":
            if value >= 30: return 10
            elif value >= 25: return 9
            elif value >= 20: return 8
            elif value >= 15: return 7
            elif value >= 10: return 6
            elif value >= 5: return 5
            elif value >= 1: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "operating_income":
            if value >= 40: return 10
            elif value >= 30: return 9
            elif value >= 20: return 8
            elif value >= 15: return 7
            elif value >= 10: return 6
            elif value >= 5: return 5
            elif value >= 1: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "net_income":
            if value >= 50: return 10
            elif value >= 40: return 9
            elif value >= 30: return 8
            elif value >= 20: return 7
            elif value >= 10: return 6
            elif value >= 5: return 5
            elif value >= 1: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "asset":
            if value >= 25: return 10
            elif value >= 20: return 9
            elif value >= 15: return 8
            elif value >= 10: return 7
            elif value >= 5: return 6
            elif value >= 1: return 5
            elif value >= 0: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1
        
        elif indicator_type == "equity":
            if value >= 20: return 10
            elif value >= 15: return 9
            elif value >= 10: return 8
            elif value >= 7: return 7
            elif value >= 5: return 6
            elif value >= 1: return 5
            elif value >= 0: return 4
            elif value >= -4: return 3
            elif value >= -9: return 2
            else: return 1

    def calculate_stability_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "debt":
            if value <= 50: return 10
            elif value <= 70: return 9
            elif value <= 90: return 8
            elif value <= 110: return 7
            elif value <= 130: return 6
            elif value <= 150: return 5
            elif value <= 180: return 4
            elif value <= 210: return 3
            elif value <= 250: return 2
            else: return 1
        
        elif indicator_type == "current":
            if value >= 200: return 10
            elif value >= 180: return 9
            elif value >= 150: return 8
            elif value >= 130: return 7
            elif value >= 110: return 6
            elif value >= 90: return 5
            elif value >= 70: return 4
            elif value >= 50: return 3
            elif value >= 30: return 2
            else: return 1
        
        elif indicator_type == "quick":
            if value >= 180: return 10
            elif value >= 150: return 9
            elif value >= 120: return 8
            elif value >= 100: return 7
            elif value >= 80: return 6
            elif value >= 60: return 5
            elif value >= 40: return 4
            elif value >= 20: return 3
            elif value >= 10: return 2
            else: return 1
        
        elif indicator_type == "interest":
            if value >= 10: return 10
            elif value >= 8: return 9
            elif value >= 6: return 8
            elif value >= 4: return 7
            elif value >= 3: return 6
            elif value >= 2: return 5
            elif value >= 1.5: return 4
            elif value >= 1: return 3
            elif value >= 0.5: return 2
            else: return 1

    def calculate_profitability_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "operating":
            if value >= 30: return 10
            elif value >= 25: return 9
            elif value >= 20: return 8
            elif value >= 15: return 7
            elif value >= 10: return 6
            elif value >= 7: return 5
            elif value >= 4: return 4
            elif value >= 1: return 3
            elif value >= 0: return 2
            else: return 1
        
        elif indicator_type == "net":
            if value >= 25: return 10
            elif value >= 20: return 9
            elif value >= 15: return 8
            elif value >= 10: return 7
            elif value >= 7: return 6
            elif value >= 4: return 5
            elif value >= 2: return 4
            elif value >= 0: return 3
            elif value >= -3: return 2
            else: return 1
        
        elif indicator_type == "gross":
            if value >= 60: return 10
            elif value >= 50: return 9
            elif value >= 40: return 8
            elif value >= 35: return 7
            elif value >= 30: return 6
            elif value >= 25: return 5
            elif value >= 20: return 4
            elif value >= 15: return 3
            elif value >= 10: return 2
            else: return 1
        
        elif indicator_type == "roe":
            if value >= 25: return 10
            elif value >= 20: return 9
            elif value >= 15: return 8
            elif value >= 12: return 7
            elif value >= 10: return 6
            elif value >= 7: return 5
            elif value >= 4: return 4
            elif value >= 1: return 3
            elif value >= 0: return 2
            else: return 1
        
        elif indicator_type == "roa":
            if value >= 15: return 10
            elif value >= 12: return 9
            elif value >= 10: return 8
            elif value >= 8: return 7
            elif value >= 6: return 6
            elif value >= 4: return 5
            elif value >= 2: return 4
            elif value >= 1: return 3
            elif value >= 0: return 2
            else: return 1

    def calculate_efficiency_score(self, value, indicator_type):
        if value is None:
            return 0
            
        if indicator_type == "asset":
            if value >= 2.5: return 10
            elif value >= 2.0: return 9
            elif value >= 1.5: return 8
            elif value >= 1.2: return 7
            elif value >= 1.0: return 6
            elif value >= 0.8: return 5
            elif value >= 0.6: return 4
            elif value >= 0.4: return 3
            elif value >= 0.2: return 2
            else: return 1
        
        elif indicator_type == "equity":
            if value >= 5.0: return 10
            elif value >= 4.0: return 9
            elif value >= 3.0: return 8
            elif value >= 2.5: return 7
            elif value >= 2.0: return 6
            elif value >= 1.5: return 5
            elif value >= 1.0: return 4
            elif value >= 0.8: return 3
            elif value >= 0.5: return 2
            else: return 1
        
        elif indicator_type == "receivables":
            if value >= 20.0: return 10
            elif value >= 15.0: return 9
            elif value >= 12.0: return 8
            elif value >= 10.0: return 7
            elif value >= 8.0: return 6
            elif value >= 6.0: return 5
            elif value >= 4.0: return 4
            elif value >= 2.0: return 3
            elif value >= 1.0: return 2
            else: return 1
        
        elif indicator_type == "inventory":
            if value >= 12.0: return 10
            elif value >= 10.0: return 9
            elif value >= 8.0: return 8
            elif value >= 6.0: return 7
            elif value >= 5.0: return 6
            elif value >= 4.0: return 5
            elif value >= 3.0: return 4
            elif value >= 2.0: return 3
            elif value >= 1.0: return 2
            else: return 1

    def calculate_financial_metrics(self):
        # 재무제표 데이터 가져오기
        financial_info = self.company_data.get('financial_info', {})
        
        # BS 관련 변수 초기화 및 계산
        self.init_bs_variables(financial_info)
        
        # CIS 관련 변수 초기화 및 계산
        self.init_cis_variables(financial_info)
        
        # 재무비율 계산
        self.calculate_ratios()
        
        # 점수 계산
        self.calculate_scores()

    def init_bs_variables(self, financial_info):
        self.liabilities_amount = 0
        self.equity_amount = 0
        self.equity_prev_amount = 0
        self.current_assets = 0
        self.current_liabilities = 0
        self.inventories = 0
        self.total_assets = 0
        self.total_assets_prev = 0
        self.trade_receivables = 0
        
        if 'BS' in financial_info:
            for item in financial_info['BS']:
                if item.get('account_id') == 'ifrs-full_Liabilities':
                    self.liabilities_amount = int(item.get('thstrm_amount', 0))
                elif item.get('account_id') == 'ifrs-full_Equity':
                    self.equity_amount = int(item.get('thstrm_amount', 0))
                    self.equity_prev_amount = int(item.get('frmtrm_amount', 0))
                elif item.get('account_id') == 'ifrs-full_CurrentAssets':
                    self.current_assets = int(item.get('thstrm_amount', 0))
                elif item.get('account_id') == 'ifrs-full_CurrentLiabilities':
                    self.current_liabilities = int(item.get('thstrm_amount', 0))
                elif item.get('account_id') == 'ifrs-full_Inventories':
                    self.inventories = int(item.get('thstrm_amount', 0))
                elif item.get('account_id') == 'ifrs-full_Assets':
                    self.total_assets = int(item.get('thstrm_amount', 0))
                    self.total_assets_prev = int(item.get('frmtrm_amount', 0))
                elif item.get('account_id') == 'ifrs-full_TradeAndOtherCurrentReceivables':
                    self.trade_receivables = int(item.get('thstrm_amount', 0))

    def init_cis_variables(self, financial_info):
        self.operating_income = 0
        self.operating_income_prev = 0
        self.finance_costs = 0
        self.revenue = 0
        self.revenue_prev = 0
        self.gross_profit = 0
        self.net_income = 0
        self.net_income_prev = 0
        
        # 먼저 CIS에서 값을 찾고, 없으면 IS에서 찾음
        statements = ['CIS', 'IS'] if 'CIS' in financial_info else ['IS']
        
        for statement in statements:
            if statement in financial_info:
                for item in financial_info[statement]:
                    if item.get('account_id') == 'dart_OperatingIncomeLoss':
                        self.operating_income = int(item.get('thstrm_amount', 0))
                        self.operating_income_prev = int(item.get('frmtrm_amount', 0))
                    elif item.get('account_id') == 'ifrs-full_FinanceCosts':
                        self.finance_costs = int(item.get('thstrm_amount', 0))
                    elif item.get('account_id') == 'ifrs-full_Revenue':
                        self.revenue = int(item.get('thstrm_amount', 0))
                        self.revenue_prev = int(item.get('frmtrm_amount', 0))
                    elif item.get('account_id') == 'ifrs-full_GrossProfit':
                        self.gross_profit = int(item.get('thstrm_amount', 0))
                    elif item.get('account_id') == 'ifrs-full_ProfitLoss':
                        self.net_income = int(item.get('thstrm_amount', 0))
                        self.net_income_prev = int(item.get('frmtrm_amount', 0))
                
                    # 값을 찾았다면 더 이상 검색하지 않음
                    if all([self.operating_income, self.finance_costs, self.revenue, 
                           self.gross_profit, self.net_income]):
                        break

    def calculate_ratios(self):
        # 안전성
        self.debt_ratio = round((self.liabilities_amount / self.equity_amount * 100), 2) if self.equity_amount != 0 else None
        self.current_ratio = round((self.current_assets / self.current_liabilities * 100), 2) if self.current_liabilities != 0 else None
        self.quick_ratio = round(((self.current_assets - self.inventories) / self.current_liabilities * 100), 2) if self.current_liabilities != 0 else None
        self.interest_coverage_ratio = round((self.operating_income / self.finance_costs), 2) if self.finance_costs != 0 else None

        # 효율성
        self.asset_turnover = round((self.revenue / self.total_assets), 2) if self.total_assets != 0 else None
        self.equity_turnover = round((self.revenue / self.equity_amount), 2) if self.equity_amount != 0 else None
        self.receivables_turnover = round((self.revenue / self.trade_receivables), 2) if self.trade_receivables != 0 else None
        self.inventory_turnover = round((self.revenue / self.inventories), 2) if self.inventories != 0 else None

        # 수익성
        self.gross_profit_margin = round((self.gross_profit / self.revenue * 100), 2) if self.revenue != 0 else None
        self.operating_profit_margin = round((self.operating_income / self.revenue * 100), 2) if self.revenue != 0 else None
        self.net_profit_margin = round((self.net_income / self.revenue * 100), 2) if self.revenue != 0 else None
        self.roe = round((self.net_income / self.equity_amount * 100), 2) if self.equity_amount != 0 else None
        self.roa = round((self.net_income / self.total_assets * 100), 2) if self.total_assets != 0 else None

        # 성장성
        self.revenue_growth = round(((self.revenue / self.revenue_prev - 1) * 100), 2) if self.revenue_prev != 0 else None
        self.operating_income_growth = round(((self.operating_income / self.operating_income_prev - 1) * 100), 2) if self.operating_income_prev != 0 else None
        self.net_income_growth = round(((self.net_income / self.net_income_prev - 1) * 100), 2) if self.net_income_prev != 0 else None
        self.asset_growth = round(((self.total_assets / self.total_assets_prev - 1) * 100), 2) if self.total_assets_prev != 0 else None
        self.equity_growth = round(((self.equity_amount / self.equity_prev_amount - 1) * 100), 2) if self.equity_prev_amount != 0 else None

    def calculate_scores(self):
        # 성장성 점수
        self.growth_scores = {
            'revenue': self.parent().calculate_growth_score(self.revenue_growth, "revenue"),
            'operating_income': self.parent().calculate_growth_score(self.operating_income_growth, "operating_income"),
            'net_income': self.parent().calculate_growth_score(self.net_income_growth, "net_income"),
            'asset': self.parent().calculate_growth_score(self.asset_growth, "asset"),
            'equity': self.parent().calculate_growth_score(self.equity_growth, "equity")
        }
        # N/A(0점)을 제외한 평균 계산
        valid_growth_scores = [score for score in self.growth_scores.values() if score != 0]
        self.growth_average = sum(valid_growth_scores) / len(valid_growth_scores) if valid_growth_scores else 0

        # 안정성 점수
        self.stability_scores = {
            'debt': self.parent().calculate_stability_score(self.debt_ratio, "debt"),
            'current': self.parent().calculate_stability_score(self.current_ratio, "current"),
            'quick': self.parent().calculate_stability_score(self.quick_ratio, "quick"),
            'interest': self.parent().calculate_stability_score(self.interest_coverage_ratio, "interest")
        }
        valid_stability_scores = [score for score in self.stability_scores.values() if score != 0]
        self.stability_average = sum(valid_stability_scores) / len(valid_stability_scores) if valid_stability_scores else 0

        # 수익성 점수
        self.profitability_scores = {
            'operating': self.parent().calculate_profitability_score(self.operating_profit_margin, "operating"),
            'net': self.parent().calculate_profitability_score(self.net_profit_margin, "net"),
            'gross': self.parent().calculate_profitability_score(self.gross_profit_margin, "gross"),
            'roe': self.parent().calculate_profitability_score(self.roe, "roe"),
            'roa': self.parent().calculate_profitability_score(self.roa, "roa")
        }
        valid_profitability_scores = [score for score in self.profitability_scores.values() if score != 0]
        self.profitability_average = sum(valid_profitability_scores) / len(valid_profitability_scores) if valid_profitability_scores else 0

        # 효율성 점수
        self.efficiency_scores = {
            'asset': self.parent().calculate_efficiency_score(self.asset_turnover, "asset"),
            'equity': self.parent().calculate_efficiency_score(self.equity_turnover, "equity"),
            'receivables': self.parent().calculate_efficiency_score(self.receivables_turnover, "receivables"),
            'inventory': self.parent().calculate_efficiency_score(self.inventory_turnover, "inventory")
        }
        valid_efficiency_scores = [score for score in self.efficiency_scores.values() if score != 0]
        self.efficiency_average = sum(valid_efficiency_scores) / len(valid_efficiency_scores) if valid_efficiency_scores else 0
        

    @staticmethod
    def calculate_growth_rate(current, previous):
        return ((current / previous - 1) * 100) if previous != 0 else None

    def get_korean_title(self, metrics_type):
        titles = {
            'growth': '성장성',
            'stability': '안정성',
            'profitability': '수익성',
            'efficiency': '효율성'
        }
        return titles.get(metrics_type, '')



if __name__ == '__main__':
    try:
        # 로그 디렉토리 경로 설정
        if getattr(sys, 'frozen', False):
            # exe 실행 시
            base_dir = os.path.dirname(sys.executable)
        else:
            # 일반 파이썬 실행 시
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        log_dir = os.path.join(base_dir, 'logs')
        
        # 로그 디렉토리 생성 시도
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            # 권한 문제 등으로 실패 시 임시 디렉토리 사용
            log_dir = os.path.join(tempfile.gettempdir(), 'searchbot_logs')
            os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'error_log.txt')
        
        # 전역 예외 처리기 설정
        def handle_exception(exc_type, exc_value, exc_traceback):
            try:
                error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                
                # 로그 파일에 오류 기록
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n")
                    f.write(error_msg)
                
                # 사용자에게 오류 메시지 표시
                QMessageBox.critical(None, '오류', 
                    f'프로그램 실행 중 오류가 발생했습니다:\n\n{str(exc_value)}\n\n'
                    f'자세한 오류 내용이 다음 위치에 저장되었습니다:\n{log_file}')
            except Exception as e:
                # 최후의 수단으로 기본 메시지 박스만 표시
                QMessageBox.critical(None, '심각한 오류',
                    f'프로그램 실행 중 치명적인 오류가 발생했습니다:\n{str(exc_value)}')
        
        sys.excepthook = handle_exception
        
        # QApplication 초기화 및 실행
        app = QApplication(sys.argv)
        font = QFont("Malgun Gothic", 9)
        app.setFont(font)
        QTextCodec.setCodecForLocale(QTextCodec.codecForName('UTF-8'))
        
        try:
            search_app = SearchApp()
            search_app.stack.show()
            sys.exit(app.exec_())
        except Exception as e:
            QMessageBox.critical(None, '초기화 오류', 
                f'프로그램 초기화 중 오류가 발생했습니다:\n{str(e)}')
            sys.exit(1)
            
    except Exception as e:
        # GUI가 초기화되기 전 발생하는 오류 처리
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, 
            f"프로그램 시작 중 심각한 오류가 발생했습니다:\n{str(e)}", 
            "치명적 오류", 0x10)
        sys.exit(1)