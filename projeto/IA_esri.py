import streamlit as st
from groq import Groq
import subprocess
import os
import sys
import folium
from streamlit_folium import st_folium
import datetime
import time
import json
import csv

# ==============================================================================
# CONFIGURACOES GERAIS E CONSTANTES DO SISTEMA
# ==============================================================================
# Estas variaveis definem caminhos criticos e configuracoes globais.
# O ARCPY_PATH deve apontar para o python.exe especifico do ArcGIS Pro.
ARCPY_PATH = r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"

# Numero maximo de mensagens antigas enviadas a IA para manter o contexto
MAX_MESSAGES_CONTEXT = 10

# Titulo da aplicacao que aparece na aba do navegador e no cabecalho
APP_TITLE = "GeoAI"

# Nomes de arquivos temporarios usados para troca de dados entre o Streamlit e o Arcpy
SCRIPT_FILENAME = "run_arcgis_script.py"
LOG_FILENAME = "system_execution.log"

# Configuracao inicial da pagina do Streamlit
st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# CLASSE: MONITORIZACAO DE PERFORMANCE
# ==============================================================================
# Esta classe serve para medir quanto tempo cada tarefa demora a executar.
class PerformanceMonitor:
    """Monitoriza e regista o tempo de execução de tarefas criticas."""
    
    def __init__(self):
        # Verifica se ja existe uma lista de metricas na sessao; se nao, cria uma.
        if "perf_metrics" not in st.session_state:
            st.session_state.perf_metrics = []

    def start_timer(self):
        # Inicia a contagem do tempo atual
        return time.time()

    def stop_timer(self, start_time, task_name):
        # Calcula a diferenca entre agora e o tempo inicial
        duration = time.time() - start_time
        
        # Cria um registo com o nome da tarefa e a duracao formatada
        entry = {
            "task": task_name,
            "duration": f"{duration:.4f}s",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        # Adiciona a lista global de metricas para exibicao posterior
        st.session_state.perf_metrics.append(entry)
        return duration

    def get_metrics(self):
        # Retorna todas as metricas recolhidas ate agora
        return st.session_state.perf_metrics

# ==============================================================================
# CLASSE: GESTAO DE LOGS
# ==============================================================================
# Esta classe serve para registar tudo o que acontece (erros, sucessos, info).
class LogManager:
    """Gere o historico de execucoes e erros do sistema de forma persistente."""
    
    def __init__(self):
        # Inicializa a lista de logs na sessao do usuario
        if "system_logs" not in st.session_state:
            st.session_state.system_logs = []

    def add_log(self, source, message, status="INFO"):
        # Cria um carimbo de data/hora para o log
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        
        # Estrutura do log: hora, fonte (quem gerou), mensagem e status (erro/sucesso)
        entry = {
            "time": timestamp,
            "source": source,
            "msg": message,
            "status": status
        }
        # Salva na memoria da sessao (para mostrar na tela imediatamente)
        st.session_state.system_logs.append(entry)
        
        # Salva num arquivo fisico (para ter historico se fechar o navegador)
        try:
            with open(LOG_FILENAME, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [{status}] {source}: {message}\n")
        except Exception:
            pass # Ignora erros de escrita de log para nao travar o sistema

    def get_logs(self):
        # Retorna a lista de logs para ser exibida na interface
        return st.session_state.system_logs

    def clear_logs(self):
        # Limpa os logs da memoria e apaga o arquivo fisico
        st.session_state.system_logs = []
        if os.path.exists(LOG_FILENAME):
            os.remove(LOG_FILENAME)

# ==============================================================================
# CLASSE: CONEXAO COM ARCGIS (CORE)
# ==============================================================================
# Esta classe serve para isolar a logica complexa de chamar o Python externo.
class ArcGISConnector:
    """Encapsula a comunicacao com o ambiente Python do ArcGIS Pro."""
    def __init__(self, python_path, logger_instance):
        self.python_path = python_path
        self.logger = logger_instance
    
    def list_layers(self):
        """
        Cria um pequeno script python para listar camadas e executa-o
        no ambiente do ArcGIS, nao no ambiente do Streamlit.
        """
        cmd = "import arcpy; print([l.name for l in arcpy.mp.ArcGISProject('CURRENT').activeMap.listLayers()])"
        try:
            # subprocess.run e usado para chamar o executavel externo
            result = subprocess.run(
                [self.python_path, "-c", cmd], 
                capture_output=True, 
                text=True, 
                timeout=8 # Timeout evita que o sistema trave se o ArcGIS demorar
            )
            # Se o codigo de retorno for 0, funcionou
            if result.returncode == 0:
                return result.stdout.strip()
            return f"Erro Subprocesso: {result.stderr}"
        except Exception as e:
            self.logger.add_log("ARCGIS_CONN", f"Falha ao listar camadas: {e}", "ERROR")
            return "Nao foi possivel conectar."

    def execute_script(self, script_content):
        """
        Recebe o codigo Python gerado ou editado, salva num arquivo .py
        e manda o executavel do ArcGIS rodar esse arquivo.
        """
        self.logger.add_log("SYSTEM", "Preparando execução de script...", "RUN")
        
        try:
            # Passo 1: Salvar o codigo num arquivo fisico
            with open(SCRIPT_FILENAME, "w", encoding="utf-8") as f:
                f.write(script_content)
            
            # Passo 2: Executar esse arquivo usando o Python do ArcGIS
            process = subprocess.Popen(
                [self.python_path, SCRIPT_FILENAME],
                stdout=subprocess.PIPE, # Captura o print() do script
                stderr=subprocess.PIPE, # Captura erros do script
                text=True
            )
            stdout, stderr = process.communicate()
            
            # Passo 3: Analisar o resultado
            if process.returncode == 0:
                self.logger.add_log("ARCPY", "Script finalizado com sucesso.", "SUCCESS")
                return f"SAIDA PADRAO:\n{stdout}"
            else:
                self.logger.add_log("ARCPY", "Script terminou com erros.", "ERROR")
                return f"ERRO:\n{stderr}"
                
        except Exception as e:
            self.logger.add_log("SYSTEM", f"Erro critico na execução: {str(e)}", "CRITICAL")
            return f"Excecao Python: {str(e)}"

# ==============================================================================
# INICIALIZACAO DE OBJETOS GLOBAIS
# ==============================================================================
# Instanciamos as classes criadas acima para uso no resto do codigo.
logger = LogManager()
perf_mon = PerformanceMonitor()
arcgis = ArcGISConnector(ARCPY_PATH, logger)

# ==============================================================================
# BIBLIOTECA DE SNIPPETS (CODIGOS PRONTOS)
# ==============================================================================
# Esta classe serve apenas para guardar exemplos de codigo uteis.
class SnippetLibrary:
    @staticmethod
    def get_snippets():
        return {
            "Selecionar Opção": "",
            "Listar Camadas": """import arcpy
# Lista todas as camadas e verifica visibilidade
aprx = arcpy.mp.ArcGISProject("CURRENT")
m = aprx.activeMap
print(f"Mapa Ativo: {m.name}")
for lyr in m.listLayers():
    print(f" - {lyr.name} (Visivel: {lyr.visible})")""",
            
            "Buffer Analysis": """import arcpy
# Cria uma zona de influencia (Buffer)
arcpy.env.overwriteOutput = True # Permite sobrescrever arquivos

camada_entrada = "Rodovias"
camada_saida = r"memory\Buffer_Rodovias" # Usa memoria RAM para ser mais rapido
distancia_buffer = "50 Meters"

try:
    arcpy.analysis.Buffer(camada_entrada, camada_saida, distancia_buffer)
    print(f"Sucesso: Buffer criado em {camada_saida}")
except Exception as e:
    print(f"Erro no Buffer: {e}")""",
            
            "Exportar Tabela para CSV": """import arcpy
import csv
import os

tabela_entrada = "Lotes"
diretorio_saida = r"C:\Temp"
nome_arquivo = "relatorio_lotes.csv"
caminho_completo = os.path.join(diretorio_saida, nome_arquivo)

# Cria diretorio se nao existir
if not os.path.exists(diretorio_saida):
    os.makedirs(diretorio_saida)

campos = [f.name for f in arcpy.ListFields(tabela_entrada)]

print(f"Exportando {tabela_entrada}...")
# Abre o arquivo CSV e escreve linha a linha usando o cursor do Arcpy
with open(caminho_completo, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(campos)
    with arcpy.da.SearchCursor(tabela_entrada, campos) as cursor:
        for row in cursor:
            writer.writerow(row)

print("Exportacao concluida com sucesso.")"""
        }

# ==============================================================================
# ESTILIZACAO CSS (DESIGN) 
# ==============================================================================
st.markdown("""
    <style>
    /* Fundo escuro para a aplicacao */
    .stApp { background-color: #0e1117; color: #c9d1d9; }
    
    /* Posiciona a caixa de chat */
    .stChatFloatingInputContainer { bottom: 20px; }
    
    /* Estilo dos expanders */
    div[data-testid="stExpander"] { border: 1px solid #30363d; background: #161b22; }
    
    /* Estilo customizado para as linhas de log */
    .log-entry { 
        font-family: 'Consolas', 'Courier New', monospace; 
        font-size: 0.85em; 
        padding: 4px; 
        border-bottom: 1px solid #21262d; 
    }
    /* Cores dinamicas baseadas no status do log */
    .log-SUCCESS { color: #56d364; font-weight: bold; }
    .log-ERROR { color: #f85149; font-weight: bold; }
    .log-INFO { color: #58a6ff; }
    .log-RUN { color: #e3b341; }
    .log-CRITICAL { color: #ff7b72; text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# Inicializa o historico de chat na sessao se nao existir
if "messages" not in st.session_state:
    st.session_state.messages = []

# ==============================================================================
# SIDEBAR (BARRA LATERAL)
# https://www.msn.com/pt-pt/noticias/other/um-aqu%C3%A1rio-especial-para-peixes-monstros/vi-AA1UXcIB?ocid=msedgntp&pc=U531&cvid=6977415452b64aaab9d9d93332bd9873&cvpid=73a13d84ed1a44a992fd73fb37193e31&ei=13
# ==============================================================================
with st.sidebar:
    st.header(APP_TITLE)
    st.markdown("Automacao Geoespacial Inteligente")
    
    # Bloco para inserir a chave da API
    with st.expander("Credenciais API", expanded=True):
        api_key = st.text_input("Chave Groq API", type="password")
        if not api_key:
            st.warning("Insira a Chave API para continuar.")
            st.stop() # Para a execução se nao houver chave
        client = Groq(api_key=api_key)
        st.divider()
    
    # Bloco para selecionar e carregar snippets
    st.subheader("Ferramentas de Codigo")
    snippets = SnippetLibrary.get_snippets()
    snippet_choice = st.selectbox("Biblioteca de Exemplos", list(snippets.keys()))
    
    if st.button("Carregar Exemplo"):
        if snippets[snippet_choice]:
            # Adiciona o snippet como uma mensagem do assistente no chat
            st.session_state.messages.append({
                "role": "assistant", 
                "content": f"Aqui esta o exemplo solicitado:\n```python\n{snippets[snippet_choice]}\n```"
            })
            logger.add_log("USER", f"Snippet inserido: {snippet_choice}")

    st.divider()
    
    # Funcao com cache para nao travar a cada clique
    @st.cache_data(ttl=60)
    def get_cached_layers():
        return arcgis.list_layers()
        
    camadas_ativas = get_cached_layers()
    st.info(f"Contexto do Projeto:\n{camadas_ativas}")
    
    # Botoes para limpar historico e logs
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Reset Chat"):
            st.session_state.messages = []
            st.rerun() # Recarrega a pagina
    with c2:
        if st.button("Reset Logs"):
            logger.clear_logs()
            st.rerun()

# ==============================================================================
# LAYOUT PRINCIPAL (COLUNAS)
# ==============================================================================
col_main_left, col_main_right = st.columns([1.3, 1])

# --- COLUNA ESQUERDA: FERRAMENTAS ---
with col_main_left:
    # Cria abas para organizar o conteudo
    tabs = st.tabs(["Mapa", "Terminal & Logs", "Performance", "Ambiente"])
    
    # --- ABA 1: MAPA ---
    with tabs[0]:
        # Seletor de visualizacao do mapa
        col_base, col_vazio = st.columns([3, 1])
        with col_base:
            basemap_select = st.selectbox(
                "Mapa Base", 
                ["OpenStreetMap", "CartoDB Dark_Matter"],
                index=0
            )
        
        # Funcao fragmentada para o mapa nao recarregar a pagina toda ao clicar
        @st.fragment
        def render_map(bmap):
            m = folium.Map(location=[32.6506, -16.9082], zoom_start=12, tiles=bmap)
            folium.LayerControl().add_to(m)
            st_folium(m, height=550, use_container_width=True, key="main_map")

        render_map(basemap_select)
        
        # Editor de Codigo: Permite ver e alterar o codigo antes de rodar
        st.subheader("Editor Python Arcpy")
        
        code_to_edit = ""
        # Logica para pegar o ultimo codigo gerado pela IA no chat
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "assistant" and "```python" in msg["content"]:
                parts = msg["content"].split("```python")
                if len(parts) > 1:
                    code_to_edit = parts[1].split("```")[0].strip()
                    break
        
        user_code = st.text_area(
            "Script para execução", 
            value=code_to_edit, 
            height=250,
            help="Pode editar este codigo manualmente antes de executar."
        )
        
        # Botao de execução Real
        if st.button("EXECUTAR SCRIPT NO ARCGIS PRO", type="primary"):
            if user_code:
                with st.spinner("A processar no motor Arcpy..."):
                    # Inicia contagem de tempo
                    t_start = perf_mon.start_timer()
                    
                    # Chama a funcao de execução
                    execution_result = arcgis.execute_script(user_code)
                    
                    # Para o timer e regista
                    perf_mon.stop_timer(t_start, "execução Script Python")
                    
                    # Mostra o resultado
                    st.text_area("Output do Console", value=execution_result, height=200)
                    st.success("execução concluida.")
            else:
                st.warning("A area de codigo esta vazia.")

    # --- ABA 2: LOGS ---
    with tabs[1]:
        st.write("### Registo de Eventos do Sistema")
        log_container = st.container(height=600)
        logs = logger.get_logs()
        
        if not logs:
            log_container.write("Sem registos de momento.")
        else:
            # Loop reverso para mostrar logs mais recentes primeiro
            for log in reversed(logs):
                css_class = f"log-{log['status']}"
                # Constroi HTML para colorir o log
                html_str = (
                    f"<div class='log-entry'>"
                    f"<span style='color:#8b949e'>[{log['time']}]</span> "
                    f"<b>{log['source']}</b>: "
                    f"<span class='{css_class}'>{log['msg']}</span>"
                    f"</div>"
                )
                log_container.markdown(html_str, unsafe_allow_html=True)

    # --- ABA 3: PERFORMANCE ---
    with tabs[2]:
        st.write("### Desempenho") 
        metrics = perf_mon.get_metrics()
        if metrics:
            # Mostra tabela de dados
            st.dataframe(metrics, use_container_width=True)
            
            # Calculos simples de media
            durations = [float(m['duration'].replace('s', '')) for m in metrics]
            if durations:
                avg_time = sum(durations) / len(durations)
                st.metric("Tempo Medio de execução", f"{avg_time:.4f}s")
                st.metric("Total de Execucoes", len(durations))
                st.metric("Ultima execução", metrics[-1]['duration'])
        else:
            st.info("Nenhuma metrica recolhida ainda. Execute scripts para gerar dados.")

    # --- ABA 4: DIAGNOSTICO ---
    with tabs[3]:
        st.write("### Configuracao do Ambiente")
        st.text_input("Executavel Python", value=ARCPY_PATH, disabled=True)
        st.text_input("Script Temporario", value=os.path.abspath(SCRIPT_FILENAME), disabled=True)
        
        # Teste de conectividade simples
        if st.button("Diagnostico de Conexao"):
            t_start = perf_mon.start_timer()
            res = arcgis.execute_script("import arcpy; import sys; print(f'Versao Arcpy: {arcpy.GetInstallInfo()['Version']} | Python: {sys.version}')")
            perf_mon.stop_timer(t_start, "Diagnostico Sistema")
            
            if "SUCESSO" in res:
                st.success("Conexao Estavel")
                st.code(res)
            else:
                st.error("Falha na Conexao")
                st.code(res)

# --- COLUNA DIREITA: CHAT ---
with col_main_right:
    st.subheader("Assistente Virtual")
    
    # Area de chat com scroll
    chat_box = st.container(height=650)
    
    # Renderiza mensagens anteriores do historico
    for msg in st.session_state.messages:
        role_avatar = None 
        with chat_box.chat_message(msg["role"], avatar=role_avatar):
            st.markdown(msg["content"])

    # Captura Input do Usuario
    user_input = st.chat_input("Descreva o que quer Fazer (ex: Fazer buffer de rios)...")
    
    if user_input:
        # 1. Guarda a mensagem do usuario no estado
        st.session_state.messages.append({"role": "user", "content": user_input})
        chat_box.chat_message("user").write(user_input)
        logger.add_log("CHAT", "Nova instrucao recebida")

        # 2. Prepara o prompt do sistema para a IA
        system_instruction = (
            f"Atue como um programador GIS Senior especialista em ArcPy. "
            f"O utilizador esta no Funchal, Madeira. "
            f"Analise o pedido e as camadas disponiveis: {camadas_ativas}. "
            f"Gere codigo Python completo, robusto e bem comentado. "
            f"Importante: "
            f"- Use blocos ```python para o codigo. "
            f"- Inclua tratamento de excecoes (try/except). "
            f"- Nao use emojis na explicacao nem no codigo. "
            f"- Seja tecnico."
        )

        # 3. Chama a API da Groq
        try:
            with st.spinner("A gerar solução..."):
                t_start_ai = perf_mon.start_timer()
                
                api_response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": system_instruction}] + st.session_state.messages[-MAX_MESSAGES_CONTEXT:],
                    temperature=0.3, 
                    max_tokens=1750
                )
                
                ai_content = api_response.choices[0].message.content
                perf_mon.stop_timer(t_start_ai, "Geracao IA (LLM)")

                # 4. Adiciona a resposta da IA ao chat
                st.session_state.messages.append({"role": "assistant", "content": ai_content})
                chat_box.chat_message("assistant").write(ai_content)
                
                logger.add_log("AI", "Resposta gerada e apresentada", "SUCCESS")
                
                # Forca a pagina a recarregar para atualizar o editor de codigo a esquerda
                st.rerun()
                
        except Exception as e:
            error_msg = f"Erro de comunicacao com a API: {str(e)}"
            st.error(error_msg)
            logger.add_log("API_ERROR", error_msg, "CRITICAL")
# ==============================================================================

st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #FFFFFF; font-size: 0.9em;'>"
    "GeoAI | Desenvolvido por Mateus Jesus | "
    f"Direitos Reservados a SIG Funchal."
    "</div>", 
    unsafe_allow_html=True
)
