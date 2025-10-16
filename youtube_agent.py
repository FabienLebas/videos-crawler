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
import locale

# --- CORRECTIF POUR L'ERREUR SSL: CERTIFICATE_VERIFY_FAILED ---
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- DÉTECTION DE LA LANGUE DU SYSTÈME ---
def get_system_language() -> str:
    """
    Détecte la langue du système et la retourne au format 'fr', 'en', 'es', etc.
    Si impossible, retourne 'en' par défaut.
    """
    try:
        lang = locale.getlocale()[0]
        if lang:
            # Extraire le code langue (ex: 'fr_FR' -> 'fr')
            lang_code = lang.split('_')[0].lower()
            return lang_code
        else:
            return 'en'
    except:
        return 'en'

# --- DOSSIER DE CACHE POUR LES TRANSCRIPTIONS ---
TRANSCRIPTIONS_DIR = "transcriptions_cache"
Path(TRANSCRIPTIONS_DIR).mkdir(exist_ok=True)

# --- FICHIER DE STATISTIQUES DE TEMPS ---
STATS_FILE = "transcription_stats.json"

def load_time_stats():
    """Charge les statistiques de temps d'une fichier JSON"""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Erreur lors du chargement des stats : {e}")
    return {}

def save_time_stats(stats):
    """Sauvegarde les statistiques de temps dans un fichier JSON"""
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des stats : {e}")

def get_average_processing_speed(model_name: str) -> float:
    """Retourne la vitesse moyenne de traitement (secondes de vidéo par seconde)"""
    stats = load_time_stats()
    model_stats = stats.get(model_name, {})
    
    if model_stats.get('total_processing_time', 0) > 0 and model_stats.get('total_video_duration', 0) > 0:
        # Vitesse = durée totale de vidéo / temps total de traitement
        speed = model_stats['total_video_duration'] / model_stats['total_processing_time']
        return speed
    return None

def estimate_processing_time(video_duration_seconds: float, model_name: str) -> float:
    """Estime le temps de traitement pour une vidéo"""
    speed = get_average_processing_speed(model_name)
    if speed:
        return video_duration_seconds / speed
    # Estimation par défaut si pas de données : ~0.3x (30% du temps vidéo)
    return video_duration_seconds * 0.3

def format_time(seconds: float) -> str:
    """Formate le temps en format lisible"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

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
def get_channel_id_from_url(url: str) -> str:
    """Extrait l'ID de la chaîne YouTube depuis une URL"""
    import re
    
    # Format: /@username
    match = re.search(r'/@([^/?]+)', url)
    if match:
        return f"@{match.group(1)}"
    
    # Format: /channel/ID
    match = re.search(r'/channel/([^/?]+)', url)
    if match:
        return match.group(1)
    
    # Format: /c/username
    match = re.search(r'/c/([^/?]+)', url)
    if match:
        return f"/c/{match.group(1)}"
    
    return None

def get_videos_from_channel(channel_identifier: str) -> list:
    """Récupère les vidéos de la playlist 'Videos' d'une chaîne"""
    # Construire l'URL de la playlist vidéos de la chaîne
    if channel_identifier.startswith('@'):
        # Format moderne: @username -> utiliser l'URL de la chaîne avec /videos
        playlist_url = f"https://www.youtube.com/{channel_identifier}/videos"
    else:
        # Format ancien: /channel/ID ou /c/username
        playlist_url = f"https://www.youtube.com/{channel_identifier}/videos"
    
    print(f"Récupération des vidéos depuis : {playlist_url}")
    
    try:
        lang = get_system_language()
        command = [
            "yt-dlp",
            "--quiet", "--no-warnings",
            "-J",
            "--flat-playlist",
            "--no-check-certificates",
            "--max-downloads", "1000",  # Limiter à 1000 vidéos pour éviter surcharge
            "--extractor-args", f"youtube:lang={lang}",  # Utiliser la langue du système
            playlist_url
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
        data = json.loads(result.stdout)
        
        videos_details = []
        
        if data.get('_type') == 'playlist':
            entries = data.get('entries', [])
            print(f"Chaîne détectée : {data.get('title')} - {len(entries)} vidéo(s) trouvée(s)")
            
            for entry in entries:
                if entry.get('id'):  # Vérifier qu'il y a un ID de vidéo valide
                    duration = entry.get('duration', 0)
                    duration_formatted = time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A"
                    
                    videos_details.append({
                        "title": entry.get('title', 'Titre indisponible'),
                        "duration": duration_formatted,
                        "url": f"https://www.youtube.com/watch?v={entry.get('id')}"
                    })
        
        return videos_details
    
    except Exception as e:
        print(f"Erreur lors de la récupération des vidéos de la chaîne : {e}")
        return []

def get_video_details(url_input: str) -> list:
    """
    Récupère les détails (URL, titre, durée) d'une vidéo unique OU de toutes
    les vidéos d'une chaîne en utilisant yt-dlp pour une meilleure stabilité.
    """
    print(f"Utilisation de yt-dlp pour récupérer les informations de : {url_input}")
    
    # Vérifier si c'est une chaîne
    is_channel = '/@' in url_input or '/channel/' in url_input or '/c/' in url_input
    is_playlist = 'playlist?list=' in url_input

    try:
        if is_channel:
            # Extraire l'identifiant de la chaîne et récupérer les vidéos
            channel_id = get_channel_id_from_url(url_input)
            if channel_id:
                return get_videos_from_channel(channel_id)
            else:
                print("Impossible d'extraire l'ID de la chaîne")
                return []
        
        elif is_playlist or not ('youtube.com/watch' in url_input or 'youtu.be' in url_input):
            # Playlist classique
            lang = get_system_language()
            command = [
                "yt-dlp",
                "--quiet", "--no-warnings",
                "-J",
                "--flat-playlist",
                "--no-check-certificates",
                "--extractor-args", f"youtube:lang={lang}",  # Utiliser la langue du système
                url_input
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
            data = json.loads(result.stdout)
            
            videos_details = []

            if data.get('_type') == 'playlist':
                print(f"Playlist détectée : {data.get('title')}")
                for entry in data.get('entries', []):
                    if entry.get('id'):
                        duration = entry.get('duration', 0)
                        duration_formatted = time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A"
                        
                        videos_details.append({
                            "title": entry.get('title', 'Titre indisponible'),
                            "duration": duration_formatted,
                            "url": f"https://www.youtube.com/watch?v={entry.get('id')}"
                        })
            
            return videos_details
        
        else:
            # Vidéo unique
            lang = get_system_language()
            command = [
                "yt-dlp",
                "--quiet", "--no-warnings",
                "-J",
                "--no-check-certificates",
                "--extractor-args", f"youtube:lang={lang}",  # Utiliser la langue du système
                url_input
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
            data = json.loads(result.stdout)
            
            print("Vidéo unique détectée.")
            duration = data.get('duration', 0)
            duration_formatted = time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A"
            
            return [{
                "title": data.get('title', 'Titre indisponible'),
                "duration": duration_formatted,
                "url": data.get('webpage_url', url_input)
            }]

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
        lang = get_system_language()
        command = [
            "yt-dlp",
            "--quiet", "--no-warnings",
            "-J",
            "--no-check-certificates",
            "--extractor-args", f"youtube:lang={lang}",  # Utiliser la langue du système
            video_url
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
        data = json.loads(result.stdout)
        return data.get('title', 'Titre indisponible')
    except Exception as e:
        print(f"Erreur lors de la récupération du titre : {e}")
        return "Titre indisponible"

# --- FONCTION DE TRANSCRIPTION REVUE AVEC YT-DLP ---
def transcribe_video_local(video_url: str, model_name: str, progress_callback=None) -> tuple:
    """
    Transcrit une vidéo YouTube.
    Retourne un tuple (transcript, title, processing_time).
    progress_callback(text) pour mettre à jour la barre de progression
    """
    start_time = time.time()
    
    # Vérifier le cache d'abord
    cached = get_cached_transcription(video_url)
    if cached:
        if progress_callback:
            progress_callback(f"✅ Récupération du cache : {cached['title'][:50]}")
        return cached['transcript'], cached['title'], 0  # 0 car pas de traitement
    
    audio_filename = f"audio_temp_{int(time.time())}.mp3"
    try:
        video_title = get_video_title(video_url)
        print(f"Traitement de la vidéo : '{video_title}'")
        
        if progress_callback:
            progress_callback(f"📥 Téléchargement et conversion de l'audio : {video_title[:50]}")
        
        command = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", audio_filename,
            "--no-check-certificates",
            video_url
        ]
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)

        if not os.path.exists(audio_filename):
            print("Le téléchargement de l'audio a échoué.")
            return "", video_title, 0

        if progress_callback:
            progress_callback(f"🤖 Chargement du modèle Whisper ({model_name})...")
        
        model = load_whisper_model(model_name)
        
        if progress_callback:
            progress_callback(f"🎙️ Transcription en cours : {video_title[:50]}")
        
        print(f"Lancement de la transcription locale avec le modèle '{model_name}'...")
        result = model.transcribe(audio_filename, fp16=False)
        transcript = result["text"]
        
        if progress_callback:
            progress_callback(f"💾 Sauvegarde du cache : {video_title[:50]}")
        
        print(f"Transcription locale terminée pour '{video_title}'.")
        
        # Sauvegarder en cache
        save_transcription_cache(video_url, video_title, transcript)
        
        # Calculer le temps de traitement
        processing_time = time.time() - start_time
        
        return transcript, video_title, processing_time

    except Exception as e:
        print(f"Erreur lors de la transcription de {video_url}: {e}")
        return "", "Titre indisponible", 0
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


def run_full_analysis(video_urls: list, keywords: list, whisper_model: str, progress_callback=None, stop_flag=None):
    total_videos = len(video_urls)
    if total_videos == 0:
        return {'total_videos': 0, 'total_occurrences': 0, 'details': {}}

    results = {
        'total_videos': total_videos,
        'total_occurrences': 0,
        'details': {keyword.strip(): [] for keyword in keywords}
    }
    
    load_whisper_model(whisper_model)
    
    # Charger les stats existantes
    stats = load_time_stats()
    if whisper_model not in stats:
        stats[whisper_model] = {
            'total_processing_time': 0,
            'total_video_duration': 0,
            'video_count': 0
        }

    for i, url in enumerate(video_urls):
        # Vérifier le flag d'arrêt
        if stop_flag:
            print("Arrêt demandé par l'utilisateur.")
            break
        
        progress = i / total_videos
        status = f"📹 Vidéo {i+1}/{total_videos}"
        
        if progress_callback:
            progress_callback(status)
        
        transcription, title, processing_time = transcribe_video_local(url, whisper_model, progress_callback)
        
        # Mettre à jour les stats si c'est une nouvelle transcription (processing_time > 0)
        if processing_time > 0:
            # Essayer d'obtenir la durée de la vidéo
            try:
                yt = YouTube(url)
                video_duration = yt.length
            except:
                video_duration = 0
            
            if video_duration > 0:
                stats[whisper_model]['total_processing_time'] += processing_time
                stats[whisper_model]['total_video_duration'] += video_duration
                stats[whisper_model]['video_count'] += 1
                save_time_stats(stats)
                
                speed = get_average_processing_speed(whisper_model)
                print(f"Vitesse actuelle : {speed:.2f}x")
            
        if transcription:
            analysis = analyze_transcription(transcription, keywords)
            for keyword, count in analysis.items():
                if count > 0:
                    results['details'][keyword].append((title, url, count))
                    results['total_occurrences'] += count
        
        # Mettre à jour la progression
        new_progress = (i + 1) / total_videos
        if progress_callback:
            progress_callback(f"✅ Vidéo {i+1}/{total_videos} complétée")
    
    if progress_callback:
        progress_callback("🎉 Analyse terminée !")

    return results