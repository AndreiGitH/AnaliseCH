import streamlit as st
import pandas as pd
import os
import io 
from youtube_utils import buscar_videos, baixar_thumbs

st.set_page_config(page_title="Buscador de Vídeos Bíblicos", layout="wide")
st.title("Buscador de Vídeos Virais")

if 'df_resultados' not in st.session_state:
    st.session_state.df_resultados = None

# CARREGAR TERMOS PADRÃO DE TXT
TERMO_BUSCA_PADRAO = "termos_busca.txt"
NEGATIVOS_PADRAO = "termos_excluir.txt"
CANAIS_EXCLUIR_PADRAO = "canais_excluir.txt"

# Carregar termos de busca iniciais
valor_termos = ""
if os.path.exists(TERMO_BUSCA_PADRAO):
    with open(TERMO_BUSCA_PADRAO, encoding="utf-8") as f:
        valor_termos = f.read()

# TERMOS POSITIVOS
termos_input = st.text_area("Digite os termos para buscar (1 por linha):", value=valor_termos)
termos = [t.strip() for t in termos_input.splitlines() if t.strip()]

# Carregar termos negativos de txt
valor_negativos = ""
if os.path.exists(NEGATIVOS_PADRAO):
    with open(NEGATIVOS_PADRAO, encoding="utf-8") as f:
        valor_negativos = f.read()
negativos_input = st.text_area("Excluir títulos com estas palavras (1 por linha):", value=valor_negativos)
negativos = [t.strip().lower() for t in negativos_input.splitlines() if t.strip()]

# Carregar canais excluídos de txt
valor_canais = ""
if os.path.exists(CANAIS_EXCLUIR_PADRAO):
    with open(CANAIS_EXCLUIR_PADRAO, encoding="utf-8") as f:
        valor_canais = f.read()
canais_input = st.text_area("Excluir vídeos destes canais (1 por linha):", value=valor_canais)
canais_excluidos = [c.strip().lower() for c in canais_input.splitlines() if c.strip()]

# QUANTIDADE DE VÍDEOS
max_results = st.number_input("Quantidade de vídeos por termo:", min_value=1, max_value=50, value=30, step=1)

# VIEWS MÍNIMAS
min_views = st.number_input("Quantidade mínima de visualizações:", min_value=0, value=10000, step=1000)

# INSCRITOS
min_inscritos = st.number_input("Mínimo de inscritos no canal:", min_value=0, value=1000, step=100)
max_inscritos = st.number_input("Máximo de inscritos no canal:", min_value=0, value=1000000, step=1000)

# IDADE MÁXIMA
max_idade_dias = st.number_input("Idade máxima do vídeo (em dias):", min_value=1, value=180, step=1)

# LOCALIZAÇÃO E IDIOMA
pais = st.selectbox("Filtrar por país:", ["Todos", "BR", "US", "IL", "IN", "PT", "MX"])
region_code = None if pais == "Todos" else pais

idioma = st.selectbox("Filtrar por idioma:", ["Todos", "Português", "Inglês", "Espanhol"])
lang_map = {"Todos": None, "Português": "pt", "Inglês": "en", "Espanhol": "es"}
relevance_language = lang_map[idioma]

# DURAÇÃO
duracao = st.selectbox("Filtrar por duração do vídeo:", ["Todos", "Curtos (<4min)", "Médios (4-20min)", "Longos (>20min)"])
duracao_map = {"Todos": "any", "Curtos (<4min)": "short", "Médios (4-20min)": "medium", "Longos (>20min)": "long"}
video_duration = duracao_map[duracao]

# BOTÃO DE BUSCA
if st.button("Buscar vídeos"):
    todos_videos = []
    with st.spinner("Buscando vídeos..."):
        for termo in termos:
            todos_videos.extend(buscar_videos(
                termo,
                max_results=max_results,
                min_views=min_views,
                max_idade_dias=max_idade_dias,
                min_subs=min_inscritos,
                max_subs=max_inscritos,
                region_code=region_code,
                video_duration=video_duration,
                relevance_language=relevance_language
            ))

    df = pd.DataFrame(todos_videos).drop_duplicates(subset='video_id')

    if not df.empty:
        if negativos:
            df = df[~df['title'].str.lower().str.contains('|'.join(negativos))]
        if canais_excluidos:
            df = df[~df['channel'].str.lower().isin(canais_excluidos)]

    if df.empty:
        st.warning("Nenhum vídeo encontrado com os filtros aplicados.")
        st.session_state.df_resultados = None
    else:
        df['published_at'] = pd.to_datetime(df['published_at'])
        df['dias_desde_pub'] = (pd.Timestamp.utcnow() - df['published_at']).dt.days
        df['views_por_dia'] = (df['views'] / df['dias_desde_pub'].replace(0, 1)).round(2)
        st.session_state.df_resultados = df
        st.success(f"{len(df)} vídeos encontrados.")

if st.session_state.df_resultados is not None:
    df = st.session_state.df_resultados
    st.dataframe(df[['title', 'channel', 'views', 'views_por_dia', 'published_at', 'search_term']])

    # CORRIGIDO: gerar CSV com BOM usando BytesIO
    output = io.BytesIO()
    df.to_csv(output, sep=';', decimal=',', encoding='utf-8-sig', index=False, float_format='%.2f')
    csv_bytes = output.getvalue()

    st.download_button("📅 Baixar CSV", data=csv_bytes, file_name="videos_biblicos.csv", mime="text/csv")
    

    if st.button("📸 Baixar Thumbnails"):
    zip_file_path = baixar_thumbs(df)
    
    with open(zip_file_path, "rb") as fp:
        st.download_button(
            label="📥 Baixar ZIP de Thumbnails",
            data=fp,
            file_name="thumbnails.zip",
            mime="application/zip"
        )
