PROTECTION_LEVEL_FIRST = '国家一级重点保护野生动物'
PROTECTION_LEVEL_SECOND = '国家二级重点保护野生动物'
PROTECTION_LEVEL_THREE = '国家三有保护动物'

_EMPTY_VALUES = {'', '-', '--', '—', '无', '无保护', '暂无', '暂无等级', '未标注', 'nan', 'none', 'null'}
_FIRST_VALUES = {'Ⅰ', 'I', '1', '一', '一级', '国家一级', '国家I级', '国家Ⅰ级'}
_SECOND_VALUES = {'Ⅱ', 'II', '2', '二', '二级', '国家二级', '国家II级', '国家Ⅱ级'}
_THREE_VALUES = {'三有', '三有动物', '国家三有'}


def _compact(value):
    text = str(value or '').strip()
    return ''.join(text.split())


def normalize_protection_level(value, blank_value=''):
    """Return the canonical protection level stored and displayed by the platform."""
    text = _compact(value)
    if text.lower() in _EMPTY_VALUES:
        return blank_value

    upper = text.upper()
    if text == PROTECTION_LEVEL_FIRST:
        return PROTECTION_LEVEL_FIRST
    if text == PROTECTION_LEVEL_SECOND:
        return PROTECTION_LEVEL_SECOND
    if text == PROTECTION_LEVEL_THREE:
        return PROTECTION_LEVEL_THREE

    if upper in _SECOND_VALUES or '二级' in text or 'Ⅱ' in text:
        return PROTECTION_LEVEL_SECOND
    if upper in _FIRST_VALUES or '一级' in text or 'Ⅰ' in text:
        return PROTECTION_LEVEL_FIRST
    if any(keyword in text for keyword in _THREE_VALUES):
        return PROTECTION_LEVEL_THREE

    return text


def get_protection_group(value):
    normalized = normalize_protection_level(value)
    if normalized == PROTECTION_LEVEL_FIRST:
        return '国家一级'
    if normalized == PROTECTION_LEVEL_SECOND:
        return '国家二级'
    if normalized == PROTECTION_LEVEL_THREE:
        return '三有动物'
    return '无危/其他'
