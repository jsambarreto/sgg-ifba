# Especificamos o 'bookworm', que é a versão mais recente e segura do Debian para o Python
FROM python:3.12-slim

# Força a atualização de segurança do Linux interno antes de qualquer outra coisa
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y gcc libjpeg-dev zlib1g-dev libfreetype6-dev pkg-config libcairo2-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "core.wsgi:application"]