from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from news.models import Post, Category, Subscription


class EmailService:

    @staticmethod
    def send_welcome_email(user, activation_url):
        """Отправка приветственного письма с активацией"""
        subject = '🎉 Добро пожаловать в News Portal!'

        context = {
            'user': user,
            'activation_url': activation_url,
            'site_url': settings.SITE_URL
        }

        text_content = render_to_string('emails/welcome_email.txt', context)
        html_content = render_to_string('emails/welcome_email.html', context)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

    @staticmethod
    def send_activation_success_email(user):
        """Отправка письма об успешной активации"""
        subject = '✅ Ваш аккаунт успешно активирован!'

        context = {
            'user': user,
            'site_url': settings.SITE_URL
        }

        text_content = render_to_string('emails/activation_success.txt', context)
        html_content = render_to_string('emails/activation_success.html', context)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

    @staticmethod
    def send_new_post_notification(post):
        """Отправка уведомлений о новом посте подписчикам"""
        # Используем метод модели Post для отправки уведомлений
        post.send_notifications_to_subscribers()

    @staticmethod
    def send_weekly_digest():
        """Отправка еженедельных дайджестов всем подписчикам"""
        week_ago = timezone.now() - timedelta(days=7)

        # Получаем все активные подписки
        subscriptions = Subscription.objects.select_related('user', 'category').all()

        sent_count = 0
        error_count = 0

        for subscription in subscriptions:
            if subscription.needs_weekly_digest():
                try:
                    category = subscription.category
                    user = subscription.user

                    # Получаем новые статьи за неделю в этой категории
                    new_posts = Post.objects.filter(
                        categories=category,
                        post_type=Post.ARTICLE,
                        created_at__gte=week_ago
                    ).order_by('-created_at')

                    if new_posts.exists():
                        subject = f'📊 Еженедельный дайджест: новые статьи в категории "{category.name}"'

                        context = {
                            'username': user.username,
                            'category_name': category.name,
                            'new_posts': new_posts,
                            'site_url': settings.SITE_URL,
                            'week_start': (timezone.now() - timedelta(days=7)).strftime('%d.%m.%Y'),
                            'week_end': timezone.now().strftime('%d.%m.%Y'),
                            'unsubscribe_url': f"{settings.SITE_URL}/news/category/{category.id}/unsubscribe/",
                        }

                        text_content = render_to_string('emails/weekly_digest.txt', context)
                        html_content = render_to_string('emails/weekly_digest.html', context)

                        send_mail(
                            subject=subject,
                            message=text_content,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[user.email],
                            html_message=html_content,
                            fail_silently=False,
                        )

                        # Обновляем время последней рассылки
                        subscription.last_weekly_sent = timezone.now()
                        subscription.save()

                        sent_count += 1
                        print(f"✅ Еженедельный дайджест отправлен {user.email}")

                except Exception as e:
                    error_count += 1
                    print(f"❌ Ошибка отправки дайджеста для {user.email}: {e}")

        return {
            'sent': sent_count,
            'errors': error_count,
            'total': sent_count + error_count
        }

    @staticmethod
    def send_immediate_article_notification(post):
        """Отправка мгновенных уведомлений о новой статье подписчикам"""
        if post.post_type != Post.ARTICLE:
            return

        categories = post.categories.all()

        for category in categories:
            subscribers = category.subscribers.all()

            for subscriber in subscribers:
                if subscriber.email:
                    try:
                        subject = f'📄 Новая статья в категории "{category.name}"'

                        context = {
                            'username': subscriber.username,
                            'post_title': post.title,
                            'post_preview': post.preview(),
                            'category_name': category.name,
                            'post_url': f"{settings.SITE_URL}/news/{post.id}/",
                            'author_name': post.author.user.username,
                            'post_date': post.created_at.strftime('%d.%m.%Y в %H:%M'),
                            'unsubscribe_url': f"{settings.SITE_URL}/news/category/{category.id}/unsubscribe/",
                        }

                        text_content = render_to_string('emails/new_article_notification.txt', context)
                        html_content = render_to_string('emails/new_article_notification.html', context)

                        send_mail(
                            subject=subject,
                            message=text_content,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[subscriber.email],
                            html_message=html_content,
                            fail_silently=False,
                        )
                        print(f"✅ Уведомление о статье отправлено {subscriber.email}")

                    except Exception as e:
                        print(f"❌ Ошибка отправки уведомления о статье для {subscriber.email}: {e}")