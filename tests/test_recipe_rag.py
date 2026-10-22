import sys
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from recipe_rag import documents, retrieve, excluded_hits, generate, NOTICE


class RagChecks(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
