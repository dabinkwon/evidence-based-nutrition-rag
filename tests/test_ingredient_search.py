import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ingredient_search import search, matches
from recipe_rag import documents


class IngredientSearchChecks(unittest.TestCase):
    def test_actual_ingredient_search_and_all_terms(self):
        for query in ('두부','두부가 들어간 요리','두부, 달걀','두부와 달걀'):
            result=search(documents(),query)
            self.assertTrue(result['evidence'],query)
            for d in result['evidence']:
                self.assertTrue(matches(d['ingredients'],'두부'))
                if '달걀' in query:
                    self.assertTrue(matches(d['ingredients'],'달걀'))

    def test_title_only_match_is_not_evidence_and_nutrition_blocked(self):
        doc=dict(id='r',collection='recipes',title='두부',ingredients='호박',source_url='https://example.org')
        self.assertEqual(search([doc],'두부')['evidence'],[])
        for query in ('단백질','두부 단백질 요리','고단백 재료 요리','저염 요리'):
            self.assertEqual(search(documents(),query)['generation']['status'],'ingredient_blocked')
        self.assertFalse(search(documents(),'두부',excluded=['두부'])['evidence'])

