import requests, time, os, re, zipfile
from datetime import datetime, timedelta
from urllib.request import urlretrieve

import pandas as pd
import streamlit as st
from isodate import parse_duration

API_KEY = st.secrets["API_KEY"]

# ---------------------------------------------------------------------------
# buscar_videos
#   • pagina automaticamente até juntar max_results
#   • filtros só valem se o parâmetro > 0
#   • aceita page_token de partida, caso o front‑end queira continuar
#   • devolve thumbnail e link pronto (video_url)
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
    next_token: str | None = page_token  # se vier do front‑end

    # publishedAfter só se max_idade_dias > 0
    published_after = None
    if max_idade_dias > 0:
        published_after = (datetime.utcnow() - timedelta(days=max_idade_dias)).isoformat("T") + "Z"

    while len(resultados) < max_results:
        # -------- 1ª chamada: /search ---------------------------------------
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

                vid       = it["id"]["videoId"]
                video_url = f"https://www.youtube.com/watch?v={vid}"
                title     = snip["title"]
                pub_at    = snip["publishedAt"]
                chan_id   = snip["channelId"]
                chan_ttl  = snip["channelTitle"]
                thumb     = snip.get("thumbnails", {}).get("default", {}).get("url")

                # -------- 2ª chamada: /videos (stats + duração) ---------------
                v = requests.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "statistics,contentDetails", "id": vid, "key": API_KEY},
                ).json()
                if not v.get("items"):
                    continue
                vstats    = v["items"][0]
                views     = int(vstats["statistics"].get("viewCount", 0))
                duration  = vstats["contentDetails"]["duration"]

                if min_views and views < min_views:
                    continue
                if parse_duration(duration).total_seconds() < 180:  # 3 min
                    continue

                # filtro de idade extra (caso max_idade_dias > 0)
                if max_idade_dias > 0:
                    pub_dt = datetime.strptime(pub_at, "%Y-%m-%dT%H:%M:%SZ")
                    if (datetime.utcnow() - pub_dt).days > max_idade_dias:
                        continue

                # -------- 3ª chamada: /channels (subs) ------------------------
                c = requests.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "statistics", "id": chan_id, "key": API_KEY},
                ).json()
                if not c.get("items"):
                    continue
                subs = int(c["items"][0]["statistics"].get("subscriberCount", 0))
                if (min_subs and subs < min_subs) or (max_subs and subs > max_subs):
                    continue

                resultados.append(
                    {
                        "video_id": vid,
                        "video_url": video_url,
                        "title": title,
                        "published_at": pub_at,
                        "channel": chan_ttl,
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
                time.sleep(0.05)
                if len(resultados) >= max_results:
                    break
            except Exception as err:
                print("[buscar_videos] erro:", err)
                continue

        if not next_token:
            break

    return resultados[:max_results]

# ---------------------------------------------------------------------------
# Utilidades de arquivo / thumbnails
# ---------------------------------------------------------------------------
def limpar_nome_arquivo(titulo: str) -> str:
    return re.sub(r"[\\/*?:\"<>|]", "", titulo)[:100]


def baixar_thumbs(df: pd.DataFrame, pasta: str = "thumbs") -> str:
    os.makedirs(pasta, exist_ok=True)
    arqs = []
    for _, row in df.iterrows():
        vid  = row["video_id"]
        nome = limpar_nome_arquivo(row["title"])
        url  = row.get("thumbnail") or f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
        dest = os.path.join(pasta, f"{nome}_{vid}.jpg")
        try:
            urlretrieve(url, dest)
            arqs.append(dest)
        except Exception as e:
            print("Thumb", vid, e)

    zpath = "thumbnails.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for a in arqs:
            zf.write(a, arcname=os.path.basename(a))
    return zpath
