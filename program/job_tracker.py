from datetime import datetime

class JobTracker:
    def __init__(self):
        self.jobs = {}

    def add_job(self, drive, job_id, status, logs=None):
        if logs is None:
            logs = []
        self.jobs[drive] = {
            "job_id": job_id,
            "status": status,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "logs": logs,
        }

    def update_job(self, drive, status, logs=None):
        if drive in self.jobs:
            self.jobs[drive]['status'] = status
            if logs is not None:
                self.jobs[drive]['logs'] = logs

    def get_jobs(self):
        return self.jobs

job_tracker = JobTracker()
