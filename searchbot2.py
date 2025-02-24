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
from PyQt5.QtGui import QColor
import re

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
                                "CF": [],
                               
                
                            }
                            for item in fnlttSinglAcnt_data['list']:
                                financial_item = {
                                    'account_nm': item.get('account_nm'),
                                    'thstrm_amount': convert_to_int(item.get('thstrm_amount')),
                                    'currency': 'KRW'
                                }
                                if item.get('sj_div') == 'BS':
                                    financial_info["BS"].append(financial_item)           
                                elif item.get('sj_div') == 'CIS':
                                    financial_info["CIS"].append(financial_item)
                                elif item.get('sj_div') == 'CF':
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
        
        cached_companies = [name for name in self.existing_corp_info.keys() 
                          if name != self.search_term and 
                          all(field in self.existing_corp_info[name] for field in self.required_fields)]
        
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
            missing_fields = self._get_missing_fields(company_name)
            if missing_fields and company_name in self.company_codes:
                print(f"\n새로운 데이터 수집 시작: {company_name}")
                collector.collect_company_data(
                    company_name,
                    self.company_codes[company_name]['corp_code'],
                    self.existing_corp_info,
                    missing_fields
                )
                # 데이터 수집 후 즉시 테이블 업데이트
                self.data_processed.emit(company_name, self.existing_corp_info[company_name])
            
            self._update_progress(company_name)
            time.sleep(0.01)

    def _get_missing_fields(self, company_name):
        missing_fields = []
        for field in self.required_fields:
            if field not in self.existing_corp_info[company_name] or not self.existing_corp_info[company_name].get(field):
                missing_fields.append(field)
        return missing_fields

    def _update_progress(self, company_name):
        self.processed += 1
        self.progress.emit(self.processed, self.total_companies)
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cache_file = os.path.join(current_dir, 'cache', 'corp_info.json')
        
        print(f"저장할 데이터: {self.existing_corp_info[company_name]}")
        
        try:
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

        # processed 변수 초기화 추가
        processed = 0
        total_companies = 1  # 현재는 한 회사만 처리하므로 1로 설정

        # 현재 연도 가져오기 추가
        current_year = datetime.now().year

        # 현재 스크립트 경로 가져오기
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cache_dir = os.path.join(current_dir, 'cache')
        cache_file = os.path.join(cache_dir, 'corp_info.json')
        
        # 캐시 디렉토리 생성
        os.makedirs(cache_dir, exist_ok=True)

        # 기존 캐시 파일 읽기
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
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

class ResultWidget(QWidget):
    def __init__(self, search_term, company_data):
        super().__init__()
        
        # 검색어와 기업 데이터를 인스턴스 변수로 저장
        self.search_term = search_term
        self.company_data = company_data
        
        # existing_corp_info 초기화 및 현재 회사 데이터 저장
        self.existing_corp_info = {search_term: company_data}
        
        # required_fields 추가
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

    def init_ui(self):
        layout = QVBoxLayout()
        
        # 검색한 기업 정보를 표시할 테이블
        standard_table = QTableWidget()
        standard_table.setColumnCount(7)  # 7개 열로 변경
        standard_table.setRowCount(1)
        
        # 헤더에 '출자현황' 추가
        headers = ['기업명', '시장', '자기주식 총계', '종가', '최대주주 지분', '시가총액(억원)', '출자현황']
        standard_table.setHorizontalHeaderLabels(headers)
        
        # data_table 초기화
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(7)  # 7개 열로 변경
        self.data_table.setHorizontalHeaderLabels(headers)
        self.data_table.setSortingEnabled(True)  # 헤더 클릭 시 오름차/내림차 정렬 활성화
        
        # 주주 지분율 계산
        shareholder_ratio = self.calculate_shareholder_ratio(self.company_data.get('shareholder_list', []), self.search_term)
        
        # 출자현황 개수 계산
        contribution_count = len(self.company_data.get('contribution_info', []))
        
        # 데이터 입력
        data = [
            self.search_term,
            self.company_data.get('corp_info', {}).get('market', 'N/A'),
            f"{self.calculate_total_treasury():,}주",
            self.get_closing_price(),
            shareholder_ratio,
            self.calculate_market_cap(self.get_closing_price(), self.company_data),
            f"{contribution_count}개"  # 출자현황 개수 추가
        ]
        
        for col, value in enumerate(data):
            if col in [2, 3, 4, 5, 6]:
                item = NumericTableWidgetItem(str(value))
            else:
                item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            if col == 0:  # 기업명 열
                item.setForeground(QColor('blue'))
                font = item.font()
                font.setUnderline(True)
                item.setFont(font)
                item.setToolTip("클릭하여 기업 정보 보기")
            elif col == 4:  # 최대주주 지분 열
                item.setForeground(QColor('blue'))
                font = item.font()
                font.setUnderline(True)
                item.setFont(font)
                item.setToolTip("클릭하여 상세 정보 보기")
            elif col == 6:  # 출자현황 열
                item.setForeground(QColor('blue'))
                font = item.font()
                font.setUnderline(True)
                item.setFont(font)
                item.setToolTip("클릭하여 출자현황 보기")
            standard_table.setItem(0, col, item)
        
        # standard_table 클릭 이벤트 연결
        standard_table.cellClicked.connect(self.handle_cell_click)
        
        # data_table인 경우
        self.data_table.cellClicked.connect(self.handle_cell_click)
        
        # standard_table 크기 조정
        standard_table.resizeColumnsToContents()
        standard_table.setFixedHeight(standard_table.verticalHeader().length() + 60)
        
        layout.addWidget(standard_table)

        # 진행 상황을 표시할 라벨 추가
        self.progress_label = QLabel('데이터 수집 중...')
        layout.addWidget(self.progress_label)

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
            
            # 데이터 리스트 생성
            data_list = [
                company_name,
                company_data.get('corp_info', {}).get('market', 'N/A'),
                f"{total_treasury:,}주" if total_treasury > 0 else "0주",
                closing_price,
                self.calculate_shareholder_ratio(company_data.get('shareholder_list', []), company_name),
                self.calculate_market_cap(closing_price, company_data),
                f"{contribution_count}개"  # 출자현황 개수 추가
            ]
            
            # 데이터 업데이트 후 셀 스타일 적용
            for col, value in enumerate(data_list):
                # 숫자 데이터가 포함된 열 (예: 2, 3, 4, 5, 6)는 NumericTableWidgetItem 사용
                if col in [2, 3, 4, 5, 6]:
                    new_item = NumericTableWidgetItem(str(value))
                else:
                    new_item = QTableWidgetItem(str(value))
                new_item.setTextAlignment(Qt.AlignCenter)
                
                # 스타일링 적용 (기업명, 최대주주 지분, 출자현황 열 등)
                if col == 0:  # 기업명 열
                    new_item.setForeground(QColor('blue'))
                    font = new_item.font()
                    font.setUnderline(True)
                    new_item.setFont(font)
                    new_item.setToolTip("클릭하여 기업 정보 보기")
                elif col == 4:  # 최대주주 지분 열
                    new_item.setForeground(QColor('blue'))
                    font = new_item.font()
                    font.setUnderline(True)
                    new_item.setFont(font)
                    new_item.setToolTip("클릭하여 상세 정보 보기")
                elif col == 6:  # 출자현황 열
                    new_item.setForeground(QColor('blue'))
                    font = new_item.font()
                    font.setUnderline(True)
                    new_item.setFont(font)
                    new_item.setToolTip("클릭하여 출자현황 보기")
                
                self.data_table.setItem(row, col, new_item)
            self.data_table.setSortingEnabled(True)
            
            print(f"{company_name} 테이블 업데이트 완료")
            
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
        elif column == 4:  # 최대주주 지분 열을 클릭했을 때
            if company_data and 'shareholder_list' in company_data:
                # 발행주식 총수 계산
                issued_total = 0
                if 'issued_share' in company_data and '합계' in company_data['issued_share']:
                    issued_total = convert_to_int(company_data['issued_share']['합계'].get('istc_totqy', 0))
                
                dialog = ShareholderDialog(company_data['shareholder_list'], company_name, issued_total, self)
                dialog.exec_()
        elif column == 6:  # 출자현황 열을 클릭했을 때
            if company_data and 'contribution_info' in company_data:
                dialog = ContributionDialog(company_data['contribution_info'], company_name, self)
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    search_app = SearchApp()
    search_app.stack.show()
    sys.exit(app.exec_())
