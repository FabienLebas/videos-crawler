from multiprocessing import Process, Queue
import time
import json

def worker_task(queue):
    while True:
        task = queue.get()
        if task is None:  # Exit signal
            break
        # Simulate task processing
        print(f"Processing task: {task}")
        time.sleep(2)  # Simulate time-consuming task
        print(f"Task completed: {task}")

def main():
    task_queue = Queue()
    worker = Process(target=worker_task, args=(task_queue,))
    worker.start()

    try:
        while True:
            # Here you would normally get tasks from a source (e.g., Streamlit app)
            # For demonstration, we will simulate task submission
            task = input("Enter a task (or 'exit' to quit): ")
            if task.lower() == 'exit':
                break
            task_queue.put(task)
    finally:
        task_queue.put(None)  # Send exit signal to worker
        worker.join()

if __name__ == "__main__":
    main()