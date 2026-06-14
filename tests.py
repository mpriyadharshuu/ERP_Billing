from django.test import TestCase

from .models import Category, Product, SalesRecord
from .services import create_bill


class BillingWorkflowTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Grocery')
        self.product = Product.objects.create(
            name='Test Rice',
            category=category,
            cost_price=80,
            selling_price=100,
            quantity=5,
            stock_level=2,
        )

    def test_product_auto_generates_barcode(self):
        self.assertTrue(self.product.barcode)

    def test_create_bill_updates_stock_and_sales_record(self):
        bill = create_bill({
            'customer_name': 'Test Customer',
            'customer_phone': '9000000000',
            'discount': '10',
            'gst_percent': '5',
            'items': [{'product_id': self.product.id, 'quantity': 2}],
        })
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 3)
        self.assertEqual(bill.items.count(), 1)
        self.assertEqual(SalesRecord.objects.count(), 1)
        self.assertEqual(str(bill.grand_total), '199.50')
