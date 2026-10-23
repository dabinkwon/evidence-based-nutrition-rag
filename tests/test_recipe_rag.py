import sys
from pathlib import Path
import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from recipe_rag import documents, retrieve, excluded_hits, generate, NOTICE, settings, stage_model


class RagChecks(unittest.TestCase):
    def test_final_example_settings_route_answer_to_sol(self):
        example = Path(__file__).resolve().parents[1] / '.env.example'
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, '.env').write_bytes(example.read_bytes())
            with patch('recipe_rag.ROOT', Path(temp)), patch.dict(os.environ, {}, clear=True):
                config = settings()
        self.assertEqual(stage_model(config, 'query'), 'gpt-6-luna')
        self.assertEqual(stage_model(config, 'selection'), 'gpt-6-luna')
        self.assertEqual(config['GMS_EMBEDDING_MODEL'], 'text-embedding-3-small')
        config['GMS_API_KEY'] = 'test-key'
        evidence = [d for d in self.docs if d['id'] == 'recipe:28']
        with patch('openai.OpenAI') as factory:
            client = factory.return_value.__enter__.return_value
            client.responses.create.return_value.output_text = '근거 [recipe:28]'
            result = generate('만드는 법 알려줘', evidence, config)
        self.assertEqual(client.responses.create.call_args.kwargs['model'], 'gpt-6.1-sol')
        self.assertEqual(result['status'], 'generated_unreviewed')

    def test_stage_settings_precedence_quotes_aliases_and_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, '.env').write_text("GMS_MODEL='legacy'\nGMS_QUERY_MODEL='query-file'\ngms_selection_model=\"selection-file\"\nGMS_ANSWER_MODEL='answer-file'\n", encoding='utf-8')
            with patch('recipe_rag.ROOT', Path(temp)), patch.dict(os.environ, {'GMS_QUERY_MODEL': 'query-env'}, clear=True):
                config = settings()
            self.assertEqual(stage_model(config, 'query'), 'query-env')
            self.assertEqual(stage_model(config, 'selection'), 'selection-file')
            self.assertEqual(stage_model(config, 'answer'), 'answer-file')
            self.assertEqual(stage_model({'GMS_MODEL': 'legacy', 'GMS_QUERY_MODEL': ''}, 'query'), 'legacy')

    @classmethod
    def setUpClass(cls):
        cls.docs = documents()

    def test_documents_preserve_identity_and_limits(self):
        self.assertEqual(sum(d['collection'] == 'recipes' for d in self.docs), 100)
        self.assertGreaterEqual(len(self.docs), 100)
        self.assertEqual(len({d['id'] for d in self.docs}), len(self.docs))
        self.assertTrue(all(NOTICE in d['text'] for d in self.docs if d['collection'] == 'recipes'))

    def test_tofu_search(self):
        rows = retrieve(self.docs, '두부를 쓰는 레시피 추천해줘')
        recipes = [d for d in rows if d['collection'] == 'recipes']
        self.assertTrue(recipes)
        self.assertTrue(all('두부' in d['title'] + d['ingredients'] for d in recipes))

    def test_exclusion_overrides_selection_and_aliases(self):
        rows = retrieve(self.docs, '두부 요리', ['새우', '계란', '우유'], 'recipe:28')
        self.assertNotIn('recipe:28', [d['id'] for d in rows])
        self.assertTrue(all(not excluded_hits(d, ['새우', '계란', '우유']) for d in rows if d['collection'] == 'recipes'))

    def test_selection_and_unknown_id(self):
        rows = retrieve(self.docs, '재료와 조리법 알려줘', selected='recipe:28')
        self.assertEqual(rows[0]['id'], 'recipe:28')
        with self.assertRaises(ValueError):
            retrieve(self.docs, '재료', selected='recipe:missing')

    def test_no_evidence_and_missing_configuration(self):
        self.assertEqual(retrieve(self.docs, 'zzzzzzzz'), [])
        config = {'GMS_API_KEY': '', 'GMS_MODEL': ''}
        self.assertEqual(generate('질문', [], config)['status'], 'no_evidence')
        self.assertEqual(generate('질문', self.docs[:1], config)['status'], 'not_configured')

    def test_generation_routes_to_configured_gateway(self):
        with patch('openai.OpenAI') as factory:
            client = MagicMock()
            factory.return_value.__enter__.return_value = client
            client.responses.create.return_value.output_text = '근거 [recipe:28]'
            evidence = [d for d in self.docs if d['id'] == 'recipe:28']
            config = dict(GMS_API_KEY='test-key', GMS_MODEL='gpt-6-luna',
                          GMS_BASE_URL='https://gateway.example/api.openai.com/v1')
            result = generate('질문', evidence, config)
            self.assertEqual(factory.call_args.kwargs['base_url'], config['GMS_BASE_URL'])
            self.assertEqual(client.responses.create.call_args.kwargs['model'], 'gpt-6-luna')
            self.assertEqual(result['status'], 'generated_unreviewed')
            for overrides in ({'GMS_ANSWER_MODEL': 'answer'}, {'GMS_MODEL': '', 'GMS_ANSWER_MODEL': 'answer'}):
                result = generate('질문', evidence, config | overrides)
                self.assertEqual(client.responses.create.call_args.kwargs['model'], 'answer')
                self.assertEqual(result['status'], 'generated_unreviewed')


if __name__ == '__main__':
    unittest.main()
