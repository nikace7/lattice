from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_recovery(self, email):
    from .actions import EmailUnavailable, issue_link
    from .models import ActionToken

    try:
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(email__iexact=email, is_active=True)
                .first()
            )
            if user is None or not user.has_usable_password():
                return
            # Per-account cooldown also bounds mail from requests spread over multiple IPs.
            if ActionToken.objects.filter(
                user=user, purpose="RESET", created_at__gt=timezone.now() - timedelta(minutes=1)
            ).exists():
                return
            issue_link(
                purpose="RESET", email=user.email.lower(), user=user, lifetime=timedelta(minutes=30)
            )
    except EmailUnavailable:
        raise self.retry(exc=RuntimeError("Recovery email delivery failed.")) from None
