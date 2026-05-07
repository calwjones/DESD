# Adds community_group and restaurant roles for TC-017.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_merge_20260430_2042'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('customer', 'Customer'),
                    ('producer', 'Producer'),
                    ('logistics', 'Logistics'),
                    ('community_group', 'Community Group'),
                    ('restaurant', 'Restaurant'),
                ],
                default='customer',
                max_length=20,
            ),
        ),
    ]
