from django.contrib import admin
from django.urls import path
from store import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('produto/<int:pk>/', views.product_detail, name='product_detail'),
    path('carrinho/', views.cart, name='cart'),
    path('carrinho/adicionar/<int:pk>/', views.add_to_cart, name='add_to_cart'),
    path('carrinho/remover/<int:pk>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    
    # Rotas de Clientes
    path('clientes/', views.customer_list, name='customer_list'),
    path('cliente/novo/', views.customer_create, name='customer_create'),
    path('cliente/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('cliente/<int:customer_pk>/pagamento/', views.payment_create, name='payment_create'),
    path('cliente/<int:pk>/extrato.pdf', views.customer_statement_pdf, name='customer_statement_pdf'),
    
    path('compra/<int:pk>/', views.order_detail, name='order_detail'),
    path('compra/<int:pk>/pdf/', views.order_pdf, name='order_pdf'),
    path('gestao/', views.management_dashboard, name='management_dashboard'),
    
    # Rotas de Produtos (Atualizado com a tela de cadastro dedicada)
    path('gestao/produtos/', views.manage_products, name='manage_products'),
    path('gestao/produtos/cadastrar/', views.create_product, name='create_product'),
    path('gestao/produtos/<int:pk>/atualizar', views.update_product_stock_price, name='update_product_stock_price'),
]