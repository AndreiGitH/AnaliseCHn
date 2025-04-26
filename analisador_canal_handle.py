import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from datetime import datetime
import io
import os
import requests
import re
import zipfile

st.title("📺 Analisador de Canal do YouTube por Handle")
HANDLE = st.text_input("🔎 Handle do canal (sem @)", "DuneGG")

API_KEY = st.secrets["API_KEY"]
HANDLE = st.text_input("\ud83d\udd0e Handle do canal (sem @)", "DuneGG")

if "df_resultados" not in st.session_state:
    st.session_state.df_resultados = None

def sanitize(nome: str, limite=80):
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome)
    return nome_limpo[:limite].strip()

def baixar_thumbs(df, pasta="thumbs"):
    os.makedirs(pasta, exist_ok=True)
    qualidades = ["maxresdefault", "hqdefault", "mqdefault", "sddefault", "default"]
    arquivos_thumbs = []

    for _, row in df.iterrows():
        vid = row["video_id"]
        title = sanitize(row["title"])
        arq = os.path.join(pasta, f"{title}_{vid}.jpg")

        for q in qualidades:
            url = f"https://i.ytimg.com/vi/{vid}/{q}.jpg"
            try:
                r = requests.get(url, timeout=8)
                if r.status_code == 200 and len(r.content) > 1500:
                    with open(arq, "wb") as f:
                        f.write(r.content)
                    arquivos_thumbs.append(arq)
                    break
            except requests.RequestException:
                pass  # tenta próxima qualidade

    # Compactar em ZIP
    zip_path = "thumbs.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in arquivos_thumbs:
            zipf.write(file, arcname=os.path.basename(file))
    return zip_path

if st.button("Buscar vídeos do canal"):
    if not API_KEY or not HANDLE:
        st.error("Por favor, preencha a chave da API e o handle do canal.")
    else:
        with st.spinner("Consultando YouTube..."):
            youtube = build('youtube', 'v3', developerKey=API_KEY)

            resp_handle = youtube.channels().list(
                part='id,contentDetails',
                forHandle=HANDLE
            ).execute()

            if not resp_handle.get('items'):
                st.error(f"Canal com handle @{HANDLE} não encontrado.")
                st.stop()

            ch = resp_handle['items'][0]
            uploads_playlist_id = ch['contentDetails']['relatedPlaylists']['uploads']

            video_ids = []
            next_page = None
            while True:
                pl = youtube.playlistItems().list(
                    part='snippet',
                    playlistId=uploads_playlist_id,
                    maxResults=50,
                    pageToken=next_page
                ).execute()
                video_ids.extend(item['snippet']['resourceId']['videoId'] for item in pl['items'])
                next_page = pl.get('nextPageToken')
                if not next_page:
                    break

            data = []
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                resp = youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(batch)
                ).execute().get('items', [])
                for vid in resp:
                    sn = vid['snippet']
                    stats = vid.get('statistics', {})
                    cd = vid.get('contentDetails', {})
                    data.append({
                        'video_id':       vid['id'],
                        'title':          sn['title'],
                        'published_at':   sn['publishedAt'],
                        'view_count':     int(stats.get('viewCount', 0)),
                        'like_count':     int(stats.get('likeCount', 0)),
                        'comment_count':  int(stats.get('commentCount', 0)),
                        'duration':       cd.get('duration'),
                    })

            df = pd.DataFrame(data)
            df['published_at'] = pd.to_datetime(df['published_at'], utc=True)
            df['days_since_publication'] = (pd.Timestamp.now(tz='UTC') - df['published_at']).dt.days
            df['views_per_day'] = (df['view_count'] / df['days_since_publication'].replace(0, 1)).round(2)

            st.session_state.df_resultados = df

if st.session_state.df_resultados is not None:
    df = st.session_state.df_resultados
    st.success(f"{len(df)} vídeos encontrados.")
    st.dataframe(df[['title', 'view_count', 'views_per_day', 'published_at']])

    csv = io.BytesIO()
    df.to_csv(csv, sep=';', decimal=',', encoding='utf-8-sig', index=False, float_format='%.2f')
    st.download_button("📅 Baixar CSV", data=csv.getvalue(), file_name=f"youtube_channel_data_{HANDLE}.csv", mime="text/csv")

    if st.button("📸 Baixar Thumbnails"):
        zip_file_path = baixar_thumbs(df)
    
        with open(zip_file_path, "rb") as fp:
            st.download_button(
                label="💾 Baixar ZIP de Thumbnails",
                data=fp,
                file_name=f"thumbs_{HANDLE}.zip",
                mime="application/zip"
            )

