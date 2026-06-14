from django.contrib import admin

from .models import Bill, BillItem, Category, Customer, Product, SalesRecord, ShopSettings, StockAlert


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    readonly_fields = ('product_name', 'barcode', 'quantity', 'unit_price', 'total_price')


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer_name', 'customer_phone', 'grand_total', 'payment_method', 'created_at')
    list_filter = ('payment_method', 'created_at')
    search_fields = ('invoice_number', 'customer_name', 'customer_phone')
    inlines = [BillItemInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'barcode', 'category', 'brand', 'selling_price', 'quantity', 'stock_level', 'stock_status')
    list_filter = ('category', 'brand')
    search_fields = ('name', 'barcode', 'brand')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'total_purchases', 'last_purchase_date')
    search_fields = ('name', 'phone', 'email')


admin.site.register(Category)
admin.site.register(SalesRecord)
admin.site.register(StockAlert)
admin.site.register(ShopSettings)
