from flask import Flask, request, jsonify
import requests
import threading

app = Flask(__name__)

# URL du worker
WORKER_URL = 'http://localhost:5001/process'

@app.route('/submit_task', methods=['POST'])
def submit_task():
    task_data = request.json
    response = requests.post(WORKER_URL, json=task_data)
    return jsonify(response.json()), response.status_code

def run_app():
    app.run(port=5000)

if __name__ == '__main__':
    threading.Thread(target=run_app).start()