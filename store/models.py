from decimal import Decimal
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
    address = models.CharField(max_length=255, blank=True)
    credit_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def purchases(self):
        return self.orders.filter(payment_method='credit').exclude(status='cancelled')

    @property
    def total_credit(self):
        # Soma o total final descontado de todas as compras fiado/crédito
        total_sum = Decimal('0.00')
        for purchase in self.purchases:
            total_sum += purchase.final_total
        return total_sum

    @property
    def total_paid(self):
        return Payment.objects.filter(
            order__customer=self, 
            order__payment_method='credit'
        ).aggregate(v=models.Sum('amount'))['v'] or Decimal('0.00')

    @property
    def balance(self):
        return self.total_credit - self.total_paid


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def profit_per_unit(self):
        return self.price - self.cost

    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('paid', 'Pago'),
        ('delivered', 'Entregue'),
        ('cancelled', 'Cancelado'),
    ]
    PAYMENT_CHOICES = [
        ('cash', 'À vista'),
        ('credit', 'Conta do cliente'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cash')
    due_date = models.DateField(null=True, blank=True)
    
    # Valores financeiros
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0) # Subtotal bruto
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0) # Desconto concedido
    
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'Pedido #{self.pk}'

    @property
    def final_total(self):
        """Retorna o total líquido após a aplicação do desconto (não permite saldo negativo)."""
        return max(Decimal('0.00'), self.total - self.discount)

    @property
    def paid_amount(self):
        return self.payments.aggregate(v=models.Sum('amount'))['v'] or Decimal('0.00')

    @property
    def balance(self):
        """Mede o saldo devedor considerando o valor líquido (com desconto)."""
        return max(Decimal('0.00'), self.final_total - self.paid_amount)

    @property
    def is_fully_paid(self):
        return self.balance <= 0


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.quantity * self.unit_price


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Dinheiro'),
        ('pix', 'PIX'),
        ('card', 'Cartão'),
        ('transfer', 'Transferência'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash')
    paid_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=180, blank=True)

    def __str__(self):
        return f'Pagamento #{self.pk} — R$ {self.amount}'


class FinancialEntry(models.Model):
    TYPE_CHOICES = [
        ('income', 'Receita'),
        ('expense', 'Despesa'),
        ('investment', 'Investimento'),
    ]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'{self.get_type_display()} — {self.description}'

    @classmethod
    def totals(cls):
        income = cls.objects.filter(type='income').aggregate(v=models.Sum('amount'))['v'] or Decimal('0.00')
        expense = cls.objects.filter(type='expense').aggregate(v=models.Sum('amount'))['v'] or Decimal('0.00')
        investment = cls.objects.filter(type='investment').aggregate(v=models.Sum('amount'))['v'] or Decimal('0.00')
        return income, expense, investment