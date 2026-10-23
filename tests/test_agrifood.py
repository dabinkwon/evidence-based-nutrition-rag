import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect_agrifood import key_from_env, parse_response, request_metadata, inspection_report, NoResearchData, collect_registered
from research_lookup import answer_research, available_research_foods

XML = '''<response><header><result_Code>200</result_Code></header><body>
<sample_Id>S-14-074</sample_Id><sample_Nm>가지</sample_Nm>
<research_Type_Cd>G001</research_Type_Cd><research_Type_Nm>동물시험</research_Type_Nm>
<items><irdnt_List><cas_Code>a</cas_Code><cas_Nm>A</cas_Nm>
<fnclty_Irdnt_Thesis_List><item><title>Paper A</title><avg>190</avg></item></fnclty_Irdnt_Thesis_List>
<cas_Code>b</cas_Code><cas_Nm>B</cas_Nm>
<fnclty_Irdnt_Thesis_List><item><title>Paper B</title></item><item><title>Paper C</title></item></fnclty_Irdnt_Thesis_List>
</irdnt_List></items></body></response>'''


class AgrifoodChecks(unittest.TestCase):
    def test_expanded_actual_foods_retrieve_own_samples(self):
        self.assertEqual(len(available_research_foods()), 174)
        for name in ('마늘', '양파', '당근', '사과', '토마토', '시금치', '감자', '고구마'):
            with self.subTest(food=name):
                result = answer_research(name + '가 몸에 뭐가 좋아?')
                self.assertEqual(result['status'], 'research_lookup')
                self.assertTrue(result['research_rows'])
                self.assertTrue(all(name in c['title'] for c in result['citations']))
        result = answer_research('두부가 몸에 뭐가 좋아?')
        self.assertEqual(result['status'], 'research_unavailable')
        self.assertNotIn('research_rows', result)

    def test_research_intent_boundaries_and_actual_metadata(self):
        for question in ('가지가 몸에 뭐가 좋아?', '가지의 효능은?', '가지 건강에 좋은가요?'):
            result = answer_research(question)
            self.assertEqual(result['status'], 'research_lookup')
            human = [r for r in result['research_rows'] if r['연구유형'] == '인체적용시험']
            animal = [r for r in result['research_rows'] if r['연구유형'] == '동물시험']
            self.assertEqual(len(human), 1)
            self.assertEqual(len(animal), 10)
            self.assertTrue(all(r['근거'] in [c['number'] for c in result['citations']] for r in result['research_rows']))
            self.assertNotIn('190', result['answer'])
        for question in ('가지 영양성분', '가지로 만드는 레시피', '가지가 들어간 요리 추천', '나뭇가지가 몸에 좋아?', '여러 가지가 몸에 좋아?'):
            self.assertIsNone(answer_research(question))
        self.assertEqual(answer_research('두부 효능')['status'], 'research_unavailable')

    def test_explicit_no_data_and_resumable_batch(self):
        raw = '<response><header><result_Code>301</result_Code><result_Msg>해당 데이터가 없습니다.</result_Msg></header><body/></response>'
        with self.assertRaises(NoResearchData):
            parse_response(raw, 'fake-key')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch('collect_agrifood.ROOT', root), patch('collect_agrifood.key_from_env', return_value='fake-key'), patch('collect_agrifood.request_metadata', side_effect=NoResearchData('no data')) as api:
                first = collect_registered(dict(foods={'test': 'S-14-074'}, source_url='https://example.invalid'), ['G003'], pause=0)
                second = collect_registered(dict(foods={'test': 'S-14-074'}, source_url='https://example.invalid'), ['G003'], pause=0)
            self.assertEqual(first[0]['status'], 'no_data')
            self.assertTrue(second[0]['cached'])
            self.assertEqual(api.call_count, 1)

    def test_catalog_aliases_variants_and_available_list_use_saved_papers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'config').mkdir()
            sources = dict(foods={'당근 (홍당근)': 'S-14-005'}, aliases={'당근': '당근 (홍당근)'}, ambiguous_names={'호박': ['호박 (단호박)', '호박(애호박)']})
            (root / 'config/agrifood_sources.json').write_text(json.dumps(sources), encoding='utf-8')
            (root / 'data').mkdir()
            (root / 'data/agrifood_collection_report.json').write_text(json.dumps(dict(records=[dict(food='당근 (홍당근)', status='success', unique_bibliography_count=2), dict(food='없음', status='no_data', unique_bibliography_count=0)])), encoding='utf-8')
            with patch('research_lookup.ROOT', root):
                self.assertEqual(answer_research('당근은 몸에 좋아?')['status'], 'research_missing')
                self.assertEqual(answer_research('호박 효능')['status'], 'research_ambiguous')
                self.assertEqual(available_research_foods(), ['당근 (홍당근)'])

    def test_missing_research_does_not_invent_benefits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'config').mkdir()
            (root / 'config/agrifood_sources.json').write_text(json.dumps(dict(foods={'가지': 'S-14-074'})), encoding='utf-8')
            with patch('research_lookup.ROOT', root):
                result = answer_research('가지 효능')
            self.assertEqual(result['status'], 'research_missing')
            self.assertEqual(result['citations'], [])

    def test_repeated_unwrapped_xml_preserves_ingredient_paper_alignment(self):
        value = parse_response(XML, 'fake-secret')['body']['items']['irdnt_List']
        self.assertEqual(value['cas_Code'], ['a', 'b'])
        self.assertEqual(value['cas_Nm'], ['A', 'B'])
        self.assertEqual(value['fnclty_Irdnt_Thesis_List'][0]['item']['title'], 'Paper A')
        self.assertEqual(value['fnclty_Irdnt_Thesis_List'][1]['item'][1]['title'], 'Paper C')

    def test_errors_credentials_and_xml_entities_are_not_exposed(self):
        for raw in (XML.replace('200', '30'), '<html>fake-secret</html>',
                    '<error>fake%2Dsecret</error>', '<!DOCTYPE x><x/>', '<html>not XML', '<response/>'):
            with self.subTest(raw_type=raw[:10]):
                with self.assertRaises(RuntimeError) as caught:
                    parse_response(raw, 'fake-secret')
                self.assertNotIn('fake-secret', str(caught.exception))

    def test_key_loading_quotes_decoding_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, '.env').write_text("AGRIFOOD_API_KEY='fake%2Bfile%3D'\n", encoding='utf-8')
            with patch('collect_agrifood.ROOT', Path(temp)), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(key_from_env(), 'fake+file=')
                with patch.dict(os.environ, {'AGRIFOOD_API_KEY': 'env-key'}):
                    self.assertEqual(key_from_env(), 'env-key')

    def test_request_matches_official_parameter_names_and_response_identity(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = XML.encode()
        with patch('collect_agrifood.urlopen', return_value=response) as fetch:
            request_metadata('fake-key', 'S-14-074', 'G001', 'food-ingredients', 2, 5)
            url = urlsplit(fetch.call_args.args[0])
            self.assertEqual(url.hostname, 'apis.data.go.kr')
            params = parse_qs(url.query)
            self.assertEqual(params['sample_Id'], ['S-14-074'])
            self.assertEqual(params['Page_No'], ['2'])
            self.assertEqual(params['Page_Size'], ['5'])
            request_metadata('fake-key', 'S-14-074', 'G001')
            self.assertNotIn('Page_No', parse_qs(urlsplit(fetch.call_args.args[0]).query))
            response.__enter__.return_value.read.return_value = XML.replace('S-14-074', 'S-00-000').encode()
            with self.assertRaisesRegex(RuntimeError, 'mismatched'):
                request_metadata('fake-key', 'S-14-074', 'G001')

    def test_network_failure_hides_request_details(self):
        with patch('collect_agrifood.urlopen', side_effect=URLError('fake-secret-url')):
            with self.assertRaises(RuntimeError) as caught:
                request_metadata('fake-key', 'S-14-074', 'G001')
        self.assertNotIn('fake-secret-url', str(caught.exception))

    def test_local_inspection_keeps_research_type_and_does_not_display_unbased_amounts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'config').mkdir()
            (root / 'config/agrifood_sources.json').write_text(json.dumps(dict(source_url='https://example.invalid', license='inspection')), encoding='utf-8')
            (root / 'data/raw/agrifood').mkdir(parents=True)
            (root / 'data/raw/agrifood/test-food-ingredients.json').write_text(json.dumps(parse_response(XML, 'fake-secret')), encoding='utf-8')
            with patch('collect_agrifood.ROOT', root):
                summaries = inspection_report()
            html = (root / 'data/agrifood_inspection.html').read_text(encoding='utf-8')
            self.assertEqual(summaries[0]['paper_record_count'], 3)
            self.assertIn('동물시험', html)
            self.assertIn('Paper A', html)
            self.assertNotIn('190', html)
            self.assertFalse(json.loads((root / 'data/agrifood_inspection.json').read_text(encoding='utf-8'))['generation_enabled'])


if __name__ == '__main__':
    unittest.main()
