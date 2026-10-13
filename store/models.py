import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


class Category(models.Model):
    name = models.CharField("Назва", max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField("Опис", blank=True)

    class Meta:
        verbose_name = "Категорія"
        verbose_name_plural = "Категорії"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("store:category", args=[self.slug])


class Mineral(models.Model):
    ORIGIN_CHOICES = [
        ("brazil", "Бразилія"),
        ("madagascar", "Мадагаскар"),
        ("ukraine", "Україна"),
        ("uruguay", "Уругвай"),
        ("russia", "Урал"),
        ("congo", "Конго"),
    ]

    category = models.ForeignKey(Category, related_name="minerals", on_delete=models.CASCADE, verbose_name="Категорія")
    name = models.CharField("Назва", max_length=150)
    slug = models.SlugField(unique=True)
    short_description = models.CharField("Короткий опис", max_length=220, blank=True)
    description = models.TextField("Опис")
    price = models.DecimalField("Ціна, грн", max_digits=9, decimal_places=2)
    old_price = models.DecimalField("Стара ціна, грн", max_digits=9, decimal_places=2, blank=True, null=True)
    weight_grams = models.PositiveIntegerField("Вага, г", default=0)
    origin = models.CharField("Походження", max_length=20, choices=ORIGIN_CHOICES, default="brazil")
    color_primary = models.CharField("Основний колір (hex)", max_length=7, default="#7C5CBF")
    color_secondary = models.CharField("Другий колір (hex)", max_length=7, default="#4A3A73")
    SHAPE_CHOICES = [("point", "Кристал-вістря"), ("cluster", "Друза/кластер"), ("tumbled", "Галтований камінь")]
    shape = models.CharField("Форма ілюстрації", max_length=10, choices=SHAPE_CHOICES, default="point")
    image = models.ImageField("Головне фото", upload_to="minerals/", blank=True)
    image_url = models.URLField("Або посилання на фото", blank=True, help_text="Якщо файл не завантажено — береться це посилання")
    stock = models.PositiveIntegerField("Залишок", default=0)
    is_featured = models.BooleanField("Показати на головній", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Мінерал"
        verbose_name_plural = "Мінерали"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("store:product_detail", args=[self.slug])

    @property
    def photo_url(self):
        if self.image:
            return self.image.url
        return self.image_url or ""

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return round((1 - self.price / self.old_price) * 100)
        return 0


class MineralImage(models.Model):
    """Додаткові фото мінералу (галерея)."""
    mineral = models.ForeignKey(Mineral, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField("Фото", upload_to="minerals/gallery/")
    alt = models.CharField("Підпис", max_length=150, blank=True)
    position = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Фото мінералу"
        verbose_name_plural = "Фото мінералів"

    def __str__(self):
        return f"{self.mineral.name} #{self.pk}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("new", "Нове (оплата при отриманні)"),
        ("awaiting_payment", "Очікує оплати"),
        ("paid", "Оплачено"),
        ("shipped", "Відправлено"),
        ("done", "Виконано"),
        ("cancelled", "Скасовано"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("online", "Оплата карткою онлайн"),
        ("cod", "Оплата при отриманні"),
    ]

    # Непередбачуваний ідентифікатор для публічних посилань (щоб не перебирали №1, №2...)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    full_name = models.CharField("Ім'я та прізвище", max_length=150)
    email = models.EmailField("Email")
    phone = models.CharField("Телефон", max_length=30)
    city = models.CharField("Місто", max_length=100)
    address = models.CharField("Відділення / адреса доставки", max_length=255)
    comment = models.TextField("Коментар", blank=True)
    payment_method = models.CharField("Спосіб оплати", max_length=10, choices=PAYMENT_METHOD_CHOICES, default="online")
    total_amount = models.DecimalField("Сума (фіксується при створенні)", max_digits=11, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="UAH")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    stock_released = models.BooleanField("Залишки повернено на склад", default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Замовлення"
        verbose_name_plural = "Замовлення"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Замовлення №{self.id} — {self.full_name}"

    def get_absolute_url(self):
        return reverse("store:order_detail", args=[self.public_id])

    def get_total_cost(self):
        return sum(item.get_cost() for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    mineral = models.ForeignKey(Mineral, related_name="order_items", on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=9, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.mineral.name} x{self.quantity}"

    def get_cost(self):
        return self.price * self.quantity


class Payment(models.Model):
    """Одна спроба оплати замовлення. Замовлення може мати кілька спроб."""
    PROVIDER_CHOICES = [("stripe", "Stripe"), ("liqpay", "LiqPay"), ("mock", "Mock (розробка)")]
    STATUS_CHOICES = [
        ("created", "Створено"),
        ("pending", "Очікує оплати"),
        ("succeeded", "Оплачено"),
        ("failed", "Невдало"),
        ("expired", "Прострочено"),
        ("refunded", "Повернено"),
    ]

    order = models.ForeignKey(Order, related_name="payments", on_delete=models.PROTECT)
    provider = models.CharField(max_length=10, choices=PROVIDER_CHOICES)
    # Наш унікальний номер платежу — його бачить провайдер (client_reference_id / order_id)
    reference = models.CharField(max_length=64, unique=True)
    # Ідентифікатор у провайдера (Stripe session id / LiqPay payment_id)
    provider_ref = models.CharField(max_length=128, blank=True, db_index=True)
    # Ключ ідемпотентності: повторний запит до провайдера не створить другий платіж
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    amount = models.DecimalField(max_digits=11, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="created", db_index=True)
    needs_review = models.BooleanField("Потрібна ручна перевірка", default=False, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Платіж"
        verbose_name_plural = "Платежі"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} {self.reference} [{self.status}]"


class PaymentEvent(models.Model):
    """Журнал усіх подій від провайдера. Унікальність (provider, event_id) гарантує,
    що повторна доставка вебхука не буде оброблена вдруге."""
    provider = models.CharField(max_length=10)
    event_id = models.CharField(max_length=160)
    event_type = models.CharField(max_length=80, blank=True)
    payment = models.ForeignKey(Payment, null=True, blank=True, related_name="events", on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict, blank=True)
    result = models.CharField(max_length=60, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Подія платежу"
        verbose_name_plural = "Події платежів"
        ordering = ["-received_at"]
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_provider_event")]

    def __str__(self):
        return f"{self.provider}:{self.event_id}"


class AdminAccessLog(models.Model):
    """Візити та входи адміністраторів у /admin/."""
    EVENT_CHOICES = [
        ("login", "Вхід"),
        ("logout", "Вихід"),
        ("login_failed", "Невдала спроба входу"),
        ("page_view", "Перегляд сторінки"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_logs")
    username = models.CharField(max_length=150, blank=True)
    event = models.CharField(max_length=15, choices=EVENT_CHOICES, db_index=True)
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=8, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Візит адміна"
        verbose_name_plural = "Візити адмінів"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.username or self.user_id} {self.event}"
