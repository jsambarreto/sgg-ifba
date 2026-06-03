from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
import json
from .models import GradeHoraria, Turma, Horario, Solicitacao, Professor, Disciplina, DiaNaoLetivo
from .services import gerar_grade_vazia_para_turma, processar_permuta, processar_acao_modal
from django.db import transaction
from datetime import datetime, timedelta, date
from .decorators import apenas_coordenadores, apenas_gestores, apenas_diretores
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
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

    aba_ativa = request.GET.get('aba', 'pessoal')
    turma_selecionada_id = request.GET.get('turma')

    # ==========================================
    # LÓGICA DE NAVEGAÇÃO POR SEMANAS
    # ==========================================
    data_str = request.GET.get('data')
    if data_str:
        try:
            data_foco = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data_foco = date.today()
    else:
        data_foco = date.today()

    # Calcula o início (Segunda) e fim (Domingo) da semana selecionada
    dia_semana_num = data_foco.weekday() # 0 = Segunda, 6 = Domingo
    inicio_semana = data_foco - timedelta(days=dia_semana_num)
    fim_semana = inicio_semana + timedelta(days=6)

    # Strings para os botões de navegação no HTML
    semana_anterior = (inicio_semana - timedelta(days=7)).strftime('%Y-%m-%d')
    proxima_semana = (inicio_semana + timedelta(days=7)).strftime('%Y-%m-%d')

    grade_pessoal_map = {}
    grade_turma_map = {}
    turma_selecionada = None

    # ==========================================
    # ABA 1: MINHA GRADE (Com sobreposição)
    # ==========================================
    aulas_do_prof = GradeHoraria.objects.filter(professores=professor_logado).select_related('turma', 'disciplina', 'horario')
    
    for aula in aulas_do_prof:
        chave = f"{aula.horario.dia_semana}-{aula.horario.hora_inicio.strftime('%H:%M')}"
        grade_pessoal_map[chave] = {
            'id': aula.id,
            'turma': aula.turma.nome,
            'disciplina': aula.disciplina.nome if aula.disciplina else "---",
            'info_extra': '', 
            'cor': ''         
        }

    # Sobrepõe Aulas APENAS SE ACONTECEREM NESTA SEMANA
    saidas = Solicitacao.objects.filter(solicitante=professor_logado, status='A', data_aplicacao__range=[inicio_semana, fim_semana])
    for sol in saidas:
        chave = f"{sol.aula_origem.horario.dia_semana}-{sol.aula_origem.horario.hora_inicio.strftime('%H:%M')}"
        if chave in grade_pessoal_map:
            data_formatada = sol.data_aplicacao.strftime('%d/%m')
            if sol.tipo == 'L':
                grade_pessoal_map[chave]['info_extra'] = f"Ausente em {data_formatada}"
                grade_pessoal_map[chave]['cor'] = '#ffcccc' 
            elif sol.tipo == 'S':
                nome_sub = sol.professor_substituto.nome_completo.split()[0] if sol.professor_substituto else 'Alguém'
                grade_pessoal_map[chave]['info_extra'] = f"Subst. por {nome_sub}"
                grade_pessoal_map[chave]['cor'] = '#ffeeba' 
            elif sol.tipo == 'P' and sol.aula_destino:
                nome_perm = sol.aula_destino.nomes_professores
                grade_pessoal_map[chave]['info_extra'] = f"Permuta c/ {nome_perm}"
                grade_pessoal_map[chave]['cor'] = '#d1ecf1' 

    entradas_sub = Solicitacao.objects.filter(professor_substituto=professor_logado, status='A', data_aplicacao__range=[inicio_semana, fim_semana], tipo='S')
    for sol in entries_sub:
        chave = f"{sol.aula_origem.horario.dia_semana}-{sol.aula_origem.horario.hora_inicio.strftime('%H:%M')}"
        grade_pessoal_map[chave] = {
            'id': sol.aula_origem.id,
            'turma': sol.aula_origem.turma.nome,
            'disciplina': sol.disciplina_substituta.nome if sol.disciplina_substituta else sol.aula_origem.disciplina.nome,
            'info_extra': f"Cobrindo {sol.solicitante.nome_completo.split()[0]}",
            'cor': '#d4edda' 
        }
        
    entradas_perm = Solicitacao.objects.filter(aula_destino__professores=professor_logado, status='A', data_aplicacao__range=[inicio_semana, fim_semana], tipo='P')
    for sol in entries_perm:
        chave = f"{sol.aula_destino.horario.dia_semana}-{sol.aula_destino.horario.hora_inicio.strftime('%H:%M')}"
        grade_pessoal_map[chave] = {
            'id': sol.aula_destino.id,
            'turma': sol.aula_origem.turma.nome, 
            'disciplina': sol.aula_origem.disciplina.nome,
            'info_extra': f"Cobrindo {sol.solicitante.nome_completo.split()[0]}",
            'cor': '#d4edda' 
        }

    # ==========================================
    # ABA 2: GRADE DA TURMA (Com sobreposição)
    # ==========================================
    turmas_do_prof = Turma.objects.filter(grade__professores=professor_logado).distinct().order_by('nome')
    
    if aba_ativa == 'turma' and turma_selecionada_id:
        turma_selecionada = Turma.objects.filter(id=turma_selecionada_id).first()
        if turma_selecionada:
            aulas_da_turma = GradeHoraria.objects.filter(turma=turma_selecionada).select_related('disciplina', 'horario').prefetch_related('professores')
            
            for aula in aulas_da_turma:
                chave = f"{aula.horario.dia_semana}-{aula.horario.hora_inicio.strftime('%H:%M')}"
                grade_turma_map[chave] = {
                    'id': aula.id,
                    'professor': aula.nomes_professores,
                    'disciplina': aula.disciplina.nome if aula.disciplina else "---",
                    'is_minha_aula': professor_logado in aula.professores.all(),
                    'info_extra': '',
                    'cor': ''
                }
                
            trocas_turma = Solicitacao.objects.filter(aula_origem__turma=turma_selecionada, status='A', data_aplicacao__range=[inicio_semana, fim_semana])
            for sol in trocas_turma:
                chave = f"{sol.aula_origem.horario.dia_semana}-{sol.aula_origem.horario.hora_inicio.strftime('%H:%M')}"
                if chave in grade_turma_map:
                    if sol.tipo == 'L':
                        grade_turma_map[chave]['info_extra'] = f"Faltará dia {sol.data_aplicacao.strftime('%d/%m')}"
                        grade_turma_map[chave]['cor'] = '#ffcccc'
                    elif sol.tipo == 'S' or sol.tipo == 'P':
                        prof_novo = sol.professor_substituto if sol.tipo == 'S' else (sol.aula_destino.professores.first() if sol.aula_destino else None)
                        nome_novo = prof_novo.nome_completo.split()[0] if prof_novo else 'Alguém'
                        grade_turma_map[chave]['professor'] = f"{nome_novo} (Subst.)"
                        grade_turma_map[chave]['info_extra'] = f"Cobrindo {sol.solicitante.nome_completo.split()[0]}"
                        grade_turma_map[chave]['cor'] = '#ffeeba'

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
        'professor': professor_logado,
        'inicio_semana': inicio_semana,
        'fim_semana': fim_semana,
        'semana_anterior': semana_anterior,
        'proxima_semana': proxima_semana,
    }
    
    return render(request, 'gestao/grade.html', contexto)

def api_solicitar_permuta(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            data_app = dados.get('data_aplicacao', datetime.now().strftime('%Y-%m-%d'))
            carater = dados.get('carater', 'T')

            solicitante = getattr(request.user, 'professor', None)

            if not solicitante:
                return JsonResponse({
                    'sucesso': False, 
                    'erro': 'O seu utilizador não está vinculado a um perfil de Professor no sistema.'
                })

            resultado = processar_permuta(
                solicitante=request.user.professor,
                id_aula_origem=dados.get('aula_origem_id'),   
                id_aula_destino=dados.get('aula_destino_id'), 
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

            if acao == 'aprovar':
                with transaction.atomic():
                    if solicitacao.carater == 'D':
                        aula_origem = solicitacao.aula_origem
                        if solicitacao.tipo == 'P': 
                            aula_destino = solicitacao.aula_destino
                            professores_orig = list(aula_origem.professores.all())
                            professores_dest = list(aula_destino.professores.all())
                            disc_orig = aula_origem.disciplina
                            
                            aula_origem.professores.set(professores_dest)
                            aula_origem.disciplina = aula_destino.disciplina
                            
                            aula_destino.professores.set(professores_orig)
                            aula_destino.disciplina = disc_orig
                            aula_destino.save()
                        else: 
                            aula_origem.professores.set([solicitacao.professor_substituto])
                            aula_origem.disciplina = solicitacao.disciplina_substituta
                        
                        aula_origem.save()

                    solicitacao.status = 'A'
                    solicitacao.save()
                    mensagem = "Alteração oficializada com sucesso!"

            elif acao == 'rejeitar':
                solicitacao.status = 'R'
                solicitacao.save()
                mensagem = "Solicitação rejeitada."

            return JsonResponse({'sucesso': True, 'mensagem': message})
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
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            turma_id = dados.get('turma_id')
            
            if not turma_id:
                return JsonResponse({'sucesso': False, 'erro': 'ID da turma não fornecido.'})
                
            resultado = gerar_grade_vazia_para_turma(turma_id)
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})
            
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
@apenas_coordenadores 
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
            h_permitidos = turma_selecionada.horarios_permitidos.all().order_by('hora_inicio')
            slots_horarios = sorted(list(set(h.hora_inicio.strftime('%H:%M') for h in h_permitidos)))
            for h in h_permitidos:
                horarios_ids[f"{h.dia_semana}-{h.hora_inicio.strftime('%H:%M')}"] = h.id

            grade = GradeHoraria.objects.filter(turma=turma_selecionada).select_related('disciplina', 'horario').prefetch_related('professores')
            for item in grade:
                chave = f"{item.horario.dia_semana}-{item.horario.hora_inicio.strftime('%H:%M')}"
                grade_map[chave] = {
                    'disciplina_id': item.disciplina.id if item.disciplina else '',
                    'disc': item.disciplina.nome if item.disciplina else "---",
                    # Array com os IDs dos professores para marcar no modal
                    'professores_ids': [p.id for p in item.professores.all()],
                    # String pronta para exibição "Jorge / Aline"
                    'professores_str': item.nomes_professores 
                }

    return render(request, 'gestao/construtor.html', {
        'turmas': turmas,
        'turma_selecionada': turma_selecionada,
        'slots_horarios': slots_horarios,
        'dias_semana': [2, 3, 4, 5, 6], 
        'grade_map': grade_map,
        'horarios_ids_json': json.dumps(horarios_ids),
        'professores': Professor.objects.all().order_by('nome_completo'),
        'disciplinas': Disciplina.objects.all().order_by('nome'),
    })

@login_required
@apenas_gestores
@apenas_coordenadores 
def api_salvar_aula_base(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            turma_id = dados.get('turma_id')
            horario_id = dados.get('horario_id')
            excluir = dados.get('excluir', False)
            disc_id = dados.get('disciplina_id') or None

            # INTELIGÊNCIA DE REMOÇÃO: Se for comando explícito ou arrastado sem destino (limpeza automática)
            if excluir or not disc_id:
                GradeHoraria.objects.filter(turma_id=turma_id, horario_id=horario_id).delete()
                return JsonResponse({"sucesso": True, "removido": True})

            aula, created = GradeHoraria.objects.update_or_create(
                turma_id=turma_id,
                horario_id=horario_id,
                defaults={'disciplina_id': disc_id}
            )
            prof_ids = dados.get('professores_ids', [])
            if prof_ids:
                aula.professores.set(prof_ids)
            else:
                aula.professores.clear()
                
            return JsonResponse({"sucesso": True})
        except Exception as e:
            return JsonResponse({"sucesso": False, "erro": str(e)}, status=500)
    return JsonResponse({"sucesso": False}, status=405)

@login_required
def relatorio_carga_horaria(request):
    if not (request.user.is_superuser or (hasattr(request.user, 'professor') and request.user.professor.is_diretor)):
        raise PermissionDenied("Acesso restrito à Direção do Campus.")

    professores = Professor.objects.annotate(
        total_aulas=Count('grades_horarias')
    ).order_by('-total_aulas') 

    return render(request, 'gestao/relatorio_carga.html', {'professores': professores})

@login_required
def pagina_inicial(request):
    """
    Dashboard principal. Renderiza atalhos e agora o BANCO DE AULAS (Créditos e Dívidas).
    """
    prof = getattr(request.user, 'professor', None)
    dividas = []
    creditos = []
    
    if prof:
        # Aulas que eu pedi substituição "A Combinar" e ainda não devolvi
        dividas = Solicitacao.objects.filter(
            solicitante=prof, status='A', devolucao_pendente=True
        ).exclude(tipo='L').order_by('data_aplicacao')

        # Aulas que eu cobri alguém e ainda não me pagaram
        creditos_sub = Solicitacao.objects.filter(
            professor_substituto=prof, status='A', devolucao_pendente=True
        )
        creditos_perm = Solicitacao.objects.filter(
            aula_destino__professores=prof, status='A', devolucao_pendente=True
        )
        creditos = list(creditos_sub) + list(creditos_perm)
        
    return render(request, 'gestao/index.html', {'dividas': dividas, 'creditos': creditos})

@login_required
def minhas_solicitacoes(request):
    if hasattr(request.user, 'professor'):
        solicitacoes = Solicitacao.objects.filter(solicitante=request.user.professor).order_by('-data_criacao')
    else:
        solicitacoes = []
        
    return render(request, 'gestao/minhas_solicitacoes.html', {'solicitacoes': solicitacoes})

def teste_email(request):
    try:
        send_mail(
            '🚀 Sucesso! Sistema SGG IFBA Conectado',
            'Email teste enviado.',
            None, 
            ['informatica.euc@ifba.edu.br'], 
            fail_silently=False,
        )
        return HttpResponse("Email enviado")
    except Exception as e:
        return HttpResponse(f"Erro: {str(e)}")

@login_required
def gerar_pdf_sei(request, id):
    solicitacao_base = get_object_or_404(Solicitacao, id=id)
    
    if solicitacao_base.status != 'A':
        return HttpResponse("Apenas solicitações APROVADAS podem gerar o formulário do SEI.", status=403)

    data_do_pedido = solicitacao_base.data_criacao.date()
    
    solicitacoes_do_lote = Solicitacao.objects.filter(
        solicitante=solicitacao_base.solicitante,
        data_criacao__date=data_do_pedido,
        status='A'
    ).order_by('data_aplicacao') 

    substitutos_unicos = set()
    tem_permuta = False
    cursos_envolvidos = set()

    for sol in solicitacoes_do_lote:
        cursos_envolvidos.add(sol.aula_origem.turma.nome)
        if sol.tipo == 'P' and sol.aula_destino:
            tem_permuta = True
            for p in sol.aula_destino.professores.all():
                substitutos_unicos.add(p)
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

    template_path = 'gestao/pdf_sei.html'
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="SEI_Permutas_{data_do_pedido.strftime("%Y%m%d")}.pdf"'

    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('Tivemos erros ao gerar o PDF: <pre>' + html + '</pre>')
    
    return response

@login_required
def nova_solicitacao(request, aula_id, tipo):
    aula_origem = get_object_or_404(GradeHoraria, id=aula_id)
    professor_logado = request.user.professor
    
    if tipo == 'P':
        nome_tipo = 'Permuta'
    elif tipo == 'S':
        nome_tipo = 'Substituição'
    elif tipo == 'L':
        nome_tipo = 'Aviso de Falta (Liberação)'
    else:
        nome_tipo = 'Solicitação'

    if request.method == 'POST':
        data_aplicacao = request.POST.get('data_aplicacao')
        carater = request.POST.get('carater', 'T') 
        
        # --- LÓGICA DE DEVOLUÇÃO (SISTEMA DE CRÉDITO) ---
        data_devolucao_post = request.POST.get('data_devolucao')
        a_combinar = request.POST.get('a_combinar') == 'on' 
        
        devolucao_pendente = False
        data_devolucao = None
        
        if tipo != 'L':
            if a_combinar or not data_devolucao_post:
                devolucao_pendente = True
            else:
                data_devolucao = data_devolucao_post

        nova_sol = Solicitacao(
            solicitante=professor_logado,
            tipo=tipo,
            aula_origem=aula_origem,
            data_aplicacao=data_aplicacao,
            data_devolucao=data_devolucao,
            devolucao_pendente=devolucao_pendente,
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
        
        try:
            assunto = f"⏳ Novo Pedido de {nome_tipo} - {professor_logado.nome_completo}"
            mensagem = f"""Olá, Coordenação. Foi feito um pedido de {nome_tipo}. Acesse o sistema."""
            destinatarios = ['informatica.euc@ifba.edu.br']
            send_mail(assunto, message, settings.DEFAULT_FROM_EMAIL, destinatarios, fail_silently=True)
        except Exception as e:
            print(f"Erro e-mail: {e}")
            
        return redirect('minhas_solicitacoes')

    contexto = {
        'aula_origem': aula_origem,
        'tipo': tipo,
        'nome_tipo': nome_tipo, 
    }
    
    if tipo == 'P':
        contexto['opcoes_destino'] = GradeHoraria.objects.filter(
            turma=aula_origem.turma
        ).exclude(
            professores=professor_logado
        ).select_related('disciplina', 'turma', 'horario').prefetch_related('professores')
        
    elif tipo == 'S':
        contexto['professores'] = Professor.objects.exclude(id=professor_logado.id).order_by('nome_completo')

    return render(request, 'gestao/form_solicitacao.html', contexto)

def api_informar_pagamento(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            solicitacao_id = dados.get('solicitacao_id')
            data_pagamento = dados.get('data_pagamento')

            solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)

            if solicitacao.solicitante != getattr(request.user, 'professor', None):
                return JsonResponse({'sucesso': False, 'erro': 'Sem permissão para alterar esta dívida.'})

            solicitacao.data_devolucao = data_pagamento
            solicitacao.devolucao_pendente = False
            solicitacao.save()

            return JsonResponse({'sucesso': True, 'mensagem': 'Pagamento registrado com sucesso!'})
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
def simulador_grade(request):
    """
    Renderiza a interface de arrastar e soltar para os coordenadores e diretores.
    """
    prof = getattr(request.user, 'professor', None)
    if not request.user.is_superuser and not (prof and (prof.is_coordenador or prof.is_diretor)):
        raise PermissionDenied("Acesso restrito à Coordenação e Direção do Campus.")

    turmas = Turma.objects.all().order_by('nome')
    professores = Professor.objects.all().order_by('nome_completo')
    horarios = Horario.objects.all().order_by('dia_semana', 'hora_inicio')
    
    grade_completa = GradeHoraria.objects.select_related('turma', 'horario', 'disciplina').prefetch_related('professores').all()
    
    horarios_unicos = Horario.objects.all().order_by('hora_inicio').values_list('hora_inicio', flat=True).distinct()
    slots_horarios = [h.strftime('%H:%M') for h in horarios_unicos]

    contexto = {
        'turmas': turmas,
        'professores': professores,
        'dias_semana': [2, 3, 4, 5, 6],
        'slots_horarios': slots_horarios,
        'grade_completa': grade_completa,
    }
    return render(request, 'gestao/simulador_grade.html', contexto)

@login_required
def exportar_pdf_simulacao(request):
    prof = getattr(request.user, 'professor', None)
    if not request.user.is_superuser and not (prof and (prof.is_coordenador or prof.is_diretor)):
        return HttpResponse("Acesso restrito à Coordenação e Direção do Campus.", status=403)

    if request.method == 'POST':
        try:
            dados_json = request.POST.get('estado_grade_json')
            if not dados_json:
                return HttpResponse("Dados da simulação não fornecidos.", status=400)
            
            estado_simulado = json.loads(dados_json)
            
            alteracoes = []
            nomes_dias = {1: 'Domingo', 2: 'Segunda-feira', 3: 'Terça-feira', 4: 'Quarta-feira', 5: 'Quinta-feira', 6: 'Sexta-feira', 7: 'Sábado'}
            
            slots_horarios = sorted(list(set(item['horaInicio'] for item in estado_simulado)))
            dias_semana = [2, 3, 4, 5, 6] 
            
            grade_map = {}
            turma_nome = "Simulação"
            
            for item in estado_simulado:
                turma_nome = item['turmaNome']
                
                aula_original = GradeHoraria.objects.select_related('horario', 'disciplina').get(id=item['id'])
                
                dia_antigo = aula_original.horario.dia_semana
                hora_antiga = aula_original.horario.hora_inicio.strftime('%H:%M')
                
                if int(item['diaSemana']) != dia_antigo or item['horaInicio'] != hora_antiga:
                    alteracoes.append({
                        'professor': item['professoresStr'],
                        'disciplina': item['disciplina'],
                        'de_dia': nomes_dias.get(dia_antigo),
                        'de_hora': hora_antiga,
                        'para_dia': nomes_dias.get(int(item['diaSemana'])),
                        'para_hora': item['horaInicio']
                    })
                
                chave = f"{item['diaSemana']}-{item['horaInicio']}"
                grade_map[chave] = f"<strong>{item['disciplina']}</strong><br><span style='color:#555;'>{item['professoresStr']}</span>"
            
            contexto = {
                'coordenador': prof if prof else request.user,
                'data_geracao': datetime.now(),
                'turma_nome': turma_nome,
                'alteracoes': alteracoes,
                'slots_horarios': slots_horarios,
                'dias_semana': dias_semana,
                'grade_map': grade_map
            }
            
            template_path = 'gestao/pdf_simulacao.html'
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="SGG_PROPOSTA_SEI_{turma_nome.replace(" ", "_")}.pdf"'

            template = get_template(template_path)
            html = template.render(contexto)
            
            pisa_status = pisa.CreatePDF(html, dest=response)
            if pisa_status.err:
                return HttpResponse('Erro ao processar e renderizar o PDF da simulação.', status=500)
            
            return response
        except Exception as e:
            return HttpResponse(f"Erro interno no motor de PDF: {str(e)}", status=500)
            
    return HttpResponse("Método não permitido.", status=405)