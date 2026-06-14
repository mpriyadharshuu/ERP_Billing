import csv
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import barcode
import pandas as pd
from barcode.writer import ImageWriter
from django.db import transaction
from django.db.models import Count, F, Sum
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Bill, BillItem, Customer, Product, SalesRecord, ShopSettings, StockAlert


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def sync_stock_alert(product):
    if product.quantity == 0:
        status = StockAlert.STATUS_OUT
        message = f'{product.name} is out of stock.'
    elif product.quantity <= product.stock_level:
        status = StockAlert.STATUS_LOW
        message = f'{product.name} is below reorder level ({product.quantity} left).'
    else:
        StockAlert.objects.filter(product=product, resolved=False).update(resolved=True)
        return None
    alert, _ = StockAlert.objects.update_or_create(
        product=product,
        resolved=False,
        defaults={'status': status, 'message': message},
    )
    return alert


@transaction.atomic
def create_bill(payload):
    items = payload.get('items', [])
    if not items:
        raise ValueError('Add at least one product to generate a bill.')

    customer_name = (payload.get('customer_name') or 'Walk-in Customer').strip()
    customer_phone = (payload.get('customer_phone') or '0000000000').strip()
    discount = money(payload.get('discount', 0))
    tax_percent = money(payload.get('tax_percent', 0))
    gst_percent = money(payload.get('gst_percent', 0))

    customer, _ = Customer.objects.get_or_create(
        phone=customer_phone,
        defaults={'name': customer_name},
    )
    if customer.name != customer_name and customer_name != 'Walk-in Customer':
        customer.name = customer_name
        customer.save(update_fields=['name', 'updated_at'])

    bill = Bill.objects.create(
        customer=customer,
        customer_name=customer_name,
        customer_phone=customer_phone,
        discount=discount,
        payment_method=payload.get('payment_method') or Bill.PAYMENT_CASH,
        notes=payload.get('notes', ''),
    )

    subtotal = Decimal('0')
    total_cost = Decimal('0')
    total_qty = 0
    for line in items:
        product = Product.objects.select_for_update().get(pk=line['product_id'])
        qty = int(line.get('quantity') or 1)
        if qty < 1:
            raise ValueError(f'Invalid quantity for {product.name}.')
        if product.quantity < qty:
            raise ValueError(f'Only {product.quantity} units available for {product.name}.')

        line_total = product.selling_price * qty
        BillItem.objects.create(
            bill=bill,
            product=product,
            product_name=product.name,
            barcode=product.barcode,
            quantity=qty,
            unit_price=product.selling_price,
            total_price=line_total,
        )
        product.quantity = F('quantity') - qty
        product.save(update_fields=['quantity', 'updated_at'])
        product.refresh_from_db()
        sync_stock_alert(product)
        subtotal += line_total
        total_cost += product.cost_price * qty
        total_qty += qty

    taxable = max(subtotal - discount, Decimal('0'))
    tax = (taxable * tax_percent / Decimal('100')).quantize(Decimal('0.01'))
    gst = (taxable * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
    bill.subtotal = subtotal
    bill.tax = tax
    bill.gst = gst
    bill.grand_total = taxable + tax + gst
    bill.save(update_fields=['subtotal', 'tax', 'gst', 'grand_total', 'updated_at'])

    customer.total_purchases = Customer.objects.filter(pk=customer.pk).first().total_purchases + bill.grand_total
    customer.last_purchase_date = timezone.now()
    customer.save(update_fields=['total_purchases', 'last_purchase_date', 'updated_at'])

    SalesRecord.objects.create(
        bill=bill,
        sale_date=timezone.localdate(),
        revenue=bill.grand_total,
        profit=max(bill.grand_total - total_cost, Decimal('0')),
        items_sold=total_qty,
    )
    return bill


def product_barcode_response(product):
    buffer = BytesIO()
    code = barcode.get('code128', product.barcode, writer=ImageWriter())
    code.write(buffer, {'module_height': 8, 'font_size': 8, 'quiet_zone': 2})
    buffer.seek(0)
    return HttpResponse(buffer.getvalue(), content_type='image/png')


def build_invoice_pdf(bill):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    settings = ShopSettings.current()
    story = [
        Paragraph(settings.shop_name, styles['Title']),
        Paragraph(settings.shop_address, styles['Normal']),
        Paragraph(f'GST: {settings.gst_number or "N/A"} | Contact: {settings.contact_number or "N/A"}', styles['Normal']),
        Spacer(1, 14),
        Paragraph(f'Invoice: {bill.invoice_number}', styles['Heading2']),
        Paragraph(f'Customer: {bill.customer_name} | Phone: {bill.customer_phone}', styles['Normal']),
        Paragraph(f'Date: {timezone.localtime(bill.created_at).strftime("%d %b %Y, %I:%M %p")}', styles['Normal']),
        Spacer(1, 12),
    ]
    rows = [['Product', 'Barcode', 'Qty', 'Unit Price', 'Total']]
    for item in bill.items.all():
        rows.append([item.product_name, item.barcode, item.quantity, f'Rs. {item.unit_price}', f'Rs. {item.total_price}'])
    rows.extend([
        ['', '', '', 'Subtotal', f'Rs. {bill.subtotal}'],
        ['', '', '', 'Discount', f'Rs. {bill.discount}'],
        ['', '', '', 'Tax', f'Rs. {bill.tax}'],
        ['', '', '', 'GST', f'Rs. {bill.gst}'],
        ['', '', '', 'Grand Total', f'Rs. {bill.grand_total}'],
    ])
    table = Table(rows, colWidths=[150, 95, 45, 85, 85])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#d7dee8')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eaf2ff')),
        ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.extend([table, Spacer(1, 18), Paragraph(settings.invoice_footer, styles['Italic'])])
    doc.build(story)
    buffer.seek(0)
    return buffer


def invoice_pdf_response(bill):
    buffer = build_invoice_pdf(bill)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{bill.invoice_number}.pdf"'
    return response


def sales_queryset(start=None, end=None):
    qs = Bill.objects.prefetch_related('items').select_related('customer')
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs


def export_sales(bills, export_format):
    rows = list(bills.values('invoice_number', 'customer_name', 'customer_phone', 'subtotal', 'discount', 'tax', 'gst', 'grand_total', 'payment_method', 'created_at'))
    for row in rows:
        row['created_at'] = timezone.localtime(row['created_at']).strftime('%Y-%m-%d %H:%M')
    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="sales-report.csv"'
        writer = csv.DictWriter(response, fieldnames=rows[0].keys() if rows else ['invoice_number'])
        writer.writeheader()
        writer.writerows(rows)
        return response
    if export_format == 'xlsx':
        buffer = BytesIO()
        pd.DataFrame(rows).to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="sales-report.xlsx"'
        return response

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    table_rows = [['Invoice', 'Customer', 'Phone', 'Total', 'Date']]
    for bill in bills:
        table_rows.append([bill.invoice_number, bill.customer_name, bill.customer_phone, f'Rs. {bill.grand_total}', bill.created_at.strftime('%d %b %Y')])
    table = Table(table_rows)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#d7dee8')),
    ]))
    doc.build([Paragraph('Sales Report', styles['Title']), Spacer(1, 12), table])
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="sales-report.pdf"'
    return response


def dashboard_metrics():
    today = timezone.localdate()
    week_start = today - timedelta(days=6)
    today_bills = Bill.objects.filter(created_at__date=today)
    return {
        'total_sales_today': today_bills.count(),
        'total_revenue': Bill.objects.aggregate(total=Sum('grand_total'))['total'] or Decimal('0'),
        'total_products': Product.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_bills': Bill.objects.count(),
        'low_stock_products': Product.objects.filter(quantity__lte=F('stock_level')).count(),
        'latest_bills': Bill.objects.all()[:6],
        'recent_customers': Customer.objects.all().order_by('-created_at')[:6],
        'latest_products': Product.objects.all().order_by('-updated_at')[:6],
        'daily_sales': chart_by_day(week_start, today),
    }


def chart_by_day(start, end):
    labels = []
    revenue = []
    current = start
    while current <= end:
        labels.append(current.strftime('%d %b'))
        revenue.append(float(Bill.objects.filter(created_at__date=current).aggregate(total=Sum('grand_total'))['total'] or 0))
        current += timedelta(days=1)
    return {'labels': labels, 'revenue': revenue}


def analytics_payload():
    sales = list(SalesRecord.objects.values('sale_date', 'revenue', 'profit', 'items_sold'))
    sales_df = pd.DataFrame(sales)
    product_rows = list(BillItem.objects.values('product_name').annotate(quantity=Sum('quantity'), revenue=Sum('total_price')).order_by('-quantity')[:10])
    products_df = pd.DataFrame(product_rows)
    monthly = {'labels': [], 'revenue': [], 'profit': []}
    if not sales_df.empty:
        sales_df['month'] = pd.to_datetime(sales_df['sale_date']).dt.strftime('%b %Y')
        grouped = sales_df.groupby('month')[['revenue', 'profit']].sum().reset_index()
        monthly = {
            'labels': grouped['month'].tolist(),
            'revenue': [float(v) for v in grouped['revenue']],
            'profit': [float(v) for v in grouped['profit']],
        }
    return {
        'monthly': monthly,
        'top_products': {
            'labels': products_df['product_name'].tolist() if not products_df.empty else [],
            'quantity': [int(v) for v in products_df['quantity']] if not products_df.empty else [],
            'revenue': [float(v) for v in products_df['revenue']] if not products_df.empty else [],
        },
        'low_selling_products': Product.objects.annotate(sold=Sum('bill_items__quantity')).order_by('sold')[:8],
        'category_distribution': list(Product.objects.values('category__name').annotate(count=Count('id')).order_by('-count')),
    }
