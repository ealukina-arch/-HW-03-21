from django.urls import path
from . import views

urlpatterns = [
    # Основные маршруты новостей
    path('news/', views.NewsList.as_view(), name='news_list'),
    path('news/<int:pk>/', views.NewsDetail.as_view(), name='news_detail'),
    path('news/search/', views.NewsSearch.as_view(), name='news_search'),

    # 🆕 Маршруты для системы подписок
    path('news/category/<int:category_id>/', views.category_posts, name='category_posts'),
    path('news/category/<int:category_id>/subscribe/', views.subscribe_to_category, name='subscribe'),
    path('news/category/<int:category_id>/unsubscribe/', views.unsubscribe_from_category, name='unsubscribe'),
    path('news/my-subscriptions/', views.my_subscriptions, name='my_subscriptions'),

    # CRUD для новостей
    path('news/create/', views.NewsCreate.as_view(), name='news_create'),
    path('news/<int:pk>/edit/', views.NewsUpdate.as_view(), name='news_edit'),
    path('news/<int:pk>/delete/', views.NewsDelete.as_view(), name='news_delete'),

    # CRUD для статей
    path('articles/create/', views.ArticleCreate.as_view(), name='article_create'),
    path('articles/<int:pk>/edit/', views.ArticleUpdate.as_view(), name='article_edit'),
    path('articles/<int:pk>/delete/', views.ArticleDelete.as_view(), name='article_delete'),

    # Авторство
    path('become-author/', views.become_author, name='become_author'),

    # Активация аккаунта
    path('accounts/activate/<str:token>/', views.ActivationView.as_view(), name='activate_account'),
    path('accounts/resend-activation/', views.resend_activation_email, name='resend_activation'),
]