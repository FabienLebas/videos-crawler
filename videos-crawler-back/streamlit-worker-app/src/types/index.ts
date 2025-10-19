export type Task = {
    id: string;
    description: string;
    status: 'pending' | 'in-progress' | 'completed' | 'failed';
};

export type WorkerResponse = {
    taskId: string;
    result?: any;
    error?: string;
};