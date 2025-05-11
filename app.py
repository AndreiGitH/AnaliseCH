import streamlit as st
import pandas as pd
import os
import io
from youtube_utils import buscar_videos, baixar_thumbs

# Inicializa session_state
if 'df_resultados' not in st.session_state:
    st.session_state.df_resultados = None

st.set_page_config(page_title="Buscador de Vídeos Bíblicos", layout="wide")
st.title("Buscador de Vídeos Virais")

# ----------------------
# Sidebar: Configurações de Busca
# ----------------------
st.sidebar.header("Configurações de Busca")

# Termos de Busca
TERMO_BUSCA_PADRAO = "termos_busca.txt"
valor_termos = ""
if os.path.exists(TERMO_BUSCA_PADRAO):
    with open(TERMO_BUSCA_PADRAO, encoding="utf-8") as f:
        valor_termos = f.read()
termos_input = st.sidebar.text_area(
    "Termos para buscar (1 por linha):", value=valor_termos, height=150
)
termos = [t.strip() for t in termos_input.splitlines() if t.strip()]

# Termos Negativos
NEGATIVOS_PADRAO = "termos_excluir.txt"
valor_negativos = ""
if os.path.exists(NEGATIVOS_PADRAO):
    with open(NEGATIVOS_PADRAO, encoding="utf-8") as f:
        valor_negativos = f.read()
negativos_input = st.sidebar.text_area(
    "Excluir títulos que contenham (1 por linha):", value=valor_negativos, height=150
)
negativos = [t.strip().lower() for t in negativos_input.splitlines() if t.strip()]

# Canais a Excluir
CANAIS_EXCLUIR_PADRAO = "canais_excluir.txt"
valor_canais = ""
if os.path.exists(CANAIS_EXCLUIR_PADRAO):
    with open(CANAIS_EXCLUIR_PADRAO, encoding="utf-8") as f:
        valor_canais = f.read()
canais_input = st.sidebar.text_area(
    "Excluir vídeos destes canais (1 por linha):", value=valor_canais, height=150
)
canais_excluidos = [c.strip().lower() for c in canais_input.splitlines() if c.strip()]

# Parâmetros Adicionais
st.sidebar.subheader("Filtros Avançados")
max_results = st.sidebar.number_input("Quantidade de vídeos a buscar:", min_value=1, max_value=200, value=50)
min_views = st.sidebar.number_input("Visualizações mínimas:", min_value=0, value=10000, step=1000)
min_inscritos = st.sidebar.number_input("Mínimo de inscritos no canal:", min_value=0, value=0, step=100)
max_inscritos = st.sidebar.number_input("Máximo de inscritos no canal:", min_value=0, value=10000000, step=1000)
max_idade_dias = st.sidebar.number_input("Idade máxima do vídeo (dias, 0 = sem filtro):", min_value=0, value=180, step=1)

pais = st.sidebar.selectbox("Filtrar por país:", ["Todos", "BR", "US", "IL", "IN", "PT", "MX"])
region_code = None if pais == "Todos" else pais

idioma = st.sidebar.selectbox("Filtrar por idioma:", ["Todos", "Português", "Inglês", "Espanhol"])
lang_map = {"Todos": None, "Português": "pt", "Inglês": "en", "Espanhol": "es"}
relevance_language = lang_map[idioma]

duracao = st.sidebar.selectbox("Filtrar duração:", ["Todos", "Curtos (<4min)", "Médios (4-20min)", "Longos (>20min)"])
duracao_map = {"Todos": "any", "Curtos (<4min)": "short", "Médios (4-20min)": "medium", "Longos (>20min)": "long"}
video_duration = duracao_map[duracao]

# ----------------------
# Botão de Ação
# ----------------------
if st.sidebar.button("Buscar vídeos"):
    # Combina termos para OR
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

    # Aplica filtros locais de exclusão
    if not df.empty:
        if negativos:
            df = df[~df['title'].str.lower().str.contains('|'.join(negativos))]
        if canais_excluidos:
            df = df[~df['channel'].str.lower().isin(canais_excluidos)]

    if df.empty:
        st.warning("Nenhum vídeo encontrado com os filtros aplicados.")
        st.session_state.df_resultados = None
    else:
        # Processa colunas adicionais
        df['published_at'] = pd.to_datetime(df['published_at'])
        df['dias_desde_pub'] = (pd.Timestamp.utcnow() - df['published_at']).dt.days
        df['views_por_dia'] = (df['views'] / df['dias_desde_pub'].replace(0, 1)).round(2)
        df['thumbnail_url'] = df['thumbnail']
        df['link_url'] = df['video_url']
        df['link_md'] = df['video_url'].apply(lambda x: f"[Abrir vídeo]({x})")
        st.session_state.df_resultados = df
        st.success(f"{len(df)} vídeos encontrados.")

# ----------------------
# Exibição dos Resultados
# ----------------------
if st.session_state.df_resultados is not None:
    df = st.session_state.df_resultados.copy()
    # Tabela ordenável com URLs brutos e thumb URL
    st.dataframe(df[[
        'thumbnail_url', 'title', 'channel', 'views', 'views_por_dia',
        'duration', 'published_at', 'link_url'
    ]])

    # Miniaturas e links clicáveis
    st.markdown("### Miniaturas e Links")
    for _, row in df.iterrows():
        cols = st.columns([1, 4])
        cols[0].image(row['thumbnail'], width=120)
        cols[1].markdown(
            f"**{row['title']}**  \n"
            f"Canal: {row['channel']}  \n"
            f"Views: {row['views']}  \n"
            f"Publicado em: {row['published_at'].date()}  \n"
            f"{row['link_md']}"
        )

    # Botões de download
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
