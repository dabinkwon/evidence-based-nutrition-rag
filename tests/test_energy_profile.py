import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from energy_profile import calculate, portion, candidates, assess_foods


class EnergyChecks(unittest.TestCase):
    def test_assessment_explains_all_outcomes(self):
        food=dict(food_id='a',name='검증 음식',basis_unit='g',basis_amount=100,energy_kcal=100)
        rows=assess_foods([food,food|dict(food_id='b',energy_kcal=201),food|dict(food_id='c',basis_unit='ml')],'',100,100)
        self.assertEqual([r['status'] for r in rows],['within','over','unknown'])
        self.assertEqual(rows[0]['delta_kcal'],0)
        self.assertEqual(rows[1]['delta_kcal'],-101)
        self.assertIn('많습니다',rows[1]['reason'])
        self.assertEqual(assess_foods([food],'',100,100,['새우'])[0]['status'],'unknown')
    def test_formula_and_user_resting(self):
        r=calculate(30,'male',170,70,'low',1.5)
        self.assertEqual(r['rmr_kcal'],1617.5)
        self.assertEqual(r['maintenance_kcal'],2426.25)
        self.assertEqual(calculate(30,'female',170,70,'low',1.5)['rmr_kcal'],1451.5)
        self.assertEqual(calculate(30,'male',170,70,'low',1.5,1500)['maintenance_kcal'],2250)

    def test_invalid_and_out_of_scope(self):
        for args in [(18,'male',170,70,'low',1.5),(30,'male',float('nan'),70,'low',1.5),
                     (30,'male',170,70,'low',1.6),(30,'x',170,70,'low',1.5)]:
            with self.assertRaises(ValueError): calculate(*args)
        with self.assertRaises(ValueError): calculate(30,'male',170,70,'low',1.5,eligible=False)

    def test_portion_and_candidate_gates(self):
        food=dict(food_id='x',name='합성음식',basis_unit='g',basis_amount=100,energy_kcal=100,
                  protein_g=4,carbohydrate_g=10,fat_g=None,sodium_mg=0)
        self.assertEqual(portion(food,150)['protein_g'],6)
        self.assertIsNone(portion(food,150)['fat_g'])
        self.assertEqual(portion(food,150)['sodium_mg'],0)
        self.assertEqual(len(candidates([food],'합성',150,200)),1)
        self.assertEqual(len(candidates([food],'',150,200)),1)
        self.assertEqual(candidates([food],'합성',150,100),[])
        self.assertEqual(candidates([food],'합성',150,200,['새우']),[])
        with self.assertRaises(ValueError):portion(food|dict(basis_unit='ml'),150)
