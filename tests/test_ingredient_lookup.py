import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ingredient_lookup import recipe_ingredients,query_ingredients,lookup,nutrition_lookup_names


class IngredientChecks(unittest.TestCase):
    def test_lookup_is_separate_from_nutrition_recommendation(self):
        recipe=dict(ingredients_text='두부 100g')
        self.assertEqual(nutrition_lookup_names('방울토마토 영양정보',recipe),['방울토마토'])
        self.assertEqual(nutrition_lookup_names('두부 단백질은 얼마야?',recipe),['두부'])
        self.assertEqual(nutrition_lookup_names('단백질 많은 요리 추천',recipe),[])
        self.assertEqual(nutrition_lookup_names('1인분 단백질 10g 이상인 요리',recipe),[])

    def test_recipe_reference_and_longest_name(self):
        recipe=dict(ingredients_text='연두부 75g, 칵테일새우 20g, 달걀 30g')
        self.assertEqual(query_ingredients('그 재료들의 영양성분은?',recipe),['연두부','칵테일새우','달걀'])
        self.assertEqual(query_ingredients('연두부 단백질',recipe),['연두부'])
        self.assertEqual(recipe_ingredients('두부(100g), 시금치(5g)'),['두부','시금치'])

    def test_no_dish_substitution_and_missing(self):
        dish=dict(name='두부찌개',data_group='음식')
        self.assertEqual(lookup(['두부'],[dish])['nutrition_rows'],[])
        self.assertIn('대신하지 않습니다',lookup(['두부'],[])['answer'])

    def test_state_and_basis_are_preserved(self):
        food=dict(name='시금치, 생것',data_group='원재료성',basis_label='100g',source_url='https://example.org',protein_g=2,energy_kcal=20)
        rows=lookup(['시금치'],[food])['nutrition_rows']
        self.assertEqual(rows[0]['영양 데이터 후보'],'시금치, 생것')
        self.assertEqual(rows[0]['기준량'],'100g')
        self.assertEqual(rows[0]['연결 상태'],'종류·조리 상태 확인 필요')
