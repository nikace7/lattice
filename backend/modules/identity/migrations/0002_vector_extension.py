from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    dependencies = [("identity", "0001_initial")]
    operations = [VectorExtension()]
