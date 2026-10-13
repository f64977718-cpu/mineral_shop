import uuid
from decimal import Decimal
from django.db import migrations


def fill(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    for o in Order.objects.all():
        o.public_id = uuid.uuid4()
        o.total_amount = sum((i.price * i.quantity for i in o.items.all()), Decimal("0"))
        o.save(update_fields=["public_id", "total_amount"])


class Migration(migrations.Migration):
    dependencies = [("store", "0002_payments_photos_adminlog")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
