"""Acquire licensed official education text; no credentials or third-party media."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    dict(document_id='diet_practice_checklist_2025', news_id=None,
         source_url='https://www.rda.go.kr/board/board.do?boardId=farmprmninfo&currPage=127&dataNo=100000802463&mode=updateCnt&prgId=day_farmprmninfoEntry&searchEDate=3&searchKey=&searchOrgDeptKey=&searchOrgDeptVal=&searchSDate=&searchVal=',
         title='나의 식생활 실천 점수는? 점검표로 알아보세요', publisher='농촌진흥청·국립식량과학원',
         published_date='2025-05-02', document_type='official_practical_education',
         topics=['식생활 점검','성인','식품 및 영양 섭취','식습관']),
    dict(document_id='nutrition_policy_2026', news_id='148957973',
         title="'통합급식관리지원센터' 전국 확대…노인·장애인까지 지원 강화",
         publisher='식품의약품안전처', published_date='2026-01-14',
         document_type='official_policy_background', topics=['영양정보','식품 선택','나트륨','당류']),
    dict(document_id='dietary_guidelines_2021', news_id='148886239',
         title='“덜 짜게, 덜 달게, 덜 기름지게”…한국인을 위한 식생활지침',
         publisher='보건복지부·농림축산식품부·식품의약품안전처', published_date='2021-04-14',
         document_type='official_guideline_announcement', topics=['식품군 균형','채소·과일','나트륨','당류','식습관']),
    dict(document_id='healthy_home_eating_2021', news_id='148888295',
         title='집콕시대, 상황별 건강 식생활 실천 가이드',
         publisher='식품의약품안전처', published_date=None,
         document_type='official_practical_education', topics=['영양표시','나트륨','당류','양념','음료']),
    dict(document_id='hmr_nutrition_2020', news_id='148874394',
         title='찌개류 가정간편식, 한 끼 식사로는 영양성분 부족',
         publisher='식품의약품안전처', published_date=None,
         document_type='official_survey_based_education', topics=['간편식','영양표시','식사 구성','나트륨']),
]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.active_depth = None
        self.selected = []
        self.all_text = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div':
            self.depth += 1
            if 'view_cont' in attrs.get('class','').split():
                self.active_depth = self.depth
        if tag in ('script','style'):
            self.skip += 1
        if tag in ('p','br','div','li') and self.active_depth is not None:
            self.selected.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script','style'):
            self.skip = max(0, self.skip-1)
        if tag == 'div':
            if self.active_depth == self.depth:
                self.active_depth = None
            self.depth -= 1
        if tag in ('p','li') and self.active_depth is not None:
            self.selected.append('\n')

    def handle_data(self, value):
        if not self.skip:
            self.all_text.append(value)
            if self.active_depth is not None:
                self.selected.append(value)


def main():
    output = ROOT / 'data/guidelines'
    raw = output / 'texts'
    raw.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in SOURCES:
        section = 'news/policyNewsView.do' if source['news_id'] in ('148886239','148957973') else 'briefing/policyBriefingView.do'
        url = source.get('source_url') or ('https://www.korea.kr/' + section + '?newsId=' + source['news_id'])
        req = Request(url, headers={'User-Agent':'RAG-service-educational-source-collector/1.0'})
        with urlopen(req,timeout=30) as response:
            html = response.read().decode('utf-8')
        parser = TextExtractor()
        parser.feed(html)
        all_text = re.sub(r'\s+',' ', ' '.join(parser.all_text))
        license_match = re.search(r'이 자료는 텍스트에 한하여 공공누리 제1유형.*?이용할 수 있습니다\.', all_text)
        if source['document_id']=='diet_practice_checklist_2025':
            license_match = re.search(r'본 저작물은.*?제1유형:출처표시.*?이용 할 수 있습니다\.',all_text)
        if not license_match:
            raise RuntimeError('Required text-only KOGL type 1 notice not found: ' + source['document_id'])
        body = ''.join(parser.selected)
        if source['document_id']=='diet_practice_checklist_2025':
            body = '\n'.join(parser.all_text)
            start = body.find('농촌진흥청(청장')
            end = body.find('첨부파일',start)
            if start<0 or end<0:
                raise RuntimeError('RDA body markers missing')
            body = body[start:end]
        # Remove contact details and document license/footer from retrieval text.
        body = re.split(r'문의\s*[:：]|이 자료는 텍스트에 한하여',body)[0]
        lines = [re.sub(r'[ \t\xa0]+',' ',line).strip() for line in body.splitlines()]
        lines = [line for line in lines if line and not re.search(r'\d{2,3}-\d{3,4}-\d{4}',line)
                 and line not in ('Previous','Next','Previous line','Next line','/')
                 and '사진=' not in line and '무단 전재' not in line]
        body = '\n'.join(lines)
        if len(body) < 250:
            raise RuntimeError('Body extraction too short: ' + source['document_id'])
        date = re.search(r'(20\d{2})\.(\d{2})\.(\d{2})',all_text)
        published = source['published_date'] or ('-'.join(date.groups()) if date else None)
        path = raw / (source['document_id'] + '.txt')
        path.write_text(body+'\n', encoding='utf-8')
        entry = source | dict(source_url=url, host='농촌진흥청' if 'rda.go.kr' in url else '대한민국 정책브리핑',
                              published_date=published, checked_date='2026-10-21',
                              license='KOGL-1-text-only', license_notice=license_match[0],
                              attribution=source['publisher']+' / '+source['title']+' / '+url,
                              local_text=path.relative_to(ROOT).as_posix(),
                              text_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                              transformation='HTML body extraction; media/navigation/contact lines omitted; whitespace normalized.',
                              audience='일반 국민 대상 교육자료. 일반 성인 생활 안내에 한정, 질환 치료·특수 대상 처방에 사용하지 않음.',
                              version_status='게시일 기준 자료. 최신 개정판 여부 미확인.',
                              allowed_use='policy_background_only' if source['document_type']=='official_policy_background' else 'qualitative_recommendation_explanation',
                              calculation_use=False, indexing_status='text_acquired_not_embedded')
        manifest.append(entry)
        print(source['document_id'],published,len(body),'characters')
        time.sleep(0.5)
    (output / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
