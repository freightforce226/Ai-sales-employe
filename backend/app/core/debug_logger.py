import os
from datetime import datetime
from contextvars import ContextVar

# Path configurations
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
EMAIL_DEBUG_DIR = os.path.join(LOGS_DIR, "email_debug")

# Create directories if they do not exist
os.makedirs(EMAIL_DEBUG_DIR, exist_ok=True)

# ContextVar to store the current request log file path
current_log_file_path: ContextVar[str] = ContextVar("current_log_file_path", default="")

def init_request_log(request_id: str) -> str:
    """
    Initialize a new request-specific log file and set it in the ContextVar.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"email_{timestamp}_REQ-{request_id}.log"
    file_path = os.path.join(EMAIL_DEBUG_DIR, filename)
    
    current_log_file_path.set(file_path)
    
    # Write initial header
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"=========================================================\n")
        f.write(f"REQUEST ID: {request_id}\n")
        f.write(f"INITIALIZED: {datetime.now().isoformat()}\n")
        f.write(f"=========================================================\n\n")
        
    return file_path

def log_to_request_file(message: str) -> None:
    """
    Append a log message to the current request's log file.
    """
    if len(message) > 2048:
        message = message[:2000] + f"... [TRUNCATED {len(message) - 2000} chars]"
        
    file_path = current_log_file_path.get()
    if file_path:
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {message}\n")
        except Exception:
            pass

def log_validation_error(error_details: str) -> None:
    """
    Append validation error logs to logs/email_validation.log.
    """
    if len(error_details) > 2048:
        error_details = error_details[:2000] + f"... [TRUNCATED {len(error_details) - 2000} chars]"
        
    val_log_path = os.path.join(LOGS_DIR, "email_validation.log")
    try:
        with open(val_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] --- VALIDATION ERROR ---\n")
            f.write(f"{error_details}\n")
            f.write("-" * 80 + "\n\n")
    except Exception:
        pass
