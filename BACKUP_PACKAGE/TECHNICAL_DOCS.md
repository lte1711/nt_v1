# NEXT-TRADE 바이낸스 테스트넷 연동 기술 문서

## 아키텍처 개요
NEXT-TRADE 시스템의 바이낸스 테스트넷 API 연동 아키텍처

## 핵심 컴포넌트

### 1. API 서버 (app.py)
- FastAPI 기반 REST API 서버
- python-dotenv를 통한 환경변수 로딩
- JSON 설정 파일 fallback 메커니즘
- 포트: 8100

### 2. 투자자 서비스 (investor_service.py)
- 바이낸스 API와의 직접 통신
- HMAC-SHA256 서명 생성
- 포지션 및 계정 정보 조회
- 에러 핸들링 및 재시 로직

### 3. 환경설정 관리
- **.env 파일**: 기본 환경변수
- **config.json**: JSON 설정 파일 (fallback)
- **requirements.txt**: 의존성 관리

## 데이터 흐름
1. 클라이언트 → API 서버 (FastAPI)
2. API 서버 → 환경설정 로딩
3. API 서버 → 바이낸스 API (HTTPS)
4. 바이낸스 API → 응답 데이터
5. 응답 데이터 → 클라이언트

## 보안 메커니즘
- API 키 및 비밀키 분리 저장
- HMAC-SHA256 서명 기반 인증
- HTTPS 통신 암호화
- 환경변수 기반 키 관리

## 에러 처리
- 환경변수 로딩 실패 시 fallback
- API 호출 실패 시 예외 처리
- 네트워크 타임아웃 설정
- 상세 에러 로깅

## 성능 최적화
- 캐싱 메커니즘 적용
- 연결 풀 관리
- 비동기 처리
- 응답 데이터 압축

## 모니터링
- API 응답 시간 측정
- 에러율 추적
- 로그 레벨 관리
- 헬스 체크 엔드포인트
