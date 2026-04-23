from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app_monitor', '0006_alter_product_options_observationrecord_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='speciesinfo',
            name='cover_image',
            field=models.ImageField(blank=True, null=True, upload_to='species/covers/', verbose_name='物种封面图'),
        ),
        migrations.CreateModel(
            name='SpeciesImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image_url', models.URLField(blank=True, max_length=500, null=True, verbose_name='图片URL')),
                ('image', models.ImageField(blank=True, null=True, upload_to='species/gallery/', verbose_name='本地上传图片')),
                ('caption', models.CharField(blank=True, max_length=300, verbose_name='图片说明')),
                ('source', models.CharField(choices=[('wikimedia', '维基百科'), ('birdsourcing', 'Birdsourcing'), ('ibc', 'Internet Bird Collection'), ('xeno_canto', 'Xeno-Canto'), ('npc', '中国鸟类图库'), ('manual', '手动上传'), ('other', '其他来源')], default='manual', max_length=20, verbose_name='图片来源')),
                ('source_url', models.URLField(blank=True, max_length=500, verbose_name='来源链接')),
                ('source_author', models.CharField(blank=True, max_length=100, verbose_name='来源作者')),
                ('views', models.IntegerField(default=0, verbose_name='浏览量')),
                ('is_featured', models.BooleanField(default=False, verbose_name='精选图片')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='添加时间')),
                ('species', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='app_monitor.speciesinfo', verbose_name='关联物种')),
            ],
            options={
                'verbose_name': '物种图片',
                'verbose_name_plural': '物种图片库',
                'ordering': ['-is_featured', '-views', '-created_at'],
            },
        ),
    ]
