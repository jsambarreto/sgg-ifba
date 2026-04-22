from django.db import models
from django.contrib.auth.models import User

class Professor(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='professor')
    nome_completo = models.CharField(max_length=150)
    matricula = models.CharField(max_length=20, unique=True, null=True, blank=True)    
    
    # Perfis de Acesso
    is_coordenador = models.BooleanField(default=False) 
    is_diretor = models.BooleanField(default=False)

    def __str__(self):
        return self.nome_completo

class Disciplina(models.Model):
    nome = models.CharField(max_length=100)
    quantidade_aulas = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.nome} ({self.quantidade_aulas} aulas)"

class Horario(models.Model):
    TURNO_CHOICES = [('M', 'Matutino'), ('V', 'Vespertino'), ('N', 'Noturno')]
    
    DIA_CHOICES = [
        (1, 'Domingo'),
        (2, 'Segunda-feira'),
        (3, 'Terça-feira'),
        (4, 'Quarta-feira'),
        (5, 'Quinta-feira'),
        (6, 'Sexta-feira'),
        (7, 'Sábado'),
    ]

    dia_semana = models.IntegerField(choices=DIA_CHOICES)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    turno = models.CharField(max_length=1, choices=TURNO_CHOICES, default='M')

    def __str__(self):
        return f"{self.get_dia_semana_display()} - {self.hora_inicio.strftime('%H:%M')} ({self.turno})"

class Turma(models.Model):
    nome = models.CharField(max_length=100)
    horarios_permitidos = models.ManyToManyField(Horario, related_name='turmas_permitidas', blank=True)

    def __str__(self):
        return self.nome

class GradeHoraria(models.Model):
    turma = models.ForeignKey(Turma, on_delete=models.CASCADE, related_name='grade')
    horario = models.ForeignKey(Horario, on_delete=models.CASCADE)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE, null=True, blank=True)
    professor = models.ForeignKey(Professor, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = ('turma', 'horario')

class Solicitacao(models.Model):
    TIPO_CHOICES = [('P', 'Permuta'), 
                    ('S', 'Substituição Direta'), 
                    ('L', 'Liberação'), 
                    ('A', 'Assumir')]
    STATUS_CHOICES = [('P', 'Pendente'), 
                      ('A', 'Aprovada'), 
                      ('R', 'Rejeitada')]
    
    CARATER_CHOICES = [('T', 'Temporário (Apenas nesta data)'), 
                       ('D', 'Definitivo (Restante do período)')]
    carater = models.CharField(max_length=1, choices=CARATER_CHOICES, default='T')
    
    tipo = models.CharField(max_length=1, choices=TIPO_CHOICES)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='P')
    solicitante = models.ForeignKey(Professor, on_delete=models.CASCADE)
    data_criacao = models.DateTimeField(auto_now_add=True)
    
    # --- DATAS DE APLICAÇÃO E DEVOLUÇÃO (SISTEMA DE CRÉDITO) ---
    data_aplicacao = models.DateField(help_text="Data específica em que a ausência/troca inicial ocorrerá")
    data_devolucao = models.DateField(null=True, blank=True, help_text="Data em que a aula será devolvida (se já estiver combinada)")
    devolucao_pendente = models.BooleanField(default=False, help_text="Marca se o professor ficou devendo esta aula para o substituto")

    # A aula que está a ser afetada inicialmente
    aula_origem = models.ForeignKey(GradeHoraria, related_name='solicitacoes_origem', on_delete=models.CASCADE)
    
    # Para Permutas
    aula_destino = models.ForeignKey(GradeHoraria, related_name='solicitacoes_destino', null=True, blank=True, on_delete=models.CASCADE)
    
    # Para Substituições Diretas OU Assunções
    professor_substituto = models.ForeignKey(Professor, related_name='substituicoes', null=True, blank=True, on_delete=models.CASCADE)
    disciplina_substituta = models.ForeignKey(Disciplina, related_name='substituicoes_disciplina', null=True, blank=True, on_delete=models.CASCADE)

class DiaNaoLetivo(models.Model):
    data = models.DateField(unique=True, help_text="Data do feriado, recesso ou conselho de classe.")
    descricao = models.CharField(max_length=100, help_text="Ex: Feriado Nacional, Recesso Escolar, etc.")
    
    turmas_afetadas = models.ManyToManyField('Turma', blank=True, help_text="Deixe em branco para aplicar a toda a instituição.")

    def __str__(self):
        return f"{self.data.strftime('%d/%m/%Y')} - {self.descricao}"