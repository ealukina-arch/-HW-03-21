from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.conf import settings

from .models import Post, Author, Category, Subscription, ActivationToken
from .filters import PostFilter
from .forms import PostForm
from .mixins import AuthRequiredMixin, NewsLimitMixin, AuthorRequiredMixin, OwnerRequiredMixin, PermissionRequiredMixinWithMessage
from .services.email_service import EmailService
import logging

logger = logging.getLogger('news.views')


class PermissionRequiredMixinWithMessage(PermissionRequiredMixin):
    permission_denied_message = "У вас недостаточно прав для доступа к этой странице."

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


class AuthorRequiredMixin(UserPassesTestMixin):
    permission_denied_message = "Только авторы могут создавать и редактировать контент."

    def test_func(self):
        return (self.request.user.is_authenticated and
                self.request.user.groups.filter(name='authors').exists())

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


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


# 🔄 ФУНКЦИИ ДЛЯ РАБОТЫ С ПОДПИСКАМИ
@login_required
def subscribe_to_category(request, category_id):
    """Подписка на категорию"""
    logger.info(f"🔔 ЗАПРОС НА ПОДПИСКУ: пользователь={request.user.username}, категория_id={category_id}")

    category = get_object_or_404(Category, id=category_id)
    logger.info(f"📦 Найдена категория: {category.name}")

    subscription, created = Subscription.objects.get_or_create(
        user=request.user,
        category=category
    )

    if created:
        logger.info(f"✅ СОЗДАНА НОВАЯ ПОДПИСКА: {request.user.username} -> {category.name}")
        messages.success(
            request,
            f'✅ Вы успешно подписались на категорию "{category.name}"! '
            f'Теперь вы будете получать уведомления о новых статьях и еженедельные дайджесты.'
        )
    else:
        logger.info(f"ℹ️ ПОДПИСКА УЖЕ СУЩЕСТВУЕТ: {request.user.username} -> {category.name}")
        messages.info(request, f'ℹ️ Вы уже подписаны на категорию "{category.name}"')

    return redirect('category_posts', category_id=category_id)


def category_posts(request, category_id):
    """Страница с постами категории"""
    logger.info(f"🔔 ЗАПРОС КАТЕГОРИЯ: категория_id={category_id}")

    category = get_object_or_404(Category, id=category_id)
    posts = Post.objects.filter(categories=category).order_by('-created_at')

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    is_subscribed = False
    if request.user.is_authenticated:
        is_subscribed = Subscription.objects.filter(
            user=request.user,
            category=category
        ).exists()

    context = {
        'category': category,
        'page_obj': page_obj,
        'is_subscribed': is_subscribed,
        'categories': Category.objects.all(),
        'subscribers_count': category.subscribers.count()
    }
    return render(request, 'news/category_posts.html', context)


@login_required
def unsubscribe_from_category(request, category_id):
    """Отписка от категории"""
    logger.info(f"🔔 ЗАПРОС НА ОТПИСКУ: пользователь={request.user.username}, категория_id={category_id}")

    category = get_object_or_404(Category, id=category_id)
    logger.info(f"📦 Найдена категория: {category.name}")

    # Проверяем существующие подписки перед удалением
    subscription_exists = Subscription.objects.filter(
        user=request.user,
        category=category
    ).exists()
    logger.info(f"📊 Подписка найдена для удаления: {subscription_exists}")

    deleted_count = Subscription.objects.filter(
        user=request.user,
        category=category
    ).delete()[0]

    if deleted_count > 0:
        logger.info(f"❌ ПОДПИСКА УДАЛЕНА: {request.user.username} -> {category.name}")
        messages.success(request, f'❌ Вы отписались от категории "{category.name}"')
    else:
        logger.info(f"⚠️ ПОДПИСКА НЕ НАЙДЕНА: {request.user.username} -> {category.name}")
        messages.warning(request, f'⚠️ Вы не были подписаны на категорию "{category.name}"')

    # Проверяем общее количество подписок пользователя после удаления
    user_subscriptions_count = Subscription.objects.filter(user=request.user).count()
    logger.info(f"📈 Всего подписок у пользователя после отписки: {user_subscriptions_count}")

    return redirect('category_posts', category_id=category_id)


@login_required
def my_subscriptions(request):
    """Страница с подписками пользователя"""
    logger.info(f"🔔 ЗАПРОС МОИ ПОДПИСКИ: пользователь={request.user.username}")

    subscriptions = Subscription.objects.filter(user=request.user).select_related('category')
    all_categories = Category.objects.annotate(
        subscribers_count=Count('subscribers'),
        posts_count=Count('post')
    )

    logger.info(f"📋 Найдено подписок: {subscriptions.count()}")

    context = {
        'subscriptions': subscriptions,
        'categories': all_categories,
        'total_subscriptions': subscriptions.count()
    }
    return render(request, 'news/my_subscriptions.html', context)


def category_posts(request, category_id):
    """Страница с постами категории"""
    logger.info(
        f"🔔 ЗАПРОС КАТЕГОРИЯ: категория_id={category_id}, пользователь={request.user.username if request.user.is_authenticated else 'неавторизован'}")

    category = get_object_or_404(Category, id=category_id)
    logger.info(f"📦 Категория: {category.name}")

    posts = Post.objects.filter(categories=category).select_related('author__user').prefetch_related(
        'categories').order_by('-created_at')
    logger.info(f"📄 Постов в категории: {posts.count()}")

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    is_subscribed = False
    if request.user.is_authenticated:
        is_subscribed = Subscription.objects.filter(
            user=request.user,
            category=category
        ).exists()
        logger.info(f"👤 Статус подписки пользователя: {is_subscribed}")
    else:
        logger.info("👤 Пользователь не аутентифицирован")

    context = {
        'category': category,
        'page_obj': page_obj,
        'is_subscribed': is_subscribed,
        'categories': Category.objects.all(),
        'subscribers_count': category.subscribers.count()
    }
    return render(request, 'news/category_posts.html', context)


# 🔄 ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ АВТОРАМИ
@login_required
def become_author(request):
    """Добавляет пользователя в группу authors"""
    logger.info(f"🔔 ЗАПРОС СТАТЬ АВТОРОМ: пользователь={request.user.username}")

    authors_group, created = Group.objects.get_or_create(name='authors')
    logger.info(f"📋 Группа authors: {'создана' if created else 'уже существует'}")

    # Назначаем права для группы authors
    content_type = ContentType.objects.get_for_model(Post)
    post_permissions = Permission.objects.filter(content_type=content_type)
    authors_group.permissions.set(post_permissions)
    logger.info(f"🔐 Назначено прав для модели Post: {post_permissions.count()}")

    if not request.user.groups.filter(name='authors').exists():
        request.user.groups.add(authors_group)

        # Создаем профиль автора если его нет
        Author.objects.get_or_create(user=request.user)

        logger.info(f"🎉 ПОЛЬЗОВАТЕЛЬ ДОБАВЛЕН В АВТОРЫ: {request.user.username}")
        messages.success(request, '🎉 Поздравляем! Теперь вы автор и можете создавать новости и статьи.')
    else:
        logger.info(f"ℹ️ ПОЛЬЗОВАТЕЛЬ УЖЕ АВТОР: {request.user.username}")
        messages.info(request, 'ℹ️ Вы уже являетесь автором.')

    return redirect('news_list')


@login_required
def author_dashboard(request):
    """Дашборд автора"""
    if not request.user.groups.filter(name='authors').exists():
        messages.error(request, 'Доступно только для авторов')
        return redirect('news_list')

    author = get_object_or_404(Author, user=request.user)

    # Статистика автора
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))

    posts_today = Post.objects.filter(
        author=author,
        created_at__gte=today_start
    ).count()

    total_posts = Post.objects.filter(author=author).count()
    recent_posts = Post.objects.filter(author=author).order_by('-created_at')[:5]

    context = {
        'author': author,
        'posts_today': posts_today,
        'total_posts': total_posts,
        'recent_posts': recent_posts,
        'news_limit_remaining': max(0, 3 - posts_today)
    }

    return render(request, 'news/author_dashboard.html', context)


# 🔄 ОСНОВНЫЕ КЛАССЫ-ПРЕДСТАВЛЕНИЯ
class NewsList(ListView):
    model = Post
    template_name = 'news/news_list.html'
    context_object_name = 'news_list'
    paginate_by = 10

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.NEWS).select_related(
            'author__user'
        ).prefetch_related('categories').order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.annotate(
            posts_count=Count('post')
        )
        context['total_news'] = Post.objects.filter(post_type=Post.NEWS).count()

        logger.info(
            f"📰 Страница новостей: {context['news_list'].count()} новостей, {context['categories'].count()} категорий")
        return context


class NewsDetail(DetailView):
    model = Post
    template_name = 'news/news_detail.html'
    context_object_name = 'news'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.NEWS).select_related(
            'author__user'
        ).prefetch_related('categories')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()

        # Добавляем информацию о подписках пользователя
        if self.request.user.is_authenticated:
            post_categories = self.object.categories.all()
            user_subscriptions = Subscription.objects.filter(
                user=self.request.user,
                category__in=post_categories
            ).values_list('category_id', flat=True)
            context['user_subscribed_categories'] = list(user_subscriptions)
            logger.info(f"📖 Детали новости: '{self.object.title}', подписан на категории: {len(user_subscriptions)}")

        # Похожие новости
        similar_posts = Post.objects.filter(
            categories__in=self.object.categories.all(),
            post_type=Post.NEWS
        ).exclude(pk=self.object.pk).distinct()[:5]
        context['similar_posts'] = similar_posts

        return context


class NewsSearch(ListView):
    model = Post
    template_name = 'news/news_search.html'
    context_object_name = 'news_list'
    paginate_by = 10

    def get_queryset(self):
        queryset = Post.objects.filter(post_type=Post.NEWS).select_related(
            'author__user'
        ).prefetch_related('categories').order_by('-created_at')
        self.filterset = PostFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['categories'] = Category.objects.all()
        context['search_query'] = self.request.GET.get('title', '')

        logger.info(f"🔍 Поиск новостей: найдено {context['news_list'].count()} результатов")
        return context


# 🔄 CRUD ПРЕДСТАВЛЕНИЯ ДЛЯ НОВОСТЕЙ
class NewsCreate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, NewsLimitMixin,
                 CreateView):
    form_class = PostForm
    model = Post
    template_name = 'news/news_edit.html'
    permission_required = 'news.add_post'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        post = form.save(commit=False)
        post.post_type = Post.NEWS
        author, created = Author.objects.get_or_create(user=self.request.user)
        post.author = author

        response = super().form_valid(form)

        # Сохраняем категории ManyToMany
        form.save_m2m()

        # Отправляем уведомления после успешного сохранения
        logger.info(f"📝 Новость создана, отправляем уведомления для ID: {self.object.pk}")
        self.object.send_notifications_to_subscribers()

        return response

    def get_success_url(self):
        messages.success(self.request, '✅ Новость успешно создана! Подписчики получат уведомления.')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Создание новости'
        context['categories'] = Category.objects.all()

        # Добавляем информацию о лимите
        if hasattr(self.request.user, 'author'):
            news_count = self.request.user.author.get_news_count_today()
            context.update({
                'news_count_today': news_count,
                'news_remaining': max(0, 3 - news_count)
            })

        return context


class NewsUpdate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                 UpdateView):
    form_class = PostForm
    model = Post
    template_name = 'news/news_edit.html'
    permission_required = 'news.change_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.NEWS)

    def get_success_url(self):
        messages.success(self.request, '✅ Новость успешно обновлена!')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактирование новости'
        context['categories'] = Category.objects.all()
        return context


class NewsDelete(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                 DeleteView):
    model = Post
    template_name = 'news/news_delete.html'
    success_url = reverse_lazy('news_list')
    permission_required = 'news.delete_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.NEWS)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        return context

    def delete(self, request, *args, **kwargs):
        messages.success(request, '✅ Новость успешно удалена!')
        return super().delete(request, *args, **kwargs)


# 🔄 CRUD ПРЕДСТАВЛЕНИЯ ДЛЯ СТАТЕЙ
class ArticleCreate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, CreateView):
    form_class = PostForm
    model = Post
    template_name = 'news/article_edit.html'
    permission_required = 'news.add_post'

    def form_valid(self, form):
        post = form.save(commit=False)
        post.post_type = Post.ARTICLE
        author, created = Author.objects.get_or_create(user=self.request.user)
        post.author = author
        response = super().form_valid(form)

        # Сохраняем категории ManyToMany
        form.save_m2m()

        logger.info(f"📄 Статья создана: {self.object.title}")
        return response

    def get_success_url(self):
        messages.success(self.request, '✅ Статья успешно создана!')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Создание статьи'
        context['categories'] = Category.objects.all()
        return context


class ArticleUpdate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                    UpdateView):
    form_class = PostForm
    model = Post
    template_name = 'news/article_edit.html'
    permission_required = 'news.change_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.ARTICLE)

    def get_success_url(self):
        messages.success(self.request, '✅ Статья успешно обновлена!')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактирование статьи'
        context['categories'] = Category.objects.all()
        return context


class ArticleDelete(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                    DeleteView):
    model = Post
    template_name = 'news/article_delete.html'
    success_url = reverse_lazy('news_list')
    permission_required = 'news.delete_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.ARTICLE)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        return context

    def delete(self, request, *args, **kwargs):
        messages.success(request, '✅ Статья успешно удалена!')
        return super().delete(request, *args, **kwargs)


# 🔄 АКТИВАЦИЯ АККАУНТА
class ActivationView(TemplateView):
    template_name = 'accounts/activation.html'

    def get(self, request, token, *args, **kwargs):
        context = self.get_context_data(**kwargs)

        try:
            activation_token = ActivationToken.objects.select_related('user').get(token=token)

            if activation_token.is_expired():
                context['status'] = 'expired'
                context['message'] = 'Ссылка активации устарела. Пожалуйста, запросите новую.'
            elif activation_token.activated:
                context['status'] = 'already_activated'
                context['message'] = 'Аккаунт уже был активирован ранее.'
            else:
                # Активируем аккаунт
                activation_token.activated = True
                activation_token.save()

                # Активируем пользователя
                user = activation_token.user
                user.is_active = True
                user.save()

                context['status'] = 'success'
                context['message'] = '✅ Аккаунт успешно активирован! Теперь вы можете войти в систему.'
                context['username'] = user.username

                logger.info(f"✅ Аккаунт активирован: {user.username}")

        except ActivationToken.DoesNotExist:
            context['status'] = 'invalid'
            context['message'] = 'Неверная ссылка активации. Пожалуйста, проверьте правильность ссылки.'

        return self.render_to_response(context)


@login_required
def resend_activation_email(request):
    """
    Повторная отправка письма активации
    """
    try:
        activation_token = ActivationToken.objects.get(user=request.user)

        if activation_token.activated:
            messages.info(request, '✅ Ваш аккаунт уже активирован.')
        elif activation_token.is_expired():
            # Создаем новый токен
            activation_token.delete()
            new_token = ActivationToken.create_token(request.user)
            activation_url = f"{settings.SITE_URL}/accounts/activate/{new_token.token}/"
            EmailService.send_welcome_email(request.user, activation_url)
            messages.success(request, '📧 Новое письмо активации отправлено на ваш email.')
        else:
            # Отправляем существующий токен
            activation_url = f"{settings.SITE_URL}/accounts/activate/{activation_token.token}/"
            EmailService.send_welcome_email(request.user, activation_url)
            messages.success(request, '📧 Письмо активации отправлено на ваш email.')

    except ActivationToken.DoesNotExist:
        # Создаем новый токен, если по какой-то причине его нет
        new_token = ActivationToken.create_token(request.user)
        activation_url = f"{settings.SITE_URL}/accounts/activate/{new_token.token}/"
        EmailService.send_welcome_email(request.user, activation_url)
        messages.success(request, '📧 Письмо активации отправлено на ваш email.')

    return redirect('profile')


# 🔄 ДОПОЛНИТЕЛЬНЫЕ ПРЕДСТАВЛЕНИЯ
class HomePageView(ListView):
    """Главная страница с последними новостями"""
    model = Post
    template_name = 'news/home.html'
    context_object_name = 'latest_news'
    paginate_by = 5

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.NEWS).select_related(
            'author__user'
        ).prefetch_related('categories').order_by('-created_at')[:10]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.annotate(
            posts_count=Count('post')
        )[:8]
        context['total_categories'] = Category.objects.count()
        return context


@login_required
def profile(request):
    """Профиль пользователя"""
    context = {
        'is_author': request.user.groups.filter(name='authors').exists(),
        'subscriptions_count': Subscription.objects.filter(user=request.user).count(),
        'categories': Category.objects.all()
    }

    if hasattr(request.user, 'author'):
        author = request.user.author
        context.update({
            'author': author,
            'posts_count': Post.objects.filter(author=author).count(),
            'news_today': author.get_news_count_today()
        })

    return render(request, 'accounts/profile.html', context)