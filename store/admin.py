from django.contrib import admin
from django.utils.html import format_html

from .models import (AdminAccessLog, Category, Mineral, MineralImage, Order,
                     OrderItem, Payment, PaymentEvent)

admin.site.site_header = "Кам'яна Грань — панель керування"
admin.site.site_title = "Кам'яна Грань"
admin.site.index_title = "Керування магазином"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


class MineralImageInline(admin.TabularInline):
    model = MineralImage
    extra = 1
    fields = ["image", "alt", "position"]


@admin.register(Mineral)
class MineralAdmin(admin.ModelAdmin):
    list_display = ["thumb", "name", "category", "price", "stock", "is_featured"]
    list_display_links = ["thumb", "name"]
    list_filter = ["category", "origin", "is_featured"]
    list_editable = ["price", "stock", "is_featured"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "description"]
    readonly_fields = ["thumb"]
    inlines = [MineralImageInline]
    fieldsets = (
        (None, {"fields": ("category", "name", "slug", "short_description", "description")}),
        ("Фото", {"fields": ("image", "image_url", "thumb")}),
        ("Ціна й склад", {"fields": ("price", "old_price", "stock", "weight_grams", "origin", "is_featured")}),
        ("Ілюстрація (якщо немає фото)", {"fields": ("shape", "color_primary", "color_secondary"), "classes": ("collapse",)}),
    )

    @admin.display(description="Фото")
    def thumb(self, obj):
        if obj.photo_url:
            return format_html('<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:4px">', obj.photo_url)
        return "—"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    raw_id_fields = ["mineral"]
    extra = 0
    readonly_fields = ["price", "quantity"]
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ["provider", "reference", "provider_ref", "amount", "currency", "status", "needs_review", "note", "paid_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "full_name", "phone", "city", "total_amount", "payment_method", "status", "created_at"]
    list_filter = ["status", "payment_method", "created_at"]
    search_fields = ["full_name", "email", "phone", "public_id"]
    readonly_fields = ["public_id", "total_amount", "currency", "paid_at", "stock_released", "created_at"]
    inlines = [OrderItemInline, PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "order", "provider", "amount", "currency", "status", "needs_review", "created_at"]
    list_filter = ["status", "provider", "needs_review"]
    search_fields = ["reference", "provider_ref"]
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ["received_at", "provider", "event_id", "event_type", "result", "payment"]
    list_filter = ["provider", "result"]
    readonly_fields = [f.name for f in PaymentEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdminAccessLog)
class AdminAccessLogAdmin(admin.ModelAdmin):
    """Журнал візитів адмінів — лише для читання, змінити/видалити неможливо."""
    list_display = ["created_at", "username", "event", "path", "method", "ip_address"]
    list_filter = ["event", "created_at", "username"]
    search_fields = ["username", "ip_address", "path"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AdminAccessLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
