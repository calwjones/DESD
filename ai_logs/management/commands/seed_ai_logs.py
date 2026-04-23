import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from ai_logs.models import AIInteraction

User = get_user_model()

PRODUCTS = [
    'Tomatoes', 'Apples', 'Oranges', 'Carrots', 'Strawberries',
    'Potatoes', 'Lettuce', 'Bananas', 'Peppers', 'Courgettes',
]

PRODUCERS = ['Green Fields Farm', 'Orchard Valley', 'Root & Co', 'Citrus Grove', 'Berry Patch']


class Command(BaseCommand):
    help = 'Seed AI interaction logs for dashboard demo'

    def handle(self, *args, **options):
        # Temporarily disable auto_now_add so we can set custom timestamps
        timestamp_field = AIInteraction._meta.get_field('timestamp')
        timestamp_field.auto_now_add = False

        user = User.objects.first()
        now = timezone.now()

        entries = []
        for day in range(7, -1, -1):
            for _ in range(random.randint(3, 6)):
                confidence = random.uniform(0.72, 0.99)
                color = random.randint(55, 95)
                size = random.randint(60, 95)
                ripeness = random.randint(50, 95)
                avg = (color + size + ripeness) / 3
                grade = 'A' if avg >= 80 else 'B' if avg >= 60 else 'C'
                product = random.choice(PRODUCTS)
                producer = random.choice(PRODUCERS)

                entries.append(AIInteraction(
                    service_type='quality',
                    user=user,
                    timestamp=now - timedelta(days=day, hours=random.randint(8, 17), minutes=random.randint(0, 59)),
                    input_data={
                        'product_id': random.randint(1, 20),
                        'filename': f'products/{product.lower()}.jpg',
                        'producer': producer,
                    },
                    prediction={
                        'prediction': 'Fresh' if confidence > 0.5 else 'Rotten',
                        'confidence': round(confidence, 4),
                        'grade': grade,
                        'color_score': color,
                        'size_score': size,
                        'ripeness_score': ripeness,
                    },
                    model_version='v1_phase2',
                    confidence_score=round(confidence, 4),
                ))

        AIInteraction.objects.bulk_create(entries)

        # Re-enable auto_now_add
        timestamp_field.auto_now_add = True

        self.stdout.write(self.style.SUCCESS(f'Created {len(entries)} AI interaction logs'))
