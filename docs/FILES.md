# 파일 안내와 실행 방법

갱신일: 2026-10-22. 파일 역할·실행법·출처·이용 제한을 이 문서에서 관리한다. 명령은 프로젝트 루트에서 실행한다.

최신 실행은 W036이다. 활성 검색 문서는 레시피 100개+새 항목 연결 근거 1개(101개)이며, 아래 W031/W034의 117건은 이전 실행 기록이다. 기존 공식 문서 5개·고정 발췌 17개 원본은 보존되어 있지만 현재 전체가 새 수집 컬렉션에 들어 있는 것은 아니다.

| 확인 목적 | 문서 |
|---|---|
| 재개할 때 최신 상태·다음 작업 | [STATE.md](STATE.md) |
| 날짜별 작업·검증 이력 | [WORKLOG.md](WORKLOG.md) |
| 요구사항과 충족 여부 | [REQUIREMENTS.md](REQUIREMENTS.md) |
| 선택 이유·결정·포트폴리오 근거 | [PORTFOLIO.md](PORTFOLIO.md) |
| 코드·데이터 설명·실행 방법 | 이 문서 |
| 고정 질문 실제 평가 결과 | [SEMANTIC_RESULTS.md](SEMANTIC_RESULTS.md), 자동 생성 |
| LLM 작업 규칙 | [AGENTS.md](../AGENTS.md) |

기본 시작 문서는 AGENTS.md와 STATE.md다. STATE는 현재 요약, WORKLOG는 누적 이력이다.

## 데이터 수와 역할 — 2026-10-22 (W031)

| 데이터 | 실제 건수 | 역할·출처 |
|---|---|---|
| data/foods.json | 100 | 식약처 식품영양성분DB API 초기 표본. 100g 기준 영양 조회 |
| data/foods_extended.json | 759 | 같은 API의 확장 후보 풀. 초기 100개 전부 포함, 새 고유 항목은 659개 |
| data/recipes.json | 100 | 식품안전나라 COOKRCP01 API. 메뉴·재료·조리법 검색 |
| data/guidelines/texts/*.txt 및 manifest.json | 문서 5 | 농촌진흥청·정책브리핑 공식 식생활/정책 웹 본문과 출처 |
| data/guidelines/chunks.jsonl | 17 | 위 5개 문서에서 발췌한 검색·인용 근거 |
| data/rag/documents.jsonl | 117 | 레시피 100개와 지침 발췌 17개의 검색용 파생본 |
| data/menu_catalog.json | 100 | 기존 레시피 중심의 음식 연결 후보 카탈로그 |
| data/recipe_food_candidates.json | 21쌍 | 19개 레시피의 이름 기반 음식 연결 후보, 확정 연결 0 |
| data/recipe_serving_menus.json | 6 | 기존 레시피 중 과거 공식 PDF와 1인분 영양 대조한 부분집합. PDF는 삭제 상태 |

LLM이 로컬 JSON/JSONL 건수와 food_id 교집합·합집합을 확인했다. 영양 음식은 중복 제거 후 759개이며 859개가 아니다. CSV·원본 응답·파생본은 별도 신규 음식으로 합산하지 않는다. API 재호출·기능 테스트는 수행하지 않았다. 현재 RAG 문서에는 영양 음식 759개가 포함되지 않으며 레시피 100개·지침 17개가 들어 있다.

## Vector DB 재생성과 건수 확인 — W034

2026-10-22 현재 실행 방법이다. 아래에 보존된 W026~W033의 SQLite/Python 검색 설명은 당시 구현에 관한 기록이며, 현재 CLI 기본 검색은 ChromaDB다. UI는 사용자 요청으로 후속 작업이다.

```powershell
python -m pip install -r requirements.txt
python scripts/index_vectors.py
python scripts/index_vectors.py --count
python scripts/recipe_rag.py --question "이 요리의 재료와 조리법 알려줘" --selected recipe:28
```

- 현재 환경에서는 공용 패키지를 변경하지 않도록 ChromaDB 1.5.9를 .tools/vector에 설치했다. 스크립트는 이 로컬 설치가 있으면 사용하며, 새 환경에서는 위 requirements.txt 설치로 실행할 수 있다. OpenAI SDK의 현재 확인 버전도 requirements.txt에 고정했다.
- 색인 입력: data/recipes.json의 레시피 100개, data/guidelines/chunks.jsonl의 원문 근거 17개. 실행 시 원본에서 검색 텍스트를 재구성하므로 documents.jsonl이나 DB 파일을 배포할 필요가 없다.
- recipe_meta는 레시피당 한 청크·recipe ID, source_docs는 발췌당 한 청크·chunk ID를 사용한다. 같은 ID를 upsert하고 삭제된 원본 ID는 해당 컬렉션에서 제거한다. source_docs의 일반 지침은 특정 레시피의 개별 설명 자료를 대신하지 않으며 F2003~F2005의 전체 충족은 별도 점검한다.
- 기본 저장 경로 data/rag/chroma/는 Git 제외다. 원본/정리 데이터·스크립트·requirements.txt·실행법을 보관하고 생성 DB·.tools/·임베딩 캐시·.env는 커밋하지 않는다. 별도 --db-dir을 쓰면 해당 경로도 Git 제외 여부를 확인해야 한다.
- --count는 실제 영속 DB에서 recipe_meta·source_docs·합계 건수를 읽으며 외부 API를 호출하지 않는다. 현재 결과는 100·17·117이다. 없는 컬렉션은 0으로 표시한다.
- 임베딩 입력/캐시는 기존 GMS 설정을 사용한다. .env에는 GMS_API_KEY·GMS_BASE_URL·GMS_EMBEDDING_MODEL이 필요하고 --generate에는 GMS_MODEL도 필요하다. 캐시가 없는 새 환경의 재생성은 임베딩 API를 호출한다. 키 값을 출력하지 않는다.
- 모델·서버가 바뀌면 다른 임베딩 공간을 섞지 않도록 색인을 중단한다. 새 --db-dir로 다시 생성하거나 기존 DB를 별도로 정리한 후 재생성한다. 검색은 현재 문서 집합/검색 텍스트와 DB가 다르면 재색인을 요구한다.
- CLI 기본은 --retriever chroma다. --retriever semantic은 이전 SQLite 캐시/Python 코사인 기준선, --retriever lexical은 외부 호출 없는 어휘 기준선이다. 기존 evaluate_semantic.py의 고정 평가는 이전 semantic_retrieve 경로이며 Chroma 기반 전체 생성 평가로 간주하지 않는다.
- scripts/index_vectors.py는 DB 생성/갱신·실제 count·Chroma 검색을 담당하고 tests/test_vector_index.py는 실제 임시 Chroma DB를 사용해 영속성·갱신·중복·삭제·검색 조건을 검증한다. 외부 API 없는 합성 벡터 검사와 실제 캐시 벡터 검색을 구분한다.

## 외부 문서 수집·선별·청킹 — W036

```powershell
python scripts/collect_source_docs.py --selected recipe:28 --index
python scripts/index_vectors.py --count
python scripts/recipe_rag.py --selected recipe:28 --question "이 요리의 재료와 조리법 알려줘"
```

- 제한 환경에서는 레포의 원본 API 응답(data/raw/recipes/)·공식 본문을 제공 문서 묶음으로 읽는다. 새 웹 검색/다운로드를 하는 명령은 아니다. GMS는 실제 전문가 검색어 추출·후보 선별·임베딩에 사용한다.
- PROMPT1은 도메인 전문가 역할+검색어 JSON 배열, PROMPT2는 제목/요약만 보고 후보 ID JSON 배열을 선택한다. 선택 recipe ID 자체의 원본은 모든 관련성/길이/후보 상한 규칙보다 우선한다. 유효하지 않은 JSON·후보 ID는 거부한다.
- config/rag_sources.json: chunk_size, chunk_overlap, min_document_chars, max_candidates_per_query. 설정 변경은 --config 경로로 적용한다. 본문은 글자 단위로 분할하며 기본 1000자·200자 중복이다.
- --bundle 경로는 제공 문서 JSON 배열을 읽는다. 필수 필드는 document_id/title/summary/text/source_url/item_ids(관련 recipe ID 배열). 선택 항목 자체 문서가 반드시 포함돼야 한다. 선택 항목 연결은 원본 ID로 확인된 자료를 제공한다.
- data/rag/source_cache/는 검색어별 후보·LLM 추출/선별 결과 캐시이며 Git 제외다. 묶음 변경 시 검색 결과가 무효화된다. 현재 CLI는 공개 레시피 메타데이터만 입력으로 받아 실제 사용자 질문·신체 정보를 자동 저장하지 않는다.
- data/rag/source_chunks.jsonl은 수집된 항목별 청크·출처·관련 ID, source_reports/항목번호.json은 실행 근거다. 출력은 해당 항목만 교체하며 다른 항목은 유지한다. 같은 문서라도 항목ID:문서ID해시:순번으로 분리한다.
- 새 source_chunks.jsonl이 있으면 기존 고정 발췌 17개를 활성 검색 문서에서 대체한다. 기존 원문/발췌 파일은 삭제하지 않는다. 현재 대표 recipe:28만 처리해 활성 문서는 레시피 100개+수집 청크 1개(101개)다. 일반 지침·전체 레시피 수집까지 완료한 것은 아니다.
- 이후 다른 항목을 처리하면 source_docs 건수가 증가한다. DB 파일 없이 원본 데이터와 캐시 또는 GMS 설정으로 다시 생성할 수 있다. UI와 전체 수집/품질 평가는 별도 후속 작업이다.

## LangGraph 답변·근거 출력 — W038

```powershell
python -m pip install -r requirements.txt
python scripts/recipe_rag.py --selected recipe:28 --question "이 요리의 재료와 조리법 알려줘" --generate
python scripts/evaluate_answer_graph.py
```

- scripts/rag_graph.py: 실제 LangGraph retrieve/generate 두 노드. 선택 원본 메타데이터를 먼저 보존하고 관련 외부 검색 결과와 ID 중복 제거·번호·유형을 부여한다. 추가 검색이 실패해도 선택 메타데이터는 유지하고 warnings로 알린다.
- config/rag_answer.json: top_k(1~10)·min_score(0~1). --answer-config 경로로 변경한다. Top-k는 컬렉션별 상한, 선택 메타데이터는 항상 별도로 포함한다.
- 생성 evidence에는 evidence_number, evidence_type(item_metadata/external_document), source_label이 있다. 제외 메뉴는 recommendation_blocked 표시를 유지하고 현재 생성은 추천 불가 안내로 차단한다.
- --generate 출력은 generation.answer·citations·citation_notice와 warnings다. 미인용 검색 원문은 출력하지 않는다. citations에는 번호·ID·제목·URL·유형·원문 파일/레코드가 있고 실제 인용만 포함한다. 검색 전용 명령은 진단 목적으로 evidence를 출력한다.
- 유효하지 않은 번호·ID·유형은 답변 차단 및 안내를 반환한다. 인용 존재 검사는 의미적 지지를 보장하지 않으며 generated_unreviewed는 최종 내용 검토 전 상태다.
- evaluate_answer_graph.py는 고정 공개 질문 A1만 실행해 data/rag/answer_graph_evaluation.json에 저장한다. 모델 호출과 비용이 발생할 수 있다. 일반 CLI의 사용자 입력·답변은 자동 기록하지 않는다. 실제 생성 성공·근거 번호와 반환 출처 일치를 확인했으며 전체 생성 품질 평가는 아니다.
- UI는 만들지 않았다. 후속 화면에서는 generation.citations만 근거 패널로 표시하고 citation_notice와 warnings를 사용자 안내에 연결한다.

## 주요 파일

| 경로 | 역할 |
|---|---|
| scripts/collect_nutrition.py | 영양 API 수집·정규화 |
| scripts/collect_recipes.py | 레시피 수집·재료/조리 단계 정리 |
| scripts/collect_guidelines.py | 공식 웹 본문·출처·이용 조건 수집 |
| scripts/prepare_guideline_chunks.py | 원문 위치·해시 검증 및 근거 발췌 |
| scripts/build_menu_catalog.py | 이름 기반 음식 후보 연결 |
| scripts/menu_personalization.py | 입력 구조·제외·선호 검사, 에너지 계산 미구현 |
| scripts/audit_recipe_basis.py | 과거 PDF 대조. 원문 삭제로 현재 재실행 불가 |
| scripts/triage_recipe_basis.py | 웹 영양 기준 검토 우선순위 생성 |
| scripts/recipe_rag.py | 검색 문서 구성·CLI·생성·인용 ID 검사 |
| scripts/semantic_search.py | 검색 문자열·임베딩 캐시·코사인 검색·검색어 확장 |
| scripts/index_vectors.py | ChromaDB 두 컬렉션 재구축·고정 ID 갱신·건수 조회·검색 |
| scripts/collect_source_docs.py | 전문가 검색어·로컬 묶음 검색·LLM 후보 선별·캐시·항목별 청킹 |
| scripts/rag_graph.py | LangGraph 두 노드·메타데이터 보존·근거 병합/번호/유형 |
| scripts/evaluate_answer_graph.py | 고정 공개 질문의 실제 그래프 생성·인용 검증 |
| config/rag_answer.json | Top-k·최소 의미 유사도 설정 |
| config/rag_sources.json | 청크 크기·중복·최소 본문 길이·후보 상한 설정 |
| scripts/evaluate_semantic.py | 고정 질문 평가·JSON 및 결과 Markdown 저장 |
| tests/test_menu_data.py | 연결 후보·입력·제외 검사 |
| tests/test_recipe_rag.py | 검색 문서·검색·생성 검사 |
| tests/test_semantic_search.py | 임베딩 캐시·검색 검사 |
| tests/test_vector_index.py | 실제 Chroma DB 영속성·중복 방지·갱신·검색 검사 |
| tests/test_source_docs.py | 검색어 JSON·자체 문서 우선·캐시·청킹·항목별 ID/저장 검사 |
| tests/test_rag_graph.py | 실제 그래프·선택 문맥·설정·근거 번호/유형·인용 안내 검사 |
| requirements.txt | 확인된 ChromaDB·OpenAI SDK 버전 |
| data/recipes.json 및 CSV | 레시피 100건 |
| data/foods.json 및 CSV | 100g 기준 영양 음식 100건 |
| data/guidelines/manifest.json | 공식 자료별 출처·이용 조건·본문 해시 |
| data/guidelines/texts/*.txt | 공식 웹 본문 |
| data/guidelines/chunks.jsonl | 원문 근거 17개·위치·활용 제한 |
| data/guidelines/allowed_candidates.json | 허용 확인 이력이 있는 후보 메타데이터 |
| data/rag/documents.jsonl | 레시피 100개·지침 17개 검색 문서 |
| data/rag/embeddings.sqlite3 | 로컬 임베딩 캐시, Git 제외 |
| data/rag/chroma/ | 두 컬렉션의 ChromaDB 영속 저장소, Git 제외 |
| data/rag/source_chunks.jsonl | 새 수집 파이프라인의 항목별 근거 청크 |
| data/rag/source_reports/ | 항목별 실제 검색어·후보·선별/필수 ID·캐시·실행 설정 |
| data/rag/source_cache/ | 수집 검색어·LLM 단계별 캐시, Git 제외 |
| data/rag/semantic_evaluation.json | 최신 고정 평가 결과 |
| data/rag/semantic_evaluation_W026.json | 과거 비교 결과 |
| data/raw/ | 수집 원본 |

## RAG 실행·평가

# 최소 RAG 검증

2026-10-21. 사용자 요청에 따라 UI보다 검색·답변·출처 검증을 우선한다. 1인분 근거 확대는 보류한다.

## 평가 질문과 기대 동작

| ID | 질문 / 구조화 입력 | 기대 동작 |
|---|---|---|
| Q1 | 두부를 쓰는 레시피 추천해줘 | 두부 재료가 있는 메뉴와 출처 반환 |
| Q2 | 두부 요리 추천해줘 / 제외: 새우·계란·우유 | 동의어 포함 제외 검사, 선택 메뉴에도 제외 조건 우선 적용 |
| Q3 | 이 요리의 재료와 조리법 알려줘 / 선택: recipe:28 | 선택 메뉴 원문 우선 포함, 재료·단계와 출처 일치 |
| Q4 | 키 170cm, 체중 70kg이고 활동량은 적어. 두부로 저녁 추천해줘 | 두부 후보 안내 가능, 에너지 계산 미구현 명시, 적정 열량·제공량 단정 금지 |
| Q5 | 새우 두부 계란찜 1인분의 열량은 얼마야? / 선택: recipe:28 | API 원문 값과 기준량 미확인 구분, 1인분 값 단정·환산 금지 |

LLM 답변마다 메뉴/재료 일치·제외 준수·기준량 표현·출처 일치·근거 부족 대응을 통과/실패/미검증으로 평가한다. 자동 검색 검사를 생성 답변의 품질 검증으로 간주하지 않는다.

2026-10-21 연결 확인(W021): 사용자 지정 모델은 `gpt-6-luna`. `open_api_key`·`openai_api_key`·`gms_model` 소문자 별칭도 읽도록 지원했다. 환경변수가 `.env`보다 우선한다. 설정 존재와 지정 모델 일치를 확인했으나 실제 요청은 HTTP 401 `AuthenticationError`로 실패했다. Q1~Q5 생성 답변 품질은 미검증이며 키 재확인 후 재시도해야 한다. `.env`는 변경하지 않았다.

## 실행

현재 인증키 변수는 `GMS_API_KEY`다(W024). 과거 W021의 키 별칭 지원은 이 변경으로 대체하며 `gms_api_key` 별칭만 지원한다. 모델은 `GMS_MODEL=gpt-6-luna`, 주소는 `GMS_BASE_URL=https://gms.ssafy.io/gmsapi/api.openai.com/v1`을 사용한다.

어휘 검색·문서 생성(외부 호출 없음):

```powershell
python scripts/recipe_rag.py --retriever lexical --question "두부를 쓰는 레시피 추천해줘" --exclude 새우
python scripts/recipe_rag.py --retriever lexical --question "재료와 조리법 알려줘" --selected recipe:28
python -m unittest discover -s tests -v
```

`data/rag/documents.jsonl`에는 recipes 100개와 guidelines 17개를 서로 다른 collection·고유 ID로 기록한다. 원본은 유지한다. 재실행 시 파생 문서를 교체해 누적 중복을 방지한다.

기본 검색은 GMS 임베딩과 코사인 유사도 검색이다(W026). `--retriever lexical`을 지정하면 이전 어휘 검색 기준선으로 비교한다. 임베딩 캐시는 SQLite에 보관하며 전용 Vector DB·LangGraph는 아직 적용하지 않았다. 자연어 제외 조건 자동 추출은 미구현이므로 `--exclude`를 명시해야 한다. 복합 재료·동의어 사전의 완전성은 보장하지 않는다.

임베딩 모델은 `GMS_EMBEDDING_MODEL=text-embedding-3-small`이며 답변 모델 `gpt-6-luna`와 별도다. `scripts/semantic_search.py`가 문서 117개와 질문을 벡터화한다. 서버 주소·모델·본문 해시로 캐시를 구분해 변경분만 요청하고, 현재 문서 ID만 검색해 삭제 문서의 잔여 캐시를 결과에 포함하지 않는다. 로컬 `data/rag/embeddings.sqlite3`는 Git 제외다. 질문 원문은 캐시에 저장하지 않지만 질문 벡터는 남는다.

```powershell
python scripts/recipe_rag.py --question "콩으로 만든 부드러운 식재료를 쓰는 요리 추천해줘" --generate
python scripts/recipe_rag.py --retriever lexical --question "두부 요리 추천해줘"
python scripts/evaluate_semantic.py
```

평가 스크립트는 고정 공개/합성 질문만 실행하고 `data/rag/semantic_evaluation.json` 및 [SEMANTIC_RESULTS.md](SEMANTIC_RESULTS.md)를 갱신한다. 일반 CLI 질문은 Markdown에 자동 기록하지 않는다. 임계값 0.25·컬렉션별 Top-3은 초기 설정이며 의미적 적합성·영양 조건 충족의 보장이 아니다. 관련 없는 입력에 대한 무응답 및 검색 유형별 문서 선택 개선은 후속 과제다. API 연동은 [공식 임베딩 명세](https://developers.openai.com/api/reference/python/resources/embeddings/methods/create)를 참조했다.

LLM 생성은 `.env` 또는 환경변수에 `GMS_API_KEY`, `GMS_MODEL`, `GMS_BASE_URL`을 설정한 후 `--generate`를 추가한다. 모델은 자동 선택하지 않는다. 질문과 검색 문서가 설정된 GMS 서버로 전달된다. 입력·답변은 파일에 자동 저장하지 않는다. 생성 API 호출에는 설치된 `openai`가 필요하며 연동 방식은 [공식 Python SDK 문서](https://developers.openai.com/api/reference/python)를 따른다.

검색 자료를 문맥으로 전달해 근거 한정 답변을 요청하고, 반환 인용 ID가 검색 결과에 존재하는지 검사한다. 인용 실패 시 답변을 내보내지 않는다. ID 존재 검사는 주장과 근거의 의미 일치를 보장하지 않는다. `generated_unreviewed`는 사람의 내용 검토 전 상태다. 키/모델 미설정은 `not_configured`, 외부 오류는 `api_error`로 반환하며 예외 원문·키를 출력하지 않는다.

## 현재 검증 범위

W027 검색 개선: 임베딩 입력에서는 API 영양 원문·공통 기준량 안내를 제외하고 메뉴·재료·조리법을 사용한다. 답변 문맥에는 원본 영양값과 안내를 유지한다. 선택 메뉴 질문은 해당 메뉴만, 소금/나트륨 등 지침 질문은 지침만, 일반 레시피 추천은 레시피만 검색한다. 혼합 질문은 두 컬렉션을 사용한다. 현재 유형 판별은 제한된 규칙이며 복합 질문의 완전성은 미검증이다.

선택 메뉴가 없는 일반 레시피 질문은 `gpt-6-luna`로 식재료 묘사를 검색어로 확장한 후 임베딩한다. 확장어는 답변 근거·영양값·제외 조건으로 사용하지 않는다. 확장 실패 시 원 질문으로 검색한다. 별도 생성 호출이 추가되며 지연/비용 비교는 미측정이다. 기존 W026 결과는 `WORKLOG.md`·`data/rag/semantic_evaluation_W026.json`에 보존했다.

2026-10-21 GMS 연결 확인(W023): 사용자 안내에 따라 `GMS_BASE_URL=https://gms.ssafy.io/gmsapi/api.openai.com/v1`을 `.env`에 설정했다. SDK는 이 주소에 `/responses`를 붙인다. 기존 키·모델은 유지했다. 두부 추천 질문으로 `gpt-6-luna` 실제 생성에 성공했으며 recipe:137·28·280 인용 ID가 검색 결과에 존재함을 검사했다. 생성 답변의 기준량 미확인 표현을 확인했다. Q1~Q5 전체 내용 평가는 아직 미완료다. W021·W022의 401은 OpenAI 직접 서버 요청 결과이며 GMS 키 무효를 증명하지 않는다.

문서 구성·검색·제외 우선·선택 ID·근거 없음·미설정 처리를 로컬 테스트로 검사한다. 실제 LLM 생성 답변 Q1~Q5의 내용 품질은 실행 후 별도로 기록한다. 숫자 개인화·알레르기 안전·성능 개선 효과는 미검증이다.


## 데이터 수집과 파일 상세

# 초기 음식 영양 데이터

## 공식 식생활 설명 근거

정부 공식 웹 문서 5건과 원문 근거 17개를 `guidelines/`에 확보했다. 출처·발행일·공공누리 제1유형 텍스트 이용 조건과 범위는 [근거 자료 안내](FILES.md) 참조. 영양 계산 기준이나 Vector DB 색인 완료를 뜻하지 않는다.

## 원문에서 1인분 기준을 확인한 레시피

PDF를 사용하지 않는 후속 검토는 [공식 웹 근거 검토](FILES.md) 참조. `python scripts/triage_recipe_basis.py`로 100개 레시피의 검토 우선순위와 계산 차단 상태를 `recipe_web_review.json`에 생성한다. 우선 후보 6개이며 신규 기준량 확정은 0개다.

`recipe_serving_menus.json`은 공식 식약처 책자와 이름·수량 포함 재료 문장·5종 영양값을 대조한 6개 메뉴입니다. 값은 **1인분 기준**이며 g 환산은 사용할 수 없습니다. 제외 재료 검토·개인화 식단 전체 구현을 완료한 데이터가 아닙니다.

`recipe_basis_audit.json`은 메뉴별 근거 페이지·URL·원문 해시·미확인 상태를 보관합니다. 재현 방법과 공식 출처는 [레시피 영양 기준 확인](FILES.md) 참조. 기존 `recipes.json`은 수정하지 않았으며 전체 100개로 기준을 일반화하지 않습니다.

## 연결 후보·개인화 준비

`foods_extended.json`은 기존 100개를 보존하며 초기 100개를 포함하는 유효 음식 759개의 후보 풀입니다. `menu_catalog.json`은 레시피 100개를 중심으로 재료·단계·후보 음식 ID를 모은 파생 데이터입니다.

`recipe_food_candidates.csv`/JSON에 이름 기반 21쌍(레시피 19개)을 기록했고 `matching_report.json`에 수집/연결 결과가 있습니다. **검토 확정된 영양 연결은 0건**이며 이름이 같아도 동일한 영양값을 보장하지 않습니다. 원본 추가 응답은 `raw/matching/` 참조.

실행법·입력 계약·제외 조건·검증 한계는 [연결 명세](FILES.md)를 읽습니다. 기존 수집 파일과 개인 프로필을 임의로 합치거나 미검토 영양값으로 계산하지 않습니다.

## 레시피 데이터

`recipes.json`은 메뉴명·재료 원문·번호별 조리 단계·이미지 주소·출처를 포함한 레시피 100건입니다. `recipes.csv`는 조리 단계를 한 셀의 여러 줄로 합친 엑셀용 정리본입니다. 원본은 `raw/recipes/`, 수집 조건·분류별 건수는 `recipe_collection_report.json`에 있습니다.

재수집: `python scripts/collect_recipes.py --limit 100`. `.env`에 `FOOD_RECIPE_API_KEY`가 필요하며 기존 결과를 갱신합니다. 이미지 주소만 저장하며 이미지 파일은 내려받지 않습니다.

출처: [식약처 조리식품의 레시피 DB](https://www.foodsafetykorea.go.kr/api/newDatasetDetail.do?svc_no=COOKRCP01), 서비스 `COOKRCP01`. 이용 조건은 재배포 전에 추가 확인해야 합니다. 기존 음식과의 매칭은 `unreviewed`이며 음식 ID를 임의 연결하지 않았습니다. 레시피의 `nutrition_raw`는 기준량 확인 전까지 영양 계산에 사용하지 않습니다.

## 영양 데이터

식약처 공식 API에서 수집한 음식 100개입니다. 수집 일시·조건은 `collection_report.json`에 기록합니다.

- `foods.csv`: 엑셀에서 확인할 정리본(UTF-8 BOM).
- `foods.json`: 후속 계산·색인에 사용할 정리본.
- `raw/nutrition_page_001.json`: API 원본 응답.
- `api_spec.json`: 공식 공공데이터포털 페이지에 포함된 Swagger 명세.

재수집: 프로젝트 루트에서 `python scripts/collect_nutrition.py --limit 100`을 실행합니다. `.env`의 `FOOD_NUTRITION_API_KEY`가 필요합니다. 기존 정리본은 갱신됩니다. 연결만 확인하려면 `--probe`를 사용합니다.

영양값은 `basis_label` 기준입니다. 현재 전 항목이 **100g 기준**이며 한 그릇·한 끼의 수치가 아닙니다. 단위는 필드명의 `_kcal`, `_g`, `_mg`를 따릅니다. 결측값은 `null`이며 0과 다릅니다. 음식 ID 중복과 기준량·열량·3대 영양소의 유효성을 확인한 항목을 저장합니다.

현재는 API 순서대로 확보한 초기 표본입니다. 밥류 51개, 빵 및 과자류 39개, 면 및 만두류 10개로 식단 추천용 분류 다양성 보완이 필요합니다. 재료·조리법과 레시피 매칭은 아직 확인하지 않았습니다.

출처: [식품의약품안전처_식품영양성분DB정보](https://www.data.go.kr/data/15127578/openapi.do). 2026-10-21 확인 시 무료·이용허락범위 제한 없음으로 안내되어 있습니다. 각 항목의 원자료 출처와 기준일은 JSON 및 원본 응답을 함께 확인합니다.

## 공식 웹 자료와 이용 조건

# 공식 식생활 RAG 근거

확보일: 2026-10-21. **5건 텍스트 확보·17개 원문 근거 준비 완료, 임베딩은 W026~W027에서 실행 확인, 전용 Vector DB 미구현**. PDF 대신 웹 텍스트를 수집하며 최신 보충 자료와 기존 지침을 구분한다.

| 문서 ID | 공식 자료 | 발행일 | 설명할 수 있는 질문 |
|---|---|---|---|
| diet_practice_checklist_2025 | [식생활 실천 점검표 안내](https://www.rda.go.kr/board/board.do?boardId=farmprmninfo&dataNo=100000802463&mode=updateCnt&prgId=day_farmprmninfoEntry) | 2025-05-02 | 식품 섭취·식습관·식생활 문화의 점검 |
| nutrition_policy_2026 | [식약처 건강 식생활·영양정보 정책](https://www.korea.kr/news/policyNewsView.do?newsId=148957973) | 2026-01-14 | 정책 배경(개인 영양 권고용 아님) |
| dietary_guidelines_2021 | [한국인을 위한 식생활지침 발표](https://www.korea.kr/news/policyNewsView.do?newsId=148886239) | 2021-04-14 | 왜 여러 식품군을 균형 있게 구성하는가? |
| healthy_home_eating_2021 | [집콕시대, 상황별 건강 식생활 실천 가이드](https://www.korea.kr/briefing/policyBriefingView.do?newsId=148888295) | 2021-06-08 | 왜 양념·국물·설탕/시럽의 양을 조절하는가? |
| hmr_nutrition_2020 | [찌개류 가정간편식, 한 끼 식사로는 영양성분 부족](https://www.korea.kr/briefing/policyBriefingView.do?newsId=148874394) | 2020-07-07 | 간편식 선택 시 열량·나트륨 표시를 왜 확인하는가? |

기관·원문 URL·게시일·확인일·이용 조건·본문 해시·출처표시 문구는 `manifest.json`이 기준이다. 게시일은 지침 개정일과 같다고 가정하지 않는다.

## 파일과 재현

- `allowed_candidates.json`: robots 허용 확인 후보만 등록한 목록. 식약처 신규 자료는 상세 본문·이용 조건 확인 전까지 링크 메타데이터만 보관하며 색인 대상이 아니다. 농촌진흥청은 이미 확보되어 중복 추가하지 않았다. 질병관리청 후보는 미편입.

- `texts/*.txt`: 공식 HTML 본문 텍스트. 탐색 메뉴·사진/사진 설명·문의 연락처를 제외하고 공백을 정리했다. PDF 사본이 아니다.
- `manifest.json`: 원문·버전·기관·변환·라이선스·활용 제한.
- `chunks.jsonl`: 선택한 원문 문장/문단 17개. 제목·원문 URL·기관·게시일·문서 ID·텍스트 줄 번호·활용 범위를 포함한다. `policy_background_only`는 개인별 추천 근거로 사용하지 않는다.
- 수집: 프로젝트 루트에서 `python scripts/collect_guidelines.py`. API 키·외부 패키지 불필요, 기존 텍스트/메타데이터 갱신.
- 근거 준비: `python scripts/prepare_guideline_chunks.py`. 로컬 본문 해시와 선택 위치를 확인하며 네트워크를 사용하지 않는다.
- 웹 자료는 페이지가 없어 `page=null`, `line_start`/`line_end`와 `section`으로 위치를 식별한다.

## 이용 조건

- 정책브리핑 4건은 텍스트 한정 공공누리 제1유형, 농촌진흥청 1건은 게시물 공공누리 제1유형을 확인했다. 표시가 없거나 바뀌면 수집기는 중단한다.
- 2026-10-21 robots 조회: 정책브리핑 일반 User-agent는 `/` 허용. 농촌진흥청은 `/` 허용, 검색·파일 다운로드 일부 제한. 이번 게시물 본문은 제한 경로에 해당하지 않는다. 첨부파일은 수집하지 않았다.
- 인용 화면에는 `attribution`과 원문 링크를 표시한다. 변환·발췌 사실도 밝힌다.
- 이미지·일러스트·동영상은 허용 대상으로 가정하지 않았고 다운로드하지 않았다.
- 검토 중 발견한 당류 안내(2024, newsId=148925854)는 별도 이용 협의 안내, 당류 안내(2021, newsId=148883542)는 제4유형이어서 현재 RAG 대상에서 제외했다. 기관 공식 자료라는 이유만으로 모두 재사용하지 않는다.

## 적용 범위와 제한

- 확보한 것은 **공식 지침 발표·실천 교육 웹 문서**다. 한국인 영양소 섭취기준 전문이나 지침 PDF 전체를 확보한 상태는 아니다.
- 일반 성인의 음식 선택 이유 설명용이며 질환 치료·임신/수유·미성년 대상 맞춤 기준으로 사용하지 않는다.
- 2025·2026 게시 자료가 기존 지침을 대체하는 새 지침이라는 뜻은 아니다. 지침 개정 여부와 최신 게시일을 구분하며 다른 버전 수치 기준을 혼합하지 않는다.
- 초기 근거에는 균형식·나트륨/당류 실천·영양표시 확인 문장만 선택했다. 역사적 조사 평균·개인별 권고로 오해할 수 있는 숫자·정책 사업 내용은 색인 준비본에서 제외했다.
- 특정 메뉴가 실제로 저나트륨인지·제외 재료를 충족하는지는 이 문서가 증명하지 않는다. 음식 수치·재료 데이터로 별도 검사한 후 일반 원칙과 연결한다.
- 예: 코드로 동일 기준량의 나트륨 차이를 확인 → 비교 수치 표시 → 국물/양념 조절 지침으로 선택 이유 설명. ‘이 메뉴가 질환을 개선한다’는 설명은 금지한다.
- **에너지 필요량 공식·활동량 계수·영양소 권장 비율·나트륨/당류 개인 목표량은 아직 확보/확정하지 않았다.** 이 파일을 계산 기준표로 사용하지 않는다.
- 나중에 외부 문서 컬렉션으로 색인할 때 `food_scope=general`을 유지하고 음식별 레시피 근거와 구분한다. 검색 품질·주장/인용 일치 검증은 미수행이다.

## robots.txt 점검 — 2026-10-22 (W028)

- LLM 확인 결과 저장 본문 5건은 정책브리핑·농촌진흥청 robots 허용 경로이며 삭제 대상은 0건이다. 근거 17개 유지.
- 확인: https://www.korea.kr/robots.txt 및 https://www.rda.go.kr/robots.txt. 농촌진흥청 검색·파일 다운로드 제한은 저장된 게시물 경로에 해당하지 않는다.
- 식약처 후보는 본문 없이 메타데이터만 있다. 이번 robots 재조회는 로컬 네트워크 및 웹 도구 접근 실패로 미확인이다. 기존 2026-10-21 허용 기록 유지. 질병관리청 후보는 기존에도 미편입이다.
- 본문 재수집·임베딩 재생성·기능 테스트는 실행하지 않았다. 남은 확인은 식약처 후보 robots 재조회다.

## 음식 연결·개인화 입력

# 음식 연결과 개인화 구현 기준

갱신일: 2026-10-21. 구현 상태와 향후 설계를 구분한다.

> D006에 따라 식단용 메뉴 확보는 **레시피 자체 영양의 원문 대조**를 우선한다. 현재 확인된 6개와 활용 제한은 `docs/FILES.md` 참조. 아래 이름 기반 연결은 보조 후보 탐색 기능으로 유지한다.

## 구현됨

- `scripts/build_menu_catalog.py`: 음식 이름의 공백·구분자 정규화 후 동일/포함 관계로 상위 3개 후보 생성.
- `--enrich`: 공식 영양 API를 100건씩 20페이지 조회하여 유효 음식만 별도 보관한다. 기존 100개 파일은 수정하지 않는다.
- `data/foods_extended.json`: 음식 후보 확장본. 영양값·기준량이 유효한 `음식`만 포함하며 759개 확보.
- `data/recipe_food_candidates.csv` 및 JSON: 검토할 21쌍. 레시피 19개에 후보 존재, 나머지 81개는 미연결.
- `data/menu_catalog.json`: 레시피 ID를 중심으로 재료·조리법·후보 음식 ID를 연결한 100개 메뉴. 확정 영양 연결은 0건.
- `data/matching_report.json`: 위 건수와 연결 정책. 이름 유사도는 문자 유사도이며 정확도·확률이 아니다.
- `scripts/menu_personalization.py`: 7종 입력의 구조 검사, 제외 재료 검출·일부 동의어 처리, 선호 일치 정렬.
- 입력 계약: `age`, `sex`, `height_cm`, `weight_kg`, `activity_level`, `preferences`(문자열 목록), `excluded_ingredients`(문자열 목록).
- 신체 수치는 양수·유한값, 나이는 정수, 성별/활동량은 비어 있지 않은 문자열이어야 한다. 적용 가능한 성별/나이/활동량 분류의 검증은 공식 선정 후 추가한다.
- 모든 결과에 차단 사유를 기록한다. 에너지 모델이 미구현이므로 현재 개인화 추천 준비 완료로 표시되는 메뉴는 없다.

## 연결을 확정하려면 필요한 근거 — 미구현

1. 레시피 ID와 음식 ID, 출처·데이터 기준일을 대조한다.
2. 메뉴 유형·핵심 재료·조리 상태·추가 소스·변형 여부를 확인한다.
3. 영양 기준량(g/ml), 조리 후 중량·섭취량, 수치 적용 대상을 확인한다. 재료 중량 단순 합계로 조리 후 중량을 추정하지 않는다.
4. `exact_recipe`(같은 조리식품 근거 확인) / `reference_only`(일반 음식 참고값) / `rejected`로 검토 결과·근거·검토일·주체를 보관한다.
5. 정확한 레시피 연결이 확인된 경우만 `nutrition_food_id`를 확정하고 `nutrition_ready`를 활성화한다. 현재 검토 결과를 읽어 승인 적용하는 기능은 없다.

이름이 같은 호박죽도 조리 비율이 같다는 근거가 없으므로 확정하지 않았다. `햄버거스테이크`와 `햄버거` 같은 포함 관계는 잘못된 후보일 수 있다. 후보표는 실제 추천이나 자동 연결 결과가 아니다.

## 개인화 고도화 순서 — 계획

1. 공식 지침과 에너지 계산식의 성인 적용 범위·버전·성별/활동량 분류를 확정한다. 미성년·임신/수유 등 적용 제외 조건을 별도 정의한다.
2. 제외 재료를 가장 먼저 검사하고, 복합 양념·동의어·재료 누락 여부를 검토한다. 재료 검토 불충분 메뉴는 제외 조건 충족으로 판정하지 않는다.
3. 검증된 영양값과 실제 섭취량으로 합계를 계산하고 영양 조건을 검사한다. 통과한 후보 내에서 선호를 반영한다.
4. RAG는 관련 지침으로 추천 이유를 설명하고 코드가 음식 ID·섭취량·영양 합계를 다시 검사한다.

현재 동의어 사전은 일부 계란·유제품·소고기·대두 표현만 지원한다. 문자열 검출은 복합 원료·교차접촉·모든 알레르기 유발 재료를 포괄하지 않으며 재료 안전 판정을 대체하지 않는다. 신체 수치가 달라도 현재는 열량 목표를 산출하지 않는다.

## 검증 근거와 정확도 평가 계획

- 실행한 회귀 검사: `python -m unittest discover -s tests -v`, 6개 통과.
- 검사 항목: 이름 일치의 미확정 유지, 무관한 이름 미연결, 잘못된 입력 거절, 계란/유제품 동의어 검출, 미검토 메뉴 차단, 선호보다 제외 우선.
- 실데이터 연결 검사 결과는 `data/matching_report.json` 참조. 확정 연결률 0이며 추천 정확도 평가는 아직 없다.
- 향후 평가: 검토 정답 연결표에 대한 후보 포함률·잘못된 확정 연결 수, 제외 재료 조건 위반 수, 영양 합계 오차·계산식 재현성, 선호 충족 여부를 동일 데이터로 기록한다.
- 개인화 전후 비교는 평가용 입력과 정답 기준을 먼저 고정한다. 입력되는 신체정보가 실제 사람의 개인정보가 되지 않도록 합성 사례를 사용한다.

## 실행

- 로컬 후보 재생성: `python scripts/build_menu_catalog.py`.
- 영양 후보 추가 조회 후 재생성: `python scripts/build_menu_catalog.py --enrich`.
- 두 명령 모두 파생 카탈로그·후보표를 갱신한다. 검토 결과는 별도 보관해야 한다. `.env` 키·개인 프로필을 결과 파일에 넣지 않는다.

## 과거 영양 대조

# 레시피 영양 기준 확인

> 2026-10-21 사용자 요청으로 로컬 PDF를 삭제했다. 아래 6개는 삭제 전 대조 결과이며 원문 URL·해시·페이지와 파생 데이터를 보존한다. 현재 로컬 원문으로 재검증할 수 없고 재확보 전 감사 스크립트는 중단한다. 이번 작업에서는 PDF를 재다운로드하지 않는다.

확인일: 2026-10-21. D006 및 W006 참조.

## 결론과 범위

- 식단용 데이터는 **레시피 자체 영양정보의 기준을 확인하는 방식**을 우선한다. 일반 음식과의 이름 연결은 보조 탐색으로 남긴다.
- 공식 API 명세의 `INFO_WGT` 설명은 중량(1인분)이다. 다른 영양 필드의 분모·단위가 모두 명시된 것은 아니므로 API 전체가 1인분 기준이라고 단정하지 않는다.
- 식약처 공식 책자에서 메뉴별 ‘영양 성분(1인분)’과 단위를 확인하고, API의 이름·영양값 5종·수량 포함 재료 문장을 대조했다.
- 현재 100개 중 **6개**가 엄격한 대조 기준을 통과했다. 나머지 94개는 불일치 확정이 아니라 **이 방법으로 확인되지 않은 상태**다. 다른 책자·이름 차이·줄바꿈/표기 차이·내용 차이를 추가 검토해야 한다.
- 이 확인은 문서와 API 수치의 일치이며 영양소의 실험적 정확성이나 개인별 건강 효과 검증이 아니다.

## 공식 근거

- [COOKRCP01 API 명세](https://www.foodsafetykorea.go.kr/api/newDatasetDetail.do?svc_no=COOKRCP01).
- [우리 몸이 원하는 삼삼한 밥상 PDF](https://www.foodsafetykorea.go.kr/upload/20170417/20170417053825_1492418305214.pdf), 식약처 공식 호스팅, 전체 129 PDF 페이지.
- 발행연도·판본은 미확인이다. 업로드 경로의 날짜를 발행연도로 단정하지 않는다. 이 책자를 최신 영양 권고 기준으로 사용한 것은 아니다.
- 로컬 사본 `data/sources/samsam_01.pdf`는 `.gitignore`로 제외했다. 다운로드 URL·SHA-256·페이지는 `data/recipe_basis_audit.json`에 보관한다. 이용 조건 검토 전 재배포하지 않는다.

## 확인한 메뉴

페이지는 인쇄 쪽수가 아닌 PDF의 1부터 시작하는 페이지다.

| recipe_id | 메뉴 | PDF 페이지 | 1인분 열량(kcal) |
|---|---|---|---|
| 28 | 새우 두부 계란찜 | 43 | 220 |
| 32 | 순두부 사과 소스 오이무침 | 47 | 75 |
| 33 | 사과 새우 북엇국 | 49 | 65 |
| 36 | 저염 된장으로 맛을 낸 황태해장국 | 52 | 100 |
| 37 | 된장국 | 53 | 20 |
| 87 | 스트로베리 샐러드 | 105 | 195 |

위 표의 실제 수치는 `data/recipe_basis_audit.json`이 기준이다. 조리 순서 전체의 문자 대조·이미지 시각 대조·복합 재료의 성분 검토는 미수행이다.

## 사용할 수 있는 것과 제한

- `data/recipe_serving_menus.json`: 같은 레시피 ID의 재료·조리법·근거가 확인된 1인분 영양정보를 묶은 6개 메뉴. 원본 `recipes.json`과 별도 보관한다.
- 열량 kcal, 탄수화물/단백질/지방 g, 나트륨 mg를 **원문 1인분 기준**으로 표시할 수 있다.
- 제공량 비례 환산·영양 합계 코드 자체는 아직 구현하지 않았다. 검증 후 0.5인분·1인분 같은 제공량 단위를 사용할 계획이다.
- 100개 중 `INFO_WGT`가 비어 있지 않은 것은 5개지만, 단위·조리 후 중량과 영양 분모 관계는 미검증이다. 숫자가 있다는 이유만으로 g 환산하지 않는다.
- 이번 확인된 6개도 **g 단위 환산은 비활성**이다. 재료 중량 합으로 완성 중량을 대신하지 않는다.
- 사용자 제외 재료 검토·에너지 모델·전체 식단 균형은 별도 과제다. 이 6개만으로 개인화 식단 기능을 완료했다고 판단하지 않는다.

## 재현

1. 과거에는 공식 PDF 로컬 사본을 사용했다. 현재는 PDF 삭제 방침을 유지하며 아래 과거 절차를 실행하지 않는다.
2. `python -m pip install --target .tools/pdf pypdf`로 추출 도구를 설치한다(`.tools/`는 Git 제외).
3. `python scripts/audit_recipe_basis.py`를 실행한다. 기존 감사 보고서와 6개 메뉴 파생본을 갱신하며 API·키를 사용하지 않는다.
4. 스크립트는 모든 수량 포함 재료 문장의 공백 제거 후 포함 관계와 5종 영양값의 정확 일치, 1인분 제목을 검사한다. 자동 추출 오류 가능성은 남아 있다.

## 다음 작업

다른 공식 책자 또는 메뉴별 원문을 추가 대조하여 1인분 기준 확인 메뉴를 확대한다. 식품군 다양성을 확보한 뒤 제공량 계산과 제외 재료 검토를 구현한다. 근거가 부족한 항목은 제공기관 문의 초안을 작성할 수 있지만 외부 문의 전송은 별도 사용자 요청이 필요하다.

## 보류된 웹 근거 검토

# 레시피 공식 웹 근거 검토

확인일: 2026-10-21. 작업 W019. 기존 PDF 대조는 `FILES.md` 참조.

## 확인 결과

- 로컬 레시피 100개를 점검했다. 재료의 `[1인분]` 표기는 1개, `INFO_WGT` 값은 5개다. 이 표기만으로 영양값의 분모나 중량 단위를 확정하지 않는다.
- [공식 API 명세·샘플](https://www.foodsafetykorea.go.kr/api/openApiInfo.do?menu_grp=MENU_GRP31&menu_no=661&show_cnt=10&start_idx=1&svc_no=COOKRCP01)은 중량을 1인분으로 설명하지만 영양 필드 각각의 기준량·단위를 명시하지 않는다. 샘플에서 메뉴 28·29·31 등의 수치를 볼 수 있어도 1인분 영양 확정 근거로 사용하지 않았다.
- [공식 간식 레시피 웹 문서](https://www.foodsafetykorea.go.kr/portal/board/boardDetail.do?bbs_no=bbs039&menu_grp=MENU_NEW03&menu_no=4847&ntctxt_no=22444)는 1인분 영양 표가 있으나 기존 레시피와의 동일성·필요 5종 영양값·개별 이용 조건이 확인되지 않아 계산 메뉴에 편입하지 않았다. 어린이 교육 맥락의 문서이며 성인 권고 근거로 사용하지 않는다.
- 기존 메뉴명 및 1인분·영양성분 조합을 공식 도메인으로 검색했다. 해물김치찌개·버섯순두부찌개·오렌지와 당근 만남주스 대상 검색에서는 결과를 확보하지 못했다. 검색 결과 부재는 공식 자료 부재의 증명이 아니다.
- PDF 검색 결과는 웹 대체 근거로 채택하지 않았다. PDF 파일 다운로드·복구, API 재호출, 신규 본문 저장·색인은 하지 않았다.

## 우선 검토 후보

| recipe_id | 메뉴 | 로컬 단서 | 남은 확인 |
|---|---|---|---|
| 29 | 부추 콩가루 찜 | 재료 `[1인분]` | 영양 표의 분모·단위가 명시된 공식 웹 원문 |
| 108 | 오렌지와 당근 만남주스 | 중량 원문 250 | 중량 단위·완성량·영양 분모 |
| 275 | 해물김치찌개 | 중량 원문 200 | 중량 단위·완성량·영양 분모 |
| 279 | 쑥갓부대찌개 | 중량 원문 200 | 중량 단위·완성량·영양 분모 |
| 282 | 버섯순두부찌개 | 중량 원문 250 | 중량 단위·완성량·영양 분모 |
| 399 | 고추김치 | 중량 원문 40 | 중량 단위·완성량·영양 분모 |

## 산출물과 재현

`python scripts/triage_recipe_basis.py`로 `data/recipe_web_review.json`을 생성한다. 키·네트워크를 사용하지 않으며 입력 해시와 100개 메뉴의 검토 우선순위·차단 상태를 기록한다. 우선순위는 단서의 유무이며 영양 품질 점수가 아니다. 공식 웹 조사는 위 기록의 수동 조사이며 스크립트가 재현하지 않는다.

신규 확정 메뉴는 0개다. 기존 6개의 과거 PDF 대조 상태와 원본 데이터를 유지한다. 모든 웹 검토 항목은 `calculation_allowed=false`, g 환산도 차단한다. 후속 작업은 후보 6개의 공식 메뉴별 페이지·웹 명세 보완 조사이며, 계속 확인되지 않으면 영양 기준량·단위·중량 정의를 묻는 제공기관 문의 초안을 작성한다. 문의 전송은 수행하지 않았다.

## 최근 자료 후보 조사

# 최근 공식 자료 교체 후보

확인일: 2026-10-21. 사용자 요청: 2020~2021 근거를 대신할 최근 공식 정보 조사. 아래는 조사 결과이며 신규 수집·색인 완료 목록이 아니다.

| 후보 | 시점 | 적합한 내용 | 현재 판정 |
|---|---|---|---|
| 질병관리청 ‘영양표시 읽는 법! 알려드리겠습니다!’ | 등록 2025-08-01, 업데이트 2026-05-27 | 제공량·총량·표시 단위·강조 문구와 실제 함량 구분 | 내용 적합, 포털 저작권 정책은 제4유형 안내. RAG 가공 활용 조건 추가 확인 전 미수집 |
| 식약처 ‘국민의 나트륨·당류 섭취 실태분석 결과 발표’ | 2025-07-01 | 최근 공개된 섭취 실태와 영양정보 확인의 필요성 | 공식 게시물은 첨부 중심. PDF 미사용 방침에 따라 첨부 미수집. 조사자료는 2019~2023년이며 개인 권장량이 아님 |
| 농촌진흥청 ‘나의 식생활 실천 점수는? 점검표로 알아보세요’ | 2025-05-02 | 식품 섭취·식습관·식생활 문화의 종합 점검 | 이미 확보된 자료. 2021 지침 기반 도구라는 점을 유지하며 새 지침으로 표시하지 않음 |

## 원문

- 질병관리청: https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=6763
- 포털 이용 정책: https://health.kdca.go.kr/healthinfo/biz/health/portalUseGuidance/hlthinsReqst/hlthinsReqstMth.do?index=1
- 식약처: https://mfds.go.kr/brd/m_99/view.do?company_cd=&company_nm=&itm_seq_1=0&itm_seq_2=0&multi_itm_seq=0&page=49&seq=49163&srchFr=&srchTo=&srchTp=&srchWord=
- 농촌진흥청: `data/guidelines/manifest.json`의 `diet_practice_checklist_2025` 참조.

## 교체 제한

- 최근 게시물이 기존 식생활지침의 개정판을 뜻하지 않는다. 이번 검색으로 별도 최신 지침 개정판을 확정하지 못했다.
- 질병관리청 자료의 본문에 과거 에너지 기준 그림도 있으므로 업데이트 날짜만 보고 모든 수치를 최신 기준으로 사용할 수 없다.
- 제4유형이 모든 RAG 처리를 무조건 금지한다는 법적 결론을 내린 것은 아니다. 현재 프로젝트의 제1유형 우선 정책에 따라 자동 가공본으로 편입하지 않았다.
- 2026-10-21 후보 robots 재검증: 식약처 `mfds.go.kr`와 농촌진흥청 `www.rda.go.kr`의 정확한 게시물 URL은 수집기 User-Agent 기준 허용. 질병관리청 `health.kdca.go.kr/robots.txt`는 연결 오류(URLError)로 미확인이다. 허용으로 단정하지 않는다. 본문 신규 수집은 하지 않았다.
- 2020~2021 기존 자료는 보존했다. 동등한 내용·이용 조건·수집 가능성을 확인한 자료부터 교체해야 하며 최신 정책 기사를 개인 식생활 지침으로 대체하지 않는다.
