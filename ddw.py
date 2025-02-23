import requests
import json

def get_treasury_stock_status(api_key, corp_code, bsns_year, reprt_code):
    url = "https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if data['status'] != '000':
        print(f"에러: {data['message']}")
        return
    
    # acqs_mth2별로 데이터 정리
    print("전체 데이터 확인:")
    for item in data.get('list', []):
        print(f"\n취득방법: {item['acqs_mth1']} > {item['acqs_mth2']} > {item['acqs_mth3']}")
        print(f"주식종류: {item['stock_knd']}")
        print(f"기초수량: {item['bsis_qy']}")
        print(f"기말수량: {item['trmend_qy']}")
    
    # 기존 집계 로직
    result = {}
    for item in data.get('list', []):
        acqs_mth2 = item['acqs_mth2']
        acqs_mth3 = item['acqs_mth3']
        stock_knd = item['stock_knd']
        trmend_qy = item['trmend_qy']
        
        # 소계나 총계가 아닌 실제 보유량만 집계
        if acqs_mth3 not in ['소계', '총계']:
            if acqs_mth2 not in result:
                result[acqs_mth2] = {}
            
            if stock_knd not in result[acqs_mth2]:
                result[acqs_mth2][stock_knd] = trmend_qy
            elif trmend_qy != '-' and result[acqs_mth2][stock_knd] == '-':
                result[acqs_mth2][stock_knd] = trmend_qy
    
    # 총계는 별도로 처리
    for item in data.get('list', []):
        if item['acqs_mth2'] == '총계':
            if '총계' not in result:
                result['총계'] = {}
            result['총계'][item['stock_knd']] = item['trmend_qy']
    
    # 결과 출력
    print(json.dumps(result, ensure_ascii=False, indent=2))

# 사용 예시
api_key = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
corp_code = "00167192"
bsns_year = "2023"
reprt_code = "11011"

get_treasury_stock_status(api_key, corp_code, bsns_year, reprt_code)
