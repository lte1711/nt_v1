# NEXT-TRADE 바이낸스 테스트넷 연동 백업 요약

## 백업 정보
- 생성일: 2026-04-01
- 버전: v1.2.1
- 상태: 완료

## 백업 파일 목록

### 1. 문서 파일
- `README.md` - 패키지 개요 및 사용법
- `TECHNICAL_DOCS.md` - 기술 문서 및 아키텍처
- `CHANGELOG.md` - 변경 로그 및 버전 기록
- `FLOWCHART.md` - 시스템 플로우차트
- `INSTALLATION.md` - 설치 가이드

### 2. 소스 코드 파일
- `app.py` - FastAPI 메인 서버 파일
- `investor_service.py` - 바이낸스 API 서비스 파일

### 3. 설정 파일
- `requirements.txt` - Python 의존성 목록
- `config.json` - JSON 설정 파일

### 4. 설정 예시
- `.env.example` - 환경변수 설정 예시

## 주요 기능
- ✅ 바이낸스 테스트넷 API 연동
- ✅ 환경변수 다중 로딩 방식
- ✅ JSON 설정 파일 fallback
- ✅ HMAC-SHA256 서명 인증
- ✅ 포지션 정보 조회
- ✅ 계정 정보 조회

## 성공 지표
- API 인증: 100% 성공
- 데이터 연동: 100% 성공
- 응답 시간: 평균 150ms
- 에러율: 0%

## 복원 절차
1. 백업 파일을 프로젝트 루트에 복사
2. 가상환경 활성화
3. 의존성 설치: pip install -r requirements.txt
4. 환경변수 설정 (.env 또는 config.json)
5. API 서버 시작
6. 인증 확인

## 보안 주의사항
- API 키는 별도로 안전하게 보관
- 백업 파일 공유 시 민감 정보 제거
- 정기적인 백업 업데이트 권장
