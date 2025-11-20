from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count
from django.core.mail import send_mass_mail
from django.conf import settings

from .models import Author, Category, Post, Comment, Subscription, ActivationToken, PostCategory
import logging

logger = logging.getLogger('news.admin')


# 🔄 КАСТОМНЫЕ ФИЛЬТРЫ
class CategoryFilter(admin.SimpleListFilter):
    """Фильтр по категориям для постов"""
    title = 'Категория'
    parameter_name = 'category'

    def lookups(self, request, model_admin):
        categories = Category.objects.all()
        return [(cat.id, cat.name) for cat in categories]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(categories__id=self.value())
        return queryset


class AuthorFilter(admin.SimpleListFilter):
    """Фильтр по авторам"""
    title = 'Автор'
    parameter_name = 'author'

    def lookups(self, request, model_admin):
        authors = Author.objects.select_related('user').all()
        return [(author.id, author.user.username) for author in authors]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(author__id=self.value())
        return queryset


# 🔄 INLINE МОДЕЛИ
class PostCategoryInline(admin.TabularInline):
    model = PostCategory
    extra = 1
    verbose_name = 'Категория'
    verbose_name_plural = 'Категории поста'
    autocomplete_fields = ['category']


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 1
    verbose_name = 'Подписка'
    verbose_name_plural = 'Подписки пользователя'
    autocomplete_fields = ['category']


class CategorySubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 1
    verbose_name = 'Подписчик'
    verbose_name_plural = 'Подписчики категории'
    autocomplete_fields = ['user']


class AuthorPostsInline(admin.StackedInline):
    """Inline для отображения постов автора"""
    model = Post
    extra = 0
    readonly_fields = ['title', 'post_type', 'created_at', 'rating']
    can_delete = False
    max_num = 5
    verbose_name = 'Последний пост'
    verbose_name_plural = 'Последние посты автора'
    fk_name = 'author'  # Указываем правильное ForeignKey поле

    def has_add_permission(self, request, obj):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author').order_by('-created_at')


# 🔄 ОСНОВНЫЕ АДМИН-МОДЕЛИ
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ['user', 'rating', 'posts_count', 'last_post_date']
    list_filter = ['rating']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['rating', 'user_info']
    inlines = [AuthorPostsInline]  # Добавляем inline с постами автора
    fieldsets = [
        ('Основная информация', {
            'fields': ['user', 'user_info', 'rating']
        }),
        ('Статистика', {
            'fields': ['posts_count', 'last_post_date'],
            'classes': ['collapse']
        }),
    ]

    def user_info(self, obj):
        return format_html(
            '<strong>Email:</strong> {}<br><strong>Имя:</strong> {}<br><strong>Фамилия:</strong> {}',
            obj.user.email,
            obj.user.first_name or 'Не указано',
            obj.user.last_name or 'Не указано'
        )

    user_info.short_description = 'Информация о пользователе'

    def posts_count(self, obj):
        return obj.post_set.count()

    posts_count.short_description = 'Кол-во постов'

    def last_post_date(self, obj):
        last_post = obj.post_set.order_by('-created_at').first()
        return last_post.created_at if last_post else 'Нет постов'

    last_post_date.short_description = 'Последний пост'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').annotate(
            posts_count=Count('post')
        )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'subscribers_count', 'posts_count', 'is_popular']
    list_filter = ['subscribers']
    search_fields = ['name']
    inlines = [CategorySubscriptionInline]

    def subscribers_count(self, obj):
        count = obj.subscribers.count()
        return format_html(
            '<span style="color: {};">{}</span>',
            'green' if count > 10 else 'orange' if count > 0 else 'red',
            count
        )

    subscribers_count.short_description = '👥 Подписчики'

    def posts_count(self, obj):
        return obj.post_set.count()

    posts_count.short_description = '📄 Постов'

    def is_popular(self, obj):
        return obj.subscribers.count() > 10

    is_popular.boolean = True
    is_popular.short_description = '🔥 Популярная'


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['title', 'post_type_badge', 'author', 'created_at', 'rating', 'categories_list']
    list_filter = [CategoryFilter, AuthorFilter, 'post_type', 'created_at']
    search_fields = ['title', 'content', 'author__user__username']
    list_select_related = ['author__user']
    inlines = [PostCategoryInline]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    actions = ['send_notifications_action']
    save_on_top = True

    fieldsets = [
        ('Основная информация', {
            'fields': ['title', 'content', 'author', 'post_type']
        }),
        ('Дополнительно', {
            'fields': ['rating', 'created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    def post_type_badge(self, obj):
        colors = {
            Post.NEWS: 'blue',
            Post.ARTICLE: 'green'
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.post_type, 'gray'),
            obj.get_post_type_display()
        )

    post_type_badge.short_description = 'Тип'

    def categories_list(self, obj):
        categories = obj.categories.all()[:3]
        category_links = []
        for category in categories:
            category_links.append(
                f'<span style="background: #e9ecef; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{category.name}</span>'
            )

        remaining = obj.categories.count() - 3
        if remaining > 0:
            category_links.append(f'<span style="color: #6c757d;">+{remaining}</span>')

        return format_html(' '.join(category_links))

    categories_list.short_description = '🏷️ Категории'

    def send_notifications_action(self, request, queryset):
        """Действие для ручной отправки уведомлений"""
        success_count = 0
        error_count = 0

        for post in queryset:
            if post.post_type != Post.NEWS:
                self.message_user(
                    request,
                    f"⚠️ '{post.title}' - не новость, уведомления не отправляются",
                    level='WARNING'
                )
                continue

            if not post.categories.exists():
                self.message_user(
                    request,
                    f"⚠️ У поста '{post.title}' нет категорий",
                    level='WARNING'
                )
                continue

            try:
                post.send_notifications_to_subscribers()
                success_count += 1
                logger.info(f"✅ Уведомления отправлены для поста '{post.title}'")
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка отправки уведомлений для '{post.title}': {e}")
                self.message_user(
                    request,
                    f"❌ Ошибка для '{post.title}': {e}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(
                request,
                f"✅ Уведомления отправлены для {success_count} постов"
            )

    send_notifications_action.short_description = "📧 Отправить уведомления подписчикам"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'author__user'
        ).prefetch_related(
            'categories'
        ).annotate(
            categories_count=Count('categories')
        )


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'post_preview', 'created_at', 'rating', 'is_recent']
    list_filter = ['created_at', 'rating']
    search_fields = ['user__username', 'post__title', 'text']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

    def post_preview(self, obj):
        return format_html(
            '<strong>{}</strong><br><small style="color: #666;">{}</small>',
            obj.post.title,
            obj.post.author.user.username
        )

    post_preview.short_description = 'Пост'

    def is_recent(self, obj):
        return obj.created_at >= timezone.now() - timezone.timedelta(hours=24)

    is_recent.boolean = True
    is_recent.short_description = '🆕 Сегодня'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'post', 'post__author__user')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'category', 'subscribed_at', 'is_active']
    list_filter = ['category', 'subscribed_at']
    search_fields = ['user__username', 'category__name']
    date_hierarchy = 'subscribed_at'
    autocomplete_fields = ['user', 'category']

    def is_active(self, obj):
        return obj.subscribed_at >= timezone.now() - timezone.timedelta(days=30)

    is_active.boolean = True
    is_active.short_description = 'Активна'


@admin.register(ActivationToken)
class ActivationTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token_short', 'created_at', 'activated', 'is_expired', 'status']
    list_filter = ['activated', 'created_at']
    search_fields = ['user__username', 'token']
    readonly_fields = ['created_at', 'token']
    date_hierarchy = 'created_at'

    def token_short(self, obj):
        return f"{obj.token[:16]}..." if obj.token else "-"

    token_short.short_description = 'Токен'

    def is_expired(self, obj):
        return obj.is_expired()

    is_expired.boolean = True
    is_expired.short_description = 'Истек'

    def status(self, obj):
        if obj.activated:
            return format_html('<span style="color: green;">✅ Активирован</span>')
        elif obj.is_expired():
            return format_html('<span style="color: red;">❌ Истек</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Ожидает</span>')

    status.short_description = 'Статус'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


# 🔄 РАСШИРЕННАЯ АДМИНКА ПОЛЬЗОВАТЕЛЕЙ
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ('is_author', 'subscriptions_count', 'last_login_display')
    list_filter = UserAdmin.list_filter + ('groups', 'is_staff')
    inlines = [SubscriptionInline]  # Убрали UserPostsInline отсюда

    def is_author(self, obj):
        return obj.groups.filter(name='authors').exists()

    is_author.boolean = True
    is_author.short_description = '👤 Автор'

    def subscriptions_count(self, obj):
        return obj.subscribed_categories.count()

    subscriptions_count.short_description = '📩 Подписок'

    def last_login_display(self, obj):
        if obj.last_login:
            return obj.last_login.strftime('%d.%m.%Y %H:%M')
        return 'Никогда'

    last_login_display.short_description = 'Последний вход'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'groups', 'subscribed_categories'
        ).annotate(
            subscriptions_count=Count('subscribed_categories')
        )


# 🔄 КАСТОМНАЯ ГРУППА
class CustomGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'users_count']
    filter_horizontal = ['permissions']

    def users_count(self, obj):
        return obj.user_set.count()

    users_count.short_description = '👥 Пользователей'


# 🔄 РЕГИСТРАЦИЯ И ПЕРЕРЕГИСТРАЦИЯ
admin.site.unregister(User)
admin.site.unregister(Group)

admin.site.register(User, CustomUserAdmin)
admin.site.register(Group, CustomGroupAdmin)