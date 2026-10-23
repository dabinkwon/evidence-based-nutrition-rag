"""Inspect official agricultural research metadata; never infer nutrient amounts.

Only registered public food names/codes are accepted. No LLM calls are made.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote
from urllib.request import urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://apis.data.go.kr/1390803/AgriFood/FncltyEfcy1'
OPERATIONS = {
    'food-functions': 'getThesisInfoOnFncltyByFood1',
    'food-ingredients': 'getThesisInfoOnIrdntAndFncltyByFood1',
}


class NoResearchData(RuntimeError):
    """Provider explicitly returned code301 with an empty-data message."""


def key_from_env():
    key = os.environ.get('AGRIFOOD_API_KEY', '')
    path = ROOT / '.env'
    if not key and path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == 'AGRIFOOD_API_KEY':
                key = value.strip().strip('\"\'')
    if not key:
        raise RuntimeError('AGRIFOOD_API_KEY is missing; values hidden.')
    return unquote(key)


def xml_value(node):
    children = list(node)
    if not children:
        return (node.text or '').strip()
    result = {}
    for child in children:
        name = child.tag.rsplit('}', 1)[-1]
        value = xml_value(child)
        if name in result:
            if not isinstance(result[name], list):
                result[name] = [result[name]]
            result[name].append(value)
        else:
            result[name] = value
    return result


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def parse_response(raw, key):
    # Prevent saving echoed credentials, including an URL-encoded service key.
    if key in unquote(raw):
        raise RuntimeError('Credential echo detected; response refused.')
    if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
        raise RuntimeError('Unsupported XML declarations; response refused.')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise RuntimeError('API response is not valid XML; content hidden.') from None
    payload = xml_value(root)
    codes = [str(d[k]) for d in walk(payload) for k in ('result_Code', 'resultCode') if k in d]
    header = payload.get('header', {}) if isinstance(payload, dict) else {}
    message = header.get('result_Msg', '')
    if codes == ['301'] and '데이터' in message and '없' in message:
        raise NoResearchData('Provider reports no research data for this request.')
    if not codes or any(code not in ('00', '0', '200', 'INFO-000') for code in codes):
        raise RuntimeError('API did not report success; response hidden.')
    return payload


def request_metadata(key, sample_id, research_code, operation='food-functions', page=1, size=5):
    if operation not in OPERATIONS:
        raise ValueError('Unknown operation')
    if not re.fullmatch(r'S-\d{2}-\d{3}', sample_id) or not re.fullmatch(r'G\d{3}', research_code):
        raise ValueError('Invalid sample/research code')
    if type(page) is not int or page < 1 or type(size) is not int or not 1 <= size <= 20:
        raise ValueError('Require page >= 1 and 1 <= size <= 20')
    params = dict(serviceKey=key, sample_Id=sample_id, research_Type_Cd=research_code)
    if operation == 'food-ingredients':
        params.update(Page_No=page, Page_Size=size)
    try:
        with urlopen(ENDPOINT + '/' + OPERATIONS[operation] + '?' + urlencode(params), timeout=30) as response:
            data = response.read(4_000_001)
        if len(data) > 4_000_000:
            raise RuntimeError('API response size limit exceeded.')
        payload = parse_response(data.decode('utf-8-sig'), key)
        body = payload.get('body', {})
        if body.get('sample_Id') != sample_id or body.get('research_Type_Cd') != research_code:
            raise RuntimeError('API returned mismatched sample/research metadata; refused.')
        return payload
    except HTTPError as exc:
        raise RuntimeError(f'API HTTP status {exc.code}; URL and response hidden.') from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError('API network connection failed; URL hidden.') from None
    except UnicodeError:
        raise RuntimeError('API response encoding unsupported; content hidden.') from None


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def inspection_report():
    """Render source metadata locally without generating scientific claims."""
    sources = json.loads((ROOT / 'config/agrifood_sources.json').read_text(encoding='utf-8'))
    sections = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>농산물 논문 API 점검</title>',
                '<style>body{font:16px/1.6 sans-serif;max-width:1200px;margin:30px auto;padding:16px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:8px;text-align:left}td{overflow-wrap:anywhere}</style>',
                '<h1>농산물 효능 API 실제 응답 점검</h1>',
                '<p>농촌진흥청 국립식량과학원 제공 메타데이터를 로컬에서 확인하는 화면입니다. '
                '논문 제목·분류를 제시하며 연구 결과나 식품 섭취 효과를 판정하지 않습니다. 논문 초록/본문은 확보하지 않았습니다.</p>',
                '<p>영양 함량: 응답에서 단위·기준량을 확인하지 못해 숫자 환산/비교를 제공하지 않습니다.</p>',
                '<p>출처: <a href="' + sources['source_url'] + '">공식 API 안내</a> / '
                + escape(sources['license']) + '. 상업 이용/요약·가공 활용 범위는 별도 확인 대상입니다.</p>']
    summaries = []
    for path in sorted((ROOT / 'data/raw/agrifood').glob('*.json')):
        payload = json.loads(path.read_text(encoding='utf-8'))
        body = payload.get('body', {})
        papers = [d for d in walk(body) if d.get('title')]
        unique = {(d['title'], d.get('details', ''), d.get('pblicte_Year', '')) for d in papers}
        summary = dict(file=path.relative_to(ROOT).as_posix(), sample_id=body.get('sample_Id'),
                       sample_name=body.get('sample_Nm'), research_code=body.get('research_Type_Cd'),
                       research_label=body.get('research_Type_Nm'), paper_record_count=len(papers),
                       unique_bibliography_count=len(unique),
                       payload_sha256=hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
        summaries.append(summary)
        label = str(body.get('sample_Nm')) + ' / ' + str(body.get('research_Type_Nm')) + ' / ' + ('성분·기능성' if 'food-ingredients' in path.name else '식품 기능성')
        sections.extend(['<h2>' + escape(label) + '</h2>',
                         '<p>논문 연결 기록 ' + str(len(papers)) + '개 / 제목·저널·연도 기준 고유 서지정보 ' + str(len(unique)) + '개. 연구의 독립성·품질 평가는 미실행.</p>',
                         '<p>응답 파일: ' + escape(path.name) + '</p>'])
        ingredients = body.get('items', {}).get('irdnt_List', {})
        if isinstance(ingredients, dict) and ingredients.get('cas_Nm'):
            names = ingredients['cas_Nm']
            sections.append('<p>응답 성분명: ' + escape(' / '.join(names if isinstance(names, list) else [names])) + '</p>')
        sections.append('<table><tr><th>논문명(원문)</th><th>저널(원문)</th><th>연도</th></tr>')
        for title, journal, year in sorted(unique):
            sections.append('<tr>' + ''.join('<td>' + escape(str(v)) + '</td>' for v in (title, journal, year)) + '</tr>')
        sections.append('</table>')
    sections.append('</html>')
    coverage = dict(available_food_count=len({s['sample_id'] for s in summaries if s['unique_bibliography_count'] > 0}),
                    animal_food_count=len({s['sample_id'] for s in summaries if s['unique_bibliography_count'] > 0 and s['research_code'] == 'G001'}),
                    human_food_count=len({s['sample_id'] for s in summaries if s['unique_bibliography_count'] > 0 and s['research_code'] == 'G003'}))
    sections.insert(3, '<p><strong>연구자료 확보 식품 ' + str(coverage['available_food_count']) + '개 · 동물시험 자료 ' + str(coverage['animal_food_count']) + '개 식품 · 인체적용시험 자료 ' + str(coverage['human_food_count']) + '개 식품</strong></p>')
    output = ROOT / 'data/agrifood_inspection.html'
    output.write_text('\n'.join(sections), encoding='utf-8')
    save(ROOT / 'data/agrifood_inspection.json', dict(source_url=sources['source_url'], responses=summaries, coverage=coverage,
        generation_enabled=False, scope='Local metadata inspection; nutrient amounts and efficacy not evaluated.'))
    return summaries


def collect_registered(sources, research_codes, limit=197, pause=0.2):
    """Bounded sequential batch with resume; never replace valid cached data."""
    key = key_from_env()
    records = []
    output = ROOT / 'data/agrifood_collection_report.json'
    selected = list(sources['foods'].items())[:limit]
    for index, (name, sample) in enumerate(selected, 1):
        for code in research_codes:
            path = ROOT / 'data/raw/agrifood' / (sample + '-' + code + '-food-functions-1-5.json')
            status_path = ROOT / 'data/agrifood_reports' / (sample + '-' + code + '-food-functions-1-5.json')
            record = dict(food=name, sample_id=sample, research_code=code)
            try:
                previous = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
                if previous.get('status') == 'no_data' and previous.get('sample_id') == sample and previous.get('research_code') == code:
                    records.append(dict(previous, cached=True))
                    continue
                cached = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
                valid = isinstance(cached, dict) and cached.get('header', {}).get('result_Code') == '200' and cached.get('body', {}).get('sample_Id') == sample and cached.get('body', {}).get('research_Type_Cd') == code
                payload = cached if valid else request_metadata(key, sample, code)
                if not valid:
                    save(path, payload)
                    time.sleep(pause)
                papers = [d for d in walk(payload) if d.get('title')]
                unique = {(p['title'], p.get('details', ''), p.get('pblicte_Year', '')) for p in papers}
                record.update(status='cached' if valid else 'success', paper_record_count=len(papers),
                              unique_bibliography_count=len(unique), research_label=payload['body'].get('research_Type_Nm'),
                              raw_file=path.relative_to(ROOT).as_posix())
            except NoResearchData:
                record.update(status='no_data', result_code='301', paper_record_count=0, unique_bibliography_count=0)
                time.sleep(pause)
            except (RuntimeError, ValueError, OSError, AttributeError):
                record.update(status='failed', error='Request/response unavailable; credentials and details hidden.')
                time.sleep(pause)
            save(status_path, record)
            records.append(record)
        save(output, dict(updated_at=datetime.now(timezone.utc).isoformat(), source_url=sources['source_url'],
                          catalog_count=len(sources['foods']), requested_food_count=len(selected),
                          research_codes=research_codes, complete=index == len(selected), records=records))
        if index % 10 == 0 or index == len(selected):
            print('foods_processed', index, 'of', len(selected), 'failed_requests', sum(r['status'] == 'failed' for r in records), flush=True)
        # Avoid spending quota on a repeated outage or authentication failure.
        if len(records) >= 6 and all(r['status'] == 'failed' for r in records[-6:]):
            print('Stopped after six consecutive failures; saved results preserved.', flush=True)
            return records
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--food', default='가지')
    parser.add_argument('--research', default='G001', help='Official research code; preserve returned label')
    parser.add_argument('--operation', choices=OPERATIONS, default='food-functions')
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--size', type=int, default=5)
    parser.add_argument('--offline-report', action='store_true', help='Render saved metadata without API calls')
    parser.add_argument('--collect-all', action='store_true', help='Collect registered food-functions metadata sequentially')
    parser.add_argument('--limit', type=int, choices=range(1, 198), default=197)
    parser.add_argument('--research-codes', nargs='+', choices=('G001', 'G003'), default=['G001', 'G003'])
    args = parser.parse_args()
    if args.offline_report:
        print('saved_response_count', len(inspection_report()))
        return
    sources = json.loads((ROOT / 'config/agrifood_sources.json').read_text(encoding='utf-8'))
    if args.collect_all:
        collect_registered(sources, list(dict.fromkeys(args.research_codes)), args.limit)
        inspection_report()
        return
    food_name = sources.get('aliases', {}).get(args.food, args.food)
    sample_id = sources['foods'].get(food_name)
    if not sample_id:
        parser.error('Food is not in the verified public code registry.')
    report = dict(collected_at=datetime.now(timezone.utc).isoformat(), food=args.food,
                  sample_id=sample_id, research_code=args.research, operation=args.operation,
                  source_url=sources['source_url'], allowed_use=sources['allowed_use'],
                  generation_enabled=False, page=args.page if args.operation == 'food-ingredients' else None,
                  size=args.size if args.operation == 'food-ingredients' else None)
    report_path = ROOT / 'data/agrifood_probe_report.json'
    try:
        payload = request_metadata(key_from_env(), sample_id, args.research, args.operation, args.page, args.size)
        records = list(walk(payload))
        papers = [d for d in records if d.get('title')]
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        path = ROOT / 'data/raw/agrifood' / (sample_id + '-' + args.research + '-' + args.operation + '-' + str(args.page) + '-' + str(args.size) + '.json')
        save(path, payload)
        report.update(status='success', paper_record_count=len(papers),
                      research_labels=sorted({str(d['research_Type_Nm']) for d in records if d.get('research_Type_Nm')}),
                      field_names=sorted({k for d in records for k in d}),
                      raw_file=path.relative_to(ROOT).as_posix(), payload_sha256=fingerprint)
    except NoResearchData:
        report.update(status='no_data', result_code='301', paper_record_count=0)
    except (RuntimeError, ValueError) as exc:
        # Only constant messages produced above, never external exception text.
        report.update(status='failed', error=str(exc))
    save(report_path, report)
    save(ROOT / 'data/agrifood_reports' / (sample_id + '-' + args.research + '-' + args.operation + '-' + str(args.page) + '-' + str(args.size) + '.json'), report)
    print(json.dumps({k: report[k] for k in ('status', 'operation', 'sample_id')}, ensure_ascii=True))
    if report['status'] not in ('success', 'no_data'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
