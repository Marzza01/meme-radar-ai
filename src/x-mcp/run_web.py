import subprocess
import sys

# Ejecutar el servidor de X directamente con uvicorn
subprocess.run([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"])