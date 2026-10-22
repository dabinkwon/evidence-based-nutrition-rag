"""Adult reference calculations; food portions are user scenarios, not prescriptions."""
import math

FORMULA_URL='https://pubmed.ncbi.nlm.nih.gov/2305711/?dopt=Abstract'
ACTIVITY_URL='https://www.andeal.org/template.cfm?key=4341&template=guide_summary'
ACTIVITY={'sedentary':(1.0,1.4),'low':(1.4,1.6),'active':(1.6,1.9),'very_active':(1.9,2.5)}
EXPLANATION_INSTRUCTIONS='한국어로 제공 evidence에만 근거해 설명하라. 주요 주장마다 evidence_number에 해당하는 [근거 N] 형식으로 인용하라. N은 숫자다. Python 계산값을 변경하거나 재계산하지 마라. 후보는 사용자 지정 중량과 예산 조건을 통과한 참고 음식이며 완성 식단·권장 제공량·감량 처방·알레르기 안전을 보장하지 않는다. RMR을 측정 BMR이라고 하지 마라. 개인 정확도는 미검증이다. 레시피로 자동 연결하지 마라.'


def positive(value, name):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<=0:
        raise ValueError(name+' 값은 양의 유한수여야 합니다.')
    return value


def calculate(age, sex, height_cm, weight_kg, activity, factor, resting_kcal=None, eligible=True):
    if not eligible:
        raise ValueError('적용 대상 확인란이 체크되지 않았습니다. 입력 폼의 “임신·수유 중이 아니며 질환 치료나 특수 식단 관리가 필요하지 않습니다”가 본인에게 맞으면 체크한 뒤 다시 계산해 주세요. 해당 문장이 맞지 않는 경우에는 이 계산을 사용하지 마세요.')
    if type(age) is not int or not 19<=age<=78:
        raise ValueError('현재 공식 적용은 원 연구의 19~78세 범위로 제한합니다.')
    if sex not in ('male','female') or activity not in ACTIVITY:
        raise ValueError('공식 성별 계수와 활동 범주를 확인하세요.')
    h=positive(height_cm,'키'); w=positive(weight_kg,'체중')
    positive(factor,'활동계수')
    lo,hi=ACTIVITY[activity]
    if not lo<=factor<hi:
        raise ValueError('활동계수가 선택 범주 범위를 벗어났습니다.')
    predicted=10*w+6.25*h-5*age+(5 if sex=='male' else -161)
    rmr=positive(resting_kcal,'입력 안정시 대사량') if resting_kcal is not None else positive(predicted,'추정 안정시 대사량')
    return dict(bmi=round(w/(h/100)**2,2),rmr_kcal=round(rmr,2),
                maintenance_kcal=round(rmr*factor,2),activity_factor=factor,
                rmr_method='user_entered' if resting_kcal is not None else 'mifflin_st_jeor_1990',
                formula_version='Mifflin-St Jeor simplified 1990 / AWM activity 2014',
                formula_url=FORMULA_URL,activity_url=ACTIVITY_URL,
                limitation='체중 유지 에너지의 참고 추정. 감량 처방·한 끼 권장량·식단 완성도가 아님. 개인 정확도/한국 성인 집단 검증 미실시.')


def portion(food, grams):
    positive(grams,'음식 중량')
    if food.get('basis_unit')!='g':
        raise ValueError('g 기준량이 확인된 식품만 계산합니다.')
    basis=positive(food.get('basis_amount'),'영양 기준량')
    result={}
    for key in ('energy_kcal','protein_g','carbohydrate_g','fat_g','sodium_mg'):
        value=food.get(key)
        if value is None:
            result[key]=None
        elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('유효하지 않은 영양값')
        else:
            result[key]=round(value*grams/basis,3)
    return result


def candidates(foods, query, grams, budget_kcal, excluded=(), limit=5):
    positive(budget_kcal,'음식 비교 예산')
    rows=[]
    for food in foods:
        if query.strip() and query.strip().casefold() not in food['name'].casefold():
            continue
        # Nutrition DB lacks ingredient lists: do not approve exclusions by name alone.
        if excluded:
            continue
        try:
            nutrients=portion(food,grams)
        except ValueError:
            continue
        energy=nutrients['energy_kcal']
        if energy is None or energy<=0 or energy>budget_kcal:
            continue
        rows.append(dict(food=food,grams=grams,nutrition=nutrients,
                         budget_remaining_kcal=round(budget_kcal-energy,2)))
    return sorted(rows,key=lambda r:(r['budget_remaining_kcal'],r['food']['food_id']))[:limit]


def assess_foods(foods, query, grams, budget_kcal, excluded=()):
    """Explain deterministic gates, including rejected and unverifiable foods."""
    positive(grams,'음식 중량'); positive(budget_kcal,'음식 비교 예산')
    assessed=[]
    for food in foods:
        if query.strip() and query.strip().casefold() not in food['name'].casefold():
            continue
        row=dict(food=food,grams=grams,status='unknown',nutrition=None)
        if excluded:
            row['reason']='재료 목록이 없어 제외 재료('+', '.join(excluded)+') 포함 여부를 확인할 수 없습니다.'
        else:
            try:
                nutrients=portion(food,grams)
                energy=nutrients['energy_kcal']
                if energy is None or energy<=0:
                    raise ValueError('열량 기준값을 확인할 수 없습니다.')
                delta=round(budget_kcal-energy,2)
                row.update(nutrition=nutrients,delta_kcal=delta,
                    budget_percent=round(energy/budget_kcal*100,1),status='within' if delta>=0 else 'over',
                    reason=f'{grams:g}g의 열량 {energy:g} kcal가 비교 예산 {budget_kcal:.1f} kcal보다 '+
                    (f'{delta:.1f} kcal 적거나 같습니다.' if delta>=0 else f'{-delta:.1f} kcal 많습니다.'))
            except ValueError:
                row['reason']='기준량·단위 또는 영양값이 확인되지 않아 비교할 수 없습니다.'
        assessed.append(row)
    return assessed


def context(calculation, rows):
    evidence=[dict(id='calculation:energy',collection='guidelines',title='Python 에너지 참고 계산',
        text=str(calculation),source_url=FORMULA_URL),
        dict(id='formula:activity',collection='guidelines',title='AWM 2014 활동계수 범위',
             text='안정시 대사량에 활동계수를 곱하는 참고 계산. 개인 맞춤 처방이 아니다.',source_url=ACTIVITY_URL)]
    for row in rows:
        f=row['food']
        evidence.append(dict(id='food:'+f['food_id'],collection='guidelines',title=f['name'],
            source_url=f['source_url'],text=str(dict(name=f['name'],basis=f['basis_label'],
            grams=row['grams'],nutrition=row['nutrition'],note='사용자 지정 중량, 요리 레시피와 연결 미확인. 식단이 아닌 음식 비교 후보.'))))
    return evidence
