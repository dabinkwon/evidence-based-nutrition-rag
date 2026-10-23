# 한끼의 근거 — 레시피·영양정보 RAG

재료로 요리를 찾고 선택 레시피의 재료·조리법을 원문 근거로 설명하는 Streamlit 서비스입니다. 원재료 영양 후보·연구 서지정보 조회, Python 에너지 참고 계산과 음식 열량 비교를 제공합니다.

## 설치와 실행

검증 환경은 Windows / Python 3.11입니다. 프로젝트 루트에서 실행합니다.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# 본인의 GMS_API_KEY 입력 후 실행
python scripts/index_vectors.py
python -m streamlit run app.py
```

기존 `.env`가 있으면 덮어쓰지 마세요. 첫 임베딩·색인 준비는 외부 호출/비용이 발생합니다. 제공 원본으로 앱을 실행할 때 수집용 키는 필수가 아닙니다. 환경변수가 `.env`보다 우선합니다. 키는 제출물/로그/캡처에 넣지 않습니다.

현재 예제는 검색어/선별 `gpt-6-luna`, 답변 `gpt-6.1-sol`, 임베딩 `text-embedding-3-small`입니다. GMS OpenAI 호환 주소는 `https://gms.ssafy.io/gmsapi/api.openai.com/v1`이며 단계별 모델 미지정 시 `GMS_MODEL`로 대체합니다.

## 화면별 사용

| 화면 | 질문/입력 | 결과 |
|---|---|---|
| 요리 찾기 | 두부 / 두부, 달걀 | 재료 원문에서 복수 재료 모두 포함·제외 조건 검사 |
| 요리 대화·영양정보 | 이 요리의 재료와 조리법 알려줘 | 선택ID의 메타데이터/연결원문 검색→답변·인용번호·출처 |
| 요리 대화·영양정보 | 두부 영양성분 / 그 재료들의 영양성분은? | 확보한 원재료 후보·기준량·출처, 미확보 안내 |
| 요리 대화·영양정보 | 가지의 효능은? | 확보 연구의 원문 서지정보/연구분류. 인체효능 확정 아님 |
| 다른 요리와 비교 | 두 요리 선택 | 실제 재료·조리원문 비교/근거 |
| 내 정보로 음식 비교 | 적용대상 확인 후 폼 제출 | Python 참고 에너지 계산·지정중량의 음식 열량/예산 차이 |

음식 열량 비교에는 사이드바 제외 재료를 적용하지 않습니다. 예산 이내는 섭취추천/제외조건 충족이 아닙니다. 요리 검색의 제외 검사는 제한된 동의어 검사이며 알레르기 안전을 보장하지 않습니다.

## 파이프라인과 파일

준비: `collect_source_docs.py` 검색어 추출→로컬 제공문서묶음 검색→후보선별→캐시→설정청킹→`index_vectors.py` Chroma upsert. 자체레시피 원문은 강제 보존합니다. 신규 웹 전체 수집이라고 표현하지 않습니다.

질문: 입력분류→재료/영양/연구 로컬조회 또는 `rag_graph.py`의 `retrieve → generate`. 선택요리 원문을 보존하고 근거번호/유형을 전달합니다. 유효한 실제 인용만 표시하며 잘못된/없는 인용은 차단·안내합니다. 열량은 `energy_profile.py`의 Python 계산이며 LLM에 맡기지 않습니다.

| 파일 | 역할 |
|---|---|
| config/rag_sources.json | 청크 크기/중복/후보 상한 |
| config/rag_answer.json | Top-k/최소 검색점수 |
| .env.example | 비밀값 없는 설정 예제 |
| docs/REQUIREMENTS.md | 요구사항 정의·충족 범위 |
| docs/FILES.md | 파이프라인 설계·실행·출처·이용제한 |
| docs/STATE.md / docs/WORKLOG.md | 최신 상태 / 실제 작업 이력 |
| docs/SEMANTIC_RESULTS.md | 검색/모델 비교 결과·측정 한계 |
| data/review/ | 셀프 점검·실제 실행 결과 |

```powershell
python scripts/index_vectors.py --count
python scripts/collect_source_docs.py --selected recipe:28 --index
python scripts/recipe_rag.py --selected recipe:28 --question "이 요리의 재료와 조리법 알려줘" --generate
python -m unittest discover -s tests
```

수집/재색인은 명시적으로 실행합니다. 모델/서버/본문이 달라지면 색인을 재구축합니다. 키/색인 실패는 확인 가능한 선택원문 범위와 서비스 불가를 안내합니다. `.tools`와 생성DB는 개발/재생성 자료이며 제출 소스에서 제외합니다.

## 현재 자료 범위와 한계

- 레시피100개, 활성 Chroma는 메타데이터100개+연결원문1개입니다. 연구/영양 파일 전체가 Chroma 문서인 것은 아닙니다.
- 원재료113개 레코드는 검토 후보이며 제품/조리상태 동일성은 미확정입니다. 미수집 자료를 일반음식 값이나 LLM 일반지식으로 대신하지 않습니다.
- 연구 메타데이터는 공식197코드 중 논문이 있는174개 식품 범위입니다. 논문 제목만으로 효능·권장량을 계산하지 않습니다.
- 레시피 API 영양 기준량은 미확인으로1인분 환산을 하지 않습니다. 영양조건 요리추천은 중단했습니다.
- 신체 계산은19~78세 적용범위의 참고 추정이며 의료·감량 처방/개인정확도 검증이 아닙니다. 임신·수유·특수질환 관리에는 적용하지 않습니다.

## 검증·제출 안내

전체88개 자동테스트와 실제 색인/캐시/Top-k/청킹/생성/실패안내를 검증했습니다. 입력과 한계는 결과JSON·WORKLOG를 따릅니다. `data/rag/model_comparison.html`과 `answer_model_comparison.html`은3문항 모델 비교이며 RAG 없이/근거 포함5문항 실험을 대체하지 않습니다. 해당실험·전체출처준수·사용자 수용속도는 미확인입니다.

제출 묶음에는 요구사항 정의·파이프라인 설계·소스·본README·요구사항 대조표·테스트 결과표·셀프작성본·상호작성용양식·증빙/실험기록을 포함합니다. **상호양식은 실제 점검자가 작성해야 하며 타인의 점검을 대신 수행한 것으로 기록하지 않습니다.** 작성자·점검자·지역/반/성명 및 최종 업로드는 사용자가 확인합니다. 파일구성 충족은 기능전체/상호평가 완료와 다릅니다.

## 출처·이용조건·보안

출처 목록은 `data/source_url_inventory.json`, 상세 조건은 `docs/FILES.md`를 참조합니다. 주요 제공처는 식품안전나라 COOKRCP01, 공공데이터포털 식품영양 API, 농촌진흥청 농산물 효능 API입니다. 계산 근거는 Mifflin 1990 논문과 AWM 2014 활동계수 원문에 연결합니다.

