import requests
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

AI_SERVICE_URL = getattr(settings, 'AI_SERVICE_URL', 'http://ai-service:8001')


def grade_product_image(product):
    """
    Sends the product image to the AI grading service.
    Updates the product with the grade if successful.
    Fails silently so the product still saves if the service is down.
    """
    if not product.image:
        return False

    try:
        with product.image.open('rb') as img_file:
            response = requests.post(
                f"{AI_SERVICE_URL}/grade",
                files={'image': (product.image.name, img_file, 'image/jpeg')},
                data={
                    'product_id': product.pk,
                    'user_id': product.producer_id,
                },
                timeout=10,
            )
        if response.status_code == 200:
            result = response.json()
            product.quality_grade = result.get('grade')
            product.quality_color_score = result.get('color_score')
            product.quality_size_score = result.get('size_score')
            product.quality_ripeness_score = result.get('ripeness_score')
            product.quality_assessed_at = timezone.now()
            product.save(update_fields=[
                'quality_grade',
                'quality_color_score',
                'quality_size_score',
                'quality_ripeness_score',
                'quality_assessed_at',
            ])
            logger.info(f"Product {product.pk} graded: {product.quality_grade}")
            return True

        logger.warning(f"AI service returned {response.status_code} for product {product.pk}")
        return False

    except requests.ConnectionError:
        logger.warning(f"AI service unavailable — product {product.pk} saved without grade")
        return False
    except requests.Timeout:
        logger.warning(f"AI service timed out — product {product.pk} saved without grade")
        return False
    except Exception as e:
        logger.error(f"Unexpected grading error for product {product.pk}: {e}")
        return False