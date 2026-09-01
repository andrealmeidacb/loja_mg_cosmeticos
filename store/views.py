from decimal import Decimal
from io import BytesIO
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from .models import Category, Customer, Product, Order, OrderItem, Payment, FinancialEntry
from .forms import CustomerForm


def home(request):
    products = Product.objects.filter(active=True).select_related('category')
    q = request.GET.get('q', '')
    category = request.GET.get('category', '')

    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    
    if category:
        products = products.filter(category__slug=category)

    context = {
        'products': products,
        'categories': Category.objects.all(),
        'q': q,
        'selected_category': category,
    }
    
    return render(request, 'home.html', context)


def product_detail(request, pk):
    return render(request, 'product_detail.html', {'product': get_object_or_404(Product, pk=pk, active=True)})


def _cart(request): 
    return request.session.get('cart', {})


def cart(request):
    data = _cart(request)
    products = Product.objects.filter(id__in=[int(i) for i in data])
    items = []
    total = Decimal('0')
    for p in products:
        qty = int(data[str(p.id)])
        subtotal = p.price * qty
        items.append({'product': p, 'quantity': qty, 'subtotal': subtotal})
        total += subtotal
    return render(request, 'cart.html', {'items': items, 'total': total})


def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk, active=True)
    data = _cart(request)
    key = str(product.id)
    data[key] = min(int(data.get(key, 0)) + 1, product.stock)
    request.session['cart'] = data
    return redirect('cart')


def remove_from_cart(request, pk):
    data = _cart(request)
    data.pop(str(pk), None)
    request.session['cart'] = data
    return redirect('cart')


def checkout(request):
    data = _cart(request)
    if not data: 
        return redirect('home')
        
    products = Product.objects.filter(id__in=[int(i) for i in data])
    subtotal = sum((p.price * int(data[str(p.id)]) for p in products), Decimal('0'))
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        # Captura e valida o valor do desconto informado
        discount_input = request.POST.get('discount', '0').replace(',', '.').strip()
        try:
            discount = Decimal(discount_input) if discount_input else Decimal('0.00')
        except Exception:
            discount = Decimal('0.00')

        # O desconto não pode ser negativo nem maior que o subtotal
        discount = min(subtotal, max(Decimal('0.00'), discount))
        total_final = subtotal - discount

        customer = Customer.objects.filter(email=email).first() if email else None
        if not customer: 
            customer = Customer.objects.create(name=name, email=email, phone=phone)
        else: 
            customer.name = name or customer.name
            customer.phone = phone or customer.phone
            customer.save()
        
        payment_method = request.POST.get('payment_method', 'cash')
        if payment_method == 'credit' and not customer.credit_enabled:
            messages.error(request, 'Este cliente não possui conta habilitada.')
            return redirect('checkout')
            
        # Salva o subtotal e o desconto no pedido
        order = Order.objects.create(
            customer=customer,
            total=subtotal,
            discount=discount,
            status='paid' if payment_method == 'cash' else 'pending',
            payment_method=payment_method,
            due_date=request.POST.get('due_date') or None
        )
        
        for p in products:
            qty = int(data[str(p.id)])
            if qty > p.stock: 
                messages.error(request, f'Estoque insuficiente para {p.name}.')
                order.delete()
                return redirect('cart')
            OrderItem.objects.create(order=order, product=p, quantity=qty, unit_price=p.price)
            p.stock -= qty
            p.save(update_fields=['stock'])
            
        if payment_method == 'cash':
            # Pagamento e entrada financeira gravam o valor líquido final (com desconto)
            pay = Payment.objects.create(
                order=order, 
                amount=total_final, 
                method=request.POST.get('payment_method_detail', 'cash')
            )
            FinancialEntry.objects.create(
                type='income', 
                description=f'Venda #{order.pk}', 
                amount=total_final, 
                order=order, 
                payment=pay
            )
            
        request.session['cart'] = {}
        return render(request, 'success.html', {'order': order})
        
    return render(request, 'checkout.html', {
        'products': products, 
        'cart_data': data, 
        'total': subtotal
    })


def customer_create(request):
    next_url = request.GET.get('next') or request.POST.get('next')

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Cliente "{customer.name}" cadastrado com sucesso!')
            
            if next_url:
                return redirect(next_url)
            return redirect('customer_list')
    else:
        form = CustomerForm()

    return render(request, 'customer_form.html', {
        'form': form,
        'next_url': next_url
    })


def customer_list(request):
    customers = Customer.objects.all().order_by('name')
    q = request.GET.get('q', '')
    if q: 
        customers = customers.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q))
    return render(request, 'customers.html', {'customers': customers, 'q': q})


def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    
    # 1. Busca seguro das compras/pedidos
    if hasattr(customer, 'purchases'):
        orders = customer.purchases.all()
    elif hasattr(customer, 'orders'):
        orders = customer.orders.all()
    else:
        orders = Order.objects.filter(customer=customer)
    
    # 2. Busca seguro dos pagamentos
    if hasattr(customer, 'payments'):
        payments = customer.payments.all()
    else:
        payments = Payment.objects.filter(order__customer=customer)
    
    # 3. Unificação dos registros no Extrato
    statement_items = []
    
    for order in orders:
        order_total = getattr(order, 'total', getattr(order, 'total_amount', 0))
        statement_items.append({
            'date': order.created_at,
            'type': 'DEBIT',
            'description': f'Compra - Pedido #{order.pk}',
            'amount': order_total,
            'object': order
        })
        
    for payment in payments:
        payment_date = getattr(payment, 'paid_at', getattr(payment, 'created_at', getattr(payment, 'date', None)))
        method_desc = payment.get_method_display() if hasattr(payment, 'get_method_display') else 'Recebimento'
        statement_items.append({
            'date': payment_date,
            'type': 'CREDIT',
            'description': f'Pagamento ({method_desc})',
            'amount': payment.amount,
            'object': payment
        })
    
    # 4. Ordenação cronológica
    statement_items.sort(key=lambda x: x['date'] if x['date'] else timezone.now())
    
    # 5. Cálculo do saldo devedor progressivo
    running_balance = Decimal('0.00')
    for item in statement_items:
        if item['type'] == 'DEBIT':
            running_balance += Decimal(str(item['amount']))
        else:
            running_balance -= Decimal(str(item['amount']))
        item['running_balance'] = running_balance

    return render(request, 'customer_detail.html', {
        'customer': customer,
        'statement_items': statement_items,
        'current_balance': running_balance,
    })


def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items__product', 'payments'), pk=pk)
    
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0'))
        balance = order.balance
        if amount <= 0 or amount > balance: 
            messages.error(request, 'Informe um valor válido para o saldo desta compra.')
        else:
            pay = Payment.objects.create(
                order=order,
                amount=amount,
                method=request.POST.get('method', 'cash'),
                note=request.POST.get('note', '')
            )
            FinancialEntry.objects.create(
                type='income',
                description=f'Pagamento pedido #{order.pk}',
                amount=amount,
                order=order,
                payment=pay
            )
            if order.balance <= 0: 
                order.status = 'paid'
                order.save(update_fields=['status'])
            messages.success(request, 'Pagamento registrado com sucesso.')
            return redirect('order_detail', pk=order.pk)
            
    # Formatação direta da data e hora em Python (com ajuste de fuso horário)
    created_at_formatted = ''
    if order.created_at:
        local_date = timezone.localtime(order.created_at)
        created_at_formatted = local_date.strftime('%d/%m/%Y %H:%M')

    return render(request, 'order_detail.html', {
        'order': order,
        'created_at_formatted': created_at_formatted
    })


def payment_create(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk)
    if request.method != 'POST': 
        return redirect('customer_detail', pk=customer.pk)
    amount = Decimal(request.POST.get('amount', '0'))
    balance = customer.balance
    if amount <= 0 or amount > balance: 
        messages.error(request, 'Valor de pagamento inválido.')
    else:
        remaining = amount
        purchases = customer.purchases.order_by('created_at') if hasattr(customer, 'purchases') else customer.orders.order_by('created_at')
        for order in purchases:
            due = order.balance
            if due <= 0: 
                continue
            part = min(remaining, due)
            pay = Payment.objects.create(order=order, amount=part, method=request.POST.get('method', 'cash'), note='Pagamento de conta')
            FinancialEntry.objects.create(type='income', description=f'Pagamento da conta de {customer.name}', amount=part, order=order, payment=pay)
            if order.balance <= 0: 
                order.status = 'paid'
                order.save(update_fields=['status'])
            remaining -= part
            if remaining <= 0: 
                break
        messages.success(request, 'Pagamento da conta registrado e distribuído entre as compras em aberto.')
    return redirect('customer_detail', pk=customer.pk)


def _pdf_response(filename, title, customer, rows, totals):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CenterTitle', parent=styles['Title'], alignment=TA_CENTER, fontSize=16))
    
    story = [
        Paragraph('MG Perfumaria, Cosméticos e Variedades', styles['CenterTitle']),
        Paragraph(title, styles['Heading2']),
        Spacer(1, 10),
        Paragraph(f'<b>Cliente:</b> {customer.name}', styles['BodyText']),
        Paragraph(f'<b>Telefone:</b> {customer.phone or "—"}', styles['BodyText']),
        Spacer(1, 14)
    ]
    
    # Cabeçalho da tabela unificada
    data = [['Data/Hora', 'Tipo', 'Descrição', 'Valor', 'Saldo Devedor']] + rows
    
    # Largura das colunas (Soma = 535 pt, ideal para A4)
    table = Table(data, colWidths=[95, 80, 160, 100, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f4c8d6')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#eaded7')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),  # Alinha valores e saldos à direita
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6)
    ]))
    
    story += [table, Spacer(1, 16)]
    story += [
        Paragraph(f'<b>Total Comprado:</b> R$ {totals[0]:.2f}', styles['BodyText']),
        Paragraph(f'<b>Total Pago:</b> R$ {totals[1]:.2f}', styles['BodyText']),
        Paragraph(f'<b>Saldo Devedor Atual:</b> R$ {totals[2]:.2f}', styles['BodyText']),
        Spacer(1, 20),
        Paragraph(f'Emitido em {timezone.localtime():%d/%m/%Y %H:%M}', styles['BodyText'])
    ]
    
    doc.build(story)
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename=filename, content_type='application/pdf')


def order_pdf(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items__product", "payments"), pk=pk)
    customer = order.customer
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=18))
    story = [
        Paragraph("MG Perfumaria, Cosméticos e Variedades", styles["CenterTitle"]),
        Paragraph(f"Comprovante da compra #{order.pk}", styles["Heading2"]),
        Spacer(1, 12),
        Paragraph(f"<b>Cliente:</b> {customer.name}", styles["BodyText"]),
        Paragraph(f"<b>Data:</b> {order.created_at:%d/%m/%Y %H:%M}", styles["BodyText"]),
        Spacer(1, 16)
    ]
    data = [["Qtd.", "Produto", "Valor unit.", "Subtotal"]]
    for item in order.items.all(): 
        data.append([str(item.quantity), item.product.name, f"R$ {item.unit_price:.2f}", f"R$ {item.subtotal:.2f}"])
    table = Table(data, colWidths=[45, 250, 90, 90])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4c8d6")),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#eaded7")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8)
    ]))
    story += [table, Spacer(1, 18)]
    story += [
        Paragraph(f"<b>Total da compra:</b> R$ {order.total:.2f}", styles["BodyText"]),
        Paragraph(f"<b>Total pago:</b> R$ {order.paid_amount:.2f}", styles["BodyText"]),
        Paragraph(f"<b>Saldo:</b> R$ {order.balance:.2f}", styles["BodyText"]),
        Spacer(1, 20),
        Paragraph("Documento gerado pelo sistema de gestão da loja.", styles["BodyText"])
    ]
    doc.build(story)
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename=f"compra_{order.pk}.pdf", content_type="application/pdf")


def customer_statement_pdf(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    
    # 1. Busca compras e pagamentos do cliente
    if hasattr(customer, 'purchases'):
        orders = customer.purchases.all()
    elif hasattr(customer, 'orders'):
        orders = customer.orders.all()
    else:
        orders = Order.objects.filter(customer=customer)
        
    if hasattr(customer, 'payments'):
        payments = customer.payments.all()
    else:
        payments = Payment.objects.filter(order__customer=customer)

    # 2. Monta e unifica os lançamentos
    statement_items = []
    
    for order in orders:
        order_total = getattr(order, 'total', getattr(order, 'total_amount', 0))
        statement_items.append({
            'date': order.created_at,
            'type': 'DEBIT',
            'type_label': 'Compra (-)',
            'description': f'Compra #{order.pk}',
            'amount': order_total,
        })
        
    for payment in payments:
        payment_date = getattr(payment, 'paid_at', getattr(payment, 'created_at', getattr(payment, 'date', None)))
        method_desc = payment.get_method_display() if hasattr(payment, 'get_method_display') else 'Recebimento'
        statement_items.append({
            'date': payment_date,
            'type': 'CREDIT',
            'type_label': 'Pagamento (+)',
            'description': f'Pagamento ({method_desc})',
            'amount': payment.amount,
        })

    # 3. Ordenação cronológica
    statement_items.sort(key=lambda x: x['date'] if x['date'] else timezone.now())

    # 4. Monta as linhas da tabela em PDF com saldo progressivo
    rows = []
    running_balance = Decimal('0.00')

    for item in statement_items:
        amount = Decimal(str(item['amount']))
        if item['type'] == 'DEBIT':
            running_balance += amount
            val_str = f"+ R$ {amount:.2f}"
        else:
            running_balance -= amount
            val_str = f"- R$ {amount:.2f}"

        date_str = item['date'].strftime('%d/%m/%Y %H:%M') if item['date'] else '—'

        rows.append([
            date_str,
            item['type_label'],
            item['description'],
            val_str,
            f"R$ {running_balance:.2f}"
        ])

    totals = (customer.total_credit, customer.total_paid, customer.balance)
    return _pdf_response(f'extrato_{customer.pk}.pdf', 'Extrato Unificado da Conta', customer, rows, totals)


def management_dashboard(request):
    income, expense, investment = FinancialEntry.totals()
    profit = income - expense - investment
    return render(request, 'management.html', {
        'income': income,
        'expense': expense,
        'investment': investment,
        'profit': profit,
        'stock_low': Product.objects.filter(active=True, stock__lte=5).order_by('stock'),
        'recent_orders': Order.objects.select_related('customer').order_by('-created_at')[:8],
        'customers_count': Customer.objects.count(),
        'products_count': Product.objects.filter(active=True).count(),
        'orders_count': Order.objects.count(),
        'credit_balance': Customer.objects.aggregate(v=Sum('orders__total'))['v'] or Decimal('0')
    })


def manage_products(request):
    query = request.GET.get('q', '').strip()
    products = Product.objects.all().select_related('category').order_by('-id')

    if query:
        if query.isdigit():
            products = products.filter(Q(id=int(query)) | Q(name__icontains=query))
        else:
            products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))

    return render(request, 'manage_products.html', {
        'products': products,
        'q': query
    })


def create_product(request):
    if request.method == 'POST':
        try:
            custom_id = request.POST.get('custom_id', '').strip()
            name = request.POST.get('name', '').strip()
            category_name = request.POST.get('category_name', '').strip()
            price = float(request.POST.get('price', 0).replace(',', '.'))
            cost = float(request.POST.get('cost', 0).replace(',', '.'))
            stock = int(request.POST.get('stock', 0))

            category, _ = Category.objects.get_or_create(
                name__iexact=category_name,
                defaults={
                    'name': category_name,
                    'slug': slugify(category_name)
                }
            )

            slug = slugify(name)
            base_slug = slug
            count = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{count}"
                count += 1

            product_kwargs = {
                'name': name,
                'slug': slug,
                'category': category,
                'price': price,
                'cost': cost,
                'stock': stock
            }

            if custom_id and custom_id.isdigit():
                product_kwargs['id'] = int(custom_id)

            product = Product.objects.create(**product_kwargs)
            messages.success(request, f'Produto "#{product.id} - {product.name}" cadastrado com sucesso!')

            return redirect('manage_products')

        except Exception as e:
            messages.error(request, f'Erro ao cadastrar produto: {str(e)}')

    categories = Category.objects.all()
    return render(request, 'create_product.html', {
        'categories': categories
    })


def update_product_stock_price(request, pk):
    if request.method == 'POST':
        product = get_object_or_404(Product, pk=pk)
        try:
            price_input = request.POST.get('price', '').replace(',', '.')
            cost_input = request.POST.get('cost', '').replace(',', '.')
            stock_input = request.POST.get('stock', '')

            if price_input:
                product.price = float(price_input)
            if cost_input:
                product.cost = float(cost_input)
            if stock_input:
                product.stock = int(stock_input)

            product.save()
            messages.success(request, f'Produto "#{product.id} - {product.name}" atualizado!')
        except ValueError:
            messages.error(request, 'Valores inválidos informados.')

    return redirect('manage_products')