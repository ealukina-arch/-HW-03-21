from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import datetime
from .models import Post


class AuthRequiredMixin(LoginRequiredMixin):
    """Миксин для проверки аутентификации пользователя"""
    login_url = '/accounts/login/'  # Используем allauth URL

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'Для доступа к этой странице необходимо войти в систему.')
            return redirect(self.login_url)
        return super().dispatch(request, *args, **kwargs)


class PermissionRequiredMixinWithMessage(PermissionRequiredMixin):
    """Миксин для проверки прав с пользовательскими сообщениями"""
    permission_denied_message = "У вас недостаточно прав для доступа к этой странице."

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


class AuthorRequiredMixin(UserPassesTestMixin):
    """Миксин для проверки, что пользователь является автором"""
    permission_denied_message = "Только авторы могут создавать и редактировать контент."

    def test_func(self):
        return (self.request.user.is_authenticated and
                self.request.user.groups.filter(name='authors').exists())

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


class NewsLimitMixin:
    """Миксин для ограничения создания новостей (3 в сутки)"""

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST':
            user = request.user
            if hasattr(user, 'author'):
                today = timezone.now().date()
                today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))

                news_count_today = Post.objects.filter(
                    author=user.author,
                    post_type=Post.NEWS,
                    created_at__gte=today_start
                ).count()

                if news_count_today >= 3:
                    raise PermissionDenied(
                        f'Вы достигли лимита в 3 новости в сутки. '
                        f'Сегодня вы уже опубликовали {news_count_today} новостей.'
                    )

        return super().dispatch(request, *args, **kwargs)


class OwnerRequiredMixin(UserPassesTestMixin):
    """Миксин для проверки владения объектом"""
    permission_denied_message = "Вы можете редактировать только свой собственный контент."

    def test_func(self):
        obj = self.get_object()
        return (obj.author.user == self.request.user or
                self.request.user.is_staff)

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


# Комбинированные миксины для удобства
class AuthorAccessMixin(AuthRequiredMixin, AuthorRequiredMixin):
    """Комбинированный миксин для доступа авторов"""
    pass


class NewsCreateMixin(AuthRequiredMixin, AuthorRequiredMixin, NewsLimitMixin):
    """Миксин для создания новостей со всеми проверками"""
    pass


class ContentEditMixin(AuthRequiredMixin, OwnerRequiredMixin):
    """Миксин для редактирования контента (только владелец)"""
    pass