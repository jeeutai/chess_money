import time
import requests

URL = "https://chessjaeguk.onrender.com"  # 여기에 Render 앱 주소 입력

while True:
    try:
        response = requests.get(URL)
        print(f"서버 응답 코드: {response.status_code}")  # 응답 코드 출력
    except Exception as e:
        print(f"오류 발생: {e}")

    time.sleep(45)  # 45초마다 요청 보내기
