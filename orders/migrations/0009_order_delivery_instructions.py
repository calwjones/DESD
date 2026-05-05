# Adds Order.delivery_instructions for TC-017 and aligns Order.status choices
# with the model (partially_delivered was added in PR #16 without a migration).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0008_paymentsplit_settlement_fk'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('confirmed', 'Confirmed'),
                    ('payment_failed', 'Payment Failed'),
                    ('processing', 'Processing'),
                    ('dispatched', 'Dispatched'),
                    ('partially_delivered', 'Partially Delivered'),
                    ('delivered', 'Delivered'),
                    ('cancelled', 'Cancelled'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_instructions',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'Optional notes for the producer / delivery driver '
                    '(access codes, leave-with-neighbour, allergies for the '
                    'kitchen, etc).'
                ),
            ),
        ),
    ]
