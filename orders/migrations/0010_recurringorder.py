# TC-018: RecurringOrder + RecurringOrderItem.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0009_order_delivery_instructions'),
        ('products', '0008_alter_review_body_alter_review_title'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RecurringOrder',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, default='', max_length=200)),
                ('recurrence_day', models.IntegerField(
                    choices=[
                        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
                        (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
                    ],
                    help_text='Day of the week the order is auto-generated.',
                )),
                ('delivery_day', models.IntegerField(
                    choices=[
                        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
                        (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
                    ],
                    help_text='Day of the week to deliver. At least 2 days after recurrence_day.',
                )),
                ('delivery_address', models.TextField()),
                ('delivery_instructions', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_generated_at', models.DateTimeField(blank=True, null=True)),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recurring_orders',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RecurringOrderItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField()),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='products.product',
                )),
                ('recurring_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='orders.recurringorder',
                )),
            ],
            options={
                'unique_together': {('recurring_order', 'product')},
            },
        ),
    ]
