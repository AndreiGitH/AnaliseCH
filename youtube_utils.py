import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import re
from urllib.request import urlretrieve
import streamlit as st
from isodate import parse_duration
import zipfile

API_KEY = st.secrets["API_KEY"]

# ---------------------------------------------------------------------------
# Função principal: buscar_videos -------------------------------------------------
# ---------------------------------------------------------------------------
#   • Pagina automaticamente enquanto houver nextPageToken.
#   • Aplica filtros min_views, idade máxima, inscritos‑canal, duração ≥ 180 s.
#   • Agora injeta o campo "video_url" (link clicável) e deixa o filtro de
#     inscritos opcional (se max_subs == 0 não filtra teto; se min_subs == 0 não
#     filtra piso).
# ---------------------------------------------------------------------------

def buscar_videos(
    termo: str,
    max_results: int = 30,
    min_views: int = 10_000,
    max_idade_dias: int = 180,
    min_subs: int = 1_000,
    max_subs: int = 1_000_000,
    region_code: str | None = None,
    video_duration: str = "any",
    relevance_language: str | None = None,
):
    resultados: list[dict] = []
    next_page_token: str | None = None

    # dois anos de recorte para PublishedAfter (pode ser ajustado externamente)
    published_after = (
        datetime.utcnow() - timedelta(days=365 * 2)
    ).isoformat("T") + "Z"

    while len(resultados) < max_results:
        params = {
            "part": "snippet",
            "q": termo,
            "type": "video",
            "order": "viewCount",
            "videoDuration": video_duration,
            "publishedAfter": published_after,
            "maxResults": 50,
            "key": API_KEY,
        }
        if region_code:
            params["regionCode"] = region_code
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        if next_page_token:
            params["pageToken"] = next_page_token

        search_data = requests.get(
            "https://www.googleapis.com/youtube/v3/search", params=params
        ).json()

        next_page_token = search_data.get("nextPageToken")
        for item in search_data.get("items", []):
            try:
                snip = item["snippet"]
                default_lang = snip.get("defaultAudioLanguage")
                if relevance_language and default_lang != relevance_language:
                    continue

                video_id = item["id"]["videoId"]
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                title = snip["title"]
                published_at = snip["publishedAt"]
                channel_id = snip["channelId"]
                channel_title = snip["channelTitle"]
                thumb_url = snip.get("thumbnails", {}).get("default", {}).get("url")

                # -------- Stats do vídeo --------
                stats_data = requests.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "part": "statistics,contentDetails",
                        "id": video_id,
                        "key": API_KEY,
                    },
                ).json()
                if not stats_data.get("items"):
                    continue
                vstats = stats_data["items"][0]
                views = int(vstats["statistics"].get("viewCount", 0))
                duration = vstats["contentDetails"]["duration"]

                # Filtros: views e duração (≥ 3 min)
                if views < min_views or parse_duration(duration).total_seconds() < 180:
                    continue

                # Filtro: idade do vídeo
                pub_dt = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
                if (datetime.utcnow() - pub_dt).days > max_idade_dias:
                    continue

                # -------- Stats do canal --------
                ch_stats = requests.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={
                        "part": "statistics",
                        "id": channel_id,
                        "key": API_KEY,
                    },
                ).json()
                if not ch_stats.get("items"):
                    continue
                subs = int(ch_stats["items"][0]["statistics"].get("subscriberCount", 0))

                # Inscritos – só filtra se o usuário realmente definir limites >0
                if (min_subs and subs < min_subs) or (max_subs and max_subs > 0 and subs > max_subs):
                    continue

                resultados.append(
                    {
                        "video_id": video_id,
                        "video_url": video_url,
                        "title": title,
                        "published_at": published_at,
                        "channel": channel_title,
                        "views": views,
                        "likes": int(vstats["statistics"].get("likeCount", 0)),
                        "comments": int(vstats["statistics"].get("commentCount", 0)),
                        "duration": duration,
                        "search_term": termo,
                        "subscribers": subs,
                        "thumbnail": thumb_url,
                        "default_audio_language": default_lang,
                    }
                )

                # pequena pausa para respeitar quotas
                time.sleep(0.05)

                if len(resultados) >= max_results:
                    break
            except Exception as exc:
                print("[buscar_videos] erro:", exc)
                continue

        if not next_page_token:
            break

    return resultados[:max_results]


# ---------------------------------------------------------------------------
# Utilidades de arquivo / thumbnails ---------------------------------------
# ---------------------------------------------------------------------------

def limpar_nome_arquivo(titulo: str) -> str:
    """Sanitiza título para uso como nome de arquivo."""
    return re.sub(r"[\\/*?:\"<>|]", "", titulo)[:100]


def baixar_thumbs(df: pd.DataFrame, pasta: str = "thumbs") -> str:
    os.makedirs(pasta, exist_ok=True)
    arquivos = []
    for _, row in df.iterrows():
        vid = row["video_id"]
        titulo = limpar_nome_arquivo(row["title"])
        url = row.get("thumbnail") or f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
        destino = os.path.join(pasta, f"{titulo}_{vid}.jpg")
        try:
            urlretrieve(url, destino)
            arquivos.append(destino)
        except Exception as e:
            print("Erro ao baixar thumb", vid, e)
    zip_path = "thumbnails.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for arq in arquivos:
            zf.write(arq, arcname=os.path.basename(arq))
    return zip_path
