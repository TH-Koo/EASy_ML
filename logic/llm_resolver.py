"""Deterministic company/model resolution. No Ollama, network calls or cache writes.

Only manually reviewed aliases are used; historical LLM cache is deliberately ignored.
"""
import re

# Verified/common spelling aliases, NOT a general claim of legal ownership.
# Extend only after checking the official corporate identity.
COMPANY_ALIASES = {
    '삼성': ['삼성전자'],
    '삼성전자': ['삼성전자', 'SAMSUNG ELECTRONICS'],
    'LG': ['엘지전자', 'LG전자'],
    'LG전자': ['엘지전자', 'LG전자'],
    '엘지전자': ['엘지전자', 'LG전자'],
    '에브리봇': ['에브리봇', 'EVERBOT'],
    '코웨이': ['코웨이', 'COWAY'],
    '로보락': ['로보락', 'Roborock'],
    '레노버': ['레노버', 'Lenovo'],
    '아이리버': ['아이리버'],  # 드림어스컴퍼니와의 법인 관계는 별도 검증 후 등록
}

def _clean(name):
    return re.sub(r'\s+', ' ', str(name or '')).strip()

def get_company_aliases(brand_name):
    name = _clean(brand_name)
    if not name or name in ('미확인', '없음'):
        return []
    aliases = COMPANY_ALIASES.get(name, [name])
    return list(dict.fromkeys([name, *aliases]))

def resolve_real_company_name(brand_name, product_name=''):
    """Compatibility API: comma-delimited candidates for existing pipeline."""
    return ','.join(get_company_aliases(brand_name)) or _clean(brand_name)

def resolve_model_name(product_title, specs_text=''):
    """Conservative fallback; never invent a model number."""
    text = str(product_title or '')
    pattern = r'(?<![A-Za-z0-9])(?=[A-Za-z0-9-]*\d)[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+(?![A-Za-z0-9])'
    candidates = re.findall(pattern, text)
    blacklist = {'WI-FI', 'USB-C', 'TYPE-C'}
    return next((m.upper() for m in candidates if m.upper() not in blacklist), '')
