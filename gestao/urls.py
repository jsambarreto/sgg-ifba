from django.urls import path
from django.contrib.auth import views as auth_views 
from . import views

urlpatterns = [
    path('', views.pagina_inicial, name='pagina_inicial'),
    path('login/', auth_views.LoginView.as_view(template_name='gestao/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('grade/', views.exibir_grade, name='exibir_grade'),
    path('api/permuta/solicitar/', views.api_solicitar_permuta, name='api_solicitar_permuta'),
    path('aprovacoes/', views.painel_aprovacoes, name='painel_aprovacoes'),
    path('api/aprovacao/processar/', views.api_processar_aprovacao, name='api_processar_aprovacao'),
    path('api/modal/acao/', views.api_acao_modal, name='api_acao_modal'),
    path('api/grade/gerar-vazia/', views.api_gerar_grade_vazia, name='api_gerar_grade_vazia'),
    path('construtor/', views.construtor_grade, name='construtor_grade'),
    path('api/construtor/salvar/', views.api_salvar_aula_base, name='api_salvar_aula_base'), 
    path('direcao/carga-horaria/', views.relatorio_carga_horaria, name='relatorio_carga_horaria'),
    path('minhas-solicitacoes/', views.minhas_solicitacoes, name='minhas_solicitacoes'),
    path('solicitacao/<int:id>/pdf-sei/', views.gerar_pdf_sei, name='gerar_pdf_sei'),
    path('solicitar/<int:aula_id>/<str:tipo>/', views.nova_solicitacao, name='nova_solicitacao'),
    path('api/pagar/', views.api_informar_pagamento, name='api_informar_pagamento'),
]

