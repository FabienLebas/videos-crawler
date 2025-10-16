# youtube_agent.py
# Ce fichier contient la logique backend pour l'analyse des chaînes YouTube.

import os
import re
import time
import ssl
import urllib3
import subprocess
import json
from pathlib import Path
import whisper

# --- CORRECTIF POUR L'ERREUR SSL: CERTIFICATE_VERIFY_FAILED ---
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- DOSSIER DE CACHE POUR LES TRANSCRIPTIONS ---
TRANSCRIPTIONS_DIR = "transcriptions_cache"
Path(TRANSCRIPTIONS_DIR).mkdir(exist_ok=True)

# --- CHARGEMENT DU MODÈLE WHISPER (GLOBAL) ---
model_cache = {}

def load_whisper_model(model_name="base"):
    if model_name not in model_cache:
        print(f"Chargement du modèle Whisper '{model_name}'...")
        model_cache[model_name] = whisper.load_model(model_name)
        print(f"Modèle '{model_name}' chargé.")
    return model_cache[model_name]

def generate_cache_filename(video_url: str) -> str:
    """Génère un nom de fichier unique basé sur l'URL de la vidéo"""
    import hashlib
    url_hash = hashlib.md5(video_url.encode()).hexdigest()
    return f"transcription_{url_hash}.json"

def get_cached_transcription(video_url: str) -> dict:
    """
    Récupère une transcription en cache si elle existe.
    Retourne un dictionnaire avec 'transcript' et 'title', ou None si pas en cache.
    """
    cache_file = Path(TRANSCRIPTIONS_DIR) / generate_cache_filename(video_url)
    
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('url') == video_url:  # Vérifier que c'est la bonne vidéo
                    print(f"✓ Transcription trouvée en cache pour : {data.get('title')}")
                    return data
        except Exception as e:
            print(f"Erreur lors de la lecture du cache : {e}")
    
    return None

def save_transcription_cache(video_url: str, title: str, transcript: str) -> None:
    """Sauvegarde la transcription en cache"""
    cache_file = Path(TRANSCRIPTIONS_DIR) / generate_cache_filename(video_url)
    
    data = {
        'url': video_url,
        'title': title,
        'transcript': transcript,
        'timestamp': time.time()
    }
    
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ Transcription sauvegardée : {cache_file.name}")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du cache : {e}")

# --- FONCTION CORRIGÉE AVEC YT-DLP ---
def get_video_details(url_input: str) -> list:
    """
    Récupère les détails (URL, titre, durée) d'une vidéo unique OU de toutes
    les vidéos d'une chaîne en utilisant yt-dlp pour une meilleure stabilité.
    """
    print(f"Utilisation de yt-dlp pour récupérer les informations de : {url_input}")
    
    # Détection simple si c'est une playlist ou une chaîne
    is_playlist_or_channel = 'playlist?list=' in url_input or '/@' in url_input or '/channel/' in url_input or '/c/' in url_input

    try:
        if is_playlist_or_channel:
            # On demande à yt-dlp de traiter l'URL comme une playlist
            command = [
                "yt-dlp",
                "--quiet", "--no-warnings",
                "-J", # Raccourci pour --dump-json
                "--flat-playlist",
                "--no-check-certificates", # Désactiver la vérification SSL
                url_input
            ]
        else:
            # Pour une vidéo unique, on ne met pas --flat-playlist
            command = [
                "yt-dlp",
                "--quiet", "--no-warnings",
                "-J",
                "--no-check-certificates", # Désactiver la vérification SSL
                url_input
            ]

        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
        data = json.loads(result.stdout)
        
        videos_details = []

        if data.get('_type') == 'playlist':
            print(f"Chaîne/Playlist détectée : {data.get('title')}")
            for entry in data.get('entries', []):
                duration = entry.get('duration', 0)
                duration_formatted = time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A"
                
                videos_details.append({
                    "title": entry.get('title', 'Titre indisponible'),
                    "duration": duration_formatted,
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}" # On reconstruit l'URL propre
                })
        else:
            print("Vidéo unique détectée.")
            duration = data.get('duration', 0)
            duration_formatted = time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A"
            videos_details.append({
                "title": data.get('title', 'Titre indisponible'),
                "duration": duration_formatted,
                "url": data.get('webpage_url', url_input)
            })
            
        print(f"{len(videos_details)} vidéo(s) trouvée(s).")
        return videos_details

    except FileNotFoundError:
        print("ERREUR : yt-dlp n'est pas installé ou n'est pas dans le PATH.")
        return []
    except subprocess.CalledProcessError as e:
        print(f"Erreur yt-dlp : {e.stderr}")
        return []
    except Exception as e:
        print(f"Une erreur inattendue est survenue : {e}")
        return []


# --- FONCTION POUR RÉCUPÉRER LE TITRE ---
def get_video_title(video_url: str) -> str:
    """Récupère le titre de la vidéo via yt-dlp"""
    try:
        command = [
            "yt-dlp",
            "--quiet", "--no-warnings",
            "-J",
            "--no-check-certificates",
            video_url
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
        data = json.loads(result.stdout)
        return data.get('title', 'Titre indisponible')
    except Exception as e:
        print(f"Erreur lors de la récupération du titre : {e}")
        return "Titre indisponible"

# --- FONCTION DE TRANSCRIPTION REVUE AVEC YT-DLP ---
def transcribe_video_local(video_url: str, model_name: str) -> tuple:
    """
    Transcrit une vidéo YouTube.
    Retourne un tuple (transcript, title).
    """
    # Vérifier le cache d'abord
    cached = get_cached_transcription(video_url)
    if cached:
        return cached['transcript'], cached['title']
    
    audio_filename = f"audio_temp_{int(time.time())}.mp3"
    try:
        video_title = get_video_title(video_url)
        print(f"Traitement de la vidéo : '{video_title}'")
        
        print(f"Téléchargement et conversion de l'audio avec yt-dlp...")
        command = [
            "yt-dlp",
            "-x", # Extraire l'audio
            "--audio-format", "mp3",
            "--audio-quality", "0", # Meilleure qualité
            "-o", audio_filename, # Fichier de sortie
            "--no-check-certificates", # Désactiver la vérification SSL
            video_url
        ]
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)

        if not os.path.exists(audio_filename):
            print("Le téléchargement de l'audio a échoué.")
            return "", video_title

        print("Chargement du modèle Whisper local...")
        model = load_whisper_model(model_name)
        
        print(f"Lancement de la transcription locale avec le modèle '{model_name}'...")
        result = model.transcribe(audio_filename, fp16=False) # fp16=False pour compatibilité Mac
        transcript = result["text"]
        
        print(f"Transcription locale terminée pour '{video_title}'.")
        
        # Sauvegarder en cache
        save_transcription_cache(video_url, video_title, transcript)
        
        return transcript, video_title

    except Exception as e:
        print(f"Erreur lors de la transcription de {video_url}: {e}")
        return "", "Titre indisponible"
    finally:
        if os.path.exists(audio_filename):
            os.remove(audio_filename)


def normalize_text(text: str) -> str:
    """Normalise le texte : minuscules, supprime accents et tirets"""
    import unicodedata
    # Convertir en minuscules
    text = text.lower()
    # Supprimer les accents
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return text

def analyze_transcription(transcription: str, keywords: list) -> dict:
    """
    Analyse la transcription pour trouver les mots-clés.
    Supporte les correspondances partielles et ignore la casse/accents.
    
    Pour un mot-clé multi-mots comme "gambit dame", cherche aussi les 
    correspondances partielles comme "Gambit d'âme".
    """
    analysis = {}
    normalized_transcript = normalize_text(transcription)
    
    for keyword in keywords:
        keyword = keyword.strip()
        normalized_keyword = normalize_text(keyword)
        
        # Diviser le mot-clé en mots individuels
        keyword_words = normalized_keyword.split()
        
        count = 0
        
        if len(keyword_words) == 1:
            # Recherche simple avec limite de mot (word boundaries)
            pattern = r'\b' + re.escape(keyword_words[0]) + r'\b'
            count = len(re.findall(pattern, normalized_transcript, re.IGNORECASE))
        else:
            # Pour les mots-clés multi-mots, chercher chaque mot avec une certaine proximité
            # On accepte les correspondances partielles (au moins 50% des mots trouvés)
            min_words_required = max(1, len(keyword_words) // 2)  # Au moins 50% des mots
            
            # Créer un pattern qui accepte des variations
            # Par exemple "gambit dame" cherche "gambit" suivi (avec du texte entre) par "dame"
            pattern_parts = [r'\b' + re.escape(word) + r'\b' for word in keyword_words]
            # Permettre jusqu'à 3 mots entre chaque mot-clé
            flexible_pattern = r'\s+(?:\S+\s+){0,3}'.join(pattern_parts)
            
            matches = re.finditer(flexible_pattern, normalized_transcript, re.IGNORECASE)
            count = len(list(matches))
            
            # Si pas de correspondance exacte, chercher les correspondances partielles
            if count == 0:
                # Chercher au moins min_words_required mots consécutifs ou proches
                words_found = 0
                for word in keyword_words:
                    if re.search(r'\b' + re.escape(word) + r'\b', normalized_transcript, re.IGNORECASE):
                        words_found += 1
                
                if words_found >= min_words_required:
                    count = 1  # Au moins une correspondance partielle trouvée
        
        analysis[keyword] = count
    
    return analysis


def run_full_analysis(video_urls: list, keywords: list, whisper_model: str, progress_callback=None):
    total_videos = len(video_urls)
    if total_videos == 0:
        return {'total_videos': 0, 'total_occurrences': 0, 'details': {}}

    results = {
        'total_videos': total_videos,
        'total_occurrences': 0,
        'details': {keyword.strip(): [] for keyword in keywords}
    }
    
    load_whisper_model(whisper_model)

    for i, url in enumerate(video_urls):
        if progress_callback:
            progress_callback(i / total_videos, f"Analyse de la vidéo {i+1}/{total_videos}...")
        
        transcription, title = transcribe_video_local(url, whisper_model)
            
        if transcription:
            analysis = analyze_transcription(transcription, keywords)
            for keyword, count in analysis.items():
                if count > 0:
                    results['details'][keyword].append((title, url, count))
                    results['total_occurrences'] += count
    
    if progress_callback:
        progress_callback(1.0, "Analyse terminée !")

    return results