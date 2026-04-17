import csv
from django.core.management.base import BaseCommand
from gestao.models import Disciplina
from django.db import transaction

class Command(BaseCommand):
    help = 'Importa nomes e carga horária das disciplinas'

    def add_arguments(self, parser):
        parser.add_argument('arquivo_csv', type=str, help='Caminho para o arquivo CSV')

    def handle(self, *args, **options):
        caminho_arquivo = options['arquivo_csv']

        try:
            with open(caminho_arquivo, newline='', encoding='utf-8') as csvfile:
                # Lembre-se: use ';' ou ',' conforme o seu arquivo CSV
                leitor = csv.DictReader(csvfile, delimiter=',')
                
                sucessos = 0
                erros = 0

                for linha in leitor:
                    nome = linha.get('nome', '').strip()
                    aulas_str = linha.get('aulas', '0').strip()

                    if not nome: continue

                    try:
                        # Convertemos para inteiro (ex: 72 ou 120)
                        aulas_int = int(aulas_str)
                        
                        with transaction.atomic():
                            # Agora o defaults inclui a quantidade_aulas
                            disciplina, criada = Disciplina.objects.update_or_create(
                                nome=nome,
                                defaults={'quantidade_aulas': aulas_int}
                            )

                            if criada:
                                self.stdout.write(self.style.SUCCESS(f"✔️ Criada: {nome}"))
                                sucessos += 1
                            else:
                                self.stdout.write(self.style.WARNING(f"🔄 Atualizada: {nome} ({aulas_int} aulas)"))

                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ Erro em {nome}: {str(e)}"))
                        erros += 1

                self.stdout.write(self.style.SUCCESS(f"\n🚀 Concluído! {sucessos} novas, {erros} erros."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Erro fatal: {str(e)}"))