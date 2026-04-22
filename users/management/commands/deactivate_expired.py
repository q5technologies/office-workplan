from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import Subscription

class Command(BaseCommand):
    help = 'Finds subscriptions past their expiry date and deactivates them.'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        
        # Find all subscriptions that are currently marked active, but the date has passed
        expired_subs = Subscription.objects.filter(is_active=True, expiry_date__lt=now)
        
        count = 0
        for sub in expired_subs:
            # Setting it to False and calling .save() triggers your bulletproof 
            # save() method in models.py, locking out the owner and all their staff instantly.
            sub.is_active = False
            sub.save() 
            count += 1
            
            self.stdout.write(self.style.WARNING(f'Deactivated: {sub.name}'))

        self.stdout.write(self.style.SUCCESS(f'Successfully deactivated {count} expired subscriptions.'))