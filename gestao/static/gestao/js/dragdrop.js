document.addEventListener('DOMContentLoaded', () => {
            const cards = document.querySelectorAll('.card-aula');
            const slots = document.querySelectorAll('.slot');
            
            let draggedCard = null;

            cards.forEach(card => {
                card.addEventListener('dragstart', () => {
                    draggedCard = card;
                    card.classList.add('dragging');
                });

                card.addEventListener('dragend', () => {
                    card.classList.remove('dragging');
                    draggedCard = null;
                });
            });

            slots.forEach(slot => {
                slot.addEventListener('dragover', (e) => {
                    e.preventDefault(); 
                    slot.classList.add('drag-over');
                });

                slot.addEventListener('dragleave', () => {
                    slot.classList.remove('drag-over');
                });

                slot.addEventListener('drop', (e) => {
                    e.preventDefault();
                    const aulaOrigemId = e.dataTransfer.getData('text/plain');
                    const aulaDestinoId = slot.getAttribute('data-aula-id');
                    const dataDoSlot = slot.getAttribute('data-data');

                    if (aulaOrigemId && aulaDestinoId && aulaOrigemId !== aulaDestinoId) {
                        
                        // 1. Configura os IDs ocultos
                        document.getElementById('modalTipoAcao').value = 'permuta';
                        document.getElementById('modalAulaId').value = aulaOrigemId;
                        
                        // Cria um campo oculto para o destino (já que a permuta envolve duas aulas)
                        let inputDestino = document.getElementById('modalDestinoId');
                        if (!inputDestino) {
                            inputDestino = document.createElement('input');
                            inputDestino.type = 'hidden';
                            inputDestino.id = 'modalDestinoId';
                            document.getElementById('meuModal').appendChild(inputDestino);
                        }
                        inputDestino.value = aulaDestinoId;

                        // 2. Preenche a data se houver
                        if (dataDoSlot) document.getElementById('modalDataAplicacao').value = dataDoSlot;

                        // 3. Prepara a janela visualmente e exibe
                        document.getElementById('modalTitulo').innerText = "Detalhes da Permuta";
                        document.getElementById('botoesModal').style.display = 'none';
                        document.getElementById('divFormSubstituicao').style.display = 'none';
                        document.getElementById('divDetalhesEvento').style.display = 'block';
                        document.getElementById('botoesConfirmacao').style.display = 'flex';
                        
                        document.getElementById('meuModal').style.display = 'flex';
                    }
                });
            });
            const slotsClicaveis = document.querySelectorAll('.slot');
                // A Lógica de abrir o Modal corrigida
            slotsClicaveis.forEach(slot => {
                slot.addEventListener('click', (e) => {
                    // Ignora se clicou num card de aula (para não bugar o arrastar)
                    if (e.target.closest('.card-aula') || e.target.closest('.badge-pendente')) return; 

                    // 1. CAPTURA A DATA DO SLOT
                    const dataDoSlot = slot.getAttribute('data-data'); 
                    const inputData = document.getElementById('modalDataAplicacao');
                    if (inputData && dataDoSlot) inputData.value = dataDoSlot;

                    // 2. CAPTURA O ID DA AULA (Se houver)
                    const aulaId = slot.getAttribute('data-aula-id');
                    document.getElementById('modalAulaId').value = aulaId || '';
                    document.getElementById('modalHorarioId').value = slot.getAttribute('data-horario-id') || '';

                    // 3. DECISÃO INTELIGENTE DE INTERFACE
                    if (!e.target.closest('.prof-nome')) { // Se não tem professor, é espaço vazio/liberado
                        document.getElementById('modalTitulo').innerText = "Assumir Horário";
                        prepararAcao('assumir'); // Pula os botões iniciais e vai direto pro formulário
                    } else {
                        document.getElementById('modalTitulo').innerText = "Opções da Aula";
                        document.getElementById('botoesModal').style.display = 'flex';
                        document.getElementById('divFormSubstituicao').style.display = 'none';
                        document.getElementById('divDetalhesEvento').style.display = 'none';
                        document.getElementById('botoesConfirmacao').style.display = 'none';
                    }

                    document.getElementById('meuModal').style.display = 'flex';
                });
            });
        }); //


        function fecharModal() {
            document.getElementById('meuModal').style.display = 'none';
            document.getElementById('botoesModal').style.display = 'flex';
            document.getElementById('botoesConfirmacao').style.display = 'none';
            document.getElementById('divFormSubstituicao').style.display = 'none';
            document.getElementById('divDetalhesEvento').style.display = 'none';
            
            document.getElementById('modalTipoAcao').value = '';
            document.getElementById('modalAulaId').value = '';
            document.getElementById('modalDataAplicacao').value = '';
        }
        // Adicione isto no escopo global do seu JavaScript
        document.getElementById('meuModal').addEventListener('click', function(e) {
        // Se o elemento clicado for exatamente o fundo escuro (e não os filhos dele)
            if (e.target === this) {
                fecharModal();
            }
        });

        function prepararAcao(acao) {
            document.getElementById('modalTipoAcao').value = acao;
            document.getElementById('botoesModal').style.display = 'none';
            document.getElementById('divDetalhesEvento').style.display = 'block';

            const selectProf = document.getElementById('modalProfId');
            const meuIdProf = document.getElementById('meuIdProfessorLogado').value;
            const ehGestor = document.getElementById('usuarioEhGestor').value === 'true';

            if (acao === 'substituir' || acao === 'assumir') {
                document.getElementById('divFormSubstituicao').style.display = 'block';
                
                if (acao === 'assumir') {
                    if (ehGestor) {
                        // GESTOR: Tudo liberado para escolher qualquer professor
                        selectProf.style.pointerEvents = 'auto';
                        selectProf.style.backgroundColor = '#fff';
                        selectProf.value = ""; // Deixa vazio para ele escolher
                    } else {
                        // PROFESSOR: Trava no nome dele
                        if (meuIdProf) {
                            selectProf.value = meuIdProf;
                            selectProf.style.pointerEvents = 'none'; 
                            selectProf.style.backgroundColor = '#e9ecef';
                        }
                    }
                } else {
                    // Ação 'substituir' sempre libera a escolha (pois você indica outra pessoa)
                    selectProf.style.pointerEvents = 'auto';
                    selectProf.style.backgroundColor = '#fff';
                }
            } else {
                document.getElementById('divFormSubstituicao').style.display = 'none';
            }

            document.getElementById('botoesConfirmacao').style.display = 'flex';
        }

        async function enviarAcaoModal() {
            const acao = document.getElementById('modalTipoAcao').value;
            const aulaId = document.getElementById('modalAulaId').value;
            const horarioId = document.getElementById('modalHorarioId')?.value;
            const turmaId = document.getElementById('modalTurmaId')?.value;
            const discId = document.getElementById('modalDiscId')?.value;
            const profId = document.getElementById('modalProfId')?.value;
            const dataAplicacao = document.getElementById('modalDataAplicacao').value;
            const carater = document.getElementById('modalCarater').value;

            if (!dataAplicacao) {
                alert("Por favor, selecione a data em que esta alteração vai ocorrer.");
                return;
            }

            // --- 1. PREPARAÇÃO DO BOTÃO DE CARREGAMENTO (LOADING) ---
            const btnConfirmar = document.querySelector('#botoesConfirmacao button:nth-child(2)');
            const btnCancelar = document.querySelector('#botoesConfirmacao button:nth-child(1)');
            const textoOriginal = btnConfirmar.innerText;
            
            btnConfirmar.innerText = "⏳ Processando e Enviando...";
            btnConfirmar.disabled = true;
            btnConfirmar.style.backgroundColor = "#7f8c8d";
            btnCancelar.disabled = true;

            // --- 2. CONFIGURAÇÃO DA ROTA E DADOS ---
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
            let url = '/api/modal/acao/'; 
            let bodyData = {
                aula_id: aulaId, horario_id: horarioId, turma_id: turmaId, 
                acao: acao, disc_id: discId, prof_id: profId,
                data_aplicacao: dataAplicacao, carater: carater
            };

            if (acao === 'permuta') {
                url = '/api/permuta/solicitar/'; 
                bodyData = {
                    aula_origem_id: aulaId,
                    aula_destino_id: document.getElementById('modalDestinoId').value,
                    data_aplicacao: dataAplicacao,
                    carater: carater
                };
            }

            // --- 3. ENVIO PARA O SERVIDOR ---
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(bodyData)
                });
                
                const data = await response.json();
                
                if (data.sucesso) {
                    alert(data.mensagem);
                    location.reload(); 
                } else {
                    alert("Erro: " + data.erro);
                    // Se der erro lógico, devolvemos os botões ao normal
                    btnConfirmar.innerText = textoOriginal;
                    btnConfirmar.disabled = false;
                    btnConfirmar.style.backgroundColor = "#34a853";
                    btnCancelar.disabled = false;
                }
                
            } catch (error) { 
                console.error(error);
                alert("Erro de comunicação com o servidor.");
                // Se der erro de rede, devolvemos os botões ao normal
                btnConfirmar.innerText = textoOriginal;
                btnConfirmar.disabled = false;
                btnConfirmar.style.backgroundColor = "#34a853";
                btnCancelar.disabled = false;
            }
        }


        async function solicitarPermuta(origemId, destinoId, elemOrigem, elemDestino, targetSlot) {
            const originalParent = elemOrigem.parentElement;
            
            // Troca visual temporária
            targetSlot.appendChild(elemOrigem);
            originalParent.appendChild(elemDestino);

            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            try {
                const response = await fetch('/api/permuta/solicitar/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({
                        aula_origem_id: origemId,
                        aula_destino_id: destinoId,
                        data_aplicacao: '2026-03-20' // Data fictícia para teste
                    })
                });

                const data = await response.json();

                if (!data.sucesso) {
                    alert("Erro: " + data.erro);
                    // Reverte a UI em caso de choque/erro
                    originalParent.appendChild(elemOrigem);
                    targetSlot.appendChild(elemDestino);
                } else {
                    alert(data.mensagem);
                    elemOrigem.style.backgroundColor = "#fff9c4"; // Amarelo para indicar pendência
                    elemDestino.style.backgroundColor = "#fff9c4";
                }
            } catch (error) {
                console.error("Erro na requisição:", error);
                originalParent.appendChild(elemOrigem);
                targetSlot.appendChild(elemDestino);
            }
        }
// Função para automatizar o preenchimento de horários vazios
        async function rodarScriptGerarGrade() {
            const turmaId = document.getElementById('turma_id').value;
            
            if (!confirm("Deseja gerar automaticamente todos os espaços em branco para esta turma? Os horários que já têm aula não serão apagados.")) {
                return;
            }

            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            try {
                const response = await fetch('/api/grade/gerar-vazia/', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json', 
                        'X-CSRFToken': csrfToken 
                    },
                    body: JSON.stringify({ turma_id: turmaId })
                });

                const data = await response.json();
                
                if (data.sucesso) {
                    alert(data.mensagem);
                    location.reload(); // Recarrega para exibir a nova grelha
                } else {
                    alert("Erro: " + data.erro);
                }
            } catch (error) {
                console.error(error);
                alert("Erro no servidor de comunicação.");
            }
        }
