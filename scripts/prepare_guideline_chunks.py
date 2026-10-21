"""Prepare exact source excerpts with line provenance; not a vector index."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECT = {
    'diet_practice_checklist_2025': [
        ('식생활 실천 점검표는 ▲', '식생활 평가 영역'),
        ('생애주기별 식생활 특성을 반영해', '생애주기별 평가 대상'),
        ('개인이 생애주기에 맞는', '식생활 실천 수준 점검')],
    'nutrition_policy_2026': [('과잉 섭취 시 건강을 해칠 수 있는 영양성분', '나트륨·당류 저감 정책 방향')],
    'dietary_guidelines_2021': [('균형 있는 식품 섭취', '식품군 균형'), ('과식을 피하고', '식습관')],
    'healthy_home_eating_2021': [
        ('1. 온라인으로', '영양표시'), ('1. 식재료 고유', '조리'),
        ('2. 가정간편식', '양념'), ('4. 조리 시', '조리'),
        ('1. 배달 주문', '양념'), ('2. 국물은', '나트륨'), ('3. 양념(', '나트륨'),
        ('5. 균형된', '식품군 균형'), ('1. 음료 대신', '음료'), ('2. 커피와', '당류')],
    'hmr_nutrition_2020': [('영양성분 표시를 반드시 확인', '간편식 영양표시')],
}


def main():
    base = ROOT / 'data/guidelines'
    docs = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    chunks = []
    for doc in docs:
        path = ROOT / doc['local_text']
        lines = path.read_text(encoding='utf-8').splitlines()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == doc['text_sha256']
        for needle, section in SELECT[doc['document_id']]:
            found = [(i+1,line) for i,line in enumerate(lines) if needle in line]
            if len(found) != 1:
                raise RuntimeError('Source section missing or ambiguous: '+doc['document_id']+' / '+section)
            number, text = found[0]
            chunks.append(dict(chunk_id=doc['document_id']+f':line:{number:04}',
                               document_id=doc['document_id'], title=doc['title'],
                               publisher=doc['publisher'], published_date=doc['published_date'],
                               source_url=doc['source_url'], source_type='official_guidance_web',
                               page=None, section=section, local_text=doc['local_text'],
                               line_start=number,line_end=number,text=text,
                               license=doc['license'],attribution=doc['attribution'],
                               allowed_use=doc['allowed_use'],
                               food_scope='general', related_food_ids=[],
                               calculation_use=False, clinical_use=False,
                               population='general_adults', version_status=doc['version_status']))
    out = base / 'chunks.jsonl'
    out.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks),encoding='utf-8')
    print(f'Prepared {len(chunks)} exact excerpts from {len(docs)} official documents; not embedded.')


if __name__ == '__main__':
    main()
