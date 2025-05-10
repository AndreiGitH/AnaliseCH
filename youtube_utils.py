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

def buscar_videos(termo, max_results=30, min_views=10000, max_idade_dias=180,
                  min_subs=1000, max_subs=1000000, region_code=None,
                  video_duration="any", relevance_language=None,
                  page_token=None):
    resultados = []
    next_page_token = None
    published_after = (datetime.utcnow() - timedelta(days=2*365)).isoformat("T") + "Z"

    base_url = 'https://www.googleapis.com/youtube/v3/search'
    params = {
        'part': 'snippet',
        'q': termo,
        'type': 'video',
        'order': 'viewCount',
        'videoDuration': video_duration,
        'publishedAfter': published_after,
        'maxResults': max_results,
        'key': API_KEY
    }
    if region_code:
        params['regionCode'] = region_code
    if relevance_language:
        params['relevanceLanguage'] = relevance_language
    if page_token:
        params['pageToken'] = page_token

    response = requests.get(base_url, params=params).json()
    next_page_token = response.get('nextPageToken')

    for item in response.get('items', []):
        try:
            snippet = item['snippet']
            video_id = item['id']['videoId']
            title = snippet['title']
            published_at = snippet['publishedAt']
            channel_title = snippet['channelTitle']
            channel_id = snippet['channelId']
            default_audio_language = snippet.get('defaultAudioLanguage')
            thumbnail_url = snippet.get('thumbnails', {}).get('default', {}).get('url')

            # Fetch video stats
            stats_url = 'https://www.googleapis.com/youtube/v3/videos'
            stats_params = {
                'part': 'statistics,contentDetails',
                'id': video_id,
                'key': API_KEY
            }
            stats_response = requests.get(stats_url, params=stats_params).json()
            items_stats = stats_response.get('items', [])
            if not items_stats:
                continue
            stats = items_stats[0]['statistics']
            duration = items_stats[0]['contentDetails']['duration']
            views = int(stats.get('viewCount', 0))

            # Duration filter: >= 180s
            duracao_segundos = parse_duration(duration).total_seconds()
            if duracao_segundos < 180:
                continue
            if views < min_views:
                continue

            # Age filter
            data_publicacao = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
            dias_desde_pub = (datetime.utcnow() - data_publicacao).days
            if dias_desde_pub > max_idade_dias:
                continue

            # Channel stats
            channel_url = 'https://www.googleapis.com/youtube/v3/channels'
            channel_params = {
                'part': 'statistics',
                'id': channel_id,
                'key': API_KEY
            }
            channel_response = requests.get(channel_url, params=channel_params).json()
            canal_info = channel_response.get('items', [])
            if not canal_info:
                continue
            subs = int(canal_info[0]['statistics'].get('subscriberCount', 0))
            if subs < min_subs or subs > max_subs:
                continue

            resultados.append({
                'video_id': video_id,
                'title': title,
                'published_at': published_at,
                'channel': channel_title,
                'views': views,
                'likes': int(stats.get('likeCount', 0)),
                'comments': int(stats.get('commentCount', 0)),
                'duration': duration,
                'search_term': termo,
                'subscribers': subs,
                'thumbnail': thumbnail_url,
                'default_audio_language': default_audio_language
            })
            time.sleep(0.1)
        except Exception as e:
            print("Erro:", e)
            continue

    return resultados, next_page_token

def limpar_nome_arquivo(titulo):
    return re.sub(r'[\\/*?:"<>|]', "", titulo)[:100]


def baixar_thumbs(df, pasta='thumbs'):
    os.makedirs(pasta, exist_ok=True)
    arquivos_thumbs = []
    for _, row in df.iterrows():
        video_id = row['video_id']
        titulo_limpo = limpar_nome_arquivo(row['title'])
        thumb_url = row.get('thumbnail') or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        caminho = os.path.join(pasta, f"{titulo_limpo}_{video_id}.jpg")
        try:
            urlretrieve(thumb_url, caminho)
            arquivos_thumbs.append(caminho)
            print(f"Thumb salva: {caminho}")
        except Exception as e:
            print(f"Erro ao baixar thumb {video_id}: {e}")
    zip_path = "thumbs.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for arquivo in arquivos_thumbs:
            zipf.write(arquivo, arcname=os.path.basename(arquivo))
    return zip_path
