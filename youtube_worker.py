import time
import json
from pathlib import Path
from youtube_agent import run_full_analysis, get_cached_transcription

QUEUE_FILE = Path("jobs_queue.json")

def load_queue():
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_queue(queue):
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    print("Worker démarré. Ctrl+C pour arrêter.")
    while True:
        queue = load_queue()
        for idx, job in enumerate(queue):
            if job["status"] != "pending":
                continue
            url = job["url"]
            print(f"Traitement : {url}")
            queue[idx]["status"] = "running"
            save_queue(queue)
            if get_cached_transcription(url):
                queue[idx]["status"] = "done"
                save_queue(queue)
                print(f"Déjà en cache : {url}")
                continue
            try:
                run_full_analysis([url], job["keywords"], job["model"])
                queue[idx]["status"] = "done"
                queue[idx]["finished_at"] = time.time()
                save_queue(queue)
                print(f"Terminé : {url}")
            except Exception as e:
                queue[idx]["status"] = "failed"
                queue[idx]["error"] = str(e)
                save_queue(queue)
                print(f"Erreur : {url} - {e}")
            time.sleep(1)
        time.sleep(5)

if __name__ == "__main__":
    main()