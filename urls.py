from django.urls import path

from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('billing/', views.BillingView.as_view(), name='billing'),
    path('api/product-lookup/', views.ProductLookupView.as_view(), name='product_lookup'),
    path('api/create-bill/', views.CreateBillView.as_view(), name='create_bill'),
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/add/', views.ProductCreateView.as_view(), name='product_add'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),
    path('products/<int:pk>/barcode/', views.ProductBarcodeView.as_view(), name='product_barcode'),
    path('customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('customers/add/', views.CustomerCreateView.as_view(), name='customer_add'),
    path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer_edit'),
    path('customers/<int:pk>/delete/', views.CustomerDeleteView.as_view(), name='customer_delete'),
    path('customers/<int:pk>/history/', views.CustomerHistoryView.as_view(), name='customer_history'),
    path('sales/', views.SalesHistoryView.as_view(), name='sales_history'),
    path('sales/<int:pk>/', views.BillDetailView.as_view(), name='bill_detail'),
    path('sales/<int:pk>/pdf/', views.BillPdfView.as_view(), name='bill_pdf'),
    path('reports/', views.ReportsView.as_view(), name='reports'),
    path('reports/export/<str:export_format>/', views.ReportExportView.as_view(), name='report_export'),
    path('analytics/', views.AnalyticsView.as_view(), name='analytics'),
    path('stock-alerts/', views.StockAlertsView.as_view(), name='stock_alerts'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
]
