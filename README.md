# GeoAI---ArcGis-Pro

Este projeto consiste numa aplicação web desenvolvida em Python que atua como um cockpit inteligente para utilizadores do ArcGIS Pro. A ferramenta combina inteligência artificial avançada (Llama 3.3 via Groq), reconhecimento de voz e integração direta com o motor arcpy da Esri.

## Pre-requisitos:

Para utilizar esta aplicacao, e necessario garantir a instalacao:

ArcGIS Pro: Instalacao ativa com o ambiente Python padrao (arcgispro-py3).

Chave de API Groq: Necessaria para o processamento de linguagem natural e transcricoes.

Dependencias Python: Execute o seguinte comando no terminal do ArcGIS Pro:


`pip install streamlit groq streamlit-folium streamlit-mic-recorder folium`

## Como Utilizar:

Siga os passos abaixo para configurar rodar o projeto:

Obter o Codigo: Efetue o clone deste repositorio ou descarregue os ficheiros.

Abrir Terminal: Utilize o Python Command Prompt do ArcGIS Pro.

Execucao: Navegue ate a pasta do projeto e execute o comando:


`streamlit run IA_esri.py`

Configuracao: Insira a sua chave de API na barra lateral da aplicacao para ativar as funcionalidades de IA.

Notas Tecnicas
A aplicacao utiliza o modelo Llama 3.3 via Groq para garantir baixa latencia nas respostas tecnicas. A comunicacao com o ArcGIS Pro e feita atraves de chamadas de subprocesso ao executavel python.exe do ambiente Conda da Esri.
