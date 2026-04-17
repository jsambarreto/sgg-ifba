from django.shortcuts import render
from django.http import JsonResponse
import json
from .models import GradeHoraria, Turma, Horario, Solicitacao, Professor, Disciplina, DiaNaoLetivo
from .services import gerar_grade_vazia_para_turma, processar_permuta, processar_acao_modal
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime, timedelta
from .decorators import apenas_coordenadores, apenas_gestores 
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.core.mail import send_mail 
from django.conf import settings       

@login_required
def exibir_grade(request):
    try:
        professor_logado = request.user.professor
    except:
        return HttpResponse("O seu utilizador não está vinculado a um perfil de Professor.")

    # Descobre qual aba o professor clicou (padrão é 'pessoal')
    aba_ativa = request.GET.get('aba', 'pessoal')
    turma_selecionada_id = request.GET.get('turma')

    grade_pessoal_map = {}
    grade_turma_map = {}
    turma_selecionada = None

    # --- ABA 1: MINHA GRADE (Todas as minhas aulas) ---
    aulas_do_prof = GradeHoraria.objects.filter(professor=professor_logado).select_related('turma', 'disciplina', 'horario')
    for aula in aulas_do_prof:
        chave = f"{aula.horario.dia_semana}-{aula.horario.hora_inicio.strftime('%H:%M')}"
        grade_pessoal_map[chave] = {
            'id': aula.id,
            'turma': aula.turma.nome,
            'disciplina': aula.disciplina.nome if aula.disciplina else "---",
        }

    # --- ABA 2: GRADE DA TURMA (Visão geral para permutas) ---
    # Busca apenas as turmas onde este professor dá aula para preencher o dropdown
    turmas_do_prof = Turma.objects.filter(grade__professor=professor_logado).distinct().order_by('nome')
    
    if aba_ativa == 'turma' and turma_selecionada_id:
        turma_selecionada = Turma.objects.filter(id=turma_selecionada_id).first()
        if turma_selecionada:
            aulas_da_turma = GradeHoraria.objects.filter(turma=turma_selecionada).select_related('professor', 'disciplina', 'horario')
            for aula in aulas_da_turma:
                chave = f"{aula.horario.dia_semana}-{aula.horario.hora_inicio.strftime('%H:%M')}"
                grade_turma_map[chave] = {
                    'id': aula.id,
                    'professor': aula.professor.nome_completo if aula.professor else "Sem Prof.",
                    'disciplina': aula.disciplina.nome if aula.disciplina else "---",
                    # Flag para pintar de cor diferente a aula que é dele
                    'is_minha_aula': aula.professor == professor_logado 
                }

    # Horários da tabela
    horarios_unicos = Horario.objects.all().order_by('hora_inicio').values_list('hora_inicio', flat=True).distinct()
    slots_horarios = [h.strftime('%H:%M') for h in horarios_unicos]

    contexto = {
        'aba_ativa': aba_ativa,
        'turmas_do_prof': turmas_do_prof,
        'turma_selecionada': turma_selecionada,
        'grade_pessoal_map': grade_pessoal_map,
        'grade_turma_map': grade_turma_map,
        'dias_semana': [2, 3, 4, 5, 6],
        'slots_horarios': slots_horarios,
        'professor': professor_logado
    }
    
    return render(request, 'gestao/grade.html', contexto)
    

def api_solicitar_permuta(request):
    if request.method == 'POST':
        try:
            # Lê os dados enviados pelo JavaScript
            dados = json.loads(request.body)
            origem_id = dados.get('aula_origem_id')
            destino_id = dados.get('aula_destino_id')
            data_aplicacao = dados.get('data_aplicacao')

            from datetime import datetime
            data_app = dados.get('data_aplicacao', datetime.now().strftime('%Y-%m-%d'))
            carater = dados.get('carater', 'T')

            # O usuário logado que está fazendo a solicitação (precisa estar logado como professor/gestor)
            # Para testes rápidos no painel admin, vamos usar o professor associado ao usuário logado
            # Em vez de: solicitante = request.user.professor

            solicitante = getattr(request.user, 'professor', None)

            if not solicitante:
                return JsonResponse({
                    'sucesso': False, 
                    'erro': 'O seu utilizador não está vinculado a um perfil de Professor no sistema.'
                })

            resultado = processar_permuta(
                solicitante=request.user.professor,
                id_aula_origem=dados.get('aula_origem_id'),   # <-- Ajustado
                id_aula_destino=dados.get('aula_destino_id'), # <-- Ajustado
                data_aplicacao=data_app,
                carater=carater
            )

            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})
    
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido'})

@login_required
@apenas_coordenadores
def painel_aprovacoes(request):
    """ Exibe a tela para o Coordenador ver as solicitações pendentes """
    # Busca todas as solicitações com status 'P' (Pendente)
    solicitacoes = Solicitacao.objects.filter(status='P').select_related(
        'solicitante', 'aula_origem__disciplina', 'aula_destino__disciplina'
    ).order_by('-data_criacao')
    
    return render(request, 'gestao/aprovacoes.html', {'solicitacoes': solicitacoes})

def api_processar_aprovacao(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            solicitacao = get_object_or_404(Solicitacao, id=dados.get('solicitacao_id'))
            acao = dados.get('acao')

            # Dentro de api_processar_aprovacao
            if acao == 'aprovar':
                print(f"DEBUG: Aprovando pedido {solicitacao.id} - Carater: {solicitacao.carater}")
                
                with transaction.atomic():
                    if solicitacao.carater == 'D':
                        print("DEBUG: Entrou na lógica de alteração DEFINITIVA da grade base.")
                        aula_origem = solicitacao.aula_origem
                        
                        if solicitacao.tipo == 'P': # Permuta
                            aula_destino = solicitacao.aula_destino
                            # Troca os dados
                            prof_orig, disc_orig = aula_origem.professor, aula_origem.disciplina
                            aula_origem.professor = aula_destino.professor
                            aula_origem.disciplina = aula_destino.disciplina
                            aula_destino.professor = prof_orig
                            aula_destino.disciplina = disc_orig
                            aula_destino.save()
                        else: # Substituição ou Assunção
                            aula_origem.professor = solicitacao.professor_substituto
                            aula_origem.disciplina = solicitacao.disciplina_substituta
                        
                        aula_origem.save()
                        print(f"DEBUG: GradeHoraria ID {aula_origem.id} atualizada com sucesso.")
                    
                    else:
                        # SE FOR TEMPORÁRIO: Nós NÃO tocamos na aula_origem nem aula_destino.
                        # O fato de a solicitação passar para status='A' já a torna uma exceção válida para o relatório e para a data específica.
                        mensagem = f"Alteração TEMPORÁRIA para o dia {solicitacao.data_aplicacao.strftime('%d/%m/%Y')} aprovada com sucesso!"

                    # Para ambos os casos, a solicitação fica aprovada
                    solicitacao.status = 'A'
                    solicitacao.save()
                    mensagem = "Alteração oficializada com sucesso!"

            elif acao == 'rejeitar':
                solicitacao.status = 'R'
                solicitacao.save()
                mensagem = "Solicitação rejeitada."

            return JsonResponse({'sucesso': True, 'mensagem': mensagem})
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

def api_acao_modal(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            solicitante = getattr(request.user, 'professor', None)
            if not solicitante:
                return JsonResponse({'sucesso': False, 'erro': 'Usuário sem perfil de professor.'})

            resultado = processar_acao_modal(
                solicitante=solicitante,
                id_aula=dados.get('aula_id'),
                acao=dados.get('acao'),
                id_prof_sub=dados.get('prof_id'),
                id_disc_sub=dados.get('disc_id'),
                data_aplicacao=dados.get('data_aplicacao', '2026-03-20'),
                id_horario=dados.get('horario_id'),
                id_turma=dados.get('turma_id'),
                carater=dados.get('carater')
            )
            return JsonResponse(resultado)
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})

@login_required
@apenas_coordenadores       
def api_gerar_grade_vazia(request):
    """ View que recebe o comando do botão HTML para rodar o script """
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            turma_id = dados.get('turma_id')
            
            if not turma_id:
                return JsonResponse({'sucesso': False, 'erro': 'ID da turma não fornecido.'})
                
            # Roda o nosso script
            resultado = gerar_grade_vazia_para_turma(turma_id)
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})
            
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
@apenas_gestores
def construtor_grade(request):
    turmas = Turma.objects.all().order_by('nome')
    turma_id = request.GET.get('turma')
    
    turma_selecionada = None
    slots_horarios = []
    grade_map = {}
    horarios_ids = {}

    if turma_id:
        turma_selecionada = Turma.objects.filter(id=turma_id).first()
        if turma_selecionada:
            # Pegamos os horários permitidos para esta turma
            h_permitidos = turma_selecionada.horarios_permitidos.all().order_by('hora_inicio')
            
            # Criamos a lista de horários (linhas da tabela)
            slots_horarios = sorted(list(set(h.hora_inicio.strftime('%H:%M') for h in h_permitidos)))
            
            # Mapeamos IDs para o JavaScript: "Dia-Hora" -> ID do Horário
            for h in h_permitidos:
                horarios_ids[f"{h.dia_semana}-{h.hora_inicio.strftime('%H:%M')}"] = h.id

            # Carregamos o que já existe na GradeHoraria
            grade = GradeHoraria.objects.filter(turma=turma_selecionada).select_related('professor', 'disciplina', 'horario')
            for item in grade:
                chave = f"{item.horario.dia_semana}-{item.horario.hora_inicio.strftime('%H:%M')}"
                grade_map[chave] = {
                    'prof': item.professor.nome_completo if item.professor else "---",
                    'disc': item.disciplina.nome if item.disciplina else "---"
                }

    return render(request, 'gestao/construtor.html', {
        'turmas': turmas,
        'turma_selecionada': turma_selecionada,
        'slots_horarios': slots_horarios,
        'dias_semana': [2, 3, 4, 5, 6], # Segunda a Sexta conforme seu DIA_CHOICES
        'grade_map': grade_map,
        'horarios_ids_json': json.dumps(horarios_ids),
        'professores': Professor.objects.all().order_by('nome_completo'),
        'disciplinas': Disciplina.objects.all().order_by('nome'),
    })

@login_required
@apenas_gestores
def api_salvar_aula_base(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            # Usamos update_or_create para garantir que não haja duplicatas (unique_together do seu model)
            GradeHoraria.objects.update_or_create(
                turma_id=dados.get('turma_id'),
                horario_id=dados.get('horario_id'),
                defaults={
                    'professor_id': dados.get('professor_id'),
                    'disciplina_id': dados.get('disciplina_id')
                }
            )
            return JsonResponse({"sucesso": True})
        except Exception as e:
            return JsonResponse({"sucesso": False, "erro": str(e)}, status=500)
    return JsonResponse({"sucesso": False}, status=405)

@login_required
def relatorio_carga_horaria(request):
    # 1. Proteção Dupla: Só entra se for Admin da TI ou Diretor
    if not (request.user.is_superuser or (hasattr(request.user, 'professor') and request.user.professor.is_diretor)):
        raise PermissionDenied("Acesso restrito à Direção do Campus.")

    # 2. A Mágica do Django (Contagem Rápida)
    # Pega todos os professores e conta quantos "quadradinhos" de gradehoraria eles têm
    professores = Professor.objects.annotate(
        total_aulas=Count('gradehoraria')
    ).order_by('-total_aulas') # O sinal de menos (-) ordena do maior para o menor

    return render(request, 'gestao/relatorio_carga.html', {'professores': professores})

@login_required
def pagina_inicial(request):
    """
    Dashboard principal. Renderiza atalhos dependendo do perfil do usuário.
    """
    return render(request, 'gestao/index.html')

from .models import Solicitacao # Confirme se está importado no topo

@login_required
def minhas_solicitacoes(request):
    """
    Tela onde o professor comum vê o status dos pedidos que ele fez.
    """
    # Se o login for o Admin e ele não tiver um "professor" associado, evitamos o erro
    if hasattr(request.user, 'professor'):
        solicitacoes = Solicitacao.objects.filter(solicitante=request.user.professor).order_by('-data_criacao')
    else:
        solicitacoes = []
        
    return render(request, 'gestao/minhas_solicitacoes.html', {'solicitacoes': solicitacoes})

from django.core.mail import send_mail
from django.http import HttpResponse

def teste_email(request):
    try:
        # Estrutura: Assunto, Mensagem, Remetente, [Lista de Destinatários]
        send_mail(
            '🚀 Sucesso! Sistema SGG IFBA Conectado',
            'Olá! Se você está lendo esta mensagem, significa que a sua Senha de Aplicativo funcionou perfeitamente.\n\nO servidor SMTP do Django está online e o sistema de gestão de grades já pode notificar a coordenação e os professores automaticamente!',
            None, # Deixe None para ele usar o DEFAULT_FROM_EMAIL do settings.py
            ['informatica.euc@ifba.edu.br'], # <-- COLOQUE O SEU EMAIL AQUI
            fail_silently=False,
        )
        return HttpResponse("""
            <div style='font-family: sans-serif; text-align: center; margin-top: 50px;'>
                <h1 style='color: #2ecc71;'>✔️ Email enviado com sucesso!</h1>
                <p>Abra a sua caixa de entrada (ou pasta de spam) para verificar.</p>
                <a href='/' style='text-decoration: none; background: #3498db; color: white; padding: 10px 20px; border-radius: 5px;'>Voltar ao Sistema</a>
            </div>
        """)
    except Exception as e:
        return HttpResponse(f"""
            <div style='font-family: sans-serif; text-align: center; margin-top: 50px;'>
                <h1 style='color: #e74c3c;'>❌ Erro ao enviar email</h1>
                <p>O servidor retornou o seguinte erro:</p>
                <code style='background: #eee; padding: 10px; display: block; max-width: 600px; margin: auto;'>{str(e)}</code>
            </div>
        """)

from django.db.models import Q # Adicione este import no topo se não o tiver

@login_required
def gerar_pdf_sei(request, id):
    # 1. Pega a solicitação em que o utilizador clicou
    solicitacao_base = get_object_or_404(Solicitacao, id=id)
    
    if solicitacao_base.status != 'A':
        return HttpResponse("Apenas solicitações APROVADAS podem gerar o formulário do SEI.", status=403)

    # 2. A MÁGICA: Puxa TODAS as solicitações do mesmo professor feitas no MESMO DIA
    data_do_pedido = solicitacao_base.data_criacao.date()
    
    solicitacoes_do_lote = Solicitacao.objects.filter(
        solicitante=solicitacao_base.solicitante,
        data_criacao__date=data_do_pedido,
        status='A'
    ).order_by('data_aplicacao') # Ordena por data da aula

    # 3. Organiza os dados para o PDF
    substitutos_unicos = set()
    tem_permuta = False
    cursos_envolvidos = set()

    for sol in solicitacoes_do_lote:
        cursos_envolvidos.add(sol.aula_origem.turma.nome)
        if sol.tipo == 'P' and sol.aula_destino:
            tem_permuta = True
            substitutos_unicos.add(sol.aula_destino.professor)
        elif sol.professor_substituto:
            substitutos_unicos.add(sol.professor_substituto)

    context = {
        'solicitante': solicitacao_base.solicitante,
        'data_criacao': data_do_pedido,
        'cursos': list(cursos_envolvidos),
        'solicitacoes': solicitacoes_do_lote,
        'tem_permuta': tem_permuta,
        'substitutos': list(substitutos_unicos),
    }

    # 4. Geração do PDF
    template_path = 'gestao/pdf_sei.html'
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="SEI_Permutas_{data_do_pedido.strftime("%Y%m%d")}.pdf"'

    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('Tivemos erros ao gerar o PDF: <pre>' + html + '</pre>')
    
    return response

from django.shortcuts import get_object_or_404, redirect

from django.core.mail import send_mail
from django.conf import settings

@login_required
def nova_solicitacao(request, aula_id, tipo):
    # 1. Identifica a aula e o professor
    aula_origem = get_object_or_404(GradeHoraria, id=aula_id)
    professor_logado = request.user.professor
    
    # CORREÇÃO: Definimos o nome_tipo aqui no topo para todo o código poder usar!
    nome_tipo = 'Permuta' if tipo == 'P' else 'Substituição'

    if request.method == 'POST':
        data_aplicacao = request.POST.get('data_aplicacao')
        carater = request.POST.get('carater', 'T') 
        
        # Cria a base da solicitação
        nova_sol = Solicitacao(
            solicitante=professor_logado,
            tipo=tipo,
            aula_origem=aula_origem,
            data_aplicacao=data_aplicacao,
            carater=carater,
            status='P'
        )

        if tipo == 'P': 
            aula_destino_id = request.POST.get('aula_destino')
            nova_sol.aula_destino = get_object_or_404(GradeHoraria, id=aula_destino_id)
        elif tipo == 'S': 
            prof_sub_id = request.POST.get('prof_substituto')
            nova_sol.professor_substituto = get_object_or_404(Professor, id=prof_sub_id)
            nova_sol.disciplina_substituta = aula_origem.disciplina

        nova_sol.save()
        
        # ========================================================
        # INÍCIO DO ALERTA POR E-MAIL (Apenas para Coordenação)
        # ========================================================
        try:
            assunto = f"⏳ Novo Pedido de {nome_tipo} - {professor_logado.nome_completo}"
            
            mensagem = f"""Olá, Coordenação.

Um novo pedido de {nome_tipo} foi submetido no Sistema de Gestão de Grades (SGG) e aguarda a sua análise.

👨‍🏫 Professor: {professor_logado.nome_completo}
📚 Disciplina: {aula_origem.disciplina.nome}
🏫 Turma: {aula_origem.turma.nome}
📅 Data da Ausência: {data_aplicacao}

Por favor, acesse o painel de aprovações do sistema para verificar os detalhes e emitir o parecer oficial.

Atenciosamente,
SGG IFBA"""

            # Lembre-se de colocar o e-mail de teste aqui
            destinatarios = ['informatica.euc@ifba.edu.br']

            send_mail(
                assunto,
                mensagem,
                settings.DEFAULT_FROM_EMAIL,
                destinatarios,
                fail_silently=True, 
            )
        except Exception as e:
            print(f"Aviso: Erro ao enviar e-mail para a coordenação: {e}")
            
        # ========================================================
        
        return redirect('minhas_solicitacoes')

    # Se for GET (Abertura da página)
    contexto = {
        'aula_origem': aula_origem,
        'tipo': tipo,
        'nome_tipo': nome_tipo, # Usa a variável que criámos lá no topo
    }
    
    if tipo == 'P':
        contexto['opcoes_destino'] = GradeHoraria.objects.exclude(professor=professor_logado).select_related('professor', 'disciplina', 'turma', 'horario')
    elif tipo == 'S':
        contexto['professores'] = Professor.objects.exclude(id=professor_logado.id).order_by('nome_completo')

    return render(request, 'gestao/form_solicitacao.html', contexto)

    # Se for GET (apenas a abrir a página), preparamos as listas para os dropdowns
    contexto = {
        'aula_origem': aula_origem,
        'tipo': tipo,
        'nome_tipo': 'Permuta' if tipo == 'P' else 'Substituição',
    }
    
    if tipo == 'P':
        # Lista as aulas de OUTROS professores para ele escolher com quem trocar
        contexto['opcoes_destino'] = GradeHoraria.objects.exclude(professor=professor_logado).select_related('professor', 'disciplina', 'turma', 'horario')
    elif tipo == 'S':
        # Lista os OUTROS professores para ele escolher quem vai substituí-lo
        contexto['professores'] = Professor.objects.exclude(id=professor_logado.id).order_by('nome_completo')

    return render(request, 'gestao/form_solicitacao.html', contexto)