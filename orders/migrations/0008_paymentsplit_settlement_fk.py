import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0007_settlement'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentsplit',
            name='settlement',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='splits',
                to='orders.settlement',
            ),
        ),
    ]
