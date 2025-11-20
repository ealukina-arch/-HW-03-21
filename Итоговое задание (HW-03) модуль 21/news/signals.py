from django.db.models.signals import m2m_changed, post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added

from .models import Post, Author, ActivationToken, Category, Subscription
from .services.email_service import EmailService
import logging

# Настройка логгера
logger = logging.getLogger('news.signals')


# 🔄 СИГНАЛЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
@receiver(user_signed_up)
def handle_user_signed_up(sender, request, user, **kwargs):
    """
    Обработка регистрации пользователя через django-allauth
    """
    logger.info(f"🆕 Регистрация пользователя через allauth: {user.email}")

    try:
        # Добавляем в группу common
        common_group, created = Group.objects.get_or_create(name='common')
        user.groups.add(common_group)

        # Создаем профиль автора
        author, author_created = Author.objects.get_or_create(user=user)

        # Создаем токен активации
        activation_token = ActivationToken.create_token(user)

        # Формируем URL для активации
        activation_url = f"{settings.SITE_URL}/accounts/activate/{activation_token.token}/"

        # Отправляем приветственное письмо
        EmailService.send_welcome_email(user, activation_url)

        logger.info(f"✅ Пользователь {user.email} зарегистрирован. Author создан: {author_created}")

    except Exception as e:
        logger.error(f"❌ Ошибка при обработке регистрации пользователя {user.email}: {e}")


@receiver(social_account_added)
def handle_social_signup(sender, request, sociallogin, **kwargs):
    """
    Обработка регистрации через социальные сети
    """
    user = sociallogin.user
    logger.info(f"🌐 Социальная регистрация: {user.email} через {sociallogin.account.provider}")

    # Для социальных регистраций сразу активируем аккаунт
    activation_token, created = ActivationToken.objects.get_or_create(user=user)
    activation_token.activated = True
    activation_token.save()


@receiver(post_save, sender=User)
def handle_user_post_save(sender, instance, created, **kwargs):
    """
    Резервный обработчик для пользователей (на случай если allauth не сработает)
    """
    if created and not instance.is_staff:
        logger.info(f"🆕 Резервная обработка пользователя: {instance.username}")

        # Проверяем, не обработан ли уже пользователь
        if not instance.groups.filter(name='common').exists():
            common_group, created = Group.objects.get_or_create(name='common')
            instance.groups.add(common_group)

            # Создаем профиль автора
            Author.objects.get_or_create(user=instance)


# 🔄 СИГНАЛЫ ДЛЯ АВТОРОВ
@receiver(post_save, sender=User)
def create_author_profile(sender, instance, created, **kwargs):
    """
    Создает профиль автора при создании пользователя
    """
    if created and not hasattr(instance, 'author'):
        Author.objects.create(user=instance)
        logger.info(f"👤 Создан профиль автора для: {instance.username}")


@receiver(post_delete, sender=Author)
def cleanup_user_group(sender, instance, **kwargs):
    """
    Очистка групп при удалении автора
    """
    try:
        instance.user.groups.filter(name='authors').delete()
        logger.info(f"🧹 Удалены группы автора для: {instance.user.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке групп: {e}")


# 🔄 СИГНАЛЫ ДЛЯ ПОСТОВ И УВЕДОМЛЕНИЙ
@receiver(m2m_changed, sender=Post.categories.through)
def handle_post_categories_changed(sender, instance, action, **kwargs):
    """
    Обрабатывает изменения в категориях поста
    """
    logger.debug(f"🎯 Сигнал M2M: action={action}, пост='{instance.title}'")

    if action == "post_add":
        logger.info(f"🚀 Новые категории добавлены к посту '{instance.title}'")

        # Используем transaction.on_commit для гарантии сохранения в БД
        transaction.on_commit(lambda: process_post_notifications(instance))


@receiver(post_save, sender=Post)
def handle_post_save(sender, instance, created, **kwargs):
    """
    Обрабатывает сохранение поста
    """
    if created:
        logger.info(f"📝 Создан новый пост: '{instance.title}' (тип: {instance.get_post_type_display()})")

        # Для новых постов с уже установленными категориями
        if created and instance.categories.exists():
            logger.info(f"📧 Запланирована отправка уведомлений для нового поста")
            transaction.on_commit(lambda: process_post_notifications(instance))

        # Инвалидация кэша
        cache_keys = [
            'latest_news',
            'news_list',
            f'post_{instance.id}',
            'categories_list'
        ]
        for key in cache_keys:
            cache.delete(key)

        logger.debug("🧹 Кэш очищен после создания поста")


def process_post_notifications(post):
    """
    Обрабатывает отправку уведомлений после коммита транзакции
    """
    logger.info(f"📧 Начало обработки уведомлений для поста: '{post.title}' (ID: {post.pk})")

    try:
        # Перезагружаем пост для получения актуальных данных
        refreshed_post = Post.objects.select_related('author__user').prefetch_related('categories').get(pk=post.pk)

        # Отправляем уведомления в зависимости от типа поста
        if refreshed_post.post_type == Post.NEWS:
            # Для новостей используем стандартный метод
            refreshed_post.send_notifications_to_subscribers()
            logger.info("✅ Уведомления о новости успешно отправлены!")
        elif refreshed_post.post_type == Post.ARTICLE:
            # Для статей используем специальный метод из EmailService
            EmailService.send_immediate_article_notification(refreshed_post)
            logger.info("✅ Уведомления о статье успешно отправлены!")

    except Post.DoesNotExist:
        logger.error(f"❌ Пост с ID {post.pk} не найден в базе данных")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при отправке уведомлений: {e}")


# 🔄 СИГНАЛЫ ДЛЯ АКТИВАЦИИ
@receiver(post_save, sender=ActivationToken)
def handle_activation_token_save(sender, instance, created, **kwargs):
    """
    Обрабатывает изменения в токенах активации
    """
    if instance.activated and not created:  # Только при активации существующего токена
        logger.info(f"✅ Аккаунт активирован: {instance.user.username}")

        try:
            EmailService.send_activation_success_email(instance.user)
            logger.info(f"📧 Письмо об успешной активации отправлено на {instance.user.email}")

            # Добавляем пользователя в группу authors при необходимости
            if not instance.user.groups.filter(name='authors').exists():
                authors_group, created = Group.objects.get_or_create(name='authors')
                instance.user.groups.add(authors_group)
                logger.info(f"👤 Пользователь {instance.user.username} добавлен в группу authors")

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке активации: {e}")


# 🔄 СИГНАЛЫ ДЛЯ ПОДПИСОК
@receiver(post_save, sender=Subscription)
def handle_new_subscription(sender, instance, created, **kwargs):
    """
    Обрабатывает новые подписки
    """
    if created:
        logger.info(f"📩 Новая подписка: {instance.user.username} -> {instance.category.name}")
        print(f"🎯 сигнал: новая подписка создана - {instance.user.username} -> {instance.category.name}")
        # Инвалидация кэша подписок
        cache.delete(f"user_{instance.user.id}_subscriptions")
        cache.delete(f"category_{instance.category.id}_subscribers_count")


@receiver(post_delete, sender=Subscription)
def handle_subscription_removed(sender, instance, **kwargs):
    """
    Обрабатывает удаление подписок
    """
    logger.info(f"📪 Удалена подписка: {instance.user.username} -> {instance.category.name}")

    # Инвалидация кэша подписок
    cache.delete(f"user_{instance.user.id}_subscriptions")
    cache.delete(f"category_{instance.category.id}_subscribers_count")


# 🔄 СИГНАЛЫ ДЛЯ ОЧИСТКИ
@receiver(post_save, sender='news.Comment')
def handle_new_comment(sender, instance, created, **kwargs):
    """
    Обрабатывает новые комментарии
    """
    if created:
        logger.info(f"💬 Новый комментарий от {instance.user.username} к посту '{instance.post.title}'")

        # Инвалидация кэша комментариев
        cache.delete(f"post_{instance.post.id}_comments")
        cache.delete(f"post_{instance.post.id}_comments_count")


def cleanup_expired_tokens():
    """
    Функция для очистки просроченных токенов активации
    """
    try:
        expired_tokens = ActivationToken.objects.filter(
            activated=False,
            created_at__lt=timezone.now() - timezone.timedelta(days=7)
        )

        count = expired_tokens.count()
        if count > 0:
            expired_tokens.delete()
            logger.info(f"🧹 Очищено {count} просроченных токенов активации")

    except Exception as e:
        logger.error(f"❌ Ошибка при очистке токенов: {e}")


# 🆕 СИГНАЛ ДЛЯ ЕЖЕНЕДЕЛЬНЫХ РАССЫЛОК
@receiver(post_save, sender=Post)
def handle_new_article_for_weekly_digest(sender, instance, created, **kwargs):
    """
    Обрабатывает создание новых статей для еженедельной рассылки
    """
    if created and instance.post_type == Post.ARTICLE:
        logger.info(f"📄 Новая статья создана: '{instance.title}' - будет включена в еженедельный дайджест")