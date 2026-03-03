import streamlit as st
from groq import Groq
import subprocess
import json
import datetime
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
import folium
from streamlit_folium import st_folium
import re

# =====================================================
# CONFIGURACAO
# =====================================================

@dataclass
class Config:
    ARCPY_PATH: Path = Path(r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe")
    MAX_MESSAGES: int = 15
    DEFAULT_LOCATION = [32.6506, -16.9082]
    TIMEOUT = 60
    APP_TITLE = "GeoAI"
    APP_VERSION = "1.1.0"
    MODEL_NAME = "llama-3.3-70b-versatile"

CONFIG = Config()

# =====================================================
# GESTAO DE REGISTOS
# =====================================================

class LogManager:
    def __init__(self):
        if "logs" not in st.session_state:
            st.session_state.logs = []

    def add(self, nivel: str, mensagem: str):
        log_entry = {
            "Hora": datetime.datetime.now().strftime("%H:%M:%S"),
            "Nivel": nivel,
            "Mensagem": mensagem
        }
        st.session_state.logs.append(log_entry)
        if len(st.session_state.logs) > 50:
            st.session_state.logs.pop(0)

    def get(self):
        return st.session_state.logs

    def clear(self):
        st.session_state.logs = []

# =====================================================
# CONECTOR ARCGIS
# =====================================================

class ArcGISConnector:
    def __init__(self, python_path: Path, logger: LogManager):
        self.python_path = python_path
        self.logger = logger

    def check_connection(self) -> bool:
        if not self.python_path.exists():
            return False
        cmd = "import arcpy; print('OK')"
        try:
            result = subprocess.run(
                [str(self.python_path), "-c", cmd],
                capture_output=True, text=True, timeout=15
            )
            return "OK" in result.stdout
        except Exception:
            return False

    def list_layers(self) -> List[str]:
        cmd = """
import arcpy, json
try:
    aprx = arcpy.mp.ArcGISProject('CURRENT')
    active_map = aprx.activeMap
    if active_map:
        layers = [l.name for l in active_map.listLayers() if not l.isGroupLayer]
        print(json.dumps(layers))
    else:
        print(json.dumps([]))
except Exception as e:
    print(json.dumps([f"Erro: {str(e)}"]))
"""
        try:
            result = subprocess.run(
                [str(self.python_path), "-c", cmd],
                capture_output=True, text=True, timeout=20
            )
            return json.loads(result.stdout)
        except Exception as e:
            self.logger.add("ERRO", f"Falha ao listar camadas: {e}")
            return []

    def execute_script(self, code: str) -> Dict:
        if not code.strip():
            return {"success": False, "error": "Codigo vazio"}

        with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode='w', encoding='utf-8') as f:
            f.write(code)
            script_path = f.name

        try:
            result = subprocess.run(
                [str(self.python_path), script_path],
                capture_output=True, text=True, timeout=CONFIG.TIMEOUT
            )
            
            if os.path.exists(script_path):
                os.remove(script_path)

            success = result.returncode == 0
            return {
                "success": success,
                "output": result.stdout,
                "error": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

# =====================================================
# UTILITARIOS
# =====================================================

def extract_python_code(text: str) -> str:
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    return match.group(1) if match else ""

def inject_custom_css():
    st.markdown("""
        <style>
        .block-container { padding-top: 2rem; padding-bottom: 5rem; }
        .stChatFloatingInputContainer { bottom: 60px !important; }
        
        .custom-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            background-color: #0e1117; 
            color: #fafafa;
            text-align: center;
            padding: 10px 0px;
            font-size: 13px;
            border-top: 1px solid #31333f;
            z-index: 9999;
        }

        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# =====================================================
# MAIN
# =====================================================

def main():
    st.set_page_config(page_title=CONFIG.APP_TITLE, layout="wide")
    inject_custom_css()
    
    logger = LogManager()
    arcgis = ArcGISConnector(CONFIG.ARCPY_PATH, logger)

    # SIDEBAR
    with st.sidebar:
        st.title("Configuracao")
        api_key = st.text_input("Groq API Key", type="password")
        
        st.subheader("Conexao")
        if arcgis.check_connection():
            st.success("ArcGIS Pro: Conectado")
        else:
            st.error("ArcGIS Pro: Desconectado")

        st.divider()
        tab_layers, tab_logs = st.tabs(["Camadas", "Logs"])
        
        with tab_layers:
            if st.button("Atualizar Lista", use_container_width=True):
                st.session_state.layers = arcgis.list_layers()
            
            layers = st.session_state.get("layers", [])
            for l in layers: st.caption(f"- {l}")

        with tab_logs:
            if st.button("Limpar Logs", use_container_width=True): logger.clear()
            st.dataframe(logger.get(), use_container_width=True, hide_index=True)

    # PAINEL PRINCIPAL
    st.title(CONFIG.APP_TITLE)
    
    col_esquerda, col_direita = st.columns([1, 1], gap="medium")

    with col_esquerda:
        with st.container(border=True):
            st.subheader("Visualizacao")
            m = folium.Map(location=CONFIG.DEFAULT_LOCATION, zoom_start=12)
            st_folium(m, height=300, use_container_width=True)

        with st.container(border=True):
            st.subheader("Editor ArcPy")
            
            if "messages" not in st.session_state:
                st.session_state.messages = [{"role": "system", "content": "Especialista em ArcPy. Gere código Python para ArcGIS Pro e explique brevemente."}]
            
            last_ai_code = ""
            for msg in reversed(st.session_state.messages):
                if msg["role"] == "assistant":
                    last_ai_code = extract_python_code(msg["content"])
                    if last_ai_code: break

            code_to_run = st.text_area("Script atual:", value=last_ai_code, height=350)
            
            if st.button("Executar Script", use_container_width=True):
                with st.status("Processando...", expanded=False) as status:
                    res = arcgis.execute_script(code_to_run)
                    if res["success"]:
                        status.update(label="Sucesso", state="complete")
                        if res["output"]: st.code(res["output"], language="txt")
                    else:
                        status.update(label="Erro na execucao", state="error")
                        st.error(res["error"])

    with col_direita:
        with st.container(border=True):
            st.subheader("Assistente de Analise")
            chat_container = st.container(height=785)
            
            with chat_container:
                for msg in st.session_state.messages:
                    if msg["role"] != "system":
                        with st.chat_message(msg["role"]):
                            st.markdown(msg["content"])

            if prompt := st.chat_input("Descreva sua operacao espacial..."):
                if not api_key:
                    st.warning("Insira a API Key na barra lateral")
                else:
                    contexto_camadas = ", ".join(st.session_state.get("layers", []))
                    contexto = f"\n\n[Contexto GIS: Camadas atuais: {contexto_camadas}]"
                    st.session_state.messages.append({"role": "user", "content": prompt + contexto})
                    
                    with chat_container:
                        with st.chat_message("user"):
                            st.markdown(prompt)

                        with st.chat_message("assistant"):
                            client = Groq(api_key=api_key)
                            response = client.chat.completions.create(
                                model=CONFIG.MODEL_NAME,
                                messages=st.session_state.messages,
                                temperature=0.1
                            )
                            full_response = response.choices[0].message.content
                            st.markdown(full_response)
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                            st.rerun()

    st.markdown(f"""
        <div class="custom-footer">
            GeoAI v{CONFIG.APP_VERSION} | DIG | Desenvolvido por <a href="https://www.github.com/yrozxm/" style="color: #00aaff;">Mateus Jesus</a>
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()