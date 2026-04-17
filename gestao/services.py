from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from .models import GradeHoraria, Solicitacao
from django.db import transaction
from django.conf import settings
import threading 

def verificar_choque_horario(professor, horario_alvo):
    """
    Verifica se o professor já possui aula registrada naquele exato dia e horário
    em qualquer outra turma da instituição.
    """
    choque = GradeHoraria.objects.filter(
        professor=professor, 
        horario=horario_alvo
    ).select_related('turma', 'disciplina').first()
    
    return choque

def processar_permuta(solicitante, id_aula_origem, id_aula_destino, data_aplicacao=None, carater='T'):
    from .models import GradeHoraria, Solicitacao
    aula_origem = GradeHoraria.objects.get(id=id_aula_origem)
    aula_destino = GradeHoraria.objects.get(id=id_aula_destino)
    
    # 1. Validar choque para o Solicitante assumindo o horário de destino
    choque_solicitante = verificar_choque_horario(aula_origem.professor, aula_destino.horario)
    if choque_solicitante:
        return {
            "sucesso": False, 
            "erro": f"Troca impossível: Professor {aula_origem.professor.nome_completo} já possui aula na turma {choque_solicitante.turma.nome} neste horário."
        }

    # 2. Validar choque para o Professor da aula de destino assumindo o horário de origem
    choque_destino = verificar_choque_horario(aula_destino.professor, aula_origem.horario)
    if choque_destino:
        return {
            "sucesso": False, 
            "erro": f"Troca impossível: Professor {aula_destino.professor.nome_completo} já possui aula na turma {choque_destino.turma.nome} neste horário."
        }

    # 3. Criar a solicitação pendente
    nova_solicitacao = Solicitacao.objects.create(
        tipo='P',
        status='P',
        carater=carater,               
        solicitante=solicitante,
        data_aplicacao=data_aplicacao,
        aula_origem=aula_origem,
        aula_destino=aula_destino
    )

    # 4. Enviar e-mail para a coordenação
    notificar_coordenacao(nova_solicitacao)

    return {"sucesso": True, "mensagem": "Permuta enviada para aprovação da coordenação."}

def notificar_coordenacao(solicitacao):
    assunto = f"Nova Solicitação de {solicitacao.get_tipo_display()} pendente de aprovação"
    mensagem = f"O professor {solicitacao.solicitante} solicitou uma alteração na grade.\nAcesse o painel do gestor para aprovar ou rejeitar."
    
    send_mail(
        subject=assunto,
        message=mensagem,
        from_email='informatica.euc@ifba.edu.br',
        recipient_list=['informatica.euc@ifba.edu.br'],
        fail_silently=False,
    )
def notificar_ausencia(solicitacao):
    assunto = f"Nova Solicitação de {solicitacao.get_tipo_display()} pendente de aprovação"
    mensagem = f"O professor {solicitacao.solicitante} informou que irá se ausentar, no horario {solicitacao.data_aplicacao}, {solicitacao.aula_origem}"
    
    send_mail(
        subject=assunto,
        message=mensagem,
        from_email='informatica.euc@ifba.edu.br',
        recipient_list=['informatica.euc@ifba.edu.br'],
        fail_silently=False,
    )

def processar_acao_modal(solicitante, id_aula, acao, id_prof_sub=None, id_disc_sub=None, data_aplicacao=None, id_horario=None, id_turma=None, carater='T'):
    from .models import Professor, Disciplina, Solicitacao, GradeHoraria, Turma, Horario
    
    # 1. LIMPEZA DE DADOS: Transforma strings vazias ou "None" do JavaScript em Nulo do Python
    if id_aula == '' or id_aula == 'None': id_aula = None
    if id_horario == '' or id_horario == 'None': id_horario = None
    if id_turma == '' or id_turma == 'None': id_turma = None

    # 2. BUSCA OU CRIAÇÃO DA AULA
    if id_aula:
        aula = GradeHoraria.objects.get(id=id_aula)
    else:
        # Se não há ID de horário, significa que a coordenação não cadastrou esse bloco no Admin
        if not id_horario:
            return {"sucesso": False, "erro": "Este bloco de horário (Dia/Hora) ainda não foi criado no painel Admin. A coordenação precisa cadastrá-lo antes de receber aulas."}
        
        turma = Turma.objects.get(id=id_turma)
        horario = Horario.objects.get(id=id_horario)
        # Cria a casca da aula vazia no banco
        aula, created = GradeHoraria.objects.get_or_create(turma=turma, horario=horario)

    # 3. LÓGICA DE AÇÃO
    if acao == 'liberar':
        with transaction.atomic():
            aula.professor = None
            aula.disciplina = None
            aula.save()

            Solicitacao.objects.create(
                tipo='L', status='A', solicitante=solicitante,
                aula_origem=aula, data_aplicacao=data_aplicacao
            )
        return {"sucesso": True, "mensagem": "Ausência registada! O horário está agora vago."}

    elif acao == 'assumir' or acao == 'substituir':
        prof_entrada = Professor.objects.get(id=id_prof_sub) if id_prof_sub else solicitante
        disc_entrada = Disciplina.objects.get(id=id_disc_sub)

        choque = verificar_choque_horario(prof_entrada, aula.horario)
        if choque:
            return {"sucesso": False, "erro": f"Choque de horário: O Prof. {prof_entrada.nome_completo} já tem aula na turma {choque.turma.nome}."}

        tipo_solicitacao = 'A' if acao == 'assumir' else 'S'
        
        Solicitacao.objects.create(
            tipo=tipo_solicitacao,
            status='P', # Pendente
            carater=carater, # SALVANDO A ESCOLHA (T ou D)
            solicitante=solicitante,
            aula_origem=aula,
            data_aplicacao=data_aplicacao,
            professor_substituto=prof_entrada,
            disciplina_substituta=disc_entrada
        )
        if acao == 'assumir':
            notificar_coordenacao_assuncao(solicitante, aula, data_aplicacao)
        return {"sucesso": True, "mensagem": "Pedido enviado para a coordenação com sucesso!"}

    return {"sucesso": False, "erro": "Ação inválida solicitada ao servidor."}


def gerar_grade_vazia_para_turma(turma_id):
    """
    LIMPEZA TOTAL: Apaga a grade atual da turma e gera uma nova 
    baseada estritamente nos horários permitidos no Admin.
    """
    from .models import Turma, GradeHoraria
    
    try:
        with transaction.atomic():
            turma = Turma.objects.get(id=turma_id)
            horarios_da_turma = turma.horarios_permitidos.all()
            
            if not horarios_da_turma.exists():
                return {
                    "sucesso": False, 
                    "erro": f"A turma {turma.nome} não possui horários permitidos vinculados no Admin."
                }

            # PASSO 1: Limpeza Radical
            # Remove todos os registros da grade para esta turma
            GradeHoraria.objects.filter(turma=turma).delete()

            # PASSO 2: Reconstrução
            slots_criados = 0
            for horario in horarios_da_turma:
                # Criamos registros 'limpos' (professor e disciplina nulos)
                GradeHoraria.objects.create(
                    turma=turma,
                    horario=horario,
                    professor=None,
                    disciplina=None
                )
                slots_criados += 1
                
            return {
                "sucesso": True, 
                "mensagem": f"Grade reiniciada! {slots_criados} novos horários vazios foram gerados para {turma.nome}."
            }
            
    except Exception as e:
        return {"sucesso": False, "erro": f"Erro crítico na reinicialização: {str(e)}"}

        from django.core.mail import send_mail
from django.conf import settings

from django.core.mail import send_mail
from django.conf import settings
import threading # <-- Importe a biblioteca de threads do Python

def enviar_email_em_segundo_plano(assunto, mensagem, destinatarios):
    """ Função operária que entrega o email sem travar o sistema. """
    try:
        send_mail(
            assunto,
            mensagem,
            settings.DEFAULT_FROM_EMAIL,
            destinatarios,
            fail_silently=True, # Silently=True impede que a tela quebre se o email falhar
        )
    except Exception as e:
        print(f"Erro na Thread de Email: {e}")

def notificar_coordenacao_assuncao(professor, aula, data_aplicacao):
    """ Prepara o texto e despacha para a função operária. """
    
    assunto = f"🔔 Novo Horário Assumido: {professor.nome_completo}"
    
    mensagem = f"""
    Olá, Coordenação.
    
    O professor {professor.nome_completo} assumiu um horário que estava vago no sistema.
    
    Detalhes da Ocorrência:
    - Disciplina: {aula.disciplina.nome if aula.disciplina else 'Não informada'}
    - Turma: {aula.turma.nome}
    - Data: {data_aplicacao}
    
    A alteração já foi registada como 'Pendente' e aguarda a sua aprovação no painel.
    """
    
    destinatarios = ['informatica.euc@ifba.edu.br'] 
    
    # EM VEZ DE ENVIAR DIRETO, PASSAMOS PARA A THREAD
    thread_email = threading.Thread(
        target=enviar_email_em_segundo_plano, 
        args=(assunto, mensagem, destinatarios)
    )
    thread_email.start() # Libera o operário para ir entregar e não espera ele voltar