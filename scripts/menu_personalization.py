"""Profile validation and conservative menu screening; no medical formula."""
import math

# Explicit, limited synonym dictionary; it is not a comprehensive allergen database.
ALIASES = {
    '계란': ('계란', '달걀', '난백', '난황', '흰자', '노른자'),
    '달걀': ('계란', '달걀', '난백', '난황', '흰자', '노른자'),
    '우유': ('우유', '생크림', '버터', '치즈', '요거트', '요구르트'),
    '소고기': ('소고기', '쇠고기'),
    '대두': ('대두', '두부', '콩', '된장', '간장', '두유'),
}


def validate_profile(profile):
    """Validate structure; supported population and activity scheme remain unconfirmed."""
    for field in ('age', 'height_cm', 'weight_kg'):
        value = profile.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{field} must be a positive finite number')
    if not isinstance(profile['age'], int):
        raise ValueError('age must be an integer')
    for field in ('sex', 'activity_level'):
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            raise ValueError(f'{field} is required')
    for field in ('preferences', 'excluded_ingredients'):
        value = profile.get(field)
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            raise ValueError(f'{field} must be a list of nonempty strings')
    return profile


def screen_menus(profile, menus):
    """Return review outcomes, never treat unverified menus as ready recommendations."""
    validate_profile(profile)
    results = []
    for menu in menus:
        text = (menu['name'] + ' ' + menu['ingredients_text']).casefold().replace(' ', '')
        hits = [term for term in profile['excluded_ingredients']
                if any(alias.casefold().replace(' ', '') in text
                       for alias in ALIASES.get(term, (term,)))]
        preferences = [term for term in profile['preferences']
                       if term.casefold().replace(' ', '') in text]
        reasons = []
        if hits:
            reasons.append('excluded_ingredient_detected')
        if menu.get('ingredients_review_status') != 'verified':
            reasons.append('ingredients_not_verified')
        if not menu.get('nutrition_ready') or not menu.get('nutrition_food_id'):
            reasons.append('nutrition_link_not_verified')
        # Demographic numbers do not alter ranking until a sourced energy model exists.
        reasons.append('energy_model_not_configured')
        results.append(dict(menu_id=menu['menu_id'], name=menu['name'],
                            excluded_hits=hits, preference_hits=preferences,
                            ready_for_personalized_recommendation=False,
                            blocking_reasons=reasons))
    return sorted(results, key=lambda x: (bool(x['excluded_hits']), -len(x['preference_hits']), x['menu_id']))
