import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_menu_catalog import candidates
from menu_personalization import screen_menus, validate_profile


class MenuChecks(unittest.TestCase):
    def profile(self, **updates):
        return dict(age=30, sex='female', height_cm=165, weight_kg=60,
                    activity_level='pending_definition', preferences=[], excluded_ingredients=[]) | updates

    def menu(self):
        return dict(menu_id='recipe:28', name='새우 두부 계란찜',
                    ingredients_text='달걀 30g, 생크림 13g',
                    ingredients_review_status='unreviewed', nutrition_ready=False)

    def test_exact_name_is_still_unverified(self):
        links = candidates({'name':'된장국'}, [{'name':'된장국','food_id':'a'}])
        self.assertEqual(links[0]['status'], 'needs_review')

    def test_unrelated_name_does_not_link(self):
        self.assertEqual(candidates({'name':'햄버거스테이크'}, [{'name':'햄버거','food_id':'a'}])[0]['status'], 'needs_review')
        self.assertEqual(candidates({'name':'새우찜'}, [{'name':'현미밥','food_id':'b'}]), [])

    def test_invalid_input(self):
        for updates in ({'weight_kg':float('nan')}, {'age':True}, {'preferences':'새우'}, {'activity_level':''}):
            with self.assertRaises(ValueError):
                validate_profile(self.profile(**updates))

    def test_egg_and_dairy_aliases(self):
        row = screen_menus(self.profile(excluded_ingredients=['계란','우유']), [self.menu()])[0]
        self.assertEqual(row['excluded_hits'], ['계란','우유'])
        self.assertFalse(row['ready_for_personalized_recommendation'])

    def test_unknown_ingredients_cannot_pass(self):
        row = screen_menus(self.profile(), [self.menu()])[0]
        self.assertIn('ingredients_not_verified', row['blocking_reasons'])
        self.assertIn('energy_model_not_configured', row['blocking_reasons'])

    def test_preference_does_not_override_exclusion(self):
        row = screen_menus(self.profile(preferences=['새우'], excluded_ingredients=['새우']), [self.menu()])[0]
        self.assertEqual(row['preference_hits'], ['새우'])
        self.assertEqual(row['excluded_hits'], ['새우'])
        self.assertFalse(row['ready_for_personalized_recommendation'])


if __name__ == '__main__':
    unittest.main()
