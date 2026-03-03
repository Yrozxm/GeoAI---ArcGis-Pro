import streamlit as st
from groq import Groq
import subprocess
import json
import datetime
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
import folium
from streamlit_folium import st_folium
import re


# =====================================================
# CONFIGURAÇÃO
# =====================================================

@dataclass
class Config:
    ARCPY_PATH: Path = Path(r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe")
    MAX_MESSAGES: int = 10
    DEFAULT_LOCATION = (32.6506, -16.9082)
    TIMEOUT = 30
    APP_TITLE = "GeoAI - Plataforma de Apoio à Análise Geoespacial"

CONFIG = Config()


# =====================================================
# GESTÃO DE REGISTOS
# =====================================================

class LogManager:
    def __init__(self):
        if "logs" not in st.session_state:
            st.session_state.logs = []

    def add(self, nivel: str, mensagem: str):
        st.session_state.logs.append({
            "Hora": datetime.datetime.now().strftime("%H:%M:%S"),
            "Nível": nivel,
            "Mensagem": mensagem
        })

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
                capture_output=True,
                text=True,
                timeout=10
            )
            return "OK" in result.stdout
        except:
            return False

    def list_layers(self) -> List[str]:
        cmd = """
import arcpy, json
try:
    proj = arcpy.mp.ArcGISProject('CURRENT')
    layers = [l.name for l in proj.activeMap.listLayers() if not l.isGroupLayer]
    print(json.dumps(layers))
except:
    print(json.dumps([]))
"""
        try:
            result = subprocess.run(
                [str(self.python_path), "-c", cmd],
                capture_output=True,
                text=True,
                timeout=10
            )
            layers = json.loads(result.stdout)
            self.logger.add("INFO", f"{len(layers)} camadas encontradas")
            return layers
        except Exception as e:
            self.logger.add("ERRO", f"Falha ao listar camadas: {e}")
            return []

    def execute_script(self, code: str) -> Dict:
        if not code.strip():
            return {"success": False, "error": "Código vazio"}

        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(code.encode("utf-8"))
            script_path = f.name

        try:
            result = subprocess.run(
                [str(self.python_path), script_path],
                capture_output=True,
                text=True,
                timeout=CONFIG.TIMEOUT
            )

            if result.returncode == 0:
                self.logger.add("INFO", "Script executado com sucesso")
            else:
                self.logger.add("ERRO", "Erro na execução do script")

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr
            }
        except Exception as e:
            self.logger.add("ERRO", str(e))
            return {"success": False, "error": str(e)}


# =====================================================
# CHAT
# =====================================================

class ChatManager:
    def __init__(self):
        if "messages" not in st.session_state:
            st.session_state.messages = [{
                "role": "system",
                "content": "És especialista em ArcPy. Gera código Python executável."
            }]

    def add(self, role: str, content: str):
        st.session_state.messages.append({"role": role, "content": content})

        if len(st.session_state.messages) > CONFIG.MAX_MESSAGES:
            st.session_state.messages = (
                [st.session_state.messages[0]] +
                st.session_state.messages[-CONFIG.MAX_MESSAGES:]
            )

    def get(self):
        return st.session_state.messages

    def extract_last_code(self):
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "assistant":
                match = re.search(r"```python\n(.*?)```", msg["content"], re.DOTALL)
                if match:
                    return match.group(1)
        return ""


# =====================================================
# MAIN
# =====================================================

def main():

    st.set_page_config(page_title=CONFIG.APP_TITLE, layout="wide")
    st.title(CONFIG.APP_TITLE)

    logger = LogManager()
    arcgis = ArcGISConnector(CONFIG.ARCPY_PATH, logger)
    chat_mgr = ChatManager()

    # ================= SIDEBAR =================

    with st.sidebar:

        st.header("Configuração do Sistema")

        api_key = st.text_input("Chave de acesso à API Groq", type="password")

        client = None
        if api_key:
            try:
                client = Groq(api_key=api_key)
                st.success("Serviço de IA operacional")
            except:
                st.error("Falha na ligação ao serviço de IA")

        st.divider()
        st.header("Estado do Sistema")

        ligado = arcgis.check_connection()

        if ligado:
            st.success("ArcGIS Pro operacional")
        else:
            st.error("ArcGIS Pro indisponível")

        st.divider()
        st.header("Camadas Ativas")

        if st.button("Atualizar camadas"):
            st.session_state.layers = arcgis.list_layers()

        if "layers" not in st.session_state:
            st.session_state.layers = arcgis.list_layers()

        if st.session_state.layers:
            for layer in st.session_state.layers:
                st.write(f"- {layer}")
        else:
            st.write("Sem camadas disponíveis")

        st.divider()
        st.header("Registos do Sistema")

        if st.button("Limpar registos"):
            logger.clear()

        logs = logger.get()
        if logs:
            st.dataframe(logs, use_container_width=True)

    # ================= PAINEL PRINCIPAL =================

    col_esquerda, col_direita = st.columns([1.3, 1])

    with col_esquerda:

        st.subheader("Visualização Cartográfica")

        mapa = folium.Map(
            location=CONFIG.DEFAULT_LOCATION,
            zoom_start=13
        )

        st_folium(mapa, height=400, use_container_width=True)

        st.subheader("Execução de Scripts ArcPy")

        codigo = st.text_area(
            "Código Python",
            value=chat_mgr.extract_last_code(),
            height=300
        )

        if st.button("Executar Script"):
            resultado = arcgis.execute_script(codigo)

            if resultado["success"]:
                st.success("Execução concluída com sucesso")
                if resultado["output"]:
                    st.text(resultado["output"])
            else:
                st.error("Ocorreu um erro na execução")
                st.text(resultado["error"])

    with col_direita:

        st.subheader("Assistente de Análise Geoespacial")

        for msg in chat_mgr.get():
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        prompt = st.chat_input("Descreva a análise pretendida")

        if prompt and client:
            chat_mgr.add("user", prompt)

            with st.chat_message("assistant"):
                resposta = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=chat_mgr.get(),
                    temperature=0.2
                )

                conteudo = resposta.choices[0].message.content
                st.markdown(conteudo)

            chat_mgr.add("assistant", conteudo)
            st.rerun()


if __name__ == "__main__":
    main()