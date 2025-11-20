from django.db import models
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from django.utils import timezone
from datetime import timedelta, datetime
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.core.exceptions import ValidationError


class Author(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    rating = models.IntegerField(default=0)

    def update_rating(self):
        """Расчет рейтинга автора на основе всех его постов и комментариев"""
        # Рейтинг постов автора
        post_rating = sum(post.rating for post in self.post_set.all())

        # Рейтинг комментариев автора
        comment_rating = sum(comment.rating for comment in Comment.objects.filter(user=self.user))

        # Рейтинг комментариев к постам автора
        comments_to_posts_rating = sum(
            comment.rating for post in self.post_set.all()
            for comment in post.comment_set.all()
        )

        self.rating = post_rating * 3 + comment_rating + comments_to_posts_rating
        self.save()

    def get_news_count_today(self):
        """Количество новостей, опубликованных автором сегодня"""
        today_start = timezone.make_aware(datetime.combine(timezone.now().date(), datetime.min.time()))
        return self.post_set.filter(
            post_type=Post.NEWS,
            created_at__gte=today_start
        ).count()

    def can_publish_news(self):
        """Проверяет, может ли автор опубликовать еще новость сегодня"""
        return self.get_news_count_today() < 3

    def __str__(self):
        return self.user.username


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    subscribers = models.ManyToManyField(
        User,
        through='Subscription',
        related_name='subscribed_categories',
        blank=True
    )

    def get_subscribers_count(self):
        return self.subscribers.count()

    def get_weekly_posts(self):
        """Возвращает посты за последнюю неделю"""
        week_ago = timezone.now() - timedelta(days=7)
        return self.post_set.filter(created_at__gte=week_ago, post_type=Post.ARTICLE)

    def __str__(self):
        return self.name


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    # 🆕 Поле для отслеживания последней рассылки
    last_weekly_sent = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['user', 'category']  # Предотвращает дублирование подписок

    def __str__(self):
        return f"{self.user.username} - {self.category.name}"

    def needs_weekly_digest(self):
        """Проверяет, нужно ли отправлять еженедельную рассылку"""
        if not self.last_weekly_sent:
            return True
        return timezone.now() - self.last_weekly_sent > timedelta(days=7)


class Post(models.Model):
    ARTICLE = 'AR'
    NEWS = 'NW'
    POST_TYPES = [
        (ARTICLE, 'Статья'),
        (NEWS, 'Новость'),
    ]

    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    post_type = models.CharField(max_length=2, choices=POST_TYPES, default=ARTICLE)
    categories = models.ManyToManyField(Category, through='PostCategory')
    title = models.CharField(max_length=255)
    content = models.TextField()
    rating = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # 🆕 Поле для отслеживания отправки уведомлений
    notifications_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']  # Сортировка по умолчанию - новые сначала

    def clean(self):
        """Валидация при создании/редактировании поста"""
        if self.post_type == self.NEWS and self.pk is None:
            # Проверяем только для новых новостей
            if not self.author.can_publish_news():
                news_count = self.author.get_news_count_today()
                raise ValidationError(
                    f'Вы не можете публиковать более 3 новостей в сутки. '
                    f'Сегодня вы уже опубликовали {news_count} новостей.'
                )

    def save(self, *args, **kwargs):
        """Переопределяем save для вызова валидации"""
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def preview(self):
        return self.content[:124] + '...' if len(self.content) > 124 else self.content

    def like(self):
        self.rating += 1
        self.save()

    def dislike(self):
        self.rating -= 1
        self.save()

    def send_notifications_to_subscribers(self):
        """Отправляет уведомления подписчикам категорий поста"""
        if self.notifications_sent:
            return

        categories = self.categories.all()
        for category in categories:
            subscribers = category.subscribers.all()
            for subscriber in subscribers:
                self._send_single_notification(subscriber, category)

        # Помечаем, что уведомления отправлены
        self.notifications_sent = True
        self.save()

    def _send_single_notification(self, subscriber, category):
        """Отправляет одно уведомление конкретному подписчику"""
        try:
            if self.post_type == self.NEWS:
                subject = f'📰 Новая новость в категории "{category.name}"'
                template = 'emails/new_post_notification.html'
                text_template = 'emails/new_post_notification.txt'
            else:
                subject = f'📄 Новая статья в категории "{category.name}"'
                template = 'emails/new_article_notification.html'
                text_template = 'emails/new_article_notification.txt'

            context = {
                'username': subscriber.username,
                'post_title': self.title,
                'post_preview': self.preview(),
                'category_name': category.name,
                'post_url': f"{settings.SITE_URL}/news/{self.id}/",
                'author_name': self.author.user.username,
                'post_date': self.created_at.strftime('%d.%m.%Y в %H:%M'),
                'unsubscribe_url': f"{settings.SITE_URL}/news/category/{category.id}/unsubscribe/",
            }

            # Текстовая версия
            message = render_to_string(text_template, context)

            # HTML версия
            html_message = render_to_string(template, context)

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[subscriber.email],
                html_message=html_message,
                fail_silently=False,
            )
            print(f"✅ Уведомление отправлено {subscriber.email}")

        except Exception as e:
            print(f"❌ Ошибка отправки уведомления для {subscriber.email}: {e}")


class PostCategory(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "Post Categories"

    def __str__(self):
        return f"{self.post.title} - {self.category.name}"


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    rating = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def like(self):
        self.rating += 1
        self.save()

    def dislike(self):
        self.rating -= 1
        self.save()

    def __str__(self):
        return f"Comment by {self.user.username} on {self.post.title}"


class ActivationToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    activated = models.BooleanField(default=False)

    def is_expired(self):
        expiration_days = 7  # Срок действия токена
        return timezone.now() > self.created_at + timedelta(days=expiration_days)

    def is_valid(self):
        return not self.activated and not self.is_expired()

    @classmethod
    def create_token(cls, user):
        """Создает новый токен активации для пользователя"""
        token = get_random_string(64)
        return cls.objects.create(user=user, token=token)

    def __str__(self):
        status = 'Activated' if self.activated else 'Expired' if self.is_expired() else 'Pending'
        return f"Token for {self.user.username} - {status}"