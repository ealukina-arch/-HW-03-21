from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from news.models import Post


def setup_authors_permissions():
    # Получаем или создаем группу authors
    authors_group, created = Group.objects.get_or_create(name='authors')
    print(f"Группа 'authors': {'создана' if created else 'уже существует'}")

    # Получаем права для модели Post
    content_type = ContentType.objects.get_for_model(Post)
    post_permissions = Permission.objects.filter(content_type=content_type)

    # Добавляем права к группе
    authors_group.permissions.set(post_permissions)

    print(f"Назначено прав для группы 'authors': {post_permissions.count()}")
    for perm in post_permissions:
        print(f"  - {perm.name}")

    return authors_group


if __name__ == "__main__":
    setup_authors_permissions()