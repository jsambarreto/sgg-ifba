import csv
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from gestao.models import Professor
from django.db import transaction

class Command(BaseCommand):
    help = 'Importa professores e cria contas de acesso a partir do Nome e Email'

    def add_arguments(self, parser):
        parser.add_argument('arquivo_csv', type=str, help='Caminho para o arquivo CSV')

    def handle(self, *args, **options):
        caminho_arquivo = options['arquivo_csv']
        senha_padrao = 'IFBA@2026'

        try:
            with open(caminho_arquivo, newline='', encoding='utf-8') as csvfile:
                # Se o seu Excel separar por vírgula em vez de ponto e vírgula, troque para delimiter=','
                leitor = csv.DictReader(csvfile, delimiter=',')
                
                sucessos = 0
                erros = 0

                for linha in leitor:
                    nome = linha.get('nome', '').strip()
                    email = linha.get('email', '').strip()

                    if not nome or not email:
                        self.stdout.write(self.style.WARNING(f"⚠️ Linha ignorada (Faltam dados): {linha}"))
                        erros += 1
                        continue

                    # A MÁGICA ACONTECE AQUI: Extrai o usuário cortando no '@'
                    # Ex: 'jorge.barreto@ifba.edu.br' vira 'jorge.barreto'
                    username_extraido = email.split('@')[0]

                    try:
                        with transaction.atomic():
                            # 1. Cria ou pega o Usuário de Login usando o username extraído
                            user, user_criado = User.objects.get_or_create(username=username_extraido)
                            if user_criado:
                                user.set_password(senha_padrao)
                                user.email = email
                                user.save()

                            # 2. Cria o Professor Físico e liga ao Usuário
                            # Como removemos a matrícula, usamos o próprio 'user' como chave de busca
                            prof, prof_criado = Professor.objects.get_or_create(
                                usuario=user,
                                defaults={'nome_completo': nome}
                            )

                            if prof_criado:
                                self.stdout.write(self.style.SUCCESS(f"✔️ Importado: {nome} (Login: {username_extraido})"))
                                sucessos += 1
                            else:
                                self.stdout.write(self.style.WARNING(f"⏩ Pulado: {nome} (Já existe no sistema)"))

                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ Erro ao salvar {nome}: {str(e)}"))
                        erros += 1

                self.stdout.write(self.style.SUCCESS(f"\n🚀 Resumo: {sucessos} adicionados, {erros} erros."))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"❌ Arquivo não encontrado: {caminho_arquivo}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Erro fatal: {str(e)}"))