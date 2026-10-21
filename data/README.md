# 초기 음식 영양 데이터

## 공식 식생활 설명 근거

정부 공식 웹 문서 5건과 원문 근거 17개를 `guidelines/`에 확보했다. 출처·발행일·공공누리 제1유형 텍스트 이용 조건과 범위는 [근거 자료 안내](guidelines/README.md) 참조. 영양 계산 기준이나 Vector DB 색인 완료를 뜻하지 않는다.

## 원문에서 1인분 기준을 확인한 레시피

`recipe_serving_menus.json`은 공식 식약처 책자와 이름·수량 포함 재료 문장·5종 영양값을 대조한 6개 메뉴입니다. 값은 **1인분 기준**이며 g 환산은 사용할 수 없습니다. 제외 재료 검토·개인화 식단 전체 구현을 완료한 데이터가 아닙니다.

`recipe_basis_audit.json`은 메뉴별 근거 페이지·URL·원문 해시·미확인 상태를 보관합니다. 재현 방법과 공식 출처는 [레시피 영양 기준 확인](../docs/RECIPE_NUTRITION.md) 참조. 기존 `recipes.json`은 수정하지 않았으며 전체 100개로 기준을 일반화하지 않습니다.

## 연결 후보·개인화 준비

`foods_extended.json`은 기존 100개를 보존하며 추가 확보한 유효 음식 759개의 후보 풀입니다. `menu_catalog.json`은 레시피 100개를 중심으로 재료·단계·후보 음식 ID를 모은 파생 데이터입니다.

`recipe_food_candidates.csv`/JSON에 이름 기반 21쌍(레시피 19개)을 기록했고 `matching_report.json`에 수집/연결 결과가 있습니다. **검토 확정된 영양 연결은 0건**이며 이름이 같아도 동일한 영양값을 보장하지 않습니다. 원본 추가 응답은 `raw/matching/` 참조.

실행법·입력 계약·제외 조건·검증 한계는 [연결 명세](../docs/MATCHING.md)를 읽습니다. 기존 수집 파일과 개인 프로필을 임의로 합치거나 미검토 영양값으로 계산하지 않습니다.

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
