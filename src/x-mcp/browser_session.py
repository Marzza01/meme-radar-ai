"""Persistent browser session manager — keeps cookies alive for days/weeks.

Instead of creating throwaway contexts from storage_state.json (which lose session cookies),
this uses launch_persistent_context() with a real Chrome user_data_dir. The browser profile
directory holds all cookies, localStorage, IndexedDB natively — just like a real Chrome install.

After each operation, we save storage_state back as a backup.
"""

import os
import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# Persistent profile directory — survives across all launches
PROFILE_DIR = str(Path.home() / ".twitter-mcp" / "chrome-profile")
STORAGE_BACKUP = str(Path.home() / ".twitter-mcp" / "storage_state.json")

# Anti-detection args
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-site-isolation-trials",
    "--disable-web-security",
]

IGNORE_ARGS = ["--enable-automation"]

# Run headless by default for silent background scanning without desktop popups
USE_HEADLESS = True


def clean_session_tabs():
    """Remove Chrome's session restore tab files so tabs never accumulate."""
    try:
        sess_dir = Path(PROFILE_DIR) / "Default" / "Sessions"
        if sess_dir.exists():
            for f in sess_dir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass


def is_authenticated() -> bool:
    """Check if we have an active authenticated session saved."""
    storage_path = Path(STORAGE_BACKUP)
    if not storage_path.exists():
        return False
    try:
        import json
        with open(storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        return any(c.get("name") == "auth_token" and c.get("value") for c in cookies)
    except Exception:
        return False


async def get_persistent_context(force_headless: bool = None) -> tuple:
    """Launch browser with persistent context.

    Returns (playwright, context) — caller must close both when done.
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)
    clean_session_tabs()

    pw = await async_playwright().start()

    if force_headless is not None:
        headless = force_headless
    elif os.environ.get("HEADLESS") is not None:
        headless = os.environ.get("HEADLESS").lower() in ("1", "true", "yes")
    else:
        headless = USE_HEADLESS

    is_windows = sys.platform == "win32"
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        if is_windows
        else "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=headless,
        args=BROWSER_ARGS,
        ignore_default_args=IGNORE_ARGS,
        viewport={"width": 1280, "height": 900},
        user_agent=ua,
    )

    # Ensure only 1 tab is open so tabs never accumulate
    while len(context.pages) > 1:
        try:
            await context.pages[-1].close()
        except Exception:
            break

    # Seed profile from storage_state.json so current cookies are always loaded
    storage_path = Path(STORAGE_BACKUP)
    if storage_path.exists():
        try:
            import json
            with open(storage_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if "cookies" in state:
                await context.add_cookies(state["cookies"])
        except Exception:
            pass  # Non-critical

    return pw, context


async def save_session(context: BrowserContext):
    """Save current session back to storage_state.json as backup."""
    try:
        os.makedirs(os.path.dirname(STORAGE_BACKUP), exist_ok=True)
        await context.storage_state(path=STORAGE_BACKUP)
    except Exception:
        pass  # Non-critical — profile dir is the primary store


async def close_session(pw, context: BrowserContext):
    """Save session and close browser cleanly."""
    try:
        await save_session(context)
    except Exception:
        pass
    try:
        for p in list(context.pages):
            try:
                await p.close()
            except Exception:
                pass
        await context.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass
    clean_session_tabs()


async def login_interactive(timeout_seconds: int = 180) -> bool:
    """Open a visible browser window so the user can log into Twitter/X.
    
    Monitors cookies for 'auth_token'. Once logged in, saves session and closes.
    """
    print("\n🌐 Abriendo ventana del navegador para iniciar sesión en Twitter/X...")
    pw, context = await get_persistent_context(force_headless=False)
    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://x.com/login", wait_until="domcontentloaded")
        print("👉 Por favor, inicia sesión con tu cuenta en la ventana abierta de Twitter/X.")
        print(f"⏳ Esperando inicio de sesión (tiempo límite: {timeout_seconds} segundos)...")

        for _ in range(timeout_seconds):
            await asyncio.sleep(1)
            cookies = await context.cookies()
            has_auth = any(c.get("name") == "auth_token" and c.get("value") for c in cookies)
            current_url = page.url
            if has_auth and ("home" in current_url or "x.com" in current_url and "login" not in current_url):
                print("\n✅ ¡Inicio de sesión detectado con éxito!")
                await page.wait_for_timeout(3000)
                await save_session(context)
                print(f"💾 Sesión guardada en: {STORAGE_BACKUP}")
                return True
        
        # Timeout reached: final check
        cookies = await context.cookies()
        if any(c.get("name") == "auth_token" and c.get("value") for c in cookies):
            print("\n✅ Sesión detectada.")
            await save_session(context)
            return True

        print("\n⚠️ Tiempo de espera agotado sin detectar sesión iniciada.")
        return False
    finally:
        await close_session(pw, context)


async def import_fresh_cookies(cookies_path: str):
    """Import fresh cookies from a file into the persistent profile."""
    pw, context = await get_persistent_context()
    try:
        import json
        with open(cookies_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        if "cookies" in state:
            await context.add_cookies(state["cookies"])

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://x.com/home", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        await save_session(context)
        return "Cookies importadas y activadas con éxito."
    finally:
        await close_session(pw, context)


def set_auth_token(auth_token: str, ct0: str = None) -> bool:
    """Save auth_token (and optional ct0) directly to storage_state.json as authenticated session."""
    import json
    os.makedirs(os.path.dirname(STORAGE_BACKUP), exist_ok=True)
    cookies = [
        {
            "name": "auth_token",
            "value": auth_token.strip(),
            "domain": ".x.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax"
        }
    ]
    if ct0:
        cookies.append({
            "name": "ct0",
            "value": ct0.strip(),
            "domain": ".x.com",
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax"
        })
    
    # Load existing state if available to keep other non-auth cookies
    state = {"cookies": [], "origins": []}
    if Path(STORAGE_BACKUP).exists():
        try:
            with open(STORAGE_BACKUP, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    existing_cookies = [c for c in state.get("cookies", []) if c.get("name") not in ("auth_token", "ct0")]
    existing_cookies.extend(cookies)
    state["cookies"] = existing_cookies

    with open(STORAGE_BACKUP, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    return True


