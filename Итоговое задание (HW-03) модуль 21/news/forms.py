from django import forms
from .models import Post, Category
from django.utils import timezone
from datetime import timedelta


class NewsCreateForm(forms.ModelForm):
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Категории'
    )

    class Meta:
        model = Post
        fields = ['title', 'content', 'categories']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
        }

    def clean(self):
        cleaned_data = super().clean()
        user = getattr(self, 'user', None)

        if user and hasattr(user, 'author'):
            today = timezone.now().date()
            today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))

            news_count_today = Post.objects.filter(
                author=user.author,
                post_type=Post.NEWS,
                created_at__gte=today_start
            ).count()

            if news_count_today >= 3:
                raise forms.ValidationError(
                    f'Вы достигли лимита в 3 новости в сутки. '
                    f'Сегодня вы уже опубликовали {news_count_today} новостей.'
                )

        return cleaned_data

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'content', 'categories', 'author']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'categories': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'author': forms.Select(attrs={'class': 'form-control'}),
        }