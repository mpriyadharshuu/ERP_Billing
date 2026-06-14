from decimal import Decimal
from urllib.parse import quote

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    name = models.CharField(max_length=180)
    barcode = models.CharField(max_length=64, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    brand = models.CharField(max_length=120, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    quantity = models.PositiveIntegerField(default=0)
    stock_level = models.PositiveIntegerField(default=10)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.barcode:
            seed = timezone.now().strftime('%y%m%d%H%M%S%f')[-12:]
            self.barcode = seed
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        return self.selling_price - self.cost_price

    @property
    def stock_status(self):
        if self.quantity == 0:
            return 'critical'
        if self.quantity <= self.stock_level:
            return 'low'
        return 'healthy'

    def get_absolute_url(self):
        return reverse('product_list')


class Customer(TimeStampedModel):
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    total_purchases = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_purchase_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.phone})'

    def get_absolute_url(self):
        return reverse('customer_list')


class ShopSettings(TimeStampedModel):
    shop_name = models.CharField(max_length=180, default='Smart Supermarket')
    shop_address = models.TextField(default='Main Market Road')
    gst_number = models.CharField(max_length=32, blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    invoice_footer = models.CharField(max_length=240, default='Thank you for shopping with us.')
    company_logo = models.ImageField(upload_to='settings/', blank=True, null=True)

    class Meta:
        verbose_name = 'settings'
        verbose_name_plural = 'settings'

    def __str__(self):
        return self.shop_name

    @classmethod
    def current(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class Bill(TimeStampedModel):
    PAYMENT_CASH = 'cash'
    PAYMENT_UPI = 'upi'
    PAYMENT_CARD = 'card'
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Cash'),
        (PAYMENT_UPI, 'UPI'),
        (PAYMENT_CARD, 'Card'),
    ]

    invoice_number = models.CharField(max_length=32, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='bills')
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=20)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=12, choices=PAYMENT_CHOICES, default=PAYMENT_CASH)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.invoice_number or f'Bill #{self.pk}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today = timezone.localdate().strftime('%Y%m%d')
            count = Bill.objects.filter(created_at__date=timezone.localdate()).count() + 1
            self.invoice_number = f'SSB-{today}-{count:04d}'
        super().save(*args, **kwargs)

    @property
    def whatsapp_url(self):
        text = quote(f'Invoice {self.invoice_number}: Rs. {self.grand_total}. Thank you for shopping with us.')
        return f'https://wa.me/{self.customer_phone}?text={text}'

    def get_absolute_url(self):
        return reverse('bill_detail', args=[self.pk])


class BillItem(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='bill_items')
    product_name = models.CharField(max_length=180)
    barcode = models.CharField(max_length=64)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product_name} x {self.quantity}'


class SalesRecord(TimeStampedModel):
    bill = models.OneToOneField(Bill, on_delete=models.CASCADE, related_name='sales_record')
    sale_date = models.DateField()
    revenue = models.DecimalField(max_digits=12, decimal_places=2)
    profit = models.DecimalField(max_digits=12, decimal_places=2)
    items_sold = models.PositiveIntegerField()

    class Meta:
        ordering = ['-sale_date']

    def __str__(self):
        return f'{self.sale_date} - {self.revenue}'


class StockAlert(TimeStampedModel):
    STATUS_LOW = 'low'
    STATUS_OUT = 'out'
    STATUS_CHOICES = [
        (STATUS_LOW, 'Low Stock'),
        (STATUS_OUT, 'Out of Stock'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_alerts')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    message = models.CharField(max_length=220)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ['resolved', '-created_at']

    def __str__(self):
        return self.message
