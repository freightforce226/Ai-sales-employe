import socket
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
