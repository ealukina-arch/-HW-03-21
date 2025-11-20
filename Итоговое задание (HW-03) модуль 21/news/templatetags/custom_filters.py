from django import template
from django.utils.html import strip_tags
import re

register = template.Library()

# Список нежелательных слов (можно расширить)
UNWANTED_WORDS = [
    'редиска', 'плохой',
    'дурак',
]


@register.filter(name='censor')
def censor(value):
    """
    Фильтр для цензурирования нежелательных слов.
    Заменяет все буквы в нежелательных словах на '*', кроме первой.
    """
    if not isinstance(value, str):
        return value

    censored_text = value
    for word in UNWANTED_WORDS:
        # Заменяем слово, сохраняя регистр
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        censored_text = pattern.sub(
            lambda match: match.group()[0] + '*' * (len(match.group()) - 1),
            censored_text
        )

    return censored_text


@register.simple_tag
def is_user_in_group(user, group_name):
    """Проверяет, находится ли пользователь в указанной группе"""
    return user.groups.filter(name=group_name).exists()




