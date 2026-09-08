# Meme Radar AI - Estado del Proyecto y Guía de Contexto

Este archivo documenta el estado actual del proyecto para poder continuar el desarrollo desde cualquier laptop o máquina sin perder el contexto.

---

## 🎯 Objetivo del Sistema
Sistema autónomo 24/7 para la detección temprana de narrativas y memecoins en Twitter/X, análisis de sentimiento y tracción con IA, y emisión de alertas en tiempo real vía Telegram y Dashboard Web.

---

## 🏗️ Estructura del Proyecto

- `src/`:
  - `radar_24_7.py`: Orquestador principal del bucle continuo de escaneo y alertas.
  - `dashboard_app.py`: Servidor Streamlit / Dashboard interactivo para visualizar métricas, señales y bitácora de actividad.
  - `scraper/`: Scrapers de Twitter (usando Apify / MCP / Playwright).
  - `analyzer/`: Módulo de evaluación de tokens, análisis de métricas y validación de seguridad.
  - `notifier/`: Enrutador de alertas hacia Telegram (`telegram_bot.py`).
  - `database/`: Conexión y modelos SQLite para almacenamiento persistente de tweets, menciones y alertas.
- `config/`: Archivos de configuración YAML/JSON con listas de influencers, tokens seguidos y umbrales de alerta.
- `scratch/`: Scripts de prueba E2E y verificación (`test_bitacora_e2e.py`, `verify_system.py`).
- `.env.example`: Plantilla de variables de entorno necesarias.

---

## 🚀 Scripts Rápidos (Windows)

En la raíz se encuentran scripts `.bat` para operar el sistema con un doble clic:
1. `CONTROL_RADAR.bat`: Menú interactivo central para encender, apagar, ver estado y abrir dashboard.
2. `ENCENDER_RADAR.bat` / `start_radar_24_7.bat`: Inicia el radar en segundo plano / proceso continuo.
3. `APAGAR_RADAR.bat` / `stop_radar.bat`: Detiene los procesos activos del radar.
4. `ABRIR_DASHBOARD.bat`: Lanza y abre el dashboard interactivo en el navegador.

---

## 💻 Instrucciones para la Segunda Laptop

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/Marzza01/meme-radar-ai.git
   cd meme-radar-ai
   ```
2. **Entorno Virtual e Instalación de Dependencias:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt  # o instalar dependencias necesarias
   ```
3. **Configurar Credenciales:**
   - Duplica `.env.example` y renómbralo a `.env`.
   - Coloca los tokens correspondientes (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, etc.).
