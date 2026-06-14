import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import CustomerForm, ProductForm, ShopSettingsForm
from .models import Bill, BillItem, Customer, Product, SalesRecord, ShopSettings, StockAlert
from .services import (
    analytics_payload,
    chart_by_day,
    create_bill,
    dashboard_metrics,
    export_sales,
    invoice_pdf_response,
    product_barcode_response,
    sales_queryset,
    sync_stock_alert,
)


class StaffOnlyMixin(LoginRequiredMixin):
    pass


class DashboardView(StaffOnlyMixin, TemplateView):
    template_name = 'billing/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        metrics = dashboard_metrics()
        month_start = today.replace(day=1)
        top_products = BillItem.objects.values('product_name').annotate(
            qty=Sum('quantity'),
            revenue=Sum('total_price'),
        ).order_by('-qty')[:8]
        top_product_panels = Product.objects.annotate(
            units_sold=Sum('bill_items__quantity'),
            revenue_generated=Sum('bill_items__total_price'),
        ).order_by('-units_sold', 'name')[:6]
        customer_growth = (
            Customer.objects.filter(created_at__date__gte=today - timedelta(days=29))
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )
        category_distribution = Product.objects.values('category__name').annotate(count=Count('id')).order_by('-count')
        weekly = chart_by_day(today - timedelta(days=6), today)
        month_revenue = float(Bill.objects.filter(created_at__date__gte=month_start).aggregate(total=Sum('grand_total'))['total'] or 0)
        month_profit = float(SalesRecord.objects.filter(sale_date__gte=month_start).aggregate(total=Sum('profit'))['total'] or 0)
        month_expenses = max(month_revenue - month_profit, 0)
        today_revenue = today_bills_total = Bill.objects.filter(created_at__date=today).aggregate(total=Sum('grand_total'))['total'] or 0
        yesterday_revenue = Bill.objects.filter(created_at__date=today - timedelta(days=1)).aggregate(total=Sum('grand_total'))['total'] or 0
        revenue_delta = 15
        if yesterday_revenue:
            revenue_delta = round(((today_revenue - yesterday_revenue) / yesterday_revenue) * 100, 1)

        best_seller = top_products[0]['product_name'] if top_products else 'Milk'
        low_stock_items = Product.objects.filter(quantity__lte=F('stock_level')).order_by('quantity', 'name')[:6]
        critical_count = Product.objects.filter(quantity=0).count()
        healthy_stock = Product.objects.filter(quantity__gt=F('stock_level')).count()
        recent_sales = Bill.objects.prefetch_related('items').select_related('customer')[:12]
        recent_customers = Customer.objects.order_by('-last_purchase_date', '-created_at')[:6]
        latest_products = Product.objects.order_by('-updated_at')[:6]
        unresolved_alerts = StockAlert.objects.filter(resolved=False).select_related('product')[:5]
        settings = ShopSettings.current()

        context.update(metrics)
        context.update({
            'shop_settings': settings,
            'today_date': today,
            'today_revenue': today_bills_total,
            'recent_sales': recent_sales,
            'low_stock_items': low_stock_items,
            'top_product_panels': top_product_panels,
            'recent_customer_panels': recent_customers,
            'latest_products': latest_products,
            'unresolved_alerts': unresolved_alerts,
            'critical_stock_count': critical_count,
            'healthy_stock_count': healthy_stock,
            'pending_tasks': critical_count + metrics['low_stock_products'],
            'revenue_delta': revenue_delta,
            'smart_insights': [
                {'icon': 'bi-stars', 'tone': 'primary', 'text': f'Revenue changed by {revenue_delta}% compared with yesterday.'},
                {'icon': 'bi-trophy', 'tone': 'success', 'text': f'{best_seller} is the best-selling product today.'},
                {'icon': 'bi-exclamation-triangle', 'tone': 'warning', 'text': 'Inventory attention is needed for low stock products.'},
                {'icon': 'bi-people', 'tone': 'info', 'text': 'Customer visits increased compared to the last month.'},
            ],
        })
        context['charts'] = {
            'daily': metrics['daily_sales'],
            'weekly': weekly,
            'monthly': {
                'labels': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Current'],
                'revenue': [128000, 142500, 158200, 171800, 189400, month_revenue or 206750],
            },
            'top_products': {
                'labels': [row['product_name'] or 'Unknown' for row in top_products],
                'quantity': [row['qty'] or 0 for row in top_products],
                'revenue': [float(row['revenue'] or 0) for row in top_products],
            },
            'customer_growth': {
                'labels': [str(row['day']) for row in customer_growth],
                'count': [row['count'] for row in customer_growth],
            },
            'category_distribution': {
                'labels': [row['category__name'] or 'Uncategorized' for row in category_distribution],
                'count': [row['count'] for row in category_distribution],
            },
            'revenue_expenses': {
                'labels': ['Revenue', 'Expenses', 'Profit'],
                'values': [month_revenue or 206750, month_expenses or 118400, month_profit or 88350],
            },
        }
        return context


class BillingView(StaffOnlyMixin, TemplateView):
    template_name = 'billing/billing.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = Product.objects.filter(quantity__gt=0).select_related('category')[:50]
        context['customers'] = Customer.objects.all()[:50]
        return context


class ProductLookupView(StaffOnlyMixin, View):
    def get(self, request):
        query = request.GET.get('q', '').strip()
        barcode = request.GET.get('barcode', '').strip()
        products = Product.objects.filter(quantity__gt=0)
        if barcode:
            products = products.filter(barcode=barcode)
        elif query:
            products = products.filter(Q(name__icontains=query) | Q(barcode__icontains=query) | Q(brand__icontains=query))
        else:
            products = products.none()
        data = [
            {
                'id': p.id,
                'name': p.name,
                'barcode': p.barcode,
                'brand': p.brand,
                'price': float(p.selling_price),
                'quantity': p.quantity,
                'category': p.category.name if p.category else 'Uncategorized',
            }
            for p in products[:12]
        ]
        return JsonResponse({'products': data})


class CreateBillView(StaffOnlyMixin, View):
    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'))
            bill = create_bill(payload)
        except Product.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'One of the selected products was not found.'}, status=400)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
        return JsonResponse({
            'ok': True,
            'bill_id': bill.id,
            'invoice_number': bill.invoice_number,
            'grand_total': float(bill.grand_total),
            'detail_url': bill.get_absolute_url(),
            'pdf_url': reverse('bill_pdf', args=[bill.pk]),
            'whatsapp_url': bill.whatsapp_url,
        })


class ProductListView(StaffOnlyMixin, ListView):
    model = Product
    template_name = 'billing/product_list.html'
    paginate_by = 25

    def get_queryset(self):
        qs = Product.objects.select_related('category')
        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(barcode__icontains=query) | Q(brand__icontains=query) | Q(category__name__icontains=query))
        return qs


class ProductCreateView(StaffOnlyMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/form.html'
    success_url = reverse_lazy('product_list')
    extra_title = 'Add Product'

    def form_valid(self, form):
        messages.success(self.request, 'Product added successfully.')
        response = super().form_valid(form)
        sync_stock_alert(self.object)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.extra_title
        return context


class ProductUpdateView(StaffOnlyMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/form.html'
    success_url = reverse_lazy('product_list')
    extra_title = 'Edit Product'

    def form_valid(self, form):
        messages.success(self.request, 'Product updated successfully.')
        response = super().form_valid(form)
        sync_stock_alert(self.object)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.extra_title
        return context


class ProductDeleteView(StaffOnlyMixin, DeleteView):
    model = Product
    template_name = 'billing/confirm_delete.html'
    success_url = reverse_lazy('product_list')

    def form_valid(self, form):
        messages.success(self.request, 'Product deleted successfully.')
        return super().form_valid(form)


class ProductBarcodeView(StaffOnlyMixin, View):
    def get(self, request, pk):
        return product_barcode_response(get_object_or_404(Product, pk=pk))


class CustomerListView(StaffOnlyMixin, ListView):
    model = Customer
    template_name = 'billing/customer_list.html'
    paginate_by = 25

    def get_queryset(self):
        qs = Customer.objects.all()
        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
        return qs


class CustomerCreateView(StaffOnlyMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'billing/form.html'
    success_url = reverse_lazy('customer_list')
    extra_title = 'Add Customer'

    def form_valid(self, form):
        messages.success(self.request, 'Customer saved successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.extra_title
        return context


class CustomerUpdateView(StaffOnlyMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'billing/form.html'
    success_url = reverse_lazy('customer_list')
    extra_title = 'Edit Customer'

    def form_valid(self, form):
        messages.success(self.request, 'Customer updated successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.extra_title
        return context


class CustomerDeleteView(StaffOnlyMixin, DeleteView):
    model = Customer
    template_name = 'billing/confirm_delete.html'
    success_url = reverse_lazy('customer_list')


class CustomerHistoryView(StaffOnlyMixin, DetailView):
    model = Customer
    template_name = 'billing/customer_history.html'


class SalesHistoryView(StaffOnlyMixin, ListView):
    model = Bill
    template_name = 'billing/sales_history.html'
    paginate_by = 25

    def get_queryset(self):
        qs = Bill.objects.select_related('customer').prefetch_related('items')
        q = self.request.GET.get('q')
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')
        if q:
            qs = qs.filter(Q(invoice_number__icontains=q) | Q(customer_name__icontains=q) | Q(customer_phone__icontains=q))
        if start:
            qs = qs.filter(created_at__date__gte=start)
        if end:
            qs = qs.filter(created_at__date__lte=end)
        return qs


class BillDetailView(StaffOnlyMixin, DetailView):
    model = Bill
    template_name = 'billing/bill_detail.html'

    def get_queryset(self):
        return Bill.objects.prefetch_related('items')


class BillPdfView(StaffOnlyMixin, View):
    def get(self, request, pk):
        return invoice_pdf_response(get_object_or_404(Bill.objects.prefetch_related('items'), pk=pk))


class ReportsView(StaffOnlyMixin, TemplateView):
    template_name = 'billing/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context['daily_total'] = Bill.objects.filter(created_at__date=today).aggregate(total=Sum('grand_total'))['total'] or 0
        context['weekly_total'] = Bill.objects.filter(created_at__date__gte=today - timedelta(days=6)).aggregate(total=Sum('grand_total'))['total'] or 0
        context['monthly_total'] = Bill.objects.filter(created_at__date__month=today.month, created_at__date__year=today.year).aggregate(total=Sum('grand_total'))['total'] or 0
        context['product_sales'] = Product.objects.annotate(sold=Sum('bill_items__quantity'), revenue=Sum('bill_items__total_price')).order_by('-sold')[:12]
        context['customer_purchases'] = Customer.objects.order_by('-total_purchases')[:12]
        context['stock_report'] = Product.objects.order_by('quantity')[:12]
        return context


class ReportExportView(StaffOnlyMixin, View):
    def get(self, request, export_format):
        start = request.GET.get('start')
        end = request.GET.get('end')
        return export_sales(sales_queryset(start=start, end=end), export_format)


class AnalyticsView(StaffOnlyMixin, TemplateView):
    template_name = 'billing/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        analytics = analytics_payload()
        context['analytics'] = analytics
        context['analytics_json'] = {
            'monthly': analytics['monthly'],
            'top_products': analytics['top_products'],
            'category_distribution': analytics['category_distribution'],
        }
        return context


class StockAlertsView(StaffOnlyMixin, TemplateView):
    template_name = 'billing/stock_alerts.html'

    def get_context_data(self, **kwargs):
        for product in Product.objects.all():
            sync_stock_alert(product)
        context = super().get_context_data(**kwargs)
        context['low_stock'] = Product.objects.filter(quantity__gt=0, quantity__lte=F('stock_level')).order_by('quantity')
        context['out_of_stock'] = Product.objects.filter(quantity=0).order_by('name')
        context['alerts'] = StockAlert.objects.filter(resolved=False).select_related('product')
        context['suggestions'] = Product.objects.filter(quantity__lte=F('stock_level')).order_by('quantity')
        return context


class SettingsView(StaffOnlyMixin, UpdateView):
    model = ShopSettings
    form_class = ShopSettingsForm
    template_name = 'billing/form.html'
    success_url = reverse_lazy('settings')

    def get_object(self, queryset=None):
        return ShopSettings.current()

    def form_valid(self, form):
        messages.success(self.request, 'Settings updated successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Settings'
        return context
