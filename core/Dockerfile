# Usa uma versão oficial e leve do Python
FROM python:3.11-slim

# Impede o Python de gravar arquivos .pyc e força o log a sair no terminal em tempo real
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Define a pasta de trabalho dentro do container
WORKDIR /app

# Copia e instala as dependências
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para o container
COPY . /app/

# Coleta os arquivos estáticos (CSS, Brasão, etc.)
RUN python manage.py collectstatic --noinput

# Expõe a porta 8000
EXPOSE 8000

# Comando para iniciar o servidor Gunicorn 
# ATENÇÃO: Troque "nome_do_seu_projeto" pelo nome da pasta onde está o seu settings.py original!
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "sistema-permutas-ifba.wsgi:application"]