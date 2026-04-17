from django.contrib import admin
from .models import Turma, Horario, GradeHoraria, Professor, Disciplina, Solicitacao

# Registos simples
admin.site.register(Horario)
admin.site.register(GradeHoraria)
admin.site.register(Professor)
admin.site.register(Disciplina)
admin.site.register(Solicitacao)

# Registo avançado para a Turma
@admin.register(Turma)
class TurmaAdmin(admin.ModelAdmin):
    list_display = ('nome',) # Aqui dizemos para listar apenas o nome da turma
    
    # Dica de Sênior: Isto transforma aquela caixa chata do ManyToMany 
    # numa interface muito bonita de "arrastar para o lado" no Admin!
    filter_horizontal = ('horarios_permitidos',)