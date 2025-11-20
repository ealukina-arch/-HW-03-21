from django.core.management.base import BaseCommand
from news.services.email_service import EmailService
import logging

logger = logging.getLogger('news.management')


class Command(BaseCommand):
    help = 'Отправляет еженедельные дайджесты подписчикам'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет отправлено без фактической отправки',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write("📊 Запуск отправки еженедельных дайджестов...")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("🔶 РЕЖИМ ПРОСМОТРА: письма не будут отправлены")
            )
            # Здесь можно добавить логику предпросмотра
            return

        try:
            result = EmailService.send_weekly_digest()

            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Еженедельные дайджесты отправлены! "
                    f"Успешно: {result['sent']}, Ошибок: {result['errors']}"
                )
            )

            logger.info(f"Еженедельные дайджесты отправлены: {result}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Ошибка при отправке дайджестов: {e}")
            )
            logger.error(f"Ошибка отправки еженедельных дайджестов: {e}")