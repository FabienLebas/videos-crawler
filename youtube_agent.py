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
import uuid

ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_system_language() -> str:
    try:
        lang = locale.getlocale()[0]
        if lang:
            return lang.split('_')[0].lower()
        else:
            return 'en'
    except:
        return 'en'

TRANSCRIPTIONS_DIR = "transcriptions_cache"
Path(TRANSCRIPTIONS_DIR).mkdir(exist_ok=True)
STATS_FILE = "transcription_stats.json"

def load_time_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_time_stats(stats):
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_average_processing_speed(model_name: str) -> float:
    stats = load_time_stats()
    model_stats = stats.get(model_name, {})
    if model_stats.get('total_processing_time', 0) > 0 and model_stats.get('total_video_duration', 0) > 0:
        return model_stats['total_video_duration'] / model_stats['total_processing_time']
    return None

def estimate_processing_time(video_duration_seconds: float, model_name: str) -> float:
    speed = get_average_processing_speed(model_name)
    if speed:
        return video_duration_seconds / speed
    return video_duration_seconds * 0.3

def format_time(seconds: float) -> str:
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

def load_whisper_model(model_name="base"):
    print(f"Chargement du modèle Whisper '{model_name}'...")
    model = whisper.load_model(model_name)
    print(f"Modèle '{model_name}' chargé.")
    return model

def generate_cache_filename(video_url: str) -> str:
    import hashlib
    url_hash = hashlib.md5(video_url.encode()).hexdigest()
    return f"transcription_{url_hash}.json"

def get_cached_transcription(video_url: str) -> dict:
    cache_file = Path(TRANSCRIPTIONS_DIR) / generate_cache_filename(video_url)
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('url') == video_url:
                    print(f"✓ Transcription trouvée en cache pour : {data.get('title')}")
                    return data
        except Exception:
            pass
    return None

def save_transcription_cache(video_url: str, title: str, transcript: str) -> None:
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
    except Exception:
        pass

def get_channel_id_from_url(url: str) -> str:
    match = re.search(r'/@([^/?]+)', url)
    if match:
        return f"@{match.group(1)}"
    match = re.search(r'/channel/([^/?]+)', url)
    if match:
        return match.group(1)
    match = re.search(r'/c/([^/?]+)', url)
    if match:
        return f"/c/{match.group(1)}"
    return None

def get_videos_from_channel(channel_identifier: str) -> list:
    if channel_identifier.startswith('@'):
        playlist_url = f"https://www.youtube.com/{channel_identifier}/videos"
    else:
        playlist_url = f"https://www.youtube.com/{channel_identifier}/videos"
    try:
        lang = get_system_language()
        command = [
            "yt-dlp",
            "--quiet", "--no-warnings",
            "-J",
            "--flat-playlist",
            "--no-check-certificates",
            "--max-downloads", "1000",
            "--extractor-args", f"youtube:lang={lang}",
            playlist_url
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
        data = json.loads(result.stdout)
        videos_details = []
        if data.get('_type') == 'playlist':
            entries = data.get('entries', [])
            for entry in entries:
                if entry.get('id'):
                    duration = entry.get('duration', 0)
                    duration_formatted = time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A"
                    videos_details.append({
                        "title": entry.get('title', 'Titre indisponible'),
                        "duration": duration_formatted,
                        "url": f"https://www.youtube.com/watch?v={entry.get('id')}"
                    })
        return videos_details
    except Exception:
        return []

def get_video_details(url_input: str) -> list:
    is_channel = '/@' in url_input or '/channel/' in url_input or '/c/' in url_input
    is_playlist = 'playlist?list=' in url_input
    try:
        if is_channel:
            channel_id = get_channel_id_from_url(url_input)
            if channel_id:
                return get_videos_from_channel(channel_id)
            else:
                return []
        elif is_playlist or not ('youtube.com/watch' in url_input or 'youtu.be' in url_input):
            lang = get_system_language()
            command = [
                "yt-dlp",
                "--quiet", "--no-warnings",
                "-J",
                "--flat-playlist",
                "--no-check-certificates",
                "--extractor-args", f"youtube:lang={lang}",
                url_input
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
            data = json.loads(result.stdout)
            videos_details = []
            if data.get('_type') == 'playlist':
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
            lang = get_system_language()
            command = [
                "yt-dlp",
                "--quiet", "--no-warnings",
                "-J",
                "--no-check-certificates",
                "--extractor-args", f"youtube:lang={lang}",
                url_input
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
            data = json.loads(result.stdout)
            duration = data.get('duration', 0)
            duration_formatted = time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A"
            return [{
                "title": data.get('title', 'Titre indisponible'),
                "duration": duration_formatted,
                "url": data.get('webpage_url', url_input)
            }]
    except FileNotFoundError:
        return []
    except subprocess.CalledProcessError:
        return []
    except Exception:
        return []

def get_video_title(video_url: str) -> str:
    try:
        lang = get_system_language()
        command = [
            "yt-dlp",
            "--quiet", "--no-warnings",
            "-J",
            "--no-check-certificates",
            "--extractor-args", f"youtube:lang={lang}",
            video_url
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
        data = json.loads(result.stdout)
        return data.get('title', 'Titre indisponible')
    except Exception:
        return "Titre indisponible"

def transcribe_video_local(video_url: str, model_name: str, progress_callback=None) -> tuple:
    start_time = time.time()
    cached = get_cached_transcription(video_url)
    if cached:
        if progress_callback:
            progress_callback(f"✅ Récupération du cache : {cached['title'][:50]}")
        return cached['transcript'], cached['title'], 0

    unique_id = uuid.uuid4().hex
    audio_filename = f"audio_temp_{unique_id}.mp3"
    wav_filename = f"audio_temp_{unique_id}.wav"
    try:
        video_title = get_video_title(video_url)
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
        subprocess.run(command, capture_output=True, text=True, timeout=300)
        if not os.path.exists(audio_filename):
            return "", video_title, 0
        convert_to_wav(audio_filename, wav_filename)
        file_size = os.path.getsize(wav_filename)
        if file_size < 1000 or not is_wav_valid(wav_filename):
            return "", video_title, 0
        model = load_whisper_model(model_name)
        result = model.transcribe(wav_filename, fp16=False)
        transcript = result["text"]
        if progress_callback:
            progress_callback(f"💾 Sauvegarde du cache : {video_title[:50]}")
        save_transcription_cache(video_url, video_title, transcript)
        processing_time = time.time() - start_time
        return transcript, video_title, processing_time
    except Exception as e:
        print(f"Erreur lors de la transcription de {video_url}: {type(e).__name__}: {e}")
        return "", "Titre indisponible", 0
    finally:
        for f in [audio_filename, wav_filename]:
            if os.path.exists(f):
                os.remove(f)

def normalize_text(text: str) -> str:
    import unicodedata
    text = text.lower()
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return text

def analyze_transcription(transcription: str, keywords: list) -> dict:
    analysis = {}
    normalized_transcript = normalize_text(transcription)
    for keyword in keywords:
        keyword = keyword.strip()
        normalized_keyword = normalize_text(keyword)
        keyword_words = normalized_keyword.split()
        count = 0
        if len(keyword_words) == 1:
            pattern = r'\b' + re.escape(keyword_words[0]) + r'\b'
            count = len(re.findall(pattern, normalized_transcript, re.IGNORECASE))
        else:
            min_words_required = max(1, len(keyword_words) // 2)
            pattern_parts = [r'\b' + re.escape(word) + r'\b' for word in keyword_words]
            flexible_pattern = r'\s+(?:\S+\s+){0,3}'.join(pattern_parts)
            matches = re.finditer(flexible_pattern, normalized_transcript, re.IGNORECASE)
            count = len(list(matches))
            if count == 0:
                words_found = 0
                for word in keyword_words:
                    if re.search(r'\b' + re.escape(word) + r'\b', normalized_transcript, re.IGNORECASE):
                        words_found += 1
                if words_found >= min_words_required:
                    count = 1
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
    stats = load_time_stats()
    if whisper_model not in stats:
        stats[whisper_model] = {
            'total_processing_time': 0,
            'total_video_duration': 0,
            'video_count': 0
        }
    for i, url in enumerate(video_urls):
        if stop_flag:
            print("Arrêt demandé par l'utilisateur.")
            break
        status = f"📹 Vidéo {i+1}/{total_videos}"
        if progress_callback:
            progress_callback(status)
        transcription, title, processing_time = transcribe_video_local(url, whisper_model, progress_callback)
        if processing_time > 0:
            try:
                from pytube import YouTube
                yt = YouTube(url)
                video_duration = yt.length
            except:
                video_duration = 0
            if video_duration > 0:
                stats[whisper_model]['total_processing_time'] += processing_time
                stats[whisper_model]['total_video_duration'] += video_duration
                stats[whisper_model]['video_count'] += 1
                save_time_stats(stats)
        if transcription:
            analysis = analyze_transcription(transcription, keywords)
            for keyword, count in analysis.items():
                if count > 0:
                    results['details'][keyword].append((title, url, count))
                    results['total_occurrences'] += count
        if progress_callback:
            progress_callback(f"✅ Vidéo {i+1}/{total_videos} complétée")
    if progress_callback:
        progress_callback("🎉 Analyse terminée !")
    return results

def convert_to_wav(input_path, output_path):
    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        "-c:a", "pcm_s16le",
        output_path
    ]
    subprocess.run(command, capture_output=True)
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise RuntimeError(f"Conversion audio échouée pour {input_path}")

def is_wav_valid(wav_path):
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "stream=channels,duration", "-of", "default=noprint_wrappers=1:nokey=1", wav_path
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stdout.strip().split('\n')
    if len(output) < 2:
        return False
    channels, duration = output
    try:
        return int(channels) > 0 and float(duration) > 0
    except:
        return False