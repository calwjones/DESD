import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0006_payment_commission_and_paymentsplit'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Settlement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('gross_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('commission_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('net_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('pending', 'Pending Bank Transfer'), ('processed', 'Processed')], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('producer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='settlements', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-period_end'],
                'unique_together': {('producer', 'period_start')},
            },
        ),
    ]
