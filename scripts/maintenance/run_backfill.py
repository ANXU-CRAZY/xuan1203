"""运行图片补全命令并输出到文件"""
import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()

from django.core.management import call_command
from io import StringIO

out = StringIO()
call_command('backfill_species_wikimedia_images', '--skip-wikidata', '--sleep', '0.05', stdout=out, stderr=out)
result = out.getvalue()
print(result)

with open('backfill_output.txt', 'w', encoding='utf-8') as f:
    f.write(result)
