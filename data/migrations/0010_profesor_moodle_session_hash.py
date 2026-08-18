from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0009_remove_entrega_archivos_remove_entrega_archivosurl_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='profesor',
            name='moodle_session_hash',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
