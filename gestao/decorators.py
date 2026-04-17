from django.core.exceptions import PermissionDenied
from functools import wraps

def apenas_gestores(view_func):
    """ Bloqueia a página para quem não for Coordenador, Diretor ou Admin """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_superuser or request.user.groups.filter(name__in=['Coordenador', 'Diretor']).exists():
            return view_func(request, *args, **kwargs)
        # Se for professor, lança erro de acesso negado
        raise PermissionDenied("Acesso restrito à Direção e Coordenação.")
    return _wrapped_view

from django.core.exceptions import PermissionDenied

def apenas_coordenadores(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser or (hasattr(request.user, 'professor') and request.user.professor.is_coordenador):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Acesso restrito à Coordenação.")
    return wrapper