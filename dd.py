import requests
import xml.etree.ElementTree as ET
import json

def get_income_statement(crno, bizYear, serviceKey, resultType="xml"):
    url = "http://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2/getIncoStat_V2"
    params = {
        "pageNo": 1,
        "numOfRows": 100,  # 충분한 데이터 조회를 위해 설정
        "resultType": resultType,
        "serviceKey": serviceKey,
        "crno": crno,
        "bizYear": bizYear,
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print("API 호출 오류", response.status_code)
        return None
    
    return response.text

def parse_xml_to_json(xml_data):
    root = ET.fromstring(xml_data)
    items = root.findall(".//item")
    
    result = []
    for item in items:
        acitNm = item.find("acitNm").text if item.find("acitNm") is not None else ""
        crtmAcitAmt = item.find("crtmAcitAmt").text if item.find("crtmAcitAmt") is not None else "0"
        
        result.append({
            "acitNm": acitNm,
            "crtmAcitAmt": crtmAcitAmt
        })
    
    return json.dumps(result, indent=4, ensure_ascii=False)

# 예제 실행
crno = "1101110414758"  # 법인등록번호
bizYear = "2023"  # 사업연도
serviceKey = "Wbh3mv0f0/yry0YxyrnXoj7vWtV1j1NLE2GIz4PDiw1nMyScrFgLy+VBFbBawkIFMeKI/eiXLLQNphjfIe5uEg=="  # 본인의 서비스키 입력

xml_response = get_income_statement(crno, bizYear, serviceKey)
if xml_response:
    json_result = parse_xml_to_json(xml_response)
    print(json_result)
