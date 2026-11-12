import copy
import json

from django import template
from django.utils.translation import gettext, override

register = template.Library()


@register.filter
def chinese_log_message(entry):
    """Translate labels saved in older English-language admin audit entries."""
    with override('zh-hans'):
        if not entry.change_message.startswith('['):
            return entry.get_change_message()
        try:
            changes = json.loads(entry.change_message)
        except json.JSONDecodeError:
            return entry.change_message
        for change in changes:
            for action in change.values():
                if 'fields' in action:
                    action['fields'] = [gettext(label[:1].lower() + label[1:]) for label in action['fields']]
                if 'name' in action:
                    label = action['name']
                    action['name'] = gettext(label[:1].lower() + label[1:])
        localized = copy.copy(entry)
        localized.change_message = json.dumps(changes, ensure_ascii=False)
        return localized.get_change_message()
