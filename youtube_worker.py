import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from youtube_agent import run_full_analysis, get_cached_transcription

QUEUE_FILE = Path("jobs_queue.json")
MAX_WORKERS = 2  # Ajuste selon la puissance de ta machine

def load_queue():
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_queue(queue):
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

def process_job(idx, job):
    url = job["url"]
    print(f"[Thread] Traitement : {url}")
    try:
        if get_cached_transcription(url):
            return idx, "done", None
        run_full_analysis([url], job["keywords"], job["model"])
        return idx, "done", None
    except Exception as e:
        print(f"Erreur lors de la transcription de {url}: {e}")
        # Ajoute le message d'erreur dans le job pour affichage côté front
        return idx, "failed", f"{type(e).__name__}: {e}"

def main():
    print("Worker multi-thread démarré.")
    while True:
        queue = load_queue()
        jobs_to_run = [(i, job) for i, job in enumerate(queue) if job["status"] == "pending"]
        if not jobs_to_run:
            # Vérifier s'il reste des jobs "running"
            running_jobs = any(job["status"] == "running" for job in queue)
            if not running_jobs:
                print("Tous les jobs sont terminés. Arrêt du worker.")
                break  # Sort de la boucle principale et termine le script
            else:
                time.sleep(5)
                continue

        # Marquer les jobs comme "running"
        for i, _ in jobs_to_run:
            queue[i]["status"] = "running"
        save_queue(queue)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(process_job, i, job) for i, job in jobs_to_run]
            for future in as_completed(futures):
                idx, status, error = future.result()
                queue = load_queue()  # Recharge pour éviter les conflits d'écriture
                queue[idx]["status"] = status
                if status == "done":
                    queue[idx]["finished_at"] = time.time()
                if error:
                    queue[idx]["error"] = error
                save_queue(queue)
        time.sleep(2)

if __name__ == "__main__":
    main()