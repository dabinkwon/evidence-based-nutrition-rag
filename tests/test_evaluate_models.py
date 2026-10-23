import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evaluate_models import CASES, run_one, write_html, summarize_comparison, run_answer, summarize_answer_comparison


class EvaluationChecks(unittest.TestCase):
    def test_answer_only_keeps_input_fixed_and_does_not_mutate_evidence_or_settings(self):
        evidence = [dict(id='recipe:28', collection='recipes', title='tofu', text='facts', source_url='https://example.invalid')]
        before = json.dumps(evidence, sort_keys=True)
        config = dict(GMS_MODEL='legacy', GMS_ANSWER_MODEL='luna')
        with patch('evaluate_models.generate', return_value=dict(status='generated_unreviewed', answer='fixed', citations=[])) as generator:
            first = run_answer(CASES[0], 'single', 1, evidence, config)
            second = run_answer(CASES[0], 'split', 1, evidence, config | {'GMS_ANSWER_MODEL': 'sol'})
        self.assertEqual(json.dumps(evidence, sort_keys=True), before)
        self.assertEqual(config['GMS_ANSWER_MODEL'], 'luna')
        self.assertEqual(first['generation_input_hash'], second['generation_input_hash'])
        self.assertEqual(first['evidence'], second['evidence'])
        self.assertEqual(generator.call_count, 2)
        summary = summarize_answer_comparison(dict(cases=[CASES[0]], repeats=1, results=[first, second]))
        self.assertEqual(summary['same_generation_input_pairs'], 1)
        self.assertEqual(summary['same_evidence_pairs'], 1)

    def test_paired_collection_uses_identical_queries_candidates_and_leaves_config_unchanged(self):
        item = dict(id='recipe:28', name='tofu', ingredients='bean')
        bundle = [dict(document_id='cookrcp01-28', title='tofu', summary='own',
                       text='tofu recipe facts', source_url='https://example.invalid', item_ids=['recipe:28'])]
        options = dict(chunk_size=1000, chunk_overlap=200, min_document_chars=0, max_candidates_per_query=12)
        payloads = []
        def ask(prompt, payload, config):
            payloads.append((payload, config['GMS_MODEL']))
            return '["cookrcp01-28"]'
        config = dict(GMS_MODEL='old', GMS_QUERY_MODEL='query', GMS_ANSWER_MODEL='answer')
        original = dict(config)
        with patch('evaluate_models.ask_json', side_effect=ask), patch('evaluate_models.generate', return_value=dict(status='generated_unreviewed', answer='fixed answer', citations=[])):
            first = run_one(CASES[0], 'single', 1, item, bundle, options, config, '["tofu"]')
            second = run_one(CASES[0], 'split', 1, item, bundle, options, config | {'GMS_SELECTION_MODEL': 'new'}, '["tofu"]')
        self.assertEqual(payloads[0][0], payloads[1][0])
        self.assertEqual([p[1] for p in payloads], ['old', 'new'])
        self.assertEqual(config, original)
        self.assertEqual(first['collection']['candidate_ids'], second['collection']['candidate_ids'])
        self.assertTrue(first['mandatory_source_present'])
        self.assertEqual(first['selection_calls'][0]['payload_hash'], second['selection_calls'][0]['payload_hash'])
        summary = summarize_comparison(dict(cases=[CASES[0]], repeats=1, results=[first, second]))
        self.assertEqual(summary['paired_runs'], 1)
        self.assertEqual(summary['same_candidate_pairs'], 1)
        self.assertEqual(summary['same_evidence_pairs'], 1)
        self.assertNotIn('accuracy', summary)

    def test_failure_report_is_safe_and_visible(self):
        item = dict(id='recipe:28', name='tofu', ingredients='bean')
        with patch('evaluate_models.collect', side_effect=RuntimeError('secret-value-must-not-leak')):
            result = run_one(CASES[0], 'single', 1, item, [], {}, {}, '[]')
        self.assertEqual(result['status'], 'experiment_error')
        self.assertNotIn('secret-value', json.dumps(result))
        report = dict(started_at='fixed', cases=CASES, repeats=1, results=[], query_error={'status': 'failed'})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'report.html'
            write_html(report, path)
            text = path.read_text(encoding='utf-8')
        self.assertIn('실제 답변 비교가 수행되지 않았습니다', text)
        self.assertIn('실행되지 않음', text)
        summary = summarize_comparison(report)
        self.assertEqual(summary['paired_runs'], 0)
        self.assertEqual(summary['timing'], {})


if __name__ == '__main__':
    unittest.main()
