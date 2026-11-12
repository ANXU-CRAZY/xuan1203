from datetime import timedelta
from time import monotonic, sleep

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from app_monitor.models import PasswordResetRequest
from app_monitor.password_reset import close, configured, mark_worker_ready, process_next_request


class Command(BaseCommand):
    help = 'Send queued password reset codes using the configured SMTP server.'

    def handle(self, *args, **options):
        if not configured():
            raise CommandError('Set SMTP_USER, SMTP_PASSWORD, SMTP_FROM and PASSWORD_RESET_HMAC_KEY.')
        heartbeat = cleanup = 0
        self.stdout.write('Password reset mail worker started.')
        try:
            while True:
                close_old_connections()
                now = monotonic()
                if now >= heartbeat:
                    mark_worker_ready()
                    heartbeat = now + 10
                if now >= cleanup:
                    current = timezone.now()
                    close(PasswordResetRequest.objects.filter(state=PasswordResetRequest.State.SENT,
                                                             expires_at__lte=current))
                    PasswordResetRequest.objects.filter(created_at__lt=current - timedelta(days=1)).delete()
                    cleanup = now + 60
                if not process_next_request():
                    sleep(1)
        except KeyboardInterrupt:
            return
