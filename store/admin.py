from django.contrib import admin
from .models import Category, Customer, Product, Order, OrderItem, Payment, FinancialEntry

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name','phone','credit_enabled','balance')
    search_fields = ('name','email','phone')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id','customer','total','payment_method','status','due_date','created_at')
    list_filter = ('payment_method','status')
    search_fields = ('customer__name',)

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(OrderItem)
admin.site.register(Payment)
admin.site.register(FinancialEntry)
