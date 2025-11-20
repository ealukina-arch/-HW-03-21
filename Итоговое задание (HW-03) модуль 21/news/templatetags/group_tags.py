from django import template

register = template.Library()

@register.filter
def in_group(user, group_name):
    """Проверяет, находится ли пользователь в указанной группе"""
    return user.groups.filter(name=group_name).exists()

@register.filter
def has_perm_for_model(user, model_name):
    """Проверяет, есть ли у пользователя права на модель"""
    perms = [
        f'news.add_{model_name}',
        f'news.change_{model_name}',
        f'news.delete_{model_name}',
        f'news.view_{model_name}'
    ]
    return any(user.has_perm(perm) for perm in perms)