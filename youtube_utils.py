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
                  video_duration='any', relevance_language=None):
    resultados = []
    published_after = (datetime.utcnow() - timedelta(days=2*365)).isoformat('T') + 'Z'
    next_page_token = None

    while len(resultados) < max_results:
        params = {
            'part': 'snippet',
            'q': termo,
            'type': 'video',
            'order': 'viewCount',
            'videoDuration': video_duration,
            'publishedAfter': published_after,
            'maxResults': 50,
            'key': API_KEY
        }
        if region_code:
            params['regionCode'] = region_code
        if relevance_language:
            params['relevanceLanguage'] = relevance_language
        if next_page_token:
            params['pageToken'] = next_page_token

        resp = requests.get('https://www.googleapis.com/youtube/v3/search', params=params).json()
        next_page_token = resp.get('nextPageToken')
        items = resp.get('items', [])
        if not items:
            break

        for item in items:
            snippet = item['snippet']
            default_audio_language = snippet.get('defaultAudioLanguage')
            thumbnail_url = snippet.get('thumbnails', {}).get('default', {}).get('url')
            if relevance_language and default_audio_language != relevance_language:
                continue

            video_id = item['id']['videoId']
            title = snippet['title']
            published_at = snippet['publishedAt']
            channel_id = snippet['channelId']
            channel_title = snippet['channelTitle']

            stats_items = requests.get(
                'https://www.googleapis.com/youtube/v3/videos',
                params={'part': 'statistics,contentDetails', 'id': video_id, 'key': API_KEY}
            ).json().get('items', [])
            if not stats_items:
                continue
            stats = stats_items[0]
            views = int(stats['statistics'].get('viewCount', 0))
            duration = stats['contentDetails']['duration']
            if parse_duration(duration).total_seconds() < 180 or views < min_views:
                continue

            pub_date = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ')
            if (datetime.utcnow() - pub_date).days > max_idade_dias:
                continue

            ch_items = requests.get(
                'https://www.googleapis.com/youtube/v3/channels',
                params={'part': 'statistics', 'id': channel_id, 'key': API_KEY}
            ).json().get('items', [])
            if not ch_items:
                continue
            subs = int(ch_items[0]['statistics'].get('subscriberCount', 0))
            if subs < min_subs or subs > max_subs:
                continue

            resultados.append({
                'video_id': video_id, 'title': title, 'published_at': published_at,
                'channel': channel_title, 'views': views,
                'likes': int(stats['statistics'].get('likeCount', 0)),
                'comments': int(stats['statistics'].get('commentCount', 0)),
                'duration': duration, 'search_term': termo,
                'subscribers': subs, 'thumbnail': thumbnail_url,
                'default_audio_language': default_audio_language
            })
            time.sleep(0.1)
            if len(resultados) >= max_results:
                break

        if not next_page_token:
            break

    return resultados[:max_results], next_page_token

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
