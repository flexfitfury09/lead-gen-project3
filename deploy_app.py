"""
LeadAI Pro - AI-Powered Lead Management & Email Marketing Platform
Deployment-ready Streamlit application for Hugging Face Spaces
"""

import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import asyncio
import threading
import time
import json
import uuid
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import smtplib
import ssl
import re
import os
import warnings
from typing import Dict, List, Optional, Tuple
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import requests
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    # Create dummy classes for fallback
    class pipeline:
        def __init__(self, *args, **kwargs):
            pass
    class AutoTokenizer:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return None
    class AutoModelForCausalLM:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return None
import schedule
import yagmail
from email_validator import validate_email, EmailNotValidError

# Lead Generation imports
try:
    from lead_generation_orchestrator import LeadGenerationOrchestrator
    from lead_database_enhanced import LeadDatabase
    LEAD_GENERATION_AVAILABLE = True
except ImportError:
    LEAD_GENERATION_AVAILABLE = False
    st.warning("Lead generation features not available. Please ensure all dependencies are installed.")
try:
    from streamlit_autorefresh import st_autorefresh  # optional dependency for real-time updates
except Exception:
    st_autorefresh = None
try:
    import websocket  # websocket-client
except Exception:
    websocket = None

# Suppress warnings
warnings.filterwarnings("ignore")

# Configure Streamlit page
st.set_page_config(
    page_title="LeadAI Pro",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database setup
DB_NAME = "leadai_pro.db"

# --- Ensure database schema exists (idempotent) ---
def _ensure_db_schema():
    """Create required tables if they don't exist. Safe to call multiple times."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Leads table (basic schema used by legacy UI)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                company TEXT,
                phone TEXT,
                title TEXT,
                industry TEXT,
                category TEXT DEFAULT 'General',
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Campaigns table (minimal fields required by UI)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT,
                content TEXT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Email tracking table used by analytics
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS email_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER,
                recipient TEXT,
                status TEXT,
                sent_at TIMESTAMP,
                opened_at TIMESTAMP,
                clicked_at TIMESTAMP,
                clicked_link TEXT
            )
            """
        )

        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

# Per-user SMTP config storage
CONFIG_DIR = ".user_configs"

def _ensure_config_dir():
    try:
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception:
        pass

def get_smtp_config_path(user_id: int) -> str:
    _ensure_config_dir()
    return os.path.join(CONFIG_DIR, f"smtp_config_user_{user_id}.json")

def load_smtp_config(user_id: Optional[int]) -> Optional[Dict]:
    """Load SMTP config for a user from local JSON. Returns None if missing/invalid."""
    try:
        if user_id is None:
            return None
        path = get_smtp_config_path(user_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None
    return None

def save_smtp_config(user_id: int, config: Dict) -> bool:
    """Persist SMTP config for a user to local JSON."""
    try:
        path = get_smtp_config_path(user_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception:
        return False

# Multi-profile SMTP support
def get_profiles_path(user_id: int) -> str:
    _ensure_config_dir()
    return os.path.join(CONFIG_DIR, f"smtp_profiles_user_{user_id}.json")

def load_smtp_profiles(user_id: Optional[int]) -> Dict:
    try:
        if user_id is None:
            return { 'profiles': [], 'default_profile_id': None }
        path = get_profiles_path(user_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and 'profiles' in data:
                    return data
        return { 'profiles': [], 'default_profile_id': None }
    except Exception:
        return { 'profiles': [], 'default_profile_id': None }

def save_smtp_profiles(user_id: int, data: Dict) -> bool:
    try:
        path = get_profiles_path(user_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False

def get_session_active_profile_id() -> Optional[str]:
    try:
        return st.session_state.get('active_sender_profile_id')
    except Exception:
        return None

def set_session_active_profile_id(profile_id: Optional[str]):
    try:
        st.session_state['active_sender_profile_id'] = profile_id
    except Exception:
        pass

def render_realtime_counters(user_id: int):
    """Render live-updating counters in the UI (uses autorefresh if available)."""
    try:
        if st_autorefresh:
            st_autorefresh(interval=5000, key="global_autorefresh")
        stats = st.session_state.get('ws_metrics') or get_analytics(user_id)
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Live Leads", stats.get('lead_count', 0))
        with col_b:
            st.metric("Live Emails Sent", stats.get('sent_emails', 0))
        with col_c:
            st.metric("Live Open Rate", f"{((stats.get('opened_emails',0)/(stats.get('sent_emails',1)))*100) if stats.get('sent_emails',0)>0 else 0:.1f}%")
    except Exception:
        pass

def _start_ws_client():
    try:
        if websocket is None:
            return
        if st.session_state.get('ws_started'):
            return
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if isinstance(data, dict) and data.get('type') == 'metrics':
                    st.session_state['ws_metrics'] = {
                        'lead_count': data.get('lead_count', 0),
                        'campaign_count': data.get('campaign_count', 0),
                        'sent_emails': data.get('sent_emails', 0),
                        'opened_emails': data.get('opened_emails', 0),
                        'clicked_emails': data.get('clicked_emails', 0)
                    }
            except Exception:
                pass
        def on_error(ws, error):
            pass
        def on_close(ws, close_status_code, close_msg):
            pass
        def on_open(ws):
            pass
        # Assume backend runs on same host with port 8000
        ws_url = os.environ.get('WS_METRICS_URL', 'ws://localhost:8000/ws/metrics')
        def run_ws():
            try:
                websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open).run_forever()
            except Exception:
                pass
        t = threading.Thread(target=run_ws, daemon=True)
        t.start()
        st.session_state['ws_started'] = True
    except Exception:
        pass

# Suppression list helpers
def get_suppression_path(user_id: int) -> str:
    _ensure_config_dir()
    return os.path.join(CONFIG_DIR, f"suppression_user_{user_id}.json")

def load_suppression_list(user_id: Optional[int]) -> List[str]:
    try:
        if user_id is None:
            return []
        path = get_suppression_path(user_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(x).strip().lower() for x in data if x]
        return []
    except Exception:
        return []

def save_suppression_list(user_id: int, emails: List[str]) -> bool:
    try:
        path = get_suppression_path(user_id)
        cleaned = sorted(list({e.strip().lower() for e in emails if e and isinstance(e, str)}))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2)
        return True
    except Exception:
        return False

# ---------- Warmup tracking helpers ----------
def get_warmup_state_path(user_id: int) -> str:
    _ensure_config_dir()
    return os.path.join(CONFIG_DIR, f"warmup_user_{user_id}.json")

def load_warmup_state(user_id: Optional[int]) -> Dict:
    try:
        if user_id is None:
            return { 'profiles': {} }
        path = get_warmup_state_path(user_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else { 'profiles': {} }
    except Exception:
        return { 'profiles': {} }
    return { 'profiles': {} }

def save_warmup_state(user_id: int, data: Dict) -> bool:
    try:
        path = get_warmup_state_path(user_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False

def get_warmup_allowance_for_profile(user_id: int, profile: Dict) -> Optional[int]:
    try:
        if not profile or not profile.get('warmup_enabled'):
            return None
        max_per_day = int(profile.get('warmup_max_per_day') or 0)
        if max_per_day <= 0:
            return None
        state = load_warmup_state(user_id)
        prof_id = profile.get('id', 'default')
        pstate = state.get('profiles', {}).get(prof_id, {})
        today = datetime.now().date().isoformat()
        sent_today = 0 if pstate.get('date') != today else int(pstate.get('sent_today') or 0)
        remaining = max(0, max_per_day - sent_today)
        return remaining
    except Exception:
        return None

def increment_warmup_sent(user_id: int, profile: Dict, count: int) -> None:
    try:
        if not profile or not profile.get('warmup_enabled'):
            return
        state = load_warmup_state(user_id)
        prof_id = profile.get('id', 'default')
        today = datetime.now().date().isoformat()
        if 'profiles' not in state:
            state['profiles'] = {}
        if prof_id not in state['profiles']:
            state['profiles'][prof_id] = {'date': today, 'sent_today': 0}
        entry = state['profiles'][prof_id]
        if entry.get('date') != today:
            entry['date'] = today
            entry['sent_today'] = 0
        entry['sent_today'] = int(entry.get('sent_today') or 0) + int(count)
        save_warmup_state(user_id, state)
    except Exception:
        pass

# ---------- Data cleaning helpers ----------
def sanitize_subject(subject: str) -> str:
    try:
        subject = subject or ""
        subject = subject.replace("\r", " ").replace("\n", " ").strip()
        subject = re.sub(r"[\x00-\x1F\x7F]", "", subject)
        return subject[:200]
    except Exception:
        return subject

def sanitize_html_body(html: str) -> str:
    try:
        html = html or ""
        # very conservative: strip script/style tags
        html = re.sub(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", "", html, flags=re.IGNORECASE|re.DOTALL)
        return html
    except Exception:
        return html

# ---------- Gmail OAuth2 helpers ----------
def _oauth2_get_access_token(client_id: str, client_secret: str, refresh_token: str) -> Optional[str]:
    try:
        token_url = "https://oauth2.googleapis.com/token"
        resp = requests.post(token_url, data={
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('access_token')
    except Exception:
        return None
    return None

def _build_xoauth2_string(username: str, access_token: str) -> str:
    import base64
    auth_str = f"user={username}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

def render_sender_selector_ui(user_id: int, label: str = "Sender Profile") -> Optional[str]:
    try:
        profiles_data = load_smtp_profiles(user_id)
        profile_options = [f"{p.get('name','Unnamed')} ({p.get('smtp_username','')})" for p in profiles_data.get('profiles', [])]
        profile_ids = [p.get('id') for p in profiles_data.get('profiles', [])]
        if not profile_ids:
            st.info("No sender profiles configured. Add one in Settings → Email SMTP Settings.")
            return None
        active_id = get_session_active_profile_id()
        default_prof = get_default_profile(profiles_data)
        default_id = active_id or (default_prof.get('id') if default_prof else None)
        idx = profile_ids.index(default_id) if default_id in profile_ids else 0
        sel_idx = st.selectbox(label, options=list(range(len(profile_options))), format_func=lambda i: profile_options[i], index=idx)
        return profile_ids[sel_idx]
    except Exception:
        return None

def get_profile_by_id(profiles_data: Dict, profile_id: Optional[str]) -> Optional[Dict]:
    if not profiles_data or not profiles_data.get('profiles'):
        return None
    for p in profiles_data['profiles']:
        if p.get('id') == profile_id:
            return p
    return None

def get_default_profile(profiles_data: Dict) -> Optional[Dict]:
    default_id = profiles_data.get('default_profile_id')
    prof = get_profile_by_id(profiles_data, default_id)
    if prof:
        return prof
    # fallback: first profile
    if profiles_data.get('profiles'):
        return profiles_data['profiles'][0]
    return None

def apply_profile_to_dotenv(profile: Dict) -> bool:
    """Write selected profile values to .env for external processes if desired."""
    try:
        env_path = ".env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        def set_kv(lines, key, value):
            found = False
            for i, line in enumerate(lines):
                if line.startswith(key + "="):
                    lines[i] = f"{key}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}")
            return lines
        lines = set_kv(lines, "SMTP_SERVER", profile.get('smtp_server', ''))
        lines = set_kv(lines, "SMTP_PORT", str(profile.get('smtp_port', '587')))
        lines = set_kv(lines, "SMTP_USERNAME", profile.get('smtp_username', ''))
        lines = set_kv(lines, "SMTP_PASSWORD", profile.get('smtp_password', ''))
        lines = set_kv(lines, "FROM_EMAIL", profile.get('from_email', ''))
        lines = set_kv(lines, "FROM_NAME", profile.get('from_name', 'LeadAI Pro'))
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception:
        return False

def init_database():
    """Initialize SQLite database with all required tables"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Leads table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            phone TEXT,
            title TEXT,
            industry TEXT,
            category TEXT DEFAULT 'General',
            status TEXT DEFAULT 'New',
            score INTEGER DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Campaigns table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'Draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scheduled_at TIMESTAMP,
            sent_at TIMESTAMP,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Email tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            lead_id INTEGER,
            email TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            sent_at TIMESTAMP,
            opened_at TIMESTAMP,
            clicked_at TIMESTAMP,
            click_count INTEGER DEFAULT 0,
            FOREIGN KEY (campaign_id) REFERENCES campaigns (id),
            FOREIGN KEY (lead_id) REFERENCES leads (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_database()

# Custom CSS for 3D cinematic UI
def load_css():
    """Load custom CSS for 3D cinematic UI"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    :root {
        --primary-color: #6366f1;
        --secondary-color: #8b5cf6;
        --accent-color: #06b6d4;
        --background-dark: #0f0f23;
        --surface-dark: #1a1a2e;
        --text-primary: #ffffff;
        --text-secondary: #a1a1aa;
        --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        --gradient-secondary: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        --gradient-accent: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    }
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    .main .block-container {
        padding: 0;
        max-width: 100%;
    }
    
    .stApp {
        background: var(--background-dark);
        color: var(--text-primary);
    }
    
    .cinematic-header {
        background: var(--gradient-primary);
        padding: 2rem;
        border-radius: 0 0 2rem 2rem;
        margin-bottom: 2rem;
        position: relative;
        overflow: hidden;
    }
    
    .cinematic-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 L 0 0 0 10" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/></pattern></defs><rect width="100" height="100" fill="url(%23grid)"/></svg>');
        opacity: 0.3;
    }
    
    .header-content {
        position: relative;
        z-index: 1;
    }
    
    .main-title {
        font-size: 3rem;
        font-weight: 800;
        margin: 0;
        background: linear-gradient(45deg, #ffffff, #e0e7ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        text-shadow: 0 0 30px rgba(255, 255, 255, 0.5);
    }
    
    .subtitle {
        font-size: 1.2rem;
        color: var(--text-secondary);
        text-align: center;
        margin-top: 1rem;
        opacity: 0.9;
    }
    
    .dashboard-card {
        background: var(--surface-dark);
        border-radius: 1rem;
        padding: 2rem;
        margin: 1rem 0;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .dashboard-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: var(--gradient-accent);
    }
    
    .dashboard-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
        border-color: var(--primary-color);
    }
    
    .metric-card {
        background: var(--gradient-primary);
        border-radius: 0.75rem;
        padding: 1.5rem;
        text-align: center;
        color: white;
        margin: 0.5rem;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .metric-card::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        transform: scale(0);
        transition: transform 0.5s ease;
    }
    
    .metric-card:hover::before {
        transform: scale(1);
    }
    
    .metric-card:hover {
        transform: scale(1.05);
        box-shadow: 0 10px 30px rgba(99, 102, 241, 0.3);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    }
    
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
        margin-top: 0.5rem;
    }
    
    .btn-primary {
        background: var(--gradient-primary);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 0.5rem;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-decoration: none;
        display: inline-block;
    }
    
    .btn-primary:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(99, 102, 241, 0.4);
    }
    
    .sidebar .sidebar-content {
        background: var(--surface-dark);
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .sidebar .sidebar-content .stSelectbox > div > div {
        background: var(--surface-dark);
        color: var(--text-primary);
    }
    
    .stTabs [data-baseweb="tab-list"] {
        background: var(--surface-dark);
        border-radius: 0.5rem;
        padding: 0.25rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: var(--text-secondary);
        border-radius: 0.25rem;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    
    .stTabs [aria-selected="true"] {
        background: var(--gradient-primary);
        color: white;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(99, 102, 241, 0.1);
        color: var(--text-primary);
    }
    
    .loading-spinner {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(255, 255, 255, 0.3);
        border-radius: 50%;
        border-top-color: var(--primary-color);
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .pulse {
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    
    .fade-in {
        animation: fadeIn 0.5s ease-in;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .glow {
        box-shadow: 0 0 20px rgba(99, 102, 241, 0.5);
    }
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--surface-dark);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--primary-color);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--secondary-color);
    }
    </style>
    """, unsafe_allow_html=True)

# Authentication functions
def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed

def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """Authenticate user and return user data"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, username, email, password_hash, role FROM users WHERE username = ?",
        (username,)
    )
    user = cursor.fetchone()
    conn.close()
    
    if user and verify_password(password, user[3]):
        return {
            'id': user[0],
            'username': user[1],
            'email': user[2],
            'role': user[4]
        }
    return None

def register_user(username: str, email: str, password: str, role: str = 'user') -> bool:
    """Register a new user"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        password_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, role)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

# AI Assistant functions
@st.cache_resource
def load_ai_models():
    """Load AI models for content generation"""
    if not TRANSFORMERS_AVAILABLE:
        return None
    
    try:
        # Load a lightweight model for text generation
        tokenizer = AutoTokenizer.from_pretrained("gpt2")
        model = AutoModelForCausalLM.from_pretrained("gpt2")
        
        # Create text generation pipeline
        text_generator = pipeline("text-generation", model=model, tokenizer=tokenizer)
        
        return {
            'text_generator': text_generator,
            'tokenizer': tokenizer
        }
    except Exception as e:
        st.error(f"Error loading AI models: {str(e)}")
        return None

def generate_email_content(prompt: str, max_length: int = 200) -> str:
    """Generate email content using AI"""
    models = load_ai_models()
    if not models:
        return "AI models not available. Please try again later."
    
    try:
        result = models['text_generator'](
            prompt,
            max_length=max_length,
            num_return_sequences=1,
            temperature=0.7,
            do_sample=True,
            pad_token_id=models['tokenizer'].eos_token_id
        )
        return result[0]['generated_text']
    except Exception as e:
        return f"Error generating content: {str(e)}"

def generate_subject_line(topic: str) -> str:
    """Generate subject line using AI"""
    prompt = f"Email subject line for: {topic}"
    content = generate_email_content(prompt, max_length=50)
    
    # Extract subject line (first line)
    lines = content.split('\n')
    subject = lines[0].strip()
    
    # Clean up the subject
    subject = re.sub(r'^[^a-zA-Z]*', '', subject)  # Remove non-alphabetic prefix
    subject = subject[:50]  # Limit length
    
    return subject if subject else f"Re: {topic}"

# Database functions
def get_user_leads(user_id: int) -> pd.DataFrame:
    """Get leads for a specific user"""
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT * FROM leads WHERE user_id = ? ORDER BY created_at DESC"
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def add_lead(user_id: int, lead_data: Dict) -> bool:
    """Add a new lead"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO leads (name, email, company, phone, title, industry, category, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            lead_data['name'],
            lead_data['email'],
            lead_data.get('company', ''),
            lead_data.get('phone', ''),
            lead_data.get('title', ''),
            lead_data.get('industry', ''),
            lead_data.get('category', 'General'),
            user_id
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error adding lead: {str(e)}")
        return False

def get_campaigns(user_id: int) -> pd.DataFrame:
    """Get campaigns for a specific user"""
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT * FROM campaigns WHERE user_id = ? ORDER BY created_at DESC"
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def create_campaign(user_id: int, campaign_data: Dict) -> bool:
    """Create a new campaign"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO campaigns (name, subject, content, user_id)
            VALUES (?, ?, ?, ?)
        ''', (
            campaign_data['name'],
            campaign_data['subject'],
            campaign_data['content'],
            user_id
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error creating campaign: {str(e)}")
        return False

def get_analytics(user_id: int) -> Dict:
    """Get analytics data for user"""
    # Ensure DB schema exists so analytics queries don't fail on fresh deploys
    _ensure_db_schema()

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Lead count
        try:
            cursor.execute("SELECT COUNT(*) FROM leads WHERE user_id = ?", (user_id,))
            lead_count = cursor.fetchone()[0] or 0
        except sqlite3.OperationalError:
            lead_count = 0

        # Campaign count
        try:
            cursor.execute("SELECT COUNT(*) FROM campaigns WHERE user_id = ?", (user_id,))
            campaign_count = cursor.fetchone()[0] or 0
        except sqlite3.OperationalError:
            campaign_count = 0

        # Email tracking aggregates
        total_emails = sent_emails = opened_emails = clicked_emails = 0
        try:
            cursor.execute(
                '''
                SELECT 
                    COUNT(*) as total_emails,
                    SUM(CASE WHEN status = 'Sent' THEN 1 ELSE 0 END) as sent_emails,
                    SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened_emails,
                    SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) as clicked_emails
                FROM email_tracking et
                JOIN campaigns c ON et.campaign_id = c.id
                WHERE c.user_id = ?
                ''',
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                total_emails = row[0] or 0
                sent_emails = row[1] or 0
                opened_emails = row[2] or 0
                clicked_emails = row[3] or 0
        except sqlite3.OperationalError:
            pass

        return {
            'lead_count': lead_count,
            'campaign_count': campaign_count,
            'total_emails': total_emails,
            'sent_emails': sent_emails,
            'opened_emails': opened_emails,
            'clicked_emails': clicked_emails,
        }
    except Exception:
        # Fail-safe default metrics
        return {
            'lead_count': 0,
            'campaign_count': 0,
            'total_emails': 0,
            'sent_emails': 0,
            'opened_emails': 0,
            'clicked_emails': 0,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass

# Email functions
def send_email_simulation(to_email: str, subject: str, content: str, profile_id: Optional[str] = None, attachments: Optional[List[Dict]] = None, auth_override: Optional[Dict] = None, custom_headers: Optional[Dict[str, str]] = None, utm_params: Optional[Dict[str, str]] = None) -> bool:
    """Send email using user's SMTP settings if configured; otherwise simulate."""
    try:
        # Validate recipient email
        try:
            validate_email(to_email)
        except Exception:
            st.warning(f"Invalid recipient email: {to_email}")
            return False

        user_id = st.session_state.user['id'] if 'user' in st.session_state and st.session_state.user else None
        # Prefer multiple profiles if available, else legacy single config
        profiles_data = load_smtp_profiles(user_id)
        # Prefer explicit profile_id, then session-active, then default
        effective_profile_id = profile_id or get_session_active_profile_id()
        profile = get_profile_by_id(profiles_data, effective_profile_id) if effective_profile_id else get_default_profile(profiles_data)
        cfg = dict(profile) if profile else (load_smtp_config(user_id) or {})
        # Apply per-send auth override (e.g., OAuth2)
        if auth_override and isinstance(auth_override, dict):
            cfg.update({k: v for k, v in auth_override.items() if v is not None})

        # Suppression list check
        sup_list = load_suppression_list(user_id)
        if to_email.strip().lower() in sup_list:
            print(f"Suppressed email skipped: {to_email}")
            return True

        if not cfg or not cfg.get('smtp_username') or not cfg.get('smtp_password'):
            print(f"Simulated email sent to {to_email}: {subject}")
            return True

        smtp_server = cfg.get('smtp_server', 'smtp.gmail.com')
        smtp_port = int(cfg.get('smtp_port', 587))
        smtp_username = cfg.get('smtp_username')
        smtp_password = cfg.get('smtp_password')
        from_email = cfg.get('from_email') or smtp_username
        from_name = cfg.get('from_name', 'LeadAI Pro')
        reply_to = cfg.get('reply_to')
        use_ssl = bool(cfg.get('use_ssl', False))
        use_starttls = bool(cfg.get('use_starttls', True))

        # Build message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{from_name} <{from_email}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        if reply_to:
            msg['Reply-To'] = reply_to
        if custom_headers:
            try:
                for k, v in custom_headers.items():
                    if k and v:
                        msg[k] = str(v)
            except Exception:
                pass

        # Clean inputs
        subject = sanitize_subject(subject)
        content = sanitize_html_body(content)

        # Add simple HTML with tracking pixel optional
        tracking_enabled = bool(cfg.get('tracking_enabled', True))
        tracking_pixel = ''
        if tracking_enabled:
            pixel_id = uuid.uuid4().hex
            tracking_pixel = f'<img src="http://localhost:8501/tracking?track=open&email_id={pixel_id}" width="1" height="1" style="display:none;" />'
        # Add UTM tagging to links
        try:
            if utm_params:
                def add_utm(url: str) -> str:
                    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                    try:
                        u = urlparse(url)
                        if not u.scheme or not u.netloc:
                            return url
                        qs = parse_qs(u.query)
                        for k, v in utm_params.items():
                            if v:
                                qs[k] = [v]
                        new_q = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
                        return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))
                    except Exception:
                        return url
                content = re.sub(r'href="(.*?)"', lambda m: f'href="{add_utm(m.group(1))}"', content)
        except Exception:
            pass
        # Unsubscribe footer
        footer_html = ''
        if bool(cfg.get('unsub_footer_enabled', False)):
            footer_text = cfg.get('unsub_footer_text', 'To unsubscribe, reply with "UNSUBSCRIBE".')
            footer_html = f"<hr><p style=\"font-size:12px;color:#666\">{footer_text}</p>"
        html_content = f"""
        <html>
        <body>
            {content}
            {tracking_pixel}
            {footer_html}
        </body>
        </html>
        """
        part_text = MIMEText(re.sub('<[^<]+?>', '', content), 'plain')
        part_html = MIMEText(html_content, 'html')
        msg.attach(part_text)
        msg.attach(part_html)

        # Attach files
        if attachments:
            for att in attachments:
                try:
                    filename = att.get('filename') or 'attachment'
                    payload = att.get('content')
                    maintype, subtype = (att.get('mime_type') or 'application/octet-stream').split('/', 1)
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(payload)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                    msg.attach(part)
                except Exception:
                    continue

        # Send
        context = ssl.create_default_context()
        # Send with retry policy
        attempts = 0
        max_attempts = int(cfg.get('retry_max_attempts', 3))
        delay = int(cfg.get('retry_initial_seconds', 10))
        backoff = float(cfg.get('retry_backoff_factor', 2.0))
        while True:
            try:
                if use_ssl:
                    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                        if cfg.get('oauth2', False):
                            access = _oauth2_get_access_token(cfg.get('oauth_client_id',''), cfg.get('oauth_client_secret',''), cfg.get('oauth_refresh_token',''))
                            if not access:
                                raise RuntimeError('OAuth2 access token fetch failed')
                            xoauth = _build_xoauth2_string(smtp_username, access)
                            server.docmd('AUTH', 'XOAUTH2 ' + xoauth)
                        else:
                            server.login(smtp_username, smtp_password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(smtp_server, smtp_port) as server:
                        if use_starttls:
                            server.starttls(context=context)
                        if cfg.get('oauth2', False):
                            access = _oauth2_get_access_token(cfg.get('oauth_client_id',''), cfg.get('oauth_client_secret',''), cfg.get('oauth_refresh_token',''))
                            if not access:
                                raise RuntimeError('OAuth2 access token fetch failed')
                            xoauth = _build_xoauth2_string(smtp_username, access)
                            server.docmd('AUTH', 'XOAUTH2 ' + xoauth)
                        else:
                            server.login(smtp_username, smtp_password)
                        server.send_message(msg)
                break
            except Exception as send_err:
                attempts += 1
                if attempts > max_attempts:
                    raise send_err
                time.sleep(delay)
                delay = int(delay * backoff)

        return True
    except Exception as e:
        st.warning(f"Email send failed: {str(e)}")
        return False

def schedule_email_campaign(campaign_id: int, lead_ids: List[int], delay_minutes: int = 5, sender_profile_id: Optional[str] = None, rate_limit_per_min: Optional[int] = None, attachments: Optional[List[Dict]] = None, stop_after_minutes: Optional[int] = None, auth_override: Optional[Dict] = None, dry_run: bool = False, max_recipients: Optional[int] = None, send_window: Optional[Dict] = None, exclude_domains: Optional[List[str]] = None, utm_params: Optional[Dict[str,str]] = None, custom_headers: Optional[Dict[str,str]] = None):
    """Schedule email campaign with delay"""
    def send_campaign():
        time.sleep(delay_minutes * 60)  # Convert minutes to seconds
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Get campaign details
        cursor.execute("SELECT name, subject, content FROM campaigns WHERE id = ?", (campaign_id,))
        campaign = cursor.fetchone()
        
        if campaign:
            name, subject, content = campaign
            
            # Get lead details
            # Deduplicate by ID and email
            unique_ids = list(dict.fromkeys([int(x) for x in lead_ids]))
            placeholders = ','.join(['?' for _ in unique_ids])
            cursor.execute(f"SELECT id, name, email, company FROM leads WHERE id IN ({placeholders})", unique_ids)
            rows = cursor.fetchall()
            # Deduplicate by email
            seen_emails = set()
            leads = []
            for r in rows:
                if r[2] and r[2].lower() not in seen_emails:
                    leads.append(r)
                    seen_emails.add(r[2].lower())
            # Exclude domains if provided
            try:
                if exclude_domains:
                    ed = set([d.lower() for d in exclude_domains])
                    def domain_of(e):
                        return e.split('@')[-1].lower() if '@' in e else ''
                    leads = [r for r in leads if domain_of((r[2] or '').lower()) not in ed]
            except Exception:
                pass
            # Apply max recipients cap
            if max_recipients and max_recipients > 0:
                leads = leads[:max_recipients]
            
            sent_count = 0
            # Determine per-email delay from selected profile or override
            per_email_delay = 0
            try:
                per_min = 0
                if rate_limit_per_min and int(rate_limit_per_min) > 0:
                    per_min = int(rate_limit_per_min)
                else:
                    user_id = st.session_state.user['id'] if 'user' in st.session_state and st.session_state.user else None
                    profiles_data = load_smtp_profiles(user_id)
                    selected_profile = get_profile_by_id(profiles_data, sender_profile_id) if sender_profile_id else get_default_profile(profiles_data)
                    if selected_profile and int(selected_profile.get('rate_limit_per_min', 0)) > 0:
                        per_min = int(selected_profile.get('rate_limit_per_min'))
                    else:
                        cfg = load_smtp_config(user_id)
                        if cfg and int(cfg.get('rate_limit_per_min', 0)) > 0:
                            per_min = int(cfg.get('rate_limit_per_min'))
                if per_min > 0:
                    per_email_delay = max(0, 60.0 / float(per_min))
            except Exception:
                per_email_delay = 0
            start_ts = time.time()
            for lead in leads:
                if stop_after_minutes and stop_after_minutes > 0:
                    if (time.time() - start_ts) >= stop_after_minutes * 60:
                        break
                # Respect send window if set
                if send_window and (send_window.get('start') or send_window.get('end')):
                    now = datetime.now().time()
                    try:
                        from datetime import time as dtime
                        start_t = datetime.fromisoformat(send_window['start']).time() if send_window.get('start') else dtime(0,0)
                        end_t = datetime.fromisoformat(send_window['end']).time() if send_window.get('end') else dtime(23,59,59)
                        if not (start_t <= now <= end_t):
                            time.sleep(30)
                            continue
                    except Exception:
                        pass
                lead_id, lead_name, lead_email, lead_company = lead
                
                # Personalize content
                personalized_content = content.replace('{name}', lead_name).replace('{company}', lead_company or '')
                
                # Send email (simulated)
                if dry_run or send_email_simulation(lead_email, subject, personalized_content, profile_id=sender_profile_id, attachments=attachments, auth_override=auth_override, custom_headers=custom_headers, utm_params=utm_params):
                    # Record in tracking table
                    status_val = 'Dry-Run' if dry_run else 'Sent'
                    cursor.execute('''
                        INSERT INTO email_tracking (campaign_id, lead_id, email, status, sent_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (campaign_id, lead_id, lead_email, status_val))
                    sent_count += 1
                if per_email_delay > 0:
                    time.sleep(per_email_delay)
            
            # Update campaign status
            cursor.execute("UPDATE campaigns SET status = 'Sent', sent_at = CURRENT_TIMESTAMP WHERE id = ?", (campaign_id,))
            conn.commit()
            
            st.success(f"Campaign '{name}' sent to {sent_count} leads!")
        
        conn.close()
        
    # Run in background thread
    thread = threading.Thread(target=send_campaign)
    thread.daemon = True
    thread.start()

# Main application
def main():
    """Main application entry point"""
    load_css()
    _start_ws_client()
    
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'Home'
    
    # Header
    st.markdown("""
    <div class="cinematic-header">
        <div class="header-content">
            <h1 class="main-title">🚀 LeadAI Pro</h1>
            <p class="subtitle">AI-Powered Lead Management & Email Marketing Platform</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Authentication
    if not st.session_state.authenticated:
        show_login_page()
    else:
        show_main_app()

def show_login_page():
    """Show login/register page"""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div class="dashboard-card">
            <h2 style="text-align: center; margin-bottom: 2rem;">🔐 Authentication</h2>
    </div>
    """, unsafe_allow_html=True)
    
        tab1, tab2 = st.tabs(["Login", "Register"])
        
        with tab1:
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
                submit = st.form_submit_button("Login", type="primary")
                
                if submit:
                    if username and password:
                        user = authenticate_user(username, password)
                        if user:
                            st.session_state.authenticated = True
                            st.session_state.user = user
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password")
                    else:
                        st.error("Please fill in all fields")
        
        with tab2:
            with st.form("register_form"):
                new_username = st.text_input("Username", placeholder="Choose a username", key="reg_username")
                new_email = st.text_input("Email", placeholder="Enter your email", key="reg_email")
                new_password = st.text_input("Password", type="password", placeholder="Choose a password", key="reg_password")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password", key="reg_confirm")
                role = st.selectbox("Role", ["User", "Admin"], key="reg_role")
                submit_reg = st.form_submit_button("Register", type="primary")
                
                if submit_reg:
                    if new_username and new_email and new_password and confirm_password:
                        if new_password == confirm_password:
                            if register_user(new_username, new_email, new_password, role.lower()):
                                st.success("Registration successful! Please login.")
                            else:
                                st.error("Username or email already exists")
                        else:
                            st.error("Passwords do not match")
                    else:
                        st.error("Please fill in all fields")

def show_main_app():
    """Show main application after authentication"""
    # Sidebar Navigation
    with st.sidebar:
        st.markdown(f"### 👋 Welcome, {st.session_state.user['username']}")
        st.markdown(f"**Role:** {st.session_state.user['role'].title()}")
        
        st.markdown("---")
        st.markdown("### 🎯 Navigation")
        
        pages = ["Home", "Lead Generation", "Lead Management", "Email Campaigns", "Analytics", "AI Assistant", "Settings"]
        current_page = st.selectbox("Choose a page", pages, key="nav_select")
        
        st.markdown("---")
        # Session-level sender selection
        try:
            user_id = st.session_state.user['id']
            profiles_data = load_smtp_profiles(user_id)
            profile_names = [f"{p.get('name','Unnamed')} ({p.get('smtp_username','')})" for p in profiles_data.get('profiles', [])]
            profile_ids = [p.get('id') for p in profiles_data.get('profiles', [])]
            default_prof = get_default_profile(profiles_data)
            default_idx = profile_ids.index(default_prof.get('id')) if default_prof and default_prof.get('id') in profile_ids else 0 if profile_ids else -1
            chosen_idx = st.selectbox("Active sender profile", options=list(range(len(profile_names))) if profile_names else [-1], format_func=(lambda i: profile_names[i] if i >= 0 else "No profiles"), index=default_idx if default_idx >= 0 else 0, key="active_sender_selector")
            active_id = profile_ids[chosen_idx] if profile_ids and chosen_idx >= 0 else None
            set_session_active_profile_id(active_id)
        except Exception:
            pass
        
        st.markdown("---")
        
        # Quick Stats
        analytics = get_analytics(st.session_state.user['id'])
        st.markdown("### 📊 Quick Stats")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Leads", analytics['lead_count'])
        with col2:
            st.metric("Campaigns", analytics['campaign_count'])
        
        st.markdown("---")
        st.markdown("### ⏱️ Real-time Counters")
        render_realtime_counters(st.session_state.user['id'])
    
    # Logout button
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()
    
    # Main Content
    if current_page == "Home":
        show_home_page()
    elif current_page == "Lead Generation":
        show_lead_generation()
    elif current_page == "Lead Management":
        show_lead_management()
    elif current_page == "Email Campaigns":
        show_email_campaigns()
    elif current_page == "Analytics":
        show_analytics()
    elif current_page == "AI Assistant":
        show_ai_assistant()
    elif current_page == "Settings":
        show_settings()

def show_home_page():
    """Show home dashboard"""
    st.markdown("## 📊 Dashboard Overview")
    render_realtime_counters(st.session_state.user['id'])
    
    # Get analytics
    analytics = get_analytics(st.session_state.user['id'])
    
    # Key Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{analytics['lead_count']}</div>
            <div class="metric-label">Total Leads</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        open_rate = (analytics['opened_emails'] / analytics['sent_emails'] * 100) if analytics['sent_emails'] > 0 else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{open_rate:.1f}%</div>
            <div class="metric-label">Open Rate</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        click_rate = (analytics['clicked_emails'] / analytics['sent_emails'] * 100) if analytics['sent_emails'] > 0 else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{click_rate:.1f}%</div>
            <div class="metric-label">Click Rate</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{analytics['campaign_count']}</div>
            <div class="metric-label">Campaigns</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Recent Activity
    st.markdown("## 📈 Recent Activity")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="dashboard-card">
            <h3>📊 Lead Distribution</h3>
            <p>Visual representation of your lead categories</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Lead distribution chart
        leads_df = get_user_leads(st.session_state.user['id'])
        if not leads_df.empty:
            category_counts = leads_df['category'].value_counts()
            fig = px.pie(values=category_counts.values, names=category_counts.index, title="Lead Categories")
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("""
        <div class="dashboard-card">
            <h3>📧 Email Performance</h3>
            <p>Track your email campaign effectiveness</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Email performance metrics
        if analytics['sent_emails'] > 0:
            performance_data = {
                'Metric': ['Sent', 'Opened', 'Clicked'],
                'Count': [analytics['sent_emails'], analytics['opened_emails'], analytics['clicked_emails']]
            }
            fig = px.bar(performance_data, x='Metric', y='Count', title="Email Performance")
            st.plotly_chart(fig, use_container_width=True)

def show_lead_generation():
    """Show lead generation interface with scraping capabilities"""
    st.markdown("## 🔍 Lead Generation")
    render_realtime_counters(st.session_state.user['id'])
    
    if not LEAD_GENERATION_AVAILABLE:
        st.error("Lead generation features are not available. Please ensure all dependencies are installed.")
        return
    
    # Initialize orchestrator
    if 'lead_orchestrator' not in st.session_state:
        try:
            st.session_state.lead_orchestrator = LeadGenerationOrchestrator()
        except Exception as e:
            st.error(f"Failed to initialize lead generation system: {e}")
            st.stop()
    
    orchestrator = st.session_state.lead_orchestrator
    
    # Check if database is available
    if not orchestrator.db:
        st.warning("⚠️ Lead generation database is not available. Some features may be limited.")
        st.info("You can still use the scrapers, but leads won't be saved to the database.")
    
    # Lead Generation Form
    st.markdown("### 📝 Search Criteria")
    
    col1, col2 = st.columns(2)
    
    with col1:
        city = st.text_input("City *", placeholder="e.g., New York", help="Required: City to search in")
        country = st.text_input("Country *", placeholder="e.g., United States", help="Required: Country to search in")
        niche = st.text_input("Niche/Industry *", placeholder="e.g., restaurants, software, healthcare", help="Required: Industry or business type")
    
    with col2:
        business_name = st.text_input("Business Name (Optional)", placeholder="e.g., McDonald's", help="Optional: Specific business name to search for")
        limit = st.number_input("Number of Leads", min_value=1, max_value=500, value=50, help="Maximum number of leads to generate")
    
    # Source Selection
    st.markdown("### 🌐 Data Sources")
    
    available_sources = orchestrator.get_available_sources()
    source_info = orchestrator.get_source_info()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Free Sources:**")
        free_sources = ['test', 'google_maps', 'yelp', 'yellowpages', 'linkedin']
        selected_free = []
        for source in free_sources:
            if source in available_sources:
                info = source_info.get(source, {})
                if st.checkbox(f"✅ {info.get('name', source)}", value=True, key=f"source_{source}"):
                    selected_free.append(source)
    
    with col2:
        st.markdown("**Source Information:**")
        for source in selected_free:
            info = source_info.get(source, {})
            st.info(f"**{info.get('name', source)}**: {info.get('description', '')} | Rate: {info.get('rate_limit', 'N/A')} | Reliability: {info.get('reliability', 'N/A')}")
    
    # Advanced Options
    with st.expander("🔧 Advanced Options"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Deduplication Settings:**")
            dedup_enabled = st.checkbox("Enable Deduplication", value=True, help="Remove duplicate leads based on name+address or email+phone")
            cleanup_existing = st.checkbox("Cleanup Existing Duplicates", value=False, help="Remove duplicates from existing database")
        
        with col2:
            st.markdown("**Export Settings:**")
            auto_export = st.checkbox("Auto-export to CSV", value=False, help="Automatically export results to CSV file")
            export_filename = st.text_input("Export Filename (Optional)", placeholder="leads_export.csv", help="Custom filename for CSV export")
    
    # Validation
    if not city or not country or not niche:
        st.warning("Please fill in all required fields (City, Country, Niche)")
        return
    
    if not selected_free:
        st.warning("Please select at least one data source")
        return
    
    # Generate Leads Button
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button("🚀 Generate Leads", type="primary", use_container_width=True):
            # Cleanup existing duplicates if requested
            if cleanup_existing:
                with st.spinner("Cleaning up existing duplicates..."):
                    duplicates_found, duplicates_removed = orchestrator.cleanup_duplicates()
                    if duplicates_removed > 0:
                        st.success(f"Removed {duplicates_removed} duplicate leads from database")
            
            # Progress tracking
            progress_container = st.container()
            status_container = st.container()
            
            with progress_container:
                progress_bar = st.progress(0)
                status_text = st.empty()
            
            def progress_callback(message):
                status_text.text(message)
                progress_bar.progress(min(100, progress_bar.progress(0) + 10))
            
            # Generate leads
            with status_container:
                with st.spinner("Generating leads from multiple sources..."):
                    results = orchestrator.generate_leads(
                        city=city,
                        country=country,
                        niche=niche,
                        business_name=business_name if business_name else None,
                        limit=limit,
                        sources=selected_free,
                        progress_callback=progress_callback
                    )
            
            # Display results
            if results.get('status') == 'completed':
                st.success(f"✅ Lead generation completed!")
                
                # Results summary
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Found", results.get('total_found', 0))
                
                with col2:
                    st.metric("Duplicates Removed", results.get('duplicates_removed', 0))
                
                with col3:
                    st.metric("Successfully Inserted", results.get('successfully_inserted', 0))
                
                with col4:
                    st.metric("Sources Used", len(results.get('sources_used', [])))
                
                # Per-source breakdown
                if results.get('leads_per_source'):
                    st.markdown("### 📊 Results by Source")
                    source_data = []
                    for source, count in results['leads_per_source'].items():
                        source_info_name = source_info.get(source, {}).get('name', source)
                        source_data.append({
                            'Source': source_info_name,
                            'Leads Found': count
                        })
                    
                    if source_data:
                        df_sources = pd.DataFrame(source_data)
                        st.dataframe(df_sources, use_container_width=True)
                
                # Errors
                if results.get('errors'):
                    st.markdown("### ⚠️ Errors")
                    for source, error in results['errors'].items():
                        st.error(f"**{source_info.get(source, {}).get('name', source)}**: {error}")
                
                # Auto-export
                if auto_export and results.get('successfully_inserted', 0) > 0:
                    try:
                        filename = export_filename if export_filename else None
                        csv_path = orchestrator.export_leads(filename=filename)
                        st.success(f"📁 Leads exported to: {csv_path}")
                        
                        # Download button
                        with open(csv_path, 'rb') as f:
                            st.download_button(
                                label="📥 Download CSV",
                                data=f.read(),
                                file_name=csv_path,
                                mime="text/csv"
                            )
                    except Exception as e:
                        st.error(f"Error exporting leads: {e}")
                
            else:
                st.error(f"❌ Lead generation failed: {results.get('error', 'Unknown error')}")
    
    # Recent Results
    st.markdown("### 📋 Recent Lead Generation Results")
    
    try:
        # Get recent leads from database
        recent_leads = orchestrator.db.get_leads(limit=10)
        
        if recent_leads:
            # Convert to DataFrame for display
            df_recent = pd.DataFrame(recent_leads)
            
            # Select relevant columns
            display_columns = ['name', 'city', 'country', 'niche', 'source', 'created_at']
            available_columns = [col for col in display_columns if col in df_recent.columns]
            
            if available_columns:
                st.dataframe(
                    df_recent[available_columns], 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No recent leads found")
        else:
            st.info("No leads found in database")
    
    except Exception as e:
        st.error(f"Error loading recent leads: {e}")
    
    # Lead Statistics
    st.markdown("### 📈 Lead Statistics")
    
    try:
        stats = orchestrator.get_lead_stats()
        
        if stats:
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Total Leads", stats.get('total_leads', 0))
                st.metric("Recent Leads (7 days)", stats.get('recent_leads', 0))
            
            with col2:
                if stats.get('leads_by_source'):
                    st.markdown("**Leads by Source:**")
                    for source, count in list(stats['leads_by_source'].items())[:5]:
                        st.text(f"{source}: {count}")
            
            # Export all leads button
            if stats.get('total_leads', 0) > 0:
                if st.button("📊 Export All Leads to CSV"):
                    try:
                        csv_path = orchestrator.export_leads()
                        st.success(f"All leads exported to: {csv_path}")
                        
                        with open(csv_path, 'rb') as f:
                            st.download_button(
                                label="📥 Download All Leads CSV",
                                data=f.read(),
                                file_name=csv_path,
                                mime="text/csv"
                            )
                    except Exception as e:
                        st.error(f"Error exporting all leads: {e}")
    
    except Exception as e:
        st.error(f"Error loading lead statistics: {e}")

def show_lead_management():
    """Show lead management interface"""
    st.markdown("## 👥 Lead Management")
    render_realtime_counters(st.session_state.user['id'])
    st.markdown("### ✉️ Quick Send to a Lead")
    with st.form("quick_send_lead_form"):
        q_col1, q_col2 = st.columns(2)
        with q_col1:
            selected_profile_id_q = render_sender_selector_ui(st.session_state.user['id'], label="Sender for quick send")
            quick_recipient = st.text_input("Recipient email")
        with q_col2:
            quick_subject = st.text_input("Subject")
        quick_body = st.text_area("Message", height=120)
        quick_files = st.file_uploader("Attachments", accept_multiple_files=True)
        quick_atts = []
        if quick_files:
            for uf in quick_files:
                try:
                    quick_atts.append({'filename': uf.name, 'content': uf.getvalue(), 'mime_type': uf.type or 'application/octet-stream'})
                except Exception:
                    continue
        if st.form_submit_button("Send Now", type="primary"):
            if quick_recipient and quick_subject and quick_body:
                ok = send_email_simulation(quick_recipient, quick_subject, quick_body, profile_id=selected_profile_id_q, attachments=quick_atts if quick_atts else None)
                if ok:
                    st.success("Email sent (or simulated if SMTP not configured)")
                else:
                    st.error("Send failed")
            else:
                st.error("Please fill recipient, subject, and message")
    
    # Upload Section
    st.markdown("""
    <div class="dashboard-card">
        <h3>📁 Upload Lead Data</h3>
        <p>Upload CSV files with lead information for AI processing</p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type="csv",
        help="Upload a CSV file with lead data including names, emails, companies, and phone numbers"
    )
    
    if uploaded_file is not None:
        try:
            # Read CSV
            df = pd.read_csv(uploaded_file)
            
            # Validate required columns
            required_columns = ['name', 'email']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"Missing required columns: {', '.join(missing_columns)}")
            else:
                st.success("✅ File uploaded successfully!")
                
                # Show preview
                st.markdown("### 📋 Data Preview")
                st.dataframe(df.head(10))
                
                # Process leads
                if st.button("🚀 Process Leads", type="primary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    processed_count = 0
                    for index, row in df.iterrows():
                        try:
                            # Validate email
                            validate_email(row['email'])
                            
                            lead_data = {
                                'name': row['name'],
                                'email': row['email'],
                                'company': row.get('company', ''),
                                'phone': row.get('phone', ''),
                                'title': row.get('title', ''),
                                'industry': row.get('industry', ''),
                                'category': row.get('category', 'General')
                            }
                            
                            if add_lead(st.session_state.user['id'], lead_data):
                                processed_count += 1
                            
                            progress_bar.progress((index + 1) / len(df))
                            status_text.text(f"Processing lead {index + 1} of {len(df)}")
                        except EmailNotValidError:
                            st.warning(f"Invalid email for {row['name']}: {row['email']}")
                        except Exception as e:
                            st.warning(f"Error processing {row.get('name', 'Unknown')}: {str(e)}")
                    
                    st.success(f"✅ Successfully processed {processed_count} leads!")
                    progress_bar.empty()
                    status_text.empty()
        except Exception as e:
            st.error(f"Error reading CSV file: {str(e)}")
        
    # Display existing leads
    st.markdown("## 📋 Your Leads")
            
    leads_df = get_user_leads(st.session_state.user['id'])
    
    if not leads_df.empty:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            categories = ['All'] + list(leads_df['category'].unique())
            selected_category = st.selectbox("Filter by Category", categories)
        with col2:
            statuses = ['All'] + list(leads_df['status'].unique())
            selected_status = st.selectbox("Filter by Status", statuses)
        
        # Apply filters
        filtered_df = leads_df.copy()
        if selected_category != 'All':
            filtered_df = filtered_df[filtered_df['category'] == selected_category]
        if selected_status != 'All':
            filtered_df = filtered_df[filtered_df['status'] == selected_status]
        
        # Display table
        st.dataframe(filtered_df[['name', 'email', 'company', 'category', 'status', 'score']])
        
        # Export button
        if st.button("📥 Export Leads as CSV"):
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.info("No leads found. Upload a CSV file to get started!")

def show_email_campaigns():
    """Show email campaign management"""
    st.markdown("## 📧 Email Campaigns")
    render_realtime_counters(st.session_state.user['id'])
    st.markdown("### ✉️ Quick Send (Ad-hoc)")
    with st.form("quick_send_campaigns_form"):
        qc1, qc2 = st.columns(2)
        with qc1:
            selected_profile_id_ec = render_sender_selector_ui(st.session_state.user['id'], label="Sender for quick send")
            ec_recipient = st.text_input("Recipient email")
        with qc2:
            ec_subject = st.text_input("Subject")
        ec_body = st.text_area("Message", height=120)
        ec_files = st.file_uploader("Attachments", accept_multiple_files=True, key="ec_quick_files")
        ec_atts = []
        if ec_files:
            for uf in ec_files:
                try:
                    ec_atts.append({'filename': uf.name, 'content': uf.getvalue(), 'mime_type': uf.type or 'application/octet-stream'})
                except Exception:
                    continue
        if st.form_submit_button("Send Now", type="primary"):
            if ec_recipient and ec_subject and ec_body:
                ok = send_email_simulation(ec_recipient, ec_subject, ec_body, profile_id=selected_profile_id_ec, attachments=ec_atts if ec_atts else None)
                if ok:
                    st.success("Email sent (or simulated if SMTP not configured)")
                else:
                    st.error("Send failed")
            else:
                st.error("Please fill recipient, subject, and message")
    
    # Create new campaign
    st.markdown("""
    <div class="dashboard-card">
        <h3>✍️ Create New Campaign</h3>
        <p>Design and schedule your email campaigns</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("campaign_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            campaign_name = st.text_input("Campaign Name", placeholder="Enter campaign name")
            subject_line = st.text_input("Subject Line", placeholder="Enter email subject")
        
        with col2:
            template_type = st.selectbox("Template Type", ["Newsletter", "Promotional", "Follow-up", "Welcome"])
            send_delay = st.number_input("Send Delay (minutes)", min_value=1, max_value=60, value=5)
            stop_after_minutes = st.number_input("Stop sending after (minutes, 0 = no stop)", min_value=0, max_value=1440, value=0, help="Optional cap to end the job even if not all recipients are processed")
            st.markdown("#### Auth override (optional)")
            use_oauth_override = st.checkbox("Use OAuth2 for this campaign", value=False)
            oauth_client_id_c = st.text_input("OAuth Client ID (override)", value="" if not use_oauth_override else "")
            oauth_client_secret_c = st.text_input("OAuth Client Secret (override)", type="password", value="" if not use_oauth_override else "")
            oauth_refresh_token_c = st.text_input("OAuth Refresh Token (override)", type="password", value="" if not use_oauth_override else "")
            st.markdown("#### Advanced controls")
            dry_run = st.checkbox("Dry-run (no emails sent)", value=False, help="Preview and track without actually sending")
            max_recipients = st.number_input("Max recipients for this send (0 = unlimited)", min_value=0, max_value=100000, value=0)
            send_window_start = st.time_input("Send window start", value=None, help="Optional daily start time")
            send_window_end = st.time_input("Send window end", value=None, help="Optional daily end time")
            excluded_domains_text = st.text_input("Exclude recipient domains (comma-separated)", value="", help="Example: gmail.com,yahoo.com")
            safety_threshold = st.number_input("Safety threshold (require double-confirm)", min_value=0, max_value=100000, value=500, help="If preview count exceeds this, an extra confirmation is required")
            st.markdown("#### UTM tagging")
            utm_source = st.text_input("utm_source", value="leadai")
            utm_medium = st.text_input("utm_medium", value="email")
            utm_campaign = st.text_input("utm_campaign", value="campaign")
            utm_content = st.text_input("utm_content", value="")
            st.markdown("#### Custom headers")
            headers_text = st.text_area("Custom headers (key:value per line)", value="")
        # Sender profile selection
        user_id = st.session_state.user['id']
        profiles_data = load_smtp_profiles(user_id)
        profile_options = [f"{p.get('name','Unnamed')} ({p.get('smtp_username','')})" for p in profiles_data.get('profiles', [])]
        profile_ids = [p.get('id') for p in profiles_data.get('profiles', [])]
        default_prof = get_default_profile(profiles_data)
        default_index = profile_ids.index(default_prof.get('id')) if default_prof and default_prof.get('id') in profile_ids else 0 if profile_ids else -1
        selected_index = st.selectbox("Sender Profile", options=list(range(len(profile_options))) if profile_options else [-1], format_func=(lambda i: profile_options[i] if i >= 0 else "No profiles configured"), index=default_index if default_index >= 0 else 0)
        selected_profile_id = profile_ids[selected_index] if profile_ids and selected_index >= 0 else None
        per_min_limit = st.number_input("Rate limit (emails per minute)", min_value=0, max_value=120, value=int(default_prof.get('rate_limit_per_min', 0)) if default_prof else 0, help="0 uses profile or global default")

        # Attachments upload
        st.markdown("### Attachments (optional)")
        uploaded_files = st.file_uploader("Upload one or more files", accept_multiple_files=True)
        attachments_payload = []
        if uploaded_files:
            for uf in uploaded_files:
                try:
                    attachments_payload.append({
                        'filename': uf.name,
                        'content': uf.getvalue(),
                        'mime_type': uf.type or 'application/octet-stream'
                    })
                except Exception:
                    continue
        
        # Email content
        email_content = st.text_area(
            "Email Content",
            placeholder="Write your email content here. Use {name} and {company} for personalization.",
            height=200
        )
        
        # AI assistance
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("🤖 Generate Subject Line", type="secondary"):
                if email_content:
                    generated_subject = generate_subject_line(email_content[:100])
                    st.session_state.generated_subject = generated_subject
                else:
                    st.warning("Please enter email content first")
        
        with col2:
            if st.form_submit_button("🤖 Improve Content", type="secondary"):
                if email_content:
                    improved_content = generate_email_content(f"Improve this email: {email_content}")
                    st.session_state.improved_content = improved_content
            else:
                    st.warning("Please enter email content first")
        
        # Use generated content
        if 'generated_subject' in st.session_state:
            subject_line = st.text_input("Subject Line", value=st.session_state.generated_subject, key="subject_input")
        
        if 'improved_content' in st.session_state:
            email_content = st.text_area("Email Content", value=st.session_state.improved_content, height=200, key="content_input")
        
        # Target leads (select by unique ID to avoid duplicate names)
        leads_df = get_user_leads(st.session_state.user['id'])
        if not leads_df.empty:
            # Build unique labels
            display_labels = [f"{row['name']} <{row['email']}> (#{row['id']})" for _, row in leads_df.iterrows()]
            id_by_label = {label: int(leads_df.iloc[i]['id']) for i, label in enumerate(display_labels)}
            selected_labels = st.multiselect("Select Target Leads", display_labels)
            selected_lead_ids = [id_by_label[lbl] for lbl in selected_labels]
        else:
            selected_lead_ids = []
            st.warning("No leads available. Please add leads first.")
        
        # Preview recipients
        preview_clicked = st.form_submit_button("Preview recipients", type="secondary")
        if preview_clicked:
            try:
                conn = sqlite3.connect(DB_NAME)
                cur = conn.cursor()
                if selected_lead_ids:
                    unique_ids = list(dict.fromkeys([int(x) for x in selected_lead_ids]))
                    placeholders = ','.join(['?' for _ in unique_ids])
                    cur.execute(f"SELECT id, name, email, company FROM leads WHERE id IN ({placeholders})", unique_ids)
                    rows = cur.fetchall()
                else:
                    rows = []
                conn.close()
                # Dedup by email
                seen = set()
                final_rows = []
                for r in rows:
                    email = (r[2] or '').lower()
                    if email and email not in seen:
                        final_rows.append(r)
                        seen.add(email)
                # Apply domain exclusions
                try:
                    excluded_domains = [d.strip().lower() for d in excluded_domains_text.split(',') if d.strip()]
                    if excluded_domains:
                        def domain_of(e):
                            return e.split('@')[-1].lower() if '@' in e else ''
                        final_rows = [r for r in final_rows if domain_of((r[2] or '').lower()) not in set(excluded_domains)]
                except Exception:
                    pass
                # Apply warmup allowance and max cap for preview
                user_id = st.session_state.user['id']
                profiles_data = load_smtp_profiles(user_id)
                sel_profile = get_profile_by_id(profiles_data, selected_profile_id) if selected_profile_id else get_default_profile(profiles_data)
                allowance = get_warmup_allowance_for_profile(user_id, sel_profile)
                max_cap = int(max_recipients) if max_recipients else None
                if allowance is not None:
                    final_rows = final_rows[:allowance]
                if max_cap and max_cap > 0:
                    final_rows = final_rows[:max_cap]
                st.session_state.campaign_preview_rows = final_rows
                st.success(f"Preview ready: {len(final_rows)} recipients after dedup and caps")
                with st.expander("Show recipients preview", expanded=False):
                    st.dataframe([{ 'id': r[0], 'name': r[1], 'email': r[2], 'company': r[3] } for r in final_rows])
                    # Export CSV
                    try:
                        import io, csv
                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerow(["id","name","email","company"])
                        for r in final_rows:
                            writer.writerow([r[0], r[1], r[2], r[3]])
                        csv_bytes = output.getvalue().encode('utf-8')
                        st.download_button(
                            label="Download preview CSV",
                            data=csv_bytes,
                            file_name=f"campaign_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    except Exception:
                        pass
                # Estimated duration
                try:
                    rate = int(per_min_limit) if per_min_limit else 0
                    count = len(final_rows)
                    if rate > 0 and count > 0:
                        import math
                        minutes = math.ceil(count / rate)
                        st.info(f"Estimated send duration: ~{minutes} minute(s) at {rate}/min (plus initial delay of {send_delay} min)")
                    else:
                        st.info("Estimated send duration: depends on your configured rate limit.")
                except Exception:
                    pass
            except Exception as e:
                st.error(f"Preview failed: {str(e)}")

        confirm_ok = st.checkbox("I have reviewed the preview and confirm the recipients")
        extra_confirm_ok = False
        try:
            preview_count = len(st.session_state.get('campaign_preview_rows', []) or [])
            if safety_threshold and preview_count > int(safety_threshold):
                extra_confirm_ok = st.checkbox(f"Large send ({preview_count} > {int(safety_threshold)}). Confirm I still want to proceed.")
            else:
                extra_confirm_ok = True
        except Exception:
            extra_confirm_ok = True
        
        # Submit campaign
        if st.form_submit_button("🚀 Create Campaign", type="primary"):
            if not confirm_ok or not extra_confirm_ok:
                st.error("Please preview recipients and confirm before scheduling.")
            elif campaign_name and subject_line and email_content and selected_lead_ids:
                campaign_data = {
                    'name': campaign_name,
                    'subject': subject_line,
                    'content': email_content
                }
                
                if create_campaign(st.session_state.user['id'], campaign_data):
                    st.success("Campaign created successfully!")
                    
                    # Schedule emails
                    # Get the latest campaign ID
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM campaigns WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (st.session_state.user['id'],))
                    campaign_id = cursor.fetchone()[0]
                    conn.close()
                    
                    # Build auth override if requested
                    auth_override = None
                    if use_oauth_override:
                        auth_override = {
                            'oauth2': True,
                            'oauth_client_id': oauth_client_id_c,
                            'oauth_client_secret': oauth_client_secret_c,
                            'oauth_refresh_token': oauth_refresh_token_c
                        }
                    # Schedule campaign with chosen sender, rate limit, attachments, stop time, and auth override
                    schedule_email_campaign(
                        campaign_id,
                        selected_lead_ids,
                        send_delay,
                        sender_profile_id=selected_profile_id,
                        rate_limit_per_min=int(per_min_limit) if per_min_limit else None,
                        attachments=attachments_payload if attachments_payload else None,
                        stop_after_minutes=int(stop_after_minutes) if stop_after_minutes else None,
                        auth_override=auth_override,
                        dry_run=bool(dry_run),
                        max_recipients=int(max_recipients) if max_recipients else None,
                        send_window={
                            'start': send_window_start.isoformat() if send_window_start else None,
                            'end': send_window_end.isoformat() if send_window_end else None
                        },
                        exclude_domains=[d.strip().lower() for d in excluded_domains_text.split(',') if d.strip()],
                        utm_params={
                            'utm_source': utm_source,
                            'utm_medium': utm_medium,
                            'utm_campaign': utm_campaign,
                            'utm_content': utm_content
                        } if utm_source or utm_medium or utm_campaign or utm_content else None,
                        custom_headers={
                            kv.split(':',1)[0].strip(): kv.split(':',1)[1].strip()
                            for kv in headers_text.splitlines() if ':' in kv
                        } if headers_text else None
                    )
                    if stop_after_minutes and stop_after_minutes > 0:
                        st.info(f"Campaign will stop automatically after {int(stop_after_minutes)} minutes if still running.")
                    st.info(f"Campaign scheduled to send in {send_delay} minutes!")
            else:
                st.error("Please fill in all fields and select target leads")
    
    # Display existing campaigns
    st.markdown("## 📋 Your Campaigns")
    
    campaigns_df = get_campaigns(st.session_state.user['id'])
    
    if not campaigns_df.empty:
        st.dataframe(campaigns_df[['name', 'subject', 'status', 'created_at']])
        
        # Export campaigns
        if st.button("📥 Export Campaigns as CSV"):
            csv = campaigns_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"campaigns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No campaigns found. Create your first campaign above!")

def show_analytics():
    """Show analytics dashboard"""
    st.markdown("## 📊 Analytics Dashboard")
    render_realtime_counters(st.session_state.user['id'])
    
    analytics = get_analytics(st.session_state.user['id'])
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Leads", analytics['lead_count'])
    with col2:
        st.metric("Total Campaigns", analytics['campaign_count'])
    with col3:
        st.metric("Emails Sent", analytics['sent_emails'])
    with col4:
        open_rate = (analytics['opened_emails'] / analytics['sent_emails'] * 100) if analytics['sent_emails'] > 0 else 0
        st.metric("Open Rate", f"{open_rate:.1f}%")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📈 Lead Distribution")
        leads_df = get_user_leads(st.session_state.user['id'])
        if not leads_df.empty:
            category_counts = leads_df['category'].value_counts()
            fig = px.pie(values=category_counts.values, names=category_counts.index, title="Lead Categories")
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("### 📧 Email Performance")
        if analytics['sent_emails'] > 0:
            performance_data = {
                'Metric': ['Sent', 'Opened', 'Clicked'],
                'Count': [analytics['sent_emails'], analytics['opened_emails'], analytics['clicked_emails']]
            }
            fig = px.bar(performance_data, x='Metric', y='Count', title="Email Performance")
            st.plotly_chart(fig, use_container_width=True)

def show_ai_assistant():
    """Show AI assistant interface"""
    st.markdown("## 🤖 AI Assistant")
    render_realtime_counters(st.session_state.user['id'])
    st.markdown("### ✉️ Quick Send")
    with st.form("quick_send_ai_form"):
        ai_col1, ai_col2 = st.columns(2)
        with ai_col1:
            selected_profile_id_ai = render_sender_selector_ui(st.session_state.user['id'], label="Sender for quick send")
            ai_recipient = st.text_input("Recipient email")
        with ai_col2:
            ai_subject = st.text_input("Subject")
        ai_body = st.text_area("Message", height=120)
        ai_files = st.file_uploader("Attachments", accept_multiple_files=True, key="ai_quick_files")
        ai_atts = []
        if ai_files:
            for uf in ai_files:
                try:
                    ai_atts.append({'filename': uf.name, 'content': uf.getvalue(), 'mime_type': uf.type or 'application/octet-stream'})
                except Exception:
                    continue
        if st.form_submit_button("Send Now", type="primary"):
            if ai_recipient and ai_subject and ai_body:
                ok = send_email_simulation(ai_recipient, ai_subject, ai_body, profile_id=selected_profile_id_ai, attachments=ai_atts if ai_atts else None)
                if ok:
                    st.success("Email sent (or simulated if SMTP not configured)")
                else:
                    st.error("Send failed")
            else:
                st.error("Please fill recipient, subject, and message")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="dashboard-card">
            <h3>📝 AI Email Writer</h3>
            <p>Generate personalized email content using AI</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Email generation
        with st.form("ai_email_form"):
            email_prompt = st.text_area(
                "Describe your email",
                placeholder="e.g., Write a follow-up email for a graphic design client who hasn't responded to my proposal",
                height=100
            )
            
            if st.form_submit_button("🤖 Generate Email", type="primary"):
                if email_prompt:
                    with st.spinner("AI is generating your email..."):
                        generated_content = generate_email_content(email_prompt)
                        st.text_area("Generated Email", value=generated_content, height=200)
                else:
                    st.warning("Please enter a description for your email")
    
    with col2:
        st.markdown("""
        <div class="dashboard-card">
            <h3>🎯 Subject Line Generator</h3>
            <p>AI-powered subject line suggestions</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Subject line generation
        with st.form("ai_subject_form"):
            topic = st.text_input("Email Topic", placeholder="e.g., Follow-up on design proposal")
            
            if st.form_submit_button("🎯 Generate Subject", type="primary"):
                if topic:
                    with st.spinner("AI is generating subject lines..."):
                        generated_subject = generate_subject_line(topic)
                        st.text_input("Generated Subject Line", value=generated_subject)
                else:
                    st.warning("Please enter a topic for your email")

def show_settings():
    """Show settings page"""
    st.markdown("## ⚙️ Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 👤 User Profile")
        st.text_input("Username", value=st.session_state.user['username'], disabled=True)
        st.text_input("Email", value=st.session_state.user['email'], disabled=True)
        st.text_input("Role", value=st.session_state.user['role'].title(), disabled=True)
    
    with col2:
        st.markdown("### 🔧 System Configuration")
        st.checkbox("Email Notifications", value=True)
        st.checkbox("SMS Notifications", value=False)
        rate_limit = st.slider("Email Send Rate (per minute)", 1, 60, 12)

    st.markdown("### ✉️ Email SMTP Settings")
    with st.expander("Configure your own SMTP sender", expanded=False):
        user_id = st.session_state.user['id'] if 'user' in st.session_state and st.session_state.user else None
        existing = load_smtp_config(user_id) if user_id else None
        profiles_data = load_smtp_profiles(user_id) if user_id else { 'profiles': [], 'default_profile_id': None }
        st.markdown("#### Multiple Sender Profiles")
        # List existing profiles
        if profiles_data.get('profiles'):
            names = [f"{p.get('name','Unnamed')} — {p.get('smtp_username','')}" for p in profiles_data['profiles']]
            ids = [p.get('id') for p in profiles_data['profiles']]
            default_id = profiles_data.get('default_profile_id')
            selected_idx = st.selectbox("Select profile", options=list(range(len(names))), format_func=lambda i: ("⭐ " if ids[i]==default_id else "") + names[i])
            active_profile = profiles_data['profiles'][selected_idx]
        else:
            active_profile = None
            st.info("No profiles yet. Create one below.")

        c1, c2, c3 = st.columns(3)
        with c1:
            if active_profile and st.button("Set as default"):
                profiles_data['default_profile_id'] = active_profile.get('id')
                save_smtp_profiles(user_id, profiles_data)
                # Auto-apply to .env
                apply_profile_to_dotenv(active_profile)
                st.success("Default sender set and applied to .env")
        with c2:
            if active_profile and st.button("Delete profile"):
                profiles_data['profiles'] = [p for p in profiles_data['profiles'] if p.get('id') != active_profile.get('id')]
                if profiles_data.get('default_profile_id') == active_profile.get('id'):
                    profiles_data['default_profile_id'] = profiles_data['profiles'][0].get('id') if profiles_data['profiles'] else None
                save_smtp_profiles(user_id, profiles_data)
                st.warning("Profile deleted")
        with c3:
            if active_profile and st.button("Apply to .env"):
                if apply_profile_to_dotenv(active_profile):
                    st.success("Applied to .env")
                else:
                    st.error("Failed to update .env")

        with st.form("smtp_config_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                smtp_server = st.text_input("SMTP Server", value=(existing.get('smtp_server') if existing else "smtp.gmail.com"))
                smtp_port = st.number_input("SMTP Port", min_value=1, max_value=65535, value=int(existing.get('smtp_port', 587) if existing else 587))
                smtp_username = st.text_input("SMTP Username (sender email)", value=(existing.get('smtp_username') if existing else ""))
                from_name = st.text_input("From Name", value=(existing.get('from_name') if existing else "LeadAI Pro"))
            with col_b:
                from_email = st.text_input("From Email", value=(existing.get('from_email') if existing else (existing.get('smtp_username') if existing and existing.get('smtp_username') else st.session_state.user['email'])))
                reply_to = st.text_input("Reply-To (optional)", value=(existing.get('reply_to') if existing else ""))
                use_ssl = st.checkbox("Use SSL (SMTPS)", value=bool(existing.get('use_ssl', False)) if existing else False)
                use_starttls = st.checkbox("Use STARTTLS", value=bool(existing.get('use_starttls', True)) if existing else True)

            smtp_password = st.text_input("SMTP Password / App Password", type="password", value=(existing.get('smtp_password') if existing else ""))
            tracking_enabled = st.checkbox("Enable tracking pixel", value=bool(existing.get('tracking_enabled', True)) if existing else True)
            prof_name = st.text_input("Profile name (label)", value=(existing.get('name') if existing and existing.get('name') else "Primary"))
            prof_rate = st.number_input("Rate limit for this profile (emails per minute)", min_value=0, max_value=120, value=int(existing.get('rate_limit_per_min', 0)) if existing else 0)
            st.markdown("#### Gmail OAuth2 (optional)")
            oauth2_enabled = st.checkbox("Use Gmail OAuth2 instead of password", value=bool(existing.get('oauth2', False)) if existing else False)
            oauth_client_id = st.text_input("OAuth Client ID", value=(existing.get('oauth_client_id') if existing else ""))
            oauth_client_secret = st.text_input("OAuth Client Secret", type="password", value=(existing.get('oauth_client_secret') if existing else ""))
            oauth_refresh_token = st.text_input("OAuth Refresh Token", type="password", value=(existing.get('oauth_refresh_token') if existing else ""))
            st.markdown("#### Warmup")
            warmup_enabled = st.checkbox("Enable warmup daily cap", value=bool(existing.get('warmup_enabled', False)) if existing else False)
            warmup_max_per_day = st.number_input("Max emails per day (warmup)", min_value=0, max_value=10000, value=int(existing.get('warmup_max_per_day', 0)) if existing else 0)
            st.markdown("#### Retry policy")
            retry_max_attempts = st.number_input("Max retries", min_value=0, max_value=10, value=int(existing.get('retry_max_attempts', 3)) if existing else 3)
            retry_initial_seconds = st.number_input("Initial retry delay (seconds)", min_value=1, max_value=300, value=int(existing.get('retry_initial_seconds', 10)) if existing else 10)
            retry_backoff_factor = st.number_input("Backoff factor", min_value=1.0, max_value=5.0, value=float(existing.get('retry_backoff_factor', 2.0)) if existing else 2.0, step=0.1)

            submitted = st.form_submit_button("Save SMTP Settings", type="primary")
            if submitted:
                if not smtp_username or not smtp_password:
                    st.error("SMTP username and password are required")
                else:
                    cfg = {
                        'smtp_server': smtp_server,
                        'smtp_port': int(smtp_port),
                        'smtp_username': smtp_username,
                        'smtp_password': smtp_password,
                        'from_email': from_email or smtp_username,
                        'from_name': from_name or "LeadAI Pro",
                        'reply_to': reply_to,
                        'use_ssl': bool(use_ssl),
                        'use_starttls': bool(use_starttls),
                        'tracking_enabled': bool(tracking_enabled),
                        'rate_limit_per_min': int(prof_rate)
                    }
                    if oauth2_enabled:
                        cfg.update({
                            'oauth2': True,
                            'oauth_client_id': oauth_client_id,
                            'oauth_client_secret': oauth_client_secret,
                            'oauth_refresh_token': oauth_refresh_token
                        })
                    if warmup_enabled:
                        cfg.update({
                            'warmup_enabled': True,
                            'warmup_max_per_day': int(warmup_max_per_day)
                        })
                    cfg.update({
                        'retry_max_attempts': int(retry_max_attempts),
                        'retry_initial_seconds': int(retry_initial_seconds),
                        'retry_backoff_factor': float(retry_backoff_factor)
                    })
                    # legacy single-config save
                    if user_id:
                        save_smtp_config(user_id, cfg)
                        # save into profiles
                        profiles = load_smtp_profiles(user_id)
                        new_id = uuid.uuid4().hex
                        prof_entry = dict(cfg)
                        prof_entry['id'] = new_id
                        prof_entry['name'] = prof_name or "Primary"
                        profiles['profiles'].append(prof_entry)
                        is_first = not profiles.get('default_profile_id')
                        if is_first:
                            profiles['default_profile_id'] = new_id
                        if save_smtp_profiles(user_id, profiles):
                            # Auto-apply to .env if first/default
                            if is_first:
                                apply_profile_to_dotenv(prof_entry)
                            st.success("SMTP profile saved")
                        else:
                            st.error("Failed to save profile")
                    else:
                        st.error("Failed to save SMTP settings")

        col_test1, col_test2 = st.columns([2,1])
        with col_test1:
            test_recipient = st.text_input("Test recipient email", value=st.session_state.user['email'])
        with col_test2:
            if st.button("Send Test Email"):
                sel_prof_id = None
                try:
                    # use currently selected active_profile if exists
                    if profiles_data and profiles_data.get('profiles'):
                        sel_prof_id = profiles_data.get('default_profile_id')
                except Exception:
                    sel_prof_id = None
                ok = send_email_simulation(test_recipient, "LeadAI Pro Test Email", "<p>This is a test email from LeadAI Pro SMTP configuration.</p>", profile_id=sel_prof_id)
                if ok:
                    st.success("Test email sent (or simulated if SMTP not configured)")
                else:
                    st.error("Test email failed. Check your SMTP settings.")
    
    # Suppression list UI
    st.markdown("### 🚫 Suppression List")
    with st.expander("Manage suppression list", expanded=False):
        user_id = st.session_state.user['id']
        suppressed = load_suppression_list(user_id)
        suppressed_text = "\n".join(suppressed)
        new_text = st.text_area("Emails to suppress (one per line)", value=suppressed_text, height=120)
        if st.button("Save suppression list"):
            emails = [e.strip() for e in new_text.splitlines() if e.strip()]
            if save_suppression_list(user_id, emails):
                st.success("Suppression list saved")
            else:
                st.error("Failed to save suppression list")

    # Unsubscribe footer config
    st.markdown("### 📭 Unsubscribe Footer")
    with st.expander("Configure unsubscribe footer", expanded=False):
        user_id = st.session_state.user['id']
        profs = load_smtp_profiles(user_id)
        default_prof = get_default_profile(profs) or {}
        unsub_enabled = st.checkbox("Enable unsubscribe footer", value=bool(default_prof.get('unsub_footer_enabled', False)))
        unsub_text = st.text_input("Footer text", value=default_prof.get('unsub_footer_text', 'To unsubscribe, reply with \"UNSUBSCRIBE\".'), help="Shown at the bottom of emails")
        if st.button("Save footer settings"):
            if profs.get('profiles'):
                for p in profs['profiles']:
                    if p.get('id') == profs.get('default_profile_id'):
                        p['unsub_footer_enabled'] = bool(unsub_enabled)
                        p['unsub_footer_text'] = unsub_text
                        break
                if save_smtp_profiles(user_id, profs):
                    st.success("Footer settings saved to default profile")
                else:
                    st.error("Failed to save footer settings")
    
    # About section
    st.markdown("### ℹ️ About LeadAI Pro")
    st.info("""
    **LeadAI Pro** is an AI-powered lead management and email marketing platform.
    
    **Features:**
    - AI-powered email generation
    - Lead management and scoring
    - Email campaign automation
    - Analytics and tracking
    - Free Hugging Face AI models
    
    **Version:** 1.0.0
    **Deployment:** Hugging Face Spaces
    """)

if __name__ == "__main__":
    main()
