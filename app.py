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

valor_termos = ""
if os.path.exists(TERMO_BUSCA_PADRAO):
    with open(TERMO_BUSCA_PADRAO, encoding="utf-8") as f:
        valor_termos = f.read()

termos_input = st.text_area("Digite os termos para buscar (1 por linha):", value=valor_termos)
termos = [t.strip() for t in termos_input.splitlines() if t.strip()]

valor_negativos = ""
if os.path.exists(NEGATIVOS_PADRAO):
    with open(NEGATIVOS_PADRAO, encoding="utf-8") as f:
        valor_negativos = f.read()
negativos = [t.strip().lower() for t in valor_negativos.splitlines() if t.strip()]

valor_canais = ""
if os.path.exists(CANAIS_EXCLUIR_PADRAO):
    with open(CANAIS_EXCLUIR_PADRAO, encoding="utf-8") as f:
        valor_canais = f.read()
canais_excluidos = [c.strip().lower() for c in valor_canais.splitlines() if c.strip()]

max_results = st.number_input("Quantidade de vídeos a buscar:", min_value=1, max_value=200, value=50)
min_views = st.number_input("Visualizações mínimas:", min_value=0, value=10000, step=1000)
min_inscritos = st.number_input("Mínimo de inscritos no canal:", min_value=0, value=1000, step=100)
max_inscritos = st.number_input("Máximo de inscritos no canal:", min_value=0, value=1000000, step=1000)
max_idade_dias = st.number_input("Idade máxima do vídeo (dias):", min_value=0, value=180, step=1)

pais = st.selectbox("Filtrar por país:", ["Todos", "BR", "US", "IL", "IN", "PT", "MX"])
region_code = None if pais == "Todos" else pais

idioma = st.selectbox("Filtrar por idioma:", ["Todos", "Português", "Inglês", "Espanhol"])
lang_map = {"Todos": None, "Português": "pt", "Inglês": "en", "Espanhol": "es"}
relevance_language = lang_map[idioma]

duracao = st.selectbox("Filtrar duração:", ["Todos", "Curtos (<4min)", "Médios (4-20min)", "Longos (>20min)"])
duracao_map = {"Todos": "any", "Curtos (<4min)": "short", "Médios (4-20min)": "medium", "Longos (>20min)": "long"}
video_duration = duracao_map[duracao]

if st.button("Buscar vídeos"):
    query = " OR ".join(f'"{t}"' for t in termos)
    todos_videos = []
    next_page = None

    with st.spinner("Buscando vídeos..."):
        while len(todos_videos) < max_results:
            batch, next_page = buscar_videos(
                termo=query,
                max_results=max_results,
                min_views=min_views,
                max_idade_dias=max_idade_dias,
                min_subs=min_inscritos,
                max_subs=max_inscritos,
                region_code=region_code,
                video_duration=video_duration,
                relevance_language=relevance_language,
                page_token=next_page
            )
            todos_videos.extend(batch)
            if not next_page:
                break

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
        df['link'] = df['video_url'].apply(lambda x: f"[Abrir vídeo]({x})")
        st.session_state.df_resultados = df
        st.success(f"{len(df)} vídeos encontrados.")

if st.session_state.df_resultados is not None:
    df = st.session_state.df_resultados
    st.dataframe(df[["title", "channel", "views", "views_por_dia", "duration", "published_at", "link"]])

    output = io.BytesIO()
    df.to_csv(output, sep=';', decimal=',', encoding='utf-8-sig', index=False, float_format='%.2f')
    st.download_button("📅 Baixar CSV", data=output.getvalue(), file_name="videos_biblicos.csv", mime="text/csv")

    if st.button("📸 Baixar Thumbnails"):
        zip_file_path = baixar_thumbs(df)
        with open(zip_file_path, "rb") as fp:
            st.download_button(
                label="📥 Baixar ZIP de Thumbnails",
                data=fp,
                file_name="thumbnails.zip",
                mime="application/zip"
            )
