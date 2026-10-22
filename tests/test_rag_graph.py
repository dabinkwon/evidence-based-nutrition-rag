import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from rag_graph import build_graph, answer_options, evidence_context
from recipe_rag import generate


class GraphChecks(unittest.TestCase):
    def setUp(self):
        self.meta = dict(id='recipe:1', collection='recipes', title='shrimp',
                         ingredients='shrimp', text='recipe facts', source_url='https://example.invalid/item')
        self.source = dict(id='recipe:1:doc:0', collection='guidelines', title='source',
                           text='source facts', source_url='https://example.invalid/source',
                           related_item_id='recipe:1')
        self.config = dict(GMS_API_KEY='fake', GMS_MODEL='fake', GMS_BASE_URL='https://example.invalid')

    def state(self):
        return dict(question='question', docs=[self.meta, self.source], selected='recipe:1',
                    excluded=[], config=self.config, options=dict(top_k=2, min_score=0.3),
                    retriever='chroma', do_generate=False)

    def test_actual_graph_nodes_merge_and_top_k(self):
        graph = build_graph()
        self.assertEqual(set(graph.get_graph().nodes), {'__start__', 'retrieve', 'generate', '__end__'})
        with patch('index_vectors.retrieve', return_value=[self.meta, self.source, self.source]) as backend:
            result = graph.invoke(self.state())
        self.assertEqual([d['id'] for d in result['evidence']], [self.meta['id'], self.source['id']])
        self.assertEqual([d['evidence_number'] for d in result['evidence']], [1, 2])
        self.assertEqual(result['evidence'][1]['evidence_type'], 'external_document')
        self.assertEqual(backend.call_args.kwargs['top_k'], 2)

    def test_selected_context_survives_search_failure(self):
        with patch('index_vectors.retrieve', side_effect=RuntimeError('synthetic')):
            result = build_graph().invoke(self.state())
        self.assertEqual(result['evidence'][0]['id'], 'recipe:1')
        self.assertTrue(result['warnings'])

    def test_excluded_context_is_kept_but_generation_blocked(self):
        state = self.state() | dict(excluded=['shrimp'], do_generate=True)
        with patch('index_vectors.retrieve', return_value=[]), patch('openai.OpenAI') as api:
            result = build_graph().invoke(state)
        self.assertTrue(result['evidence'][0]['recommendation_blocked'])
        self.assertEqual(result['generation']['status'], 'excluded_selected')
        api.assert_not_called()

    def test_only_used_sources_and_numbered_claim(self):
        with patch('openai.OpenAI') as api:
            api.return_value.__enter__.return_value.responses.create.return_value.output_text = 'fact [근거 2]'
            result = generate('question', [self.meta, self.source], self.config)
        self.assertEqual(result['citations'][0]['id'], self.source['id'])
        self.assertEqual(len(result['citations']), 1)
        self.assertEqual(result['citations'][0]['number'], 2)
        self.assertEqual(result['citations'][0]['evidence_type'], 'external_document')

    def test_missing_unknown_and_empty_citations(self):
        with patch('openai.OpenAI') as api:
            self.assertTrue(generate('question', [], self.config)['citation_notice'])
            api.assert_not_called()
            for answer in ('no citation', 'fact [근거 99]'):
                api.return_value.__enter__.return_value.responses.create.return_value.output_text = answer
                result = generate('question', [self.meta], self.config)
                self.assertEqual(result['status'], 'invalid_citations')
                self.assertTrue(result['citation_notice'])
                self.assertIsNone(result['answer'])

    def test_typed_citation_normalization_checks_source_type(self):
        with patch('openai.OpenAI') as api:
            create = api.return_value.__enter__.return_value.responses.create
            create.return_value.output_text = 'fact [근거 2: 외부 문서]'
            result = generate('question', [self.meta, self.source], self.config)
            self.assertEqual(result['answer'], 'fact [근거 2]')
            create.return_value.output_text = 'fact [근거 2: 항목 메타데이터]'
            self.assertEqual(generate('question', [self.meta, self.source], self.config)['status'],
                             'invalid_citations')

    def test_external_top_k_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'config.json'
            path.write_text(json.dumps(dict(top_k=1, min_score=0.4)), encoding='utf-8')
            self.assertEqual(answer_options(path)['top_k'], 1)
            path.write_text(json.dumps(dict(top_k=0, min_score=0.4)), encoding='utf-8')
            with self.assertRaises(ValueError):
                answer_options(path)
