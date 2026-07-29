import socket
import time
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/debug", tags=["Debug"])

@router.get("/smtp-connectivity")
def check_smtp_connectivity():
    """
    TEMPORARY: Diagnostic endpoint to test Render outbound TCP connectivity to SMTP port 465.
    Will be removed after debugging.
    """
    host = "mail.ampluslogistics.com"
    port = 465
    try:
        with socket.create_connection((host, port), timeout=10.0) as sock:
            return {
                "success": True,
                "host": host,
                "port": port,
                "message": "TCP connection established"
            }
    except Exception as e:
        return {
            "success": False,
            "host": host,
            "port": port,
            "error_type": type(e).__name__,
            "error": str(e)
        }

@router.get("/smtp-matrix")
def check_smtp_matrix():
    """
    TEMPORARY: Diagnostic matrix endpoint to isolate Render port blocking vs target firewall blocks.
    Will be removed after debugging.
    """
    targets = [
        {"host": "smtp.gmail.com", "port": 465},
        {"host": "smtp.office365.com", "port": 587},
        {"host": "smtp.zoho.com", "port": 465},
        {"host": "mail.ampluslogistics.com", "port": 465}
    ]
    
    results = []
    for target in targets:
        host = target["host"]
        port = target["port"]
        start_time = time.time()
        try:
            with socket.create_connection((host, port), timeout=5.0) as sock:
                latency_ms = round((time.time() - start_time) * 1000, 2)
                results.append({
                    "host": host,
                    "port": port,
                    "success": True,
                    "latency_ms": latency_ms
                })
        except Exception as e:
            results.append({
                "host": host,
                "port": port,
                "success": False,
                "error": type(e).__name__
            })
            
    return {"results": results}
