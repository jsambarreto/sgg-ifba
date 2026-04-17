from django import template
from django.contrib.auth.models import Group

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
    """
    Verifica se o utilizador pertence a um grupo específico.
    Uso no HTML: {% if request.user|has_group:"Coordenador" %}
    """
    if user.is_superuser:
        return True # Superusuário tem acesso a tudo
    return user.groups.filter(name=group_name).exists()

@register.filter(name='is_gestor')
def is_gestor(user):
    """ Atalho para verificar se é Coordenador ou Diretor """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=['Coordenador', 'Diretor']).exists()

