"""Fixed synthetic A/B experiment; never accept or persist real user questions.

Compare collection + lexical evidence retrieval + production generation helpers.
This is not the Streamlit/Chroma end-to-end path or an automatic semantic grade.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import tempfile
from statistics import mean
from time import perf_counter

from collect_source_docs import collect, load_bundle, ask_json, PROMPT1, digest, save, string_array
from recipe_rag import documents, generate, retrieve, settings, stage_model

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    dict(id='M1', recipe_id='28', question='새우 두부 계란찜의 재료와 만드는 순서, 찌는 시간을 알려줘.',
         rubric='연두부·새우·달걀 등 원문 재료, 원문 조리 순서, 중간 불 10분을 확인한다. 다른 요리의 방법을 섞지 않는다.'),
    dict(id='M2', recipe_id='36', question='저염 된장으로 맛을 낸 황태해장국은 어떻게 만들고, 짠맛을 줄이는 일반적인 식생활 방법은 뭐야?',
         rubric='황태·무를 끓인 뒤 된장, 콩나물 등 원문 순서를 지킨다. 일반 식생활 설명은 확보된 지침에서만 제시하고 나트륨 감소량은 추정하지 않는다.'),
    dict(id='M3', recipe_id='31', question='방울토마토 소박이에 쓰는 방울토마토 150g의 비타민 C는 몇 mg이야? 모르면 자료 부족이라고 알려줘.',
         rubric='현재 문서 묶음에 원재료 비타민 C 수치가 없으므로 mg 값을 만들지 않고 자료 부족을 안내한다. 레시피 영양값을 원재료 값으로 대체하지 않는다.'),
]


def run_one(case, variant, repeat, item, bundle, options, config, query_raw):
    calls = []
    def ask(prompt, payload, stage_config):
        if prompt == PROMPT1:
            return query_raw
        started = perf_counter()
        try:
            return ask_json(prompt, payload, stage_config)
        finally:
            calls.append(dict(stage='selection', model=stage_config['GMS_MODEL'],
                              seconds=round(perf_counter() - started, 3), payload_hash=digest(payload)))
    result = dict(case_id=case['id'], variant=variant, repeat=repeat,
                  selection_model=stage_model(config, 'selection'), answer_model=stage_model(config, 'answer'))
    try:
        with tempfile.TemporaryDirectory() as temp:
            chunks, report = collect(item, bundle, options, config, Path(temp), ask)
        recipe_docs = [d for d in documents() if d['id'] == item['id']]
        evidence = retrieve(recipe_docs + chunks, case['question'], selected=item['id'], top_k=3)
        started = perf_counter()
        generation = generate(case['question'], evidence, config)
        result.update(status=generation['status'], generation=generation,
                      answer_seconds=round(perf_counter() - started, 3),
                      selection_calls=calls, collection=report, evidence=evidence,
                      mandatory_source_present=any(d.get('document_id') == 'cookrcp01-' + case['recipe_id'] for d in chunks))
    except Exception:
        # API exception text may include credentials or request URLs.
        result.update(status='experiment_error', selection_calls=calls,
                      error='Collection or evaluation failed; exception details hidden.')
    return result


def write_html(report, path):
    answer_only = report.get('mode') == 'answer_only'
    labels = report.get('variant_labels', {'single': '기존: 단일 모델', 'split': '변경: 단계별 모델'})
    sections = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>모델 비교 평가</title>',
                '<style>body{font:16px/1.6 sans-serif;max-width:1500px;margin:30px auto;padding:16px} '
                '.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px} article{border:1px solid #aaa;padding:18px;min-width:0} '
                'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit} @media(max-width:800px){.pair{grid-template-columns:1fr}}</style>',
                '<h1>' + ('동일 근거 / 답변 모델 Luna·Sol 비교' if answer_only else '단일 모델 / 단계별 모델 실제 비교') + '</h1>',
                '<p>이전 실험의 검색 근거·질문·프롬프트·출력 한도를 고정하고 답변 모델만 변경합니다. 검색/선별은 재실행하지 않습니다.</p>' if answer_only else '<p>고정 합성 질문. 검색어·후보·프롬프트·답변 모델을 고정하고 선별 모델만 변경합니다. '
                '자료 수집 → 어휘 검색 → 답변 생성의 통제 실험이며 실제 UI 전체 경로의 성능 평가는 아닙니다. '
                '인용 ID 유효성은 의미 정확성 점수가 아닙니다. 소수 질문의 반복은 일반화 근거로 부족합니다.</p>',
                '<p>실행 시각(UTC): ' + escape(report['started_at']) + '</p>']
    if report.get('summary'):
        summary = report['summary']
        sections.append('<h2>실제 비교 요약</h2><p><strong>' + escape(summary['conclusion']) + '</strong></p>')
        sections.append('<p>' + ('생성 입력 동일 ' + str(summary.get('same_generation_input_pairs', 0)) if answer_only else '후보 입력 동일 ' + str(summary['same_candidate_pairs'])) + '/' + str(summary['paired_runs']) + '쌍 · 최종 생성 근거 동일 ' + str(summary['same_evidence_pairs']) + '/' + str(summary['paired_runs']) + '쌍. 근거 동일성이 답변의 완전한 정확성을 뜻하지는 않습니다.</p>')
        sections.append('<table><tr><th>구성</th>' + ('<th>생성 평균(초)</th>' if answer_only else '<th>선별 평균(초)</th><th>생성 평균(초)</th><th>선별+생성 평균(초)</th>') + '</tr>')
        for variant, row in summary['timing'].items():
            keys = ('answer_mean_seconds',) if answer_only else ('selection_mean_seconds', 'answer_mean_seconds', 'selection_plus_answer_mean_seconds')
            sections.append('<tr><td>' + escape(labels[variant]) + '</td>' + ''.join('<td>' + str(row[key]) + '</td>' for key in keys) + '</tr>')
        sections.append('</table><p>네트워크/서버 부하와 두 구성의 동시 실행 영향을 포함합니다. 검색어 추출·전처리 시간과 비용은 제외했으므로 서비스 전체 속도/비용 개선 수치가 아닙니다.</p>')
    if report.get('review'):
        review = report['review']
        sections.append('<h2>질문별 원문 대조 검토</h2><p>' + escape(review['method']) + '</p>')
        for row in review['cases']:
            sections.append('<p><strong>' + escape(row['case_id']) + '</strong>: ' + escape(row['finding']) + '</p>')
        if review.get('metrics'):
            sections.append('<table><tr><th>검토 기준</th><th>Luna</th><th>Sol</th></tr>')
            for metric in review['metrics']:
                sections.append('<tr>' + ''.join('<td>' + escape(str(metric[key])) + '</td>' for key in ('label', 'luna', 'sol')) + '</tr>')
            sections.append('</table>')
        sections.append('<p>' + escape(review.get('rubric_correction', '')) + '</p>')
    if report.get('query_error'):
        sections.append('<p><strong>검색어 추출 API 호출 실패: 실제 답변 비교가 수행되지 않았습니다. 성능 개선은 미검증입니다.</strong></p>')
    for case in report['cases']:
        sections += ['<h2>' + escape(case['id'] + ': ' + case['question']) + '</h2>',
                     '<p>사전 검토 기준: ' + escape(case['rubric']) + '</p>']
        if case.get('criteria'):
            sections.append('<ol>' + ''.join('<li>' + escape(c) + '</li>' for c in case['criteria']) + '</ol>')
        for repeat in range(1, report['repeats'] + 1):
            sections.append('<h3>반복 ' + str(repeat) + '</h3><div class="pair">')
            for variant in ('single', 'split'):
                row = next((r for r in report['results'] if r['case_id'] == case['id'] and r['repeat'] == repeat and r['variant'] == variant), None)
                sections.append('<article><h3>' + escape(labels[variant]) + '</h3>')
                if row:
                    sections.append('<p>' + ('' if answer_only else escape(str(row['selection_model'])) + ' 선별 / ') + escape(str(row['answer_model'])) + ' 답변</p>')
                    sections.append('<p>상태: ' + escape(row['status']) + ('' if answer_only else ' / 선별 ' + str(sum(c['seconds'] for c in row.get('selection_calls', []))) + '초') + ' / 답변 ' + str(row.get('answer_seconds', '-')) + '초</p>')
                    sections.append('<pre>' + escape(row.get('generation', {}).get('answer') or row.get('error', '표시 가능한 답변 없음')) + '</pre>')
                    if row.get('review'):
                        sections.append('<p>사전 기준 충족: ' + str(sum(row['review']['checks'])) + '/' + str(len(row['review']['checks'])) + ' · ' + escape(row['review']['note']) + '</p>')
                    sections.append('<details><summary>' + ('고정된 검색 근거' if answer_only else '선별 문서·실제 답변 근거') + '</summary><pre>' + escape(json.dumps(dict(collection=row.get('collection'), evidence=row.get('evidence')), ensure_ascii=False, indent=2)) + '</pre></details>')
                else:
                    sections.append('<p>실행되지 않음</p>')
                sections.append('</article>')
            sections.append('</div>')
    sections.append('</html>')
    # Keep raw model output in JSON; trim Markdown line-break spaces in this preformatted view.
    path.write_text('\n'.join(line.rstrip() for line in '\n'.join(sections).splitlines()) + '\n', encoding='utf-8')


ANSWER_CRITERIA = {
    'M1': ['원문7종 재료를 다른 요리와 섞지 않음', '새우 데치기→혼합→시금치/찌기의 순서 유지', '중간 불 약10분을 원문대로 안내', '원문에 없는 조리 수치/조건을 추가하지 않음'],
    'M2': ['원문 재료와 주요 조리 순서 유지', '육수의 모호한 문구를 인지하고 줄바꿈을 문장 미제공으로 오해하지 않음', '저염 방법을 전달된 지침 내용/인용에 맞게 설명', '나트륨 감소량/조리시간 등 미제공 수치를 추정하지 않음'],
    'M3': ['비타민C mg 수치를 만들지 않음', '전달된 자료에 수치가 없다는 한계를 명시', '레시피 영양값을 원재료 값으로 환산/대체하지 않음', '유효한 근거 인용으로 부족 안내를 뒷받침'],
}


def run_answer(case, variant, repeat, fixed_evidence, config):
    from recipe_rag import INSTRUCTIONS
    from rag_graph import evidence_context
    evidence = json.loads(json.dumps(fixed_evidence, ensure_ascii=False))
    canonical = evidence_context(evidence, evidence)
    started = perf_counter()
    generation = generate(case['question'], evidence, config)
    return dict(case_id=case['id'], variant=variant, repeat=repeat,
                answer_model=stage_model(config, 'answer'), status=generation['status'],
                generation=generation, answer_seconds=round(perf_counter()-started, 3),
                evidence=evidence, selection_calls=[],
                generation_input_hash=digest(dict(question=case['question'], evidence=canonical,
                                                  instructions=INSTRUCTIONS, max_output_tokens=1400)))


def summarize_answer_comparison(report):
    pairs = []
    for case in report['cases']:
        for repeat in range(1, report['repeats']+1):
            arms = {r['variant']: r for r in report['results'] if r['case_id'] == case['id'] and r['repeat'] == repeat}
            if len(arms) != 2:
                continue
            a, b = arms['single'], arms['split']
            pairs.append(dict(case_id=case['id'], repeat=repeat,
                              same_evidence=digest(a['evidence']) == digest(b['evidence']),
                              same_input=a['generation_input_hash'] == b['generation_input_hash']))
    timing = {}
    for variant in ('single', 'split'):
        rows = [r for r in report['results'] if r['variant'] == variant]
        if rows:
            seconds = round(mean(r['answer_seconds'] for r in rows), 3)
            timing[variant] = dict(runs=len(rows), selection_mean_seconds=0,
                                  answer_mean_seconds=seconds, selection_plus_answer_mean_seconds=seconds)
    return dict(paired_runs=len(pairs), same_evidence_pairs=sum(p['same_evidence'] for p in pairs),
                same_generation_input_pairs=sum(p['same_input'] for p in pairs), timing=timing, pairs=pairs,
                conclusion='동일 입력의 답변을 비교했습니다. 원문 대조 검토 전에는 품질 개선을 판정하지 않습니다.')


def evaluate_answers(config, repeats):
    previous = json.loads((ROOT / 'data/rag/model_comparison.json').read_text(encoding='utf-8'))
    fixed = {}
    for case in CASES:
        matches = [r for r in previous['results'] if r['case_id'] == case['id'] and r['variant'] == 'single' and r['repeat'] == 1]
        if not matches or not matches[0].get('evidence'):
            raise SystemExit('Prior experiment evidence missing; no API calls made.')
        fixed[case['id']] = matches[0]['evidence']
    report = dict(mode='answer_only', started_at=datetime.now(timezone.utc).isoformat(),
                  cases=[dict(c, criteria=ANSWER_CRITERIA[c['id']]) for c in CASES], repeats=repeats, results=[],
                  variant_labels={'single': 'Luna: gpt-6-luna', 'split': 'Sol: gpt-6.1-sol'},
                  source_experiment_file='data/rag/model_comparison.json',
                  source_experiment_hash=digest(previous),
                  scoring='Predeclared criteria; manual source comparison required. No automatic semantic accuracy.',
                  limits='Model only; default model reasoning settings, same output cap1400. No cost/token measurement or full UI evaluation.')
    output = ROOT / 'data/rag/answer_model_comparison.json'
    save(output, report)
    for case in report['cases']:
        for repeat in range(1, repeats+1):
            variants = ('single', 'split') if repeat % 2 else ('split', 'single')
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(run_answer, case, v, repeat, fixed[case['id']],
                    dict(config, GMS_ANSWER_MODEL='gpt-6-luna' if v == 'single' else 'gpt-6.1-sol')) for v in variants]
                for future in futures:
                    result = future.result()
                    report['results'].append(result)
                    save(output, report)
                    print(case['id'], result['answer_model'], repeat, result['status'], flush=True)
            report['summary'] = summarize_answer_comparison(report)
            write_html(report, output.with_suffix('.html'))
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save(output, report)
    write_html(report, output.with_suffix('.html'))


def summarize_comparison(report):
    """Mechanical comparisons only; never label these as semantic accuracy."""
    pairs = []
    for case in report['cases']:
        for repeat in range(1, report['repeats'] + 1):
            arms = {row['variant']: row for row in report['results'] if row['case_id'] == case['id'] and row['repeat'] == repeat}
            if not all(arms.get(v, {}).get('status') == 'generated_unreviewed' for v in ('single', 'split')):
                continue
            a, b = arms['single'], arms['split']
            pairs.append(dict(case_id=case['id'], repeat=repeat,
                same_candidates=[c['payload_hash'] for c in a['selection_calls']] == [c['payload_hash'] for c in b['selection_calls']],
                same_evidence=digest(a['evidence']) == digest(b['evidence']),
                same_selected_set=set(a['collection']['llm_selected_ids']) == set(b['collection']['llm_selected_ids'])))
    timing = {}
    for variant in ('single', 'split'):
        rows = [r for r in report['results'] if r['variant'] == variant and r.get('status') == 'generated_unreviewed']
        if rows:
            selection = [sum(c['seconds'] for c in r['selection_calls']) for r in rows]
            answer = [r['answer_seconds'] for r in rows]
            timing[variant] = dict(runs=len(rows), selection_mean_seconds=round(mean(selection), 3),
                                  answer_mean_seconds=round(mean(answer), 3),
                                  selection_plus_answer_mean_seconds=round(mean(a+b for a,b in zip(selection, answer)), 3))
    same_evidence = sum(p['same_evidence'] for p in pairs)
    return dict(paired_runs=len(pairs), same_candidate_pairs=sum(p['same_candidates'] for p in pairs),
                same_evidence_pairs=same_evidence, pairs=pairs, timing=timing,
                conclusion='본 실험에서 최종 근거 개선은 관찰되지 않았습니다. 답변 표현 차이를 선별 모델의 품질 향상으로 귀속할 수 없습니다.' if pairs and same_evidence == len(pairs)
                           else '질문별로 근거와 답변을 대조해야 하며, 자동 비교만으로 품질 향상을 판정하지 않습니다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=2)
    parser.add_argument('--answer-only', action='store_true', help='Reuse prior evidence and compare only answer models')
    args = parser.parse_args()
    config = settings()
    if not all(config.get(k) for k in ('GMS_API_KEY', 'GMS_BASE_URL')):
        raise SystemExit('GMS credentials/server configuration missing; values hidden.')
    if args.answer_only:
        evaluate_answers(config, args.repeats)
        return
    baseline = stage_model(config, 'query')
    if not baseline or not stage_model(config, 'selection'):
        raise SystemExit('Model configuration missing.')
    # Deliberately use the same answer model in both arms to isolate selection.
    configs = dict(single=dict(config, GMS_QUERY_MODEL=baseline, GMS_SELECTION_MODEL=baseline, GMS_ANSWER_MODEL=baseline),
                   split=dict(config, GMS_QUERY_MODEL=baseline, GMS_ANSWER_MODEL=baseline))
    bundle = load_bundle()
    options = json.loads((ROOT / 'config/rag_sources.json').read_text(encoding='utf-8'))
    recipes = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
    output = ROOT / 'data/rag/model_comparison.json'
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), cases=CASES, repeats=args.repeats,
                  bundle_hash=digest(bundle), options=options, results=[],
                  scope='Controlled collection/lexical retrieval/generation; not UI or Chroma end-to-end.',
                  scoring='Manual rubric review required; no automatic semantic quality score.',
                  cost='Token usage/cost not measured; timing includes network latency.')
    output.parent.mkdir(parents=True, exist_ok=True)
    save(output, report)
    for case in CASES:
        recipe = next(r for r in recipes if r['recipe_id'] == case['recipe_id'])
        item = dict(id='recipe:' + case['recipe_id'], name=recipe['name'], ingredients=recipe['ingredients_text'])
        try:
            query_raw = ask_json(PROMPT1, item, dict(config, GMS_MODEL=baseline))
            string_array(query_raw, limit=5)
        except Exception:
            report['query_error'] = dict(case_id=case['id'], status='query_api_failed', details='hidden')
            save(output, report)
            write_html(report, output.with_suffix('.html'))
            print(case['id'], 'query_api_failed', flush=True)
            return
        for repeat in range(1, args.repeats + 1):
            variants = ('single', 'split') if repeat % 2 else ('split', 'single')
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(run_one, case, v, repeat, item, bundle, options, configs[v], query_raw) for v in variants]
                for future in futures:
                    result = future.result()
                    report['results'].append(result)
                    save(output, report)
                    print(case['id'], result['variant'], repeat, result['status'], flush=True)
            write_html(report, output.with_suffix('.html'))
        if all(r['status'] == 'experiment_error' for r in report['results'] if r['case_id'] == case['id']):
            print('Stopped after repeated collection failures; see report.', flush=True)
            return
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    report['summary'] = summarize_comparison(report)
    save(output, report)
    write_html(report, output.with_suffix('.html'))


if __name__ == '__main__':
    main()
