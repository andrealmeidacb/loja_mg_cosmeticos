from django.core.management.base import BaseCommand
from store.models import Category, Product

class Command(BaseCommand):
    help = 'Cadastra produtos automaticamente no banco de dados'

    def handle(self, *args, **options):
        # Coloque a lógica de criação do produto aqui...
        self.stdout.write(self.style.SUCCESS('Produtos cadastrados com sucesso!'))