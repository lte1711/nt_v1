# NEXT-TRADE 바이낸스 테스트넷 연동 설치 가이드

## 시스템 요구사항
- Python 3.8+
- pip (Python 패키지 매니저)
- 가상환경 (권장)

## 설치 절차

### 1. 저장소 복제
```bash
git clone <repository-url>
cd next-trade-ver1.0
```

### 2. 가상환경 생성
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경설정
#### 4.1 .env 파일 설정
```bash
# .env 파일 생성
BINANCE_TESTNET_API_KEY=your_api_key_here
BINANCE_TESTNET_API_SECRET=your_api_secret_here
BINANCE_TESTNET_URL=https://demo-fapi.binance.com
```

#### 4.2 config.json 설정 (권장)
```json
{
  "binance_testnet": {
    "api_key": "your_api_key_here",
    "api_secret": "your_api_secret_here",
    "base_url": "https://demo-fapi.binance.com"
  }
}
```

### 5. API 서버 시작
```bash
python -m uvicorn next_trade.api.app:app --host 127.0.0.1 --port 8100
```

### 6. 인증 확인
```bash
curl http://127.0.0.1:8100/api/investor/account
```

예상 응답:
```json
{
  "ok": true,
  "ts": "2026-04-01T10:17:56.110587+00:00",
  "credentials_present": true,
  "api_base": "https://demo-fapi.binance.com",
  "mode": "probe_only"
}
```

### 7. 데이터 연동 확인
```bash
curl http://127.0.0.1:8100/api/v1/investor/positions
```

## 트러블슈팅

### 문제 1: credentials_present: false
**해결책:**
1. .env 파일의 API 키 확인
2. config.json 파일의 API 키 확인
3. 바이낸스 데모 플랫폼에서 키 재발급

### 문제 2: 서버 시작 실패
**해결책:**
1. 가상환경 활성화 확인
2. 의존성 설치 확인
3. 포트 8100 사용 여부 확인

### 문제 3: 네트워크 연결 실패
**해결책:**
1. 인터넷 연결 확인
2. 방화벽 설정 확인
3. 바이낸스 데모 엔드포인트 접근 확인

## API 엔드포인트

### 인증 관련
- `GET /api/investor/account` - 인증 상태 확인
- `GET /api/v1/investor/positions` - 포지션 정보 조회
- `POST /api/v1/investor/order` - 주문 제출

### 시스템 관련
- `GET /health` - 시스템 헬스 체크
- `GET /api/runtime` - 런타임 정보

## 보안 주의사항
- API 키를 공개 저장소에 커밋하지 마세요
- config.json 파일을 .gitignore에 추가하세요
- 정기적으로 API 키를 교체하세요

## 지원
문제 발생 시 기술 문서를 참조하거나 개발팀에 문의하세요.
