import os
import time

BASE_FILE = os.path.dirname(os.path.abspath(__file__))

def create_log_file(requirement_id):
    logs_base_path = os.path.join(BASE_FILE, 'test_logs')

    if not os.path.exists(logs_base_path):
        os.mkdir(logs_base_path)

    latest_link = logs_base_path + '/latest'

    timestamp = time.strftime("%Y-%m-%d-%H:%M:%S")
    log_file = requirement_id + '-' + timestamp
    log_path = os.path.join(logs_base_path, log_file)

    os.mkdir(log_path)

    if os.path.exists(latest_link):
        os.unlink(latest_link)

    os.symlink(log_path, latest_link)
    return log_path

