import requests

def get_stock_status(api_key, corp_code, bsns_year, reprt_code):
    url = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    print(data)
    
    if data['status'] != '000':
        print(f"에러: {data['message']}")
        return
    
    for item in data.get('list', []):
        if item['se'] == '합계':
            print(f"발행주식의 총수: {item['istc_totqy']}")
            print(f"자기주식수: {item['tesstk_co']}")
            print(f"유통주식수: {item['distb_stock_co']}")

# 사용 예시
api_key = "bea2a84f1ed21a05c3bc44c406f4b12f9ba56902"
corp_code = "00113410"
bsns_year = "2024"
reprt_code = "11012"

get_stock_status(api_key, corp_code, bsns_year, reprt_code)
