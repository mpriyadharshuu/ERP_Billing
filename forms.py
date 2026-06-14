from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from django import forms

from .models import Category, Customer, Product, ShopSettings


class CrispyMixin:
    submit_label = 'Save'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', self.submit_label, css_class='btn btn-primary'))


class ProductForm(CrispyMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'barcode', 'category', 'brand', 'cost_price', 'selling_price',
            'quantity', 'stock_level', 'image', 'description',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.all()
        self.fields['barcode'].help_text = 'Leave blank to auto-generate.'


class CustomerForm(CrispyMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }


class CategoryForm(CrispyMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class ShopSettingsForm(CrispyMixin, forms.ModelForm):
    class Meta:
        model = ShopSettings
        fields = ['shop_name', 'shop_address', 'gst_number', 'contact_number', 'invoice_footer', 'company_logo']
        widgets = {
            'shop_address': forms.Textarea(attrs={'rows': 3}),
            'invoice_footer': forms.Textarea(attrs={'rows': 2}),
        }
