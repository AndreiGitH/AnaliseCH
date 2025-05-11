import requests, time, os, re, zipfile
from datetime import datetime, timedelta
from urllib.request import urlretrieve

import pandas as pd
import streamlit as st
from isodate import parse_duration

API_KEY = st.secrets["API_KEY"]

# ---------------------------------------------------------------------------
# buscar_videos
#   • Page‑token primeiro → paginação externa opcional
#   • Filtros ignorados quando valor = 0 (idade, views, subs)
#   • Retorna (lista_resultados, next_page_token)
# ---------------------------------------------------------------------------

def buscar_videos(
    termo: str,
    max_results: int = 30,
    min_views: int = 0,
    max_idade_dias: int = 0,
    min_subs: int = 0,
    max_subs: int = 0,
    region_code: str | None = None,
    video_duration: str = "any",
    relevance_language: str | None = None,
    page_token: str | None = None,
):
    resultados: list[dict] = []
    next_token: str | None = page_token  # permite iniciar em página arbitrária

    published_after = None
    if max_idade_dias > 0:
        published_after = (
            datetime.utcnow() - timedelta(days=max_idade_dias)
        ).isoformat("T") + "Z"

    while len(resultados) < max_results:
        params = {
            "part": "snippet",
            "q": termo,
            "type": "video",
            "order": "viewCount",
            "videoDuration": video_duration,
            "maxResults": 50,
            "key": API_KEY,
        }
        if published_after:
            params["publishedAfter"] = published_after
        if region_code:
            params["regionCode"] = region_code
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        if next_token:
            params["pageToken"] = next_token

        search = requests.get("https://www.googleapis.com/youtube/v3/search", params=params).json()
        next_token = search.get("nextPageToken")

        for it in search.get("items", []):
            try:
                snip = it["snippet"]
                if relevance_language and snip.get("defaultAudioLanguage") != relevance_language:
                    continue

                vid = it["id"]["videoId"]
                video_url = f"https://www.youtube.com/watch?v={vid}"
                title = snip["title"]
                pub_at = snip["publishedAt"]
                chan_id = snip["channelId"]
                chan_title = snip["channelTitle"]
                thumb = snip.get("thumbnails", {}).get("default", {}).get("url")

                # Stats vídeo ------------------------------------------------
                vstats_json = requests.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "statistics,contentDetails", "id": vid, "key": API_KEY},
                ).json()
                if not vstats_json.get("items"):
                    continue
                vstats = vstats_json["items"][0]
                views = int(vstats["statistics"].get("viewCount", 0))
                duration = vstats["contentDetails"]["duration"]

                if min_views and views < min_views:
                    continue
                if parse_duration(duration).total_seconds() < 180:
                    continue  # rejeita < 3 min

                # filtro idade local
                if max_idade_dias > 0:
                    pub_dt = datetime.strptime(pub_at, "%Y-%m-%dT%H:%M:%SZ")
                    if (datetime.utcnow() - pub_dt).days > max_idade_dias:
                        continue

                # Stats canal ----------------------------------------------
                cstats_json = requests.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "statistics", "id": chan_id, "key": API_KEY},
                ).json()
                if not cstats_json.get("items"):
                    continue
                subs = int(cstats_json["items"][0]["statistics"].get("subscriberCount", 0))

                if (min_subs and subs < min_subs) or (max_subs and subs > max_subs):
                    continue

                resultados.append(
                    {
                        "video_id": vid,
                        "video_url": video_url,
                        "title": title,
                        "published_at": pub_at,
                        "channel": chan_title,
                        "views": views,
                        "likes": int(vstats["statistics"].get("likeCount", 0)),
                        "comments": int(vstats["statistics"].get("commentCount", 0)),
                        "duration": duration,
                        "search_term": termo,
                        "subscribers": subs,
                        "thumbnail": thumb,
                        "default_audio_language": snip.get("defaultAudioLanguage"),
                    }
                )
                if len(resultados) >= max_results:
                    break
            except Exception as err:
                print("[buscar_videos] erro:", err)
                continue
        if not next_token or len(resultados) >= max_results:
            break

        # Pequena pausa para não estourar cota
        time.sleep(0.05)

    return resultados[:max_results], next_token

# ---------------------------------------------------------------------------
# THUMBNAILS ---------------------------------------------------------------

def limpar_nome_arquivo(titulo: str) -> str:
    return re.sub(r"[\\/*?:\"<>|]", "", titulo)[:100]


def baixar_thumbs(df: pd.DataFrame, pasta: str = "thumbs") -> str:
    os.makedirs(pasta, exist_ok=True)
    arquivos = []
    for _, row in df.iterrows():
        vid = row["video_id"]
        nome = limpar_nome_arquivo(row["title"])
        url = row.get("thumbnail") or f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
        destino = os.path.join(pasta, f"{nome}_{vid}.jpg")
        try:
            urlretrieve(url, destino)
            arquivos.append(destino)
        except Exception as e:
            print("Erro thumb", vid, e)
    zip_path = "thumbnails.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for arq in arquivos:
            zf.write(arq, arcname=os.path.basename(arq))
    return zip_path
