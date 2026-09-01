# MG Perfumaria, Cosméticos e Variedades — Django + MySQL

Sistema web de loja com e-commerce e gestão de contas de clientes.

## Novas funcionalidades de contas
- Cliente pode ter uma conta para compras que não serão pagas à vista.
- Cada compra fiada fica vinculada ao cliente e aparece no histórico.
- Abertura de uma compra mostra todos os produtos, quantidades, valores, pagamentos e saldo.
- Registro de pagamentos parciais ou totais.
- Pagamento da conta pode ser distribuído automaticamente entre as compras em aberto, das mais antigas para as mais novas.
- Extrato completo da conta em PDF.
- Comprovante detalhado de uma compra em PDF, incluindo os produtos comprados.
- Os PDFs são gerados no navegador para download e posterior envio ao cliente por WhatsApp, e-mail etc.

## Instalação

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Crie o banco MySQL `loja_rosa_bege` e configure as variáveis de ambiente (`.env.example`).

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse:
- Loja: `http://127.0.0.1:8000/`
- Gestão: `http://127.0.0.1:8000/gestao/`
- Contas: `http://127.0.0.1:8000/clientes/`
- Admin: `http://127.0.0.1:8000/admin/`

## Importante
O projeto usa ReportLab para gerar os PDFs. Para envio automático por WhatsApp/e-mail seria necessário integrar um serviço externo; nesta versão o sistema gera o PDF pronto para download e compartilhamento.
