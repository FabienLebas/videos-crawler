# youtube_agent.py
# Ce fichier contient la logique backend pour l'analyse des chaînes YouTube.

import os
import re
import time
import ssl
import urllib3
import subprocess
import json
from pytube import YouTube
from pydub import AudioSegment
import openai
import httpx

# --- CORRECTIF POUR L'ERREUR SSL: CERTIFICATE_VERIFY_FAILED ---
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_video_details(url_input: str) -> list:
    """
    Récupère les détails (URL, titre, durée) d'une vidéo unique OU de toutes
    les vidéos d'une chaîne en utilisant yt-dlp (plus stable que Pytube).
    """
    # --- DÉTECTION DU TYPE D'URL ---
    if "/watch?v=" in url_input or "youtu.be/" in url_input:
        print("URL de vidéo unique détectée.")
        try:
            yt = YouTube(url_input)
            duration_seconds = yt.length
            duration_formatted = time.strftime('%H:%M:%S', time.gmtime(duration_seconds))
            if duration_formatted.startswith("00:"):
                duration_formatted = duration_formatted[3:]
            
            video_details = [{
                "title": yt.title,
                "duration": duration_formatted,
                "url": yt.watch_url
            }]
            print("Détails de la vidéo unique récupérés.")
            return video_details
        except Exception as e:
            print(f"Une erreur est survenue lors de la récupération de la vidéo unique : {e}")
            return []

    # --- LOGIQUE POUR LES CHAÎNES (UTILISE YT-DLP) ---
    print("URL de chaîne détectée. Utilisation de yt-dlp pour récupérer les vidéos...")
    try:
        # Commande yt-dlp pour récupérer les URLs des vidéos au format JSON
        cmd = [
            "yt-dlp",
            "-j",
            "--flat-playlist",
            "--quiet",
            "--no-check-certificates",
            url_input
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"Erreur yt-dlp : {result.stderr}")
            return []
        
        videos_details = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                video_id = data.get('id')
                title = data.get('title', 'Titre indisponible')
                duration = data.get('duration', 0)
                
                if video_id:
                    duration_formatted = time.strftime('%H:%M:%S', time.gmtime(duration)) if duration else "0:00"
                    if duration_formatted.startswith("00:"):
                        duration_formatted = duration_formatted[3:]
                    
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    videos_details.append({
                        "title": title,
                        "duration": duration_formatted,
                        "url": video_url
                    })
            except json.JSONDecodeError:
                continue
        
        print(f"Récupération de {len(videos_details)} vidéos depuis la chaîne.")
        return videos_details[:250]  # Limite à 250 vidéos

    except FileNotFoundError:
        print("ERREUR : yt-dlp n'est pas installé.")
        print("Installez-le avec : pip install yt-dlp")
        return []
    except subprocess.TimeoutExpired:
        print("ERREUR : Timeout lors de la récupération des vidéos.")
        return []
    except Exception as e:
        print(f"ERREUR : {e}")
        return []


def transcribe_video(video_url: str, openai_api_key: str) -> str:
    """
    Télécharge l'audio d'une vidéo, le convertit et le transcrit avec Whisper.
    """
    try:
        # Nettoie l'URL en supprimant les paramètres de timestamp (&t=...)
        clean_url = video_url.split('&t=')[0] if '&t=' in video_url else video_url
        
        print(f"Téléchargement de l'audio avec yt-dlp...")
        
        # Utilise yt-dlp pour télécharger l'audio
        audio_file = f"audio_{int(time.time())}.mp3"
        cmd = [
            "yt-dlp",
            "-f", "bestaudio[ext=m4a]/bestaudio",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "192",
            "-o", audio_file,
            "--no-check-certificates",
            clean_url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            print(f"Erreur yt-dlp : {result.stderr}")
            return ""
        
        if not os.path.exists(audio_file):
            print(f"Fichier audio non créé")
            return ""
        
        audio_mp3_path = audio_file
        
        # Récupère le titre de la vidéo
        try:
            yt = YouTube(clean_url)
            print(f"Traitement de la vidéo : '{yt.title}'")
        except:
            print("Traitement de la vidéo...")
        
        print("Envoi à l'API OpenAI Whisper pour transcription...")
        
        # Vérifie que le fichier existe et sa taille
        file_size = os.path.getsize(audio_mp3_path)
        print(f"Taille du fichier audio : {file_size / (1024*1024):.2f} MB")
        
        if file_size > 25 * 1024 * 1024:
            print("Erreur : Le fichier audio dépasse 25MB (limite Whisper)")
            return ""
        
        try:
            # Crée un client OpenAI avec gestion SSL désactivée
            client = openai.OpenAI(
                api_key=openai_api_key,
                http_client=httpx.Client(verify=False)
            )
            print(f"Client OpenAI initialisé avec SSL désactivé")
            
            with open(audio_mp3_path, "rb") as audio_file:
                print(f"Envoi du fichier à Whisper...")
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            print(f"Transcription terminée.")
            return transcript
        except openai.APIConnectionError as e:
            print(f"Erreur de connexion OpenAI : {e}")
            print("Conseil : Vérifiez votre connexion Internet et vos paramètres proxy")
            return ""
        except openai.AuthenticationError as e:
            print(f"Erreur d'authentification OpenAI : {e}")
            print("Conseil : Vérifiez que votre clé API est correcte dans le fichier .env")
            return ""
        except Exception as e:
            print(f"Erreur OpenAI : {type(e).__name__}: {e}")
            return ""

    except Exception as e:
        print(f"Erreur lors de la transcription de {video_url}: {e}")
        return ""
    finally:
        # Nettoyage des fichiers temporaires
        if 'audio_mp3_path' in locals() and os.path.exists(audio_mp3_path):
            try:
                os.remove(audio_mp3_path)
            except:
                pass

def analyze_transcription(transcription: str, keywords: list) -> dict:
    """
    Analyse une transcription pour trouver les occurrences de mots-clés.
    """
    analysis = {}
    for keyword in keywords:
        count = len(re.findall(r'\b' + re.escape(keyword.strip()) + r'\b', transcription, re.IGNORECASE))
        analysis[keyword.strip()] = count
    return analysis

def run_full_analysis(video_urls: list, keywords: list, openai_api_key: str, progress_callback=None):
    """
    Orchestre l'ensemble du processus d'analyse pour une liste de vidéos donnée.
    """
    total_videos = len(video_urls)
    if total_videos == 0:
        return {'total_videos': 0, 'total_occurrences': 0, 'details': {}}

    results = {
        'total_videos': total_videos,
        'total_occurrences': 0,
        'details': {keyword.strip(): [] for keyword in keywords}
    }

    for i, url in enumerate(video_urls):
        if progress_callback:
            progress_callback(i / total_videos, f"Analyse de la vidéo {i+1}/{total_videos}...")

        try:
            yt = YouTube(url)
            title = yt.title
        except Exception:
            title = "Titre Indisponible"
            
        transcription = transcribe_video(url, openai_api_key)
        if transcription:
            analysis = analyze_transcription(transcription, keywords)
            for keyword, count in analysis.items():
                if count > 0:
                    results['details'][keyword].append((title, url, count))
                    results['total_occurrences'] += count
    
    if progress_callback:
        progress_callback(1.0, "Analyse terminée !")

    return results