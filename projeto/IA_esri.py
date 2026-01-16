import streamlit as st
from groq import Groq
import subprocess
import os
import folium
from streamlit_folium import st_folium
from streamlit_mic_recorder import mic_recorder

# --- CONFIGURACOES TECNICAS ---
ARCPY_PATH = r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"  # Substitua pela sua chave de API Groq
client = Groq(api_key=GROQ_API_KEY)

st.set_page_config(page_title="GeoAI Pro Master", layout="wide")

# --- FUNCAO PARA LER CAMADAS DO ARCGIS ---
def obter_camadas_projeto():
    # Este script corre dentro do Python do ArcGIS para listar camadas
    comando = "import arcpy; print([l.name for l in arcpy.mp.ArcGISProject('CURRENT').activeMap.listLayers()])"
    try:
        resultado = subprocess.run([ARCPY_PATH, "-c", comando], capture_output=True, text=True, timeout=10)
        if resultado.returncode == 0:
            return resultado.stdout.strip()
        return "Nenhum projeto ativo detetado"
    except:
        return "Nao foi possivel aceder ao ArcGIS Pro"

# --- ESTILO CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .css-1d391kg { background-color: #161b22; }
    iframe { border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- FUNCAO DE TRANSCRICAO ---
def transcrever_audio(audio_bytes):
    try:
        with open("temp_audio.wav", "wb") as f: f.write(audio_bytes)
        with open("temp_audio.wav", "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=("temp_audio.wav", file.read()),
                model="whisper-large-v3",
                language="pt"
            )
        return transcription.text
    except Exception as e: return f"Erro: {e}"
    finally: 
        if os.path.exists("temp_audio.wav"): os.remove("temp_audio.wav")

# --- BARRA LATERAL ---
with st.sidebar:
    st.title("Configuracoes")
    st.divider()
    
    # Detecao de Camadas
    st.write("**Camadas no Projeto Atual:**")
    camadas_vivas = obter_camadas_projeto()
    st.info(camadas_vivas)
    
    st.divider()
    status = "Detetado" if os.path.exists(ARCPY_PATH) else "Nao encontrado"
    st.write(f"**Motor ArcGIS:** {status}")
    
    if st.button("Limpar Historico"):
        st.session_state.messages = []
        st.rerun()

# --- LAYOUT (MAPA E CHAT) ---
col_map, col_chat = st.columns([1.2, 1])

with col_map:
    st.subheader("Visualizacao Geografica")
    m = folium.Map(location=[32.6506, -16.9082], zoom_start=13, tiles="OpenStreetMap")
    
    st_folium(
        m, 
        height=500, 
        use_container_width=True,
        returned_objects=[] 
    )
    
    st.divider()
    st.subheader("Consola de Execucao")
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        texto = st.session_state.messages[-1]["content"]
        if "```python" in texto:
            codigo = texto.split("```python")[1].split("```")[0]
            st.code(codigo, language="python")
            if st.button("EXECUTAR NO ARCGIS PRO"):
                with st.spinner("A processar no motor Esri..."):
                    with open("run_arcgis.py", "w", encoding="utf-8") as f: f.write(codigo)
                    res = subprocess.run([ARCPY_PATH, "run_arcgis.py"], capture_output=True, text=True)
                    if res.returncode == 0: st.success("Executado com sucesso!")
                    else: st.error(f"Erro no ArcGIS: {res.stderr}")

with col_chat:
    st.subheader("Assistente GeoAI")
    
    audio_data = mic_recorder(start_prompt="Falar Comando", stop_prompt="Parar", key='recorder')
    chat_input = st.chat_input("Escreve aqui o teu pedido...")

    query = None
    if audio_data and 'bytes' in audio_data:
        query = transcrever_audio(audio_data['bytes'])
    elif chat_input:
        query = chat_input

    if query:
        st.session_state.messages.append({"role": "user", "content": query})
        with st.spinner("A analisar contexto..."):
            # O System Prompt agora inclui as camadas detetadas para a IA ser mais precisa
            sys_msg = f"""Es um Engenheiro SIG Senior. 
            O utilizador tem estas camadas abertas no ArcGIS Pro: {camadas_vivas}.
            Usa estes nomes de camadas sempre que possivel.
            NUNCA digas que nao tens acesso a dados em tempo real. 
            Responde sempre com logica espacial e codigo arcpy.
            NAO UTILIZES EMOJIS NAS TUAS RESPOSTAS."""
            
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": sys_msg}] + st.session_state.messages,
                temperature=0.3
            )
            st.session_state.messages.append({"role": "assistant", "content": completion.choices[0].message.content})
            st.rerun()

    for msg in reversed(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
