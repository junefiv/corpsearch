import requests
import json
import urllib3
from requests.packages.urllib3.util.ssl_ import create_urllib3_context

# SSL 설정
urllib3.disable_warnings()
CIPHERS = 'DEFAULT:@SECLEVEL=1'  # 보안 수준 조정

# 커스텀 어댑터 생성
class CustomAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers=CIPHERS)
        kwargs['ssl_context'] = context
        return super(CustomAdapter, self).init_poolmanager(*args, **kwargs)

# API URL 및 서비스키
BASE_URL = "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2"
SERVICE_KEY = "Wbh3mv0f0%2Fyry0YxyrnXoj7vWtV1j1NLE2GIz4PDiw1nMyScrFgLy%2BVBFbBawkIFMeKI%2FeiXLLQNphjfIe5uEg%3D%3D"  # 본인의 API 서비스키 입력

# 세션 생성 및 어댑터 설정
session = requests.Session()
session.mount('https://', CustomAdapter())

# 요청 파라미터 설정
params = {
    "ServiceKey": SERVICE_KEY,
    "crno": "1101111874654",  # 조회할 기업의 법인등록번호 입력
    "numOfRows": 1,
    "pageNo": 1,
    "resultType": "json"  # JSON 형식으로 응답 받기
}

# SSL 검증을 비활성화하고 API 호출
response = session.get(BASE_URL, params=params, verify=False)

if response.status_code == 200:
    result = response.json()
    items = result.get('response', {}).get('body', {}).get('items', {}).get('item', [])
    for item in items:
        print(f"기업명: {item.get('corpNm')}")
        print(f"법인등록시장구분코드명: {item.get('corpRegMrktDcdNm')}")
        print(f"표준산업분류명: {item.get('sicNm')}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
