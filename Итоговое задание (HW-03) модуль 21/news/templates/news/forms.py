from django import forms
from .models import Post, Category
from django.utils import timezone
from datetime import datetime


class PostForm(forms.ModelForm):
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Категории',
        required=True
    )

    class Meta:
        model = Post
        fields = ['title', 'content', 'categories']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Введите заголовок новости...',
                'minlength': '5',
                'maxlength': '255'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Напишите содержание новости...',
                'rows': 12,
                'minlength': '50'
            }),
        }
        labels = {
            'title': 'Заголовок',
            'content': 'Содержание',
        }
        help_texts = {
            'title': 'Минимум 5 символов',
            'content': 'Минимум 50 символов',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Кастомизация queryset для категорий если нужно
        self.fields['categories'].queryset = Category.objects.all()
        self.fields['categories'].label_from_instance = lambda \
            obj: f"{obj.name} ({obj.subscribers.count()} подписчиков)"

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if len(title) < 5:
            raise forms.ValidationError("Заголовок должен содержать минимум 5 символов")
        if len(title) > 255:
            raise forms.ValidationError("Заголовок не может превышать 255 символов")
        return title

    def clean_content(self):
        content = self.cleaned_data.get('content', '').strip()
        if len(content) < 50:
            raise forms.ValidationError("Содержание новости должно быть не менее 50 символов")
        return content

    def clean_categories(self):
        categories = self.cleaned_data.get('categories')
        if not categories:
            raise forms.ValidationError("Выберите хотя бы одну категорию")
        return categories

    def clean(self):
        cleaned_data = super().clean()

        # Проверка лимита новостей
        if self.user and hasattr(self.user, 'author'):
            today = timezone.now().date()
            today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))

            news_count_today = Post.objects.filter(
                author=self.user.author,
                post_type=Post.NEWS,
                created_at__gte=today_start
            ).count()

            if news_count_today >= 3:
                raise forms.ValidationError(
                    f"Вы достигли лимита в 3 новости в сутки. "
                    f"Сегодня вы уже опубликовали {news_count_today} новостей."
                )

        return cleaned_data