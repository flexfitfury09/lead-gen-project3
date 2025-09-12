import streamlit as st
import sqlite3
import hashlib
import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False
    def st_autorefresh(*args, **kwargs):
        pass
from tenacity import retry, stop_after_attempt, wait_exponential
import urllib.parse

import sys
import os

# Optional transformers import removed to simplify main app and avoid heavy deps

# Page configuration
st.set_page_config(
    page_title="Lead Generation & Email Marketing Platform",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .dashboard-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        margin: 1rem 0;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-left: 4px solid #667eea;
    }
    .success-message {
        background: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
    }
    .error-message {
        background: #f8d7da;
        color: #721c24;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
    }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%);
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Database setup
def init_database():
    """Initialize SQLite database with all required tables"""
    conn = sqlite3.connect('lead_gen.db')
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
            user_id INTEGER,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            company TEXT,
            title TEXT,
            industry TEXT,
            city TEXT,
            country TEXT,
            website TEXT,
            source TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Campaigns table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            subject TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scheduled_at TIMESTAMP,
            sent_at TIMESTAMP,
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
            status TEXT DEFAULT 'sent',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            opened_at TIMESTAMP,
            clicked_at TIMESTAMP,
            bounced_at TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns (id),
            FOREIGN KEY (lead_id) REFERENCES leads (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def _ensure_db_schema():
    """Ensure core application tables exist"""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    # Create core tables if they don't exist
    tables = ['users', 'leads', 'campaigns', 'email_tracking']
    for table in tables:
        if table == 'users':
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
        elif table == 'leads':
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    company TEXT,
                    title TEXT,
                    industry TEXT,
                    city TEXT,
                    country TEXT,
                    website TEXT,
                    source TEXT,
                    status TEXT DEFAULT 'new',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        elif table == 'campaigns':
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT DEFAULT 'draft',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    scheduled_at TIMESTAMP,
                    sent_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        elif table == 'email_tracking':
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS email_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER,
                    lead_id INTEGER,
                    email TEXT NOT NULL,
                    status TEXT DEFAULT 'sent',
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    opened_at TIMESTAMP,
                    clicked_at TIMESTAMP,
                    bounced_at TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns (id),
                    FOREIGN KEY (lead_id) REFERENCES leads (id)
                )
            ''')
    
    conn.commit()

    # Ensure optional columns exist (safe migrations)
    try:
        def _column_exists(curs, table_name, column_name):
            curs.execute(f"PRAGMA table_info({table_name})")
            return any(row[1] == column_name for row in curs.fetchall())

        # Add tags column to leads if missing
        if not _column_exists(cursor, 'leads', 'tags'):
            cursor.execute("ALTER TABLE leads ADD COLUMN tags TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    # Drip sequences schema
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sequences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sequence_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id INTEGER NOT NULL,
                step_order INTEGER NOT NULL,
                delay_days INTEGER NOT NULL,
                subject TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sequence_id) REFERENCES sequences(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL,
                sequence_id INTEGER NOT NULL,
                step_id INTEGER NOT NULL,
                scheduled_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'scheduled',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception:
        pass

    # Email accounts schema (for multi-sender support)
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                smtp_server TEXT NOT NULL,
                smtp_port INTEGER NOT NULL,
                smtp_username TEXT NOT NULL,
                smtp_password TEXT NOT NULL,
                from_email TEXT NOT NULL,
                use_tls INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    except Exception:
        pass
    conn.close()

# Authentication functions
def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, email, password, role='user'):
    """Register a new user"""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    try:
        password_hash = hash_password(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (username, email, password_hash, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def list_users():
    """List all users (admin only)."""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC')
        rows = cursor.fetchall()
        return [{'id': r[0], 'username': r[1], 'email': r[2], 'role': r[3], 'created_at': r[4]} for r in rows]
    finally:
        conn.close()

def update_user_role(user_id: int, role: str):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

# DNS checks (no backend required)
def check_spf_record(domain: str):
    try:
        import dns.resolver
    except Exception:
        return { 'ok': False, 'error': 'dnspython not installed', 'spf': '' }
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        for rdata in answers:
            txt = ''.join([b.decode('utf-8') if isinstance(b, (bytes, bytearray)) else b for b in rdata.strings])
            if txt.lower().startswith('v=spf1'):
                return { 'ok': True, 'spf': txt }
        return { 'ok': False, 'error': 'No SPF record found', 'spf': '' }
    except Exception as e:
        return { 'ok': False, 'error': str(e), 'spf': '' }

def check_dkim_record(domain: str, selector: str):
    try:
        import dns.resolver
    except Exception:
        return { 'ok': False, 'error': 'dnspython not installed', 'dkim': '' }
    try:
        name = f"{selector}._domainkey.{domain}"
        answers = dns.resolver.resolve(name, 'TXT')
        for rdata in answers:
            txt = ''.join([b.decode('utf-8') if isinstance(b, (bytes, bytearray)) else b for b in rdata.strings])
            if 'v=DKIM1' in txt or 'k=rsa' in txt:
                return { 'ok': True, 'dkim': txt }
        return { 'ok': False, 'error': 'No DKIM record found', 'dkim': '' }
    except Exception as e:
        return { 'ok': False, 'error': str(e), 'dkim': '' }

def _suppress_email_for_user(user_id: int, email: str):
    path = f"suppression_list_{user_id}.txt"
    try:
        existing = set()
        if os.path.exists(path):
            with open(path, 'r') as f:
                existing = set(line.strip().lower() for line in f if line.strip())
        email_l = email.strip().lower()
        if email_l not in existing:
            with open(path, 'a') as f:
                f.write(email_l + "\n")
        return True
    except Exception:
        return False

def _mark_email_bounced(email: str):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE email_tracking SET status = 'bounced' WHERE email = ?", (email,))
        conn.commit()
    finally:
        conn.close()

def process_webhook_event(user_id: int, event: dict):
    etype = str(event.get('type','')).lower()
    email = event.get('email') or event.get('recipient') or ''
    if not email:
        return 'ignored: no email'
    if etype in ('bounce','bounced','complaint','spamreport','spam_report'):
        _suppress_email_for_user(user_id, email)
        _mark_email_bounced(email)
        return f"suppressed:{etype}"
    return 'processed'

def authenticate_user(username, password):
    """Authenticate user login"""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute('''
        SELECT id, username, email, role FROM users
        WHERE username = ? AND password_hash = ?
    ''', (username, password_hash))
    
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user[0],
            'username': user[1],
            'email': user[2],
            'role': user[3]
        }
    return None

# Email configuration functions
def save_email_config(user_id, config):
    """Save email configuration for user"""
    config_file = f'email_config_{user_id}.json'
    with open(config_file, 'w') as f:
        json.dump(config, f)

def load_email_config(user_id):
    """Load email configuration for user"""
    config_file = f'email_config_{user_id}.json'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    return None

def add_email_account(user_id: int, label: str, server: str, port: int, username: str, password: str, from_email: str, use_tls: bool = True) -> int:
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO email_accounts (user_id, label, smtp_server, smtp_port, smtp_username, smtp_password, from_email, use_tls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, label, server, int(port), username, password, from_email, 1 if use_tls else 0))
        eid = cursor.lastrowid
        conn.commit()
        return eid
    finally:
        conn.close()

def list_email_accounts(user_id: int):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id, label, from_email, smtp_server, smtp_port, smtp_username, use_tls FROM email_accounts WHERE user_id = ? ORDER BY created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        return [{'id': r[0], 'label': r[1], 'from_email': r[2], 'smtp_server': r[3], 'smtp_port': r[4], 'smtp_username': r[5], 'use_tls': bool(r[6])} for r in rows]
    finally:
        conn.close()

def get_email_account(user_id: int, account_id: int):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id, label, from_email, smtp_server, smtp_port, smtp_username, smtp_password, use_tls FROM email_accounts WHERE user_id = ? AND id = ?
        ''', (user_id, account_id))
        r = cursor.fetchone()
        if not r:
            return None
        return {'id': r[0], 'label': r[1], 'from_email': r[2], 'smtp_server': r[3], 'smtp_port': r[4], 'smtp_username': r[5], 'smtp_password': r[6], 'use_tls': bool(r[7])}
    finally:
        conn.close()

# Lead management functions
def add_lead(user_id, name, email, phone=None, company=None, title=None, industry=None, city=None, country=None, website=None, source='manual'):
    """Add a new lead"""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO leads (user_id, name, email, phone, company, title, industry, city, country, website, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, name, email, phone, company, title, industry, city, country, website, source))
    
    conn.commit()
    conn.close()

def update_lead_status_bulk(user_id: int, lead_ids: list, new_status: str):
    """Bulk update status for selected leads belonging to the user."""
    if not lead_ids:
        return 0
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        q_marks = ','.join('?' for _ in lead_ids)
        params = [new_status, user_id] + lead_ids
        cursor.execute(f"UPDATE leads SET status = ? WHERE user_id = ? AND id IN ({q_marks})", params)
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()

def get_leads(user_id, limit=100):
    """Get leads for user"""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, email, phone, company, title, industry, city, country, website, source, status, created_at
        FROM leads WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
    ''', (user_id, limit))
    
    leads = cursor.fetchall()
    conn.close()
    
    return [{
        'id': lead[0],
        'name': lead[1],
        'email': lead[2],
        'phone': lead[3],
        'company': lead[4],
        'title': lead[5],
        'industry': lead[6],
        'city': lead[7],
        'country': lead[8],
        'website': lead[9],
        'source': lead[10],
        'status': lead[11],
        'created_at': lead[12]
    } for lead in leads]

# Campaign management functions
def create_campaign(user_id, name, subject, content):
    """Create a new campaign"""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO campaigns (user_id, name, subject, content)
        VALUES (?, ?, ?, ?)
    ''', (user_id, name, subject, content))
    
    campaign_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return campaign_id

# Drip sequence CRUD helpers
def create_sequence(user_id: int, name: str, description: str = "") -> int:
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO sequences (user_id, name, description)
            VALUES (?, ?, ?)
        ''', (user_id, name, description))
        sid = cursor.lastrowid
        conn.commit()
        return sid
    finally:
        conn.close()

def add_sequence_step(sequence_id: int, step_order: int, delay_days: int, subject: str, content: str) -> int:
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO sequence_steps (sequence_id, step_order, delay_days, subject, content)
            VALUES (?, ?, ?, ?, ?)
        ''', (sequence_id, step_order, delay_days, subject, content))
        step_id = cursor.lastrowid
        conn.commit()
        return step_id
    finally:
        conn.close()

def get_sequences(user_id: int):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, description, created_at FROM sequences WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({'id': row[0], 'name': row[1], 'description': row[2], 'created_at': row[3]})
        return result
    finally:
        conn.close()

def get_sequence_steps(sequence_id: int):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, step_order, delay_days, subject, content FROM sequence_steps WHERE sequence_id = ? ORDER BY step_order ASC", (sequence_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({'id': row[0], 'step_order': row[1], 'delay_days': row[2], 'subject': row[3], 'content': row[4]})
        return result
    finally:
        conn.close()

def schedule_sequence_for_leads(user_id: int, sequence_id: int, lead_ids: list, start_date: datetime):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        steps = get_sequence_steps(sequence_id)
        for lead_id in lead_ids:
            for s in steps:
                sched_at = datetime.combine(start_date.date(), datetime.min.time()) + timedelta(days=int(s['delay_days']))
                cursor.execute('''
                    INSERT INTO scheduled_jobs (user_id, lead_id, sequence_id, step_id, scheduled_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, lead_id, sequence_id, s['id'], sched_at.isoformat()))
        conn.commit()
    finally:
        conn.close()
def _insert_email_tracking(campaign_id: int, lead_id: int, email: str, status: str = 'sent'):
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO email_tracking (campaign_id, lead_id, email, status)
            VALUES (?, ?, ?, ?)
        ''', (campaign_id, lead_id, email, status))
        conn.commit()
    finally:
        conn.close()

def process_scheduled_jobs(max_jobs: int = 50):
    """Process due scheduled jobs (simple in-app scheduler)."""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        now_iso = datetime.now().isoformat()
        cursor.execute('''
            SELECT id, user_id, lead_id, sequence_id, step_id, scheduled_at
            FROM scheduled_jobs
            WHERE status = 'scheduled' AND scheduled_at <= ?
            ORDER BY scheduled_at ASC
            LIMIT ?
        ''', (now_iso, max_jobs))
        jobs = cursor.fetchall()
        if not jobs:
            return 0
        # Load step content for each job
        processed = 0
        for job in jobs:
            job_id, user_id, lead_id, sequence_id, step_id, scheduled_at = job
            # Fetch lead email
            cursor.execute("SELECT email FROM leads WHERE id = ?", (lead_id,))
            row = cursor.fetchone()
            email = row[0] if row else ''
            if not email:
                cursor.execute("UPDATE scheduled_jobs SET status = 'skipped' WHERE id = ?", (job_id,))
                continue
            # Fetch step subject/content
            cursor.execute("SELECT subject, content FROM sequence_steps WHERE id = ?", (step_id,))
            srow = cursor.fetchone()
            if not srow:
                cursor.execute("UPDATE scheduled_jobs SET status = 'skipped' WHERE id = ?", (job_id,))
                continue
            subject, content = srow
            # Send (simulate) and track
            try:
                send_email_simulation(email, subject, content, user_id)
                _insert_email_tracking(0, lead_id, email, 'sent')
                cursor.execute("UPDATE scheduled_jobs SET status = 'sent' WHERE id = ?", (job_id,))
            except Exception:
                cursor.execute("UPDATE scheduled_jobs SET status = 'error' WHERE id = ?", (job_id,))
            processed += 1
        conn.commit()
        return processed
    finally:
        conn.close()

def update_lead_tags(lead_id: int, tags: str):
    """Update tags for a given lead (comma-separated)."""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE leads SET tags = ? WHERE id = ?", (tags, lead_id))
        conn.commit()
    finally:
        conn.close()

def get_filtered_leads(user_id: int, name_query: str = "", tag_query: str = "", city: str = "", country: str = "", limit: int = 200):
    """Return leads filtered by basic fields and tags."""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    try:
        query = "SELECT id, name, email, phone, company, title, industry, city, country, website, source, status, created_at, COALESCE(tags, '') as tags FROM leads WHERE user_id = ?"
        params = [user_id]
        if name_query:
            query += " AND name LIKE ?"
            params.append(f"%{name_query}%")
        if city:
            query += " AND city LIKE ?"
            params.append(f"%{city}%")
        if country:
            query += " AND country LIKE ?"
            params.append(f"%{country}%")
        if tag_query:
            # simple contains match on tags CSV
            query += " AND COALESCE(tags,'') LIKE ?"
            params.append(f"%{tag_query}%")
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r[0], 'name': r[1], 'email': r[2], 'phone': r[3], 'company': r[4], 'title': r[5],
                'industry': r[6], 'city': r[7], 'country': r[8], 'website': r[9], 'source': r[10],
                'status': r[11], 'created_at': r[12], 'tags': r[13]
            })
        return result
    finally:
        conn.close()

def get_campaigns(user_id):
    """Get campaigns for user"""
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, subject, content, status, created_at, scheduled_at, sent_at
        FROM campaigns WHERE user_id = ? ORDER BY created_at DESC
    ''', (user_id,))
    
    campaigns = cursor.fetchall()
    conn.close()
    
    return [{
        'id': campaign[0],
        'name': campaign[1],
        'subject': campaign[2],
        'content': campaign[3],
        'status': campaign[4],
        'created_at': campaign[5],
        'scheduled_at': campaign[6],
        'sent_at': campaign[7]
    } for campaign in campaigns]

# Analytics functions
def get_analytics(user_id):
    """Get analytics data for user"""
    _ensure_db_schema()
    
    conn = sqlite3.connect('lead_gen.db')
    cursor = conn.cursor()
    
    try:
        # Lead count
        cursor.execute("SELECT COUNT(*) FROM leads WHERE user_id = ?", (user_id,))
        lead_count = cursor.fetchone()[0] or 0
    except sqlite3.OperationalError:
        lead_count = 0
        
    try:
        # Campaign count
        cursor.execute("SELECT COUNT(*) FROM campaigns WHERE user_id = ?", (user_id,))
        campaign_count = cursor.fetchone()[0] or 0
    except sqlite3.OperationalError:
        campaign_count = 0

    # Email tracking aggregates
    total_emails = sent_emails = opened_emails = clicked_emails = 0
    
    try:
        cursor.execute('''
            SELECT COUNT(*) FROM email_tracking et
            JOIN campaigns c ON et.campaign_id = c.id
            WHERE c.user_id = ?
        ''', (user_id,))
        total_emails = cursor.fetchone()[0] or 0
        
        cursor.execute('''
            SELECT COUNT(*) FROM email_tracking et
            JOIN campaigns c ON et.campaign_id = c.id
            WHERE c.user_id = ? AND et.status = 'sent'
        ''', (user_id,))
        sent_emails = cursor.fetchone()[0] or 0
        
        cursor.execute('''
            SELECT COUNT(*) FROM email_tracking et
            JOIN campaigns c ON et.campaign_id = c.id
            WHERE c.user_id = ? AND et.opened_at IS NOT NULL
        ''', (user_id,))
        opened_emails = cursor.fetchone()[0] or 0
        
        cursor.execute('''
            SELECT COUNT(*) FROM email_tracking et
            JOIN campaigns c ON et.campaign_id = c.id
            WHERE c.user_id = ? AND et.clicked_at IS NOT NULL
        ''', (user_id,))
        clicked_emails = cursor.fetchone()[0] or 0
    except sqlite3.OperationalError:
        pass
    
    conn.close()
    
    return {
        'lead_count': lead_count,
        'campaign_count': campaign_count,
        'total_emails': total_emails,
        'sent_emails': sent_emails,
        'opened_emails': opened_emails,
        'clicked_emails': clicked_emails
    }

# Email sending functions
def load_suppression_list(user_id):
    """Load suppression list for user"""
    sup_file = f'suppression_list_{user_id}.txt'
    if os.path.exists(sup_file):
        with open(sup_file, 'r') as f:
            return set(line.strip().lower() for line in f)
    return set()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def send_email_simulation(to_email, subject, content, user_id, from_email=None):
    """Send email with retry logic and rate limiting"""
    # Load suppression list
    sup_list = load_suppression_list(user_id)
    if to_email.strip().lower() in sup_list:
        print(f"Suppressed email skipped: {to_email}")
        return True

    # Load email configuration
    cfg = load_email_config(user_id)
    
    if not cfg or not cfg.get('smtp_username') or not cfg.get('smtp_password'):
        print(f"Simulated email sent to {to_email}: {subject}")
        return True

    smtp_server = cfg.get('smtp_server', 'smtp.gmail.com')
    smtp_port = int(cfg.get('smtp_port', 587))
    smtp_username = cfg.get('smtp_username')
    smtp_password = cfg.get('smtp_password')
    
    # Create message
    msg = MIMEMultipart()
    msg['From'] = from_email or smtp_username
    msg['To'] = to_email
    msg['Subject'] = subject
    
    # Add content
    msg.attach(MIMEText(content, 'html'))
    
    # Add unsubscribe footer
    unsubscribe_url = f"https://yourapp.com/unsubscribe?email={urllib.parse.quote(to_email)}"
    footer = f"<br><br><hr><p style='font-size: 12px; color: #666;'>If you no longer wish to receive these emails, <a href='{unsubscribe_url}'>click here to unsubscribe</a>.</p>"
    msg.attach(MIMEText(footer, 'html'))
    
    try:
        # Connect to server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        
        # Send email
        text = msg.as_string()
        server.sendmail(smtp_username, to_email, text)
        server.quit()
        
        print(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")
        raise

# Real-time counters
def render_realtime_counters(user_id, key: str = "realtime_refresh"):
    """Render real-time counters with WebSocket connection"""
    col1, col2, col3, col4 = st.columns(4)
    
    # Try to connect to WebSocket for real-time updates
    try:
        # This would connect to your FastAPI backend WebSocket
        # For now, we'll use auto-refresh as fallback
        if st.session_state.get('enable_global_autorefresh', True):
            st_autorefresh(interval=3000, key=key)
        
        # Get current analytics
        analytics = get_analytics(user_id)
        
        with col1:
            st.metric("📧 Total Emails", analytics['total_emails'])
        with col2:
            st.metric("📤 Sent", analytics['sent_emails'])
        with col3:
            st.metric("👁️ Opened", analytics['opened_emails'])
        with col4:
            st.metric("🖱️ Clicked", analytics['clicked_emails'])
            
    except Exception as e:
        st.error(f"Real-time updates unavailable: {e}")
        # Fallback to static display
        analytics = get_analytics(user_id)
        with col1:
            st.metric("📧 Total Emails", analytics['total_emails'])
        with col2:
            st.metric("📤 Sent", analytics['sent_emails'])
        with col3:
            st.metric("👁️ Opened", analytics['opened_emails'])
        with col4:
            st.metric("🖱️ Clicked", analytics['clicked_emails'])


# Main pages
def show_home_page():
    """Show home page with dashboard"""
    st.markdown("## 🏠 Dashboard")
    
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
    render_realtime_counters(st.session_state.user['id'], key="home_realtime_refresh")

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
        st.markdown("### 🧭 Navigation")
        current_page = st.selectbox(
            "Select Page",
            ["Home", "Lead Management", "Email Campaigns", "Analytics", "Settings", "Admin"],
            key="page_selector"
        )
        
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
        render_realtime_counters(st.session_state.user['id'], key="sidebar_realtime_refresh")
    
    # Logout button
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()
    
    # Main Content
    if current_page == "Home":
        show_home_page()
    
    elif current_page == "Lead Management":
        st.markdown("## 👥 Lead Management")
        st.markdown("### Filters")
        colf1, colf2, colf3, colf4 = st.columns(4)
        with colf1:
            f_name = st.text_input("Search name", value=st.session_state.get('name_query',''))
            st.session_state['name_query'] = f_name
        with colf2:
            f_city = st.text_input("City filter", value=st.session_state.get('city_filter',''))
            st.session_state['city_filter'] = f_city
        with colf3:
            f_country = st.text_input("Country filter", value=st.session_state.get('country_filter',''))
            st.session_state['country_filter'] = f_country
        with colf4:
            f_tag = st.text_input("Tag filter", value=st.session_state.get('tag_filter',''))
            st.session_state['tag_filter'] = f_tag
        st.markdown("### CSV Import")
        if 'csv_import_done' not in st.session_state:
            st.session_state.csv_import_done = False
        uploaded = st.file_uploader("Upload CSV of leads", type=["csv"], accept_multiple_files=False, key="leads_csv")
        if uploaded is not None and not st.session_state.csv_import_done:
            try:
                import pandas as pd
                df = pd.read_csv(uploaded)
                required_cols = {"name"}
                if not required_cols.issubset(set(c.lower() for c in df.columns)):
                    st.error("CSV must include at least a 'name' column.")
                else:
                    # Normalize columns
                    cols_map = {c: c.lower() for c in df.columns}
                    df.rename(columns=cols_map, inplace=True)
                    inserted = 0
                    for _, row in df.iterrows():
                        try:
                            add_lead(
                                st.session_state.user['id'],
                                name=str(row.get('name','')).strip(),
                                email=str(row.get('email','')).strip() if 'email' in df.columns else None,
                                phone=str(row.get('phone','')).strip() if 'phone' in df.columns else None,
                                company=str(row.get('company','')).strip() if 'company' in df.columns else None,
                                title=str(row.get('title','')).strip() if 'title' in df.columns else None,
                                industry=str(row.get('industry','')).strip() if 'industry' in df.columns else None,
                                city=str(row.get('city','')).strip() if 'city' in df.columns else None,
                                country=str(row.get('country','')).strip() if 'country' in df.columns else None,
                                website=str(row.get('website','')).strip() if 'website' in df.columns else None,
                                source=str(row.get('source','csv')).strip() if 'source' in df.columns else 'csv'
                            )
                            inserted += 1
                        except Exception:
                            pass
                    st.success(f"Imported {inserted} leads from CSV.")
                    st.session_state.csv_import_done = True
            except Exception as e:
                st.error(f"Failed to import CSV: {e}")
        if st.session_state.csv_import_done and st.button("Reset Import State"):
            st.session_state.csv_import_done = False
        st.markdown("### Leads")
        leads = get_filtered_leads(st.session_state.user['id'], name_query=f_name, tag_query=f_tag, city=f_city, country=f_country, limit=200)
        if leads:
            import pandas as pd
            df = pd.DataFrame(leads)
            # Select for bulk status
            df['selected'] = False
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True)
            if st.button("Save Tag Changes"):
                updated = 0
                for _, row in edited.iterrows():
                    try:
                        update_lead_tags(int(row['id']), str(row.get('tags','')).strip())
                        updated += 1
                    except Exception:
                        pass
                st.success(f"Saved tags for {updated} leads.")
            st.markdown("#### Bulk Status Update")
            new_status = st.selectbox("Set status to", ["new", "contacted", "qualified", "unqualified", "customer"])
            if st.button("Apply to Selected"):
                try:
                    selected_ids = [int(r['id']) for _, r in edited.iterrows() if r.get('selected', False)]
                    changed = update_lead_status_bulk(st.session_state.user['id'], selected_ids, new_status)
                    st.success(f"Updated {changed} leads to status '{new_status}'.")
                except Exception as e:
                    st.error(f"Failed to update: {e}")
            # Export filtered
            if st.button("Export Filtered to CSV"):
                try:
                    from io import StringIO
                    buff = StringIO()
                    edited.to_csv(buff, index=False)
                    st.download_button(
                        label="Download Filtered CSV",
                        data=buff.getvalue(),
                        file_name=f"filtered_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                except Exception as e:
                    st.error(f"Failed to export: {e}")
        else:
            st.info("No leads yet. Upload a CSV to get started.")
    elif current_page == "Email Campaigns":
        st.markdown("## 📧 Email Campaigns")
        st.markdown("### Templates")
        templates = {
            "Welcome": {
                "subject": "Welcome to our community!",
                "content": "<p>Hi {{name}},</p><p>Thanks for joining us!</p>"
            },
            "Promotion": {
                "subject": "Special offer just for you",
                "content": "<p>Hi {{name}},</p><p>Don't miss our limited-time deal.</p>"
            },
            "Follow-up": {
                "subject": "Following up on our last conversation",
                "content": "<p>Hi {{name}},</p><p>Just checking in to see if you had any questions.</p>"
            }
        }
        tname = st.selectbox("Choose a template", list(templates.keys()))
        subject = st.text_input("Subject", value=templates[tname]["subject"]) 
        content = st.text_area("HTML Content", value=templates[tname]["content"], height=200)
        st.markdown("### Schedule Preview")
        schedule_date = st.date_input("Schedule date")
        schedule_time = st.time_input("Schedule time")
        if st.button("Save Campaign"):
            cid = create_campaign(st.session_state.user['id'], tname, subject, content)
            st.success(f"Campaign saved with ID {cid}.")
        st.markdown("### Send Test/Bulk Emails")
        to_email = st.text_input("Test recipient email")
        if st.button("Send Test Email") and to_email:
            try:
                send_email_simulation(to_email, subject, content, st.session_state.user['id'])
                st.success("Test email sent (or simulated).")
            except Exception as e:
                st.error(f"Failed to send: {e}")
        st.markdown("#### Bulk send to filtered leads")
        filt_name = st.text_input("Filter name contains (bulk)")
        bulk = get_filtered_leads(st.session_state.user['id'], name_query=filt_name, limit=200)
        sel_ids = [l['id'] for l in bulk]
        st.write(f"Matched {len(sel_ids)} leads.")
        # Select sender account and send delay
        accounts_for_send = list_email_accounts(st.session_state.user['id'])
        sender_map = {f"{a['label']} <{a['from_email']}> (# {a['id']})": a['id'] for a in accounts_for_send} if accounts_for_send else {}
        selected_sender_label = st.selectbox("Send from account", list(sender_map.keys()) if sender_map else ["Default (single-config)"])
        selected_sender_id = sender_map.get(selected_sender_label)
        send_delay_minutes = st.number_input("Delay between emails (minutes)", min_value=0, max_value=120, value=0)
        if st.button("Start Bulk Send"):
            from time import sleep
            prog = st.progress(0.0)
            done = 0
            total = len(sel_ids)
            for l in bulk:
                email = l.get('email','')
                if email:
                    try:
                        # If account selected, temporarily override email config
                        if selected_sender_id:
                            acct = get_email_account(st.session_state.user['id'], int(selected_sender_id))
                            if acct:
                                # Temporarily set email config to account for send_email_simulation
                                cfg = {
                                    'smtp_server': acct['smtp_server'],
                                    'smtp_port': acct['smtp_port'],
                                    'smtp_username': acct['smtp_username'],
                                    'smtp_password': acct['smtp_password']
                                }
                                # Stash and send
                                # Note: send_email_simulation reads config via load_email_config; we simulate by writing a temp config
                                save_email_config(st.session_state.user['id'], cfg)
                                send_email_simulation(email, subject, content, st.session_state.user['id'], from_email=acct['from_email'])
                            else:
                                send_email_simulation(email, subject, content, st.session_state.user['id'])
                        else:
                            send_email_simulation(email, subject, content, st.session_state.user['id'])
                        # Track send
                        _insert_email_tracking(0, l['id'], email, 'sent')
                    except Exception:
                        pass
                done += 1
                prog.progress(min(1.0, done/max(1,total)))
                # Apply user-selected delay between sends (minutes)
                if send_delay_minutes > 0:
                    sleep(int(send_delay_minutes) * 60)
                else:
                    sleep(0.05)
            st.success(f"Bulk process completed for {total} leads.")
        st.markdown("### Drip Sequences")
        seq_name = st.text_input("Sequence name")
        seq_desc = st.text_input("Description")
        if st.button("Create Sequence") and seq_name:
            sid = create_sequence(st.session_state.user['id'], seq_name, seq_desc)
            st.success(f"Sequence created with ID {sid}")
        # Add steps
        st.markdown("#### Add Step")
        try:
            # reload sequences
            seqs = get_sequences(st.session_state.user['id'])
        except Exception:
            seqs = []
        if seqs:
            seq_options = {f"{s['name']} (#{s['id']})": s['id'] for s in seqs}
            sel_seq_label = st.selectbox("Select sequence", list(seq_options.keys()))
            sel_seq = seq_options[sel_seq_label]
            step_order = st.number_input("Order", min_value=1, value=1)
            delay_days = st.number_input("Delay days", min_value=0, value=0)
            s_subject = st.text_input("Step subject")
            s_content = st.text_area("Step content", height=120)
            if st.button("Add Step") and s_subject and s_content:
                add_sequence_step(sel_seq, int(step_order), int(delay_days), s_subject, s_content)
                st.success("Step added.")
            # Schedule sequence to a segment
            st.markdown("#### Schedule Sequence to Segment")
            start_date = st.date_input("Start date")
            seg_name_query = st.text_input("Segment filter: name contains")
            seg_tag = st.text_input("Segment filter: tag contains")
            segment_leads = get_filtered_leads(st.session_state.user['id'], name_query=seg_name_query, tag_query=seg_tag, limit=500)
            st.write(f"Segment size: {len(segment_leads)}")
            if st.button("Schedule Sequence"):
                lead_ids = [l['id'] for l in segment_leads]
                schedule_sequence_for_leads(st.session_state.user['id'], sel_seq, lead_ids, datetime.now())
                st.success("Sequence scheduled for selected segment.")
        st.markdown("### Email Accounts (From addresses)")
        with st.expander("Manage Email Accounts"):
            colA, colB = st.columns(2)
            with colA:
                label = st.text_input("Label", key="acc_label")
                from_email_cfg = st.text_input("From Email", key="acc_from")
                server = st.text_input("SMTP Server", value="smtp.gmail.com", key="acc_server")
                port = st.number_input("SMTP Port", min_value=1, max_value=65535, value=587, key="acc_port")
            with colB:
                username = st.text_input("SMTP Username", key="acc_user")
                password = st.text_input("SMTP Password", type="password", key="acc_pass")
                use_tls = st.checkbox("Use TLS", value=True, key="acc_tls")
                if st.button("Add Email Account") and label and from_email_cfg and server and port and username and password:
                    add_email_account(st.session_state.user['id'], label, server, int(port), username, password, from_email_cfg, use_tls)
                    st.success("Email account added.")
            accounts = list_email_accounts(st.session_state.user['id'])
            if accounts:
                import pandas as pd
                st.dataframe(pd.DataFrame(accounts), use_container_width=True)
        st.markdown("### Your Campaigns")
        st.dataframe(get_campaigns(st.session_state.user['id']), use_container_width=True)
    elif current_page == "Analytics":
        st.markdown("## 📊 Analytics")
        data = get_analytics(st.session_state.user['id'])
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Emails", data['total_emails'])
        with col2:
            st.metric("Sent", data['sent_emails'])
        with col3:
            st.metric("Opened", data['opened_emails'])
        with col4:
            st.metric("Clicked", data['clicked_emails'])
        st.markdown("---")
        st.markdown("### Email Sent Trend (mock)")
        try:
            import pandas as pd
            from datetime import timedelta
            today = datetime.now().date()
            days = [today - timedelta(days=i) for i in range(14)]
            counts = [max(0, data['sent_emails'] // 14 + (i % 3)) for i in range(14)]
            trend_df = pd.DataFrame({'date': list(reversed(days)), 'sent': list(reversed(counts))})
            st.line_chart(trend_df.set_index('date'))
        except Exception:
            pass
        st.markdown("### Segmentation")
        try:
            # Pull a larger set for segmentation
            seg = get_leads(st.session_state.user['id'], limit=500)
            if seg:
                import pandas as pd
                sdf = pd.DataFrame(seg)
                # Status counts
                status_counts = sdf['status'].value_counts().rename_axis('status').reset_index(name='count')
                st.bar_chart(status_counts.set_index('status'))
                # Top tags (split CSV)
                if 'tags' in sdf.columns:
                    from collections import Counter
                    tags_series = sdf['tags'].fillna('').astype(str).tolist()
                    all_tags = []
                    for t in tags_series:
                        all_tags.extend([x.strip() for x in t.split(',') if x.strip()])
                    top = Counter(all_tags).most_common(10)
                    if top:
                        tag_df = pd.DataFrame(top, columns=['tag','count']).set_index('tag')
                        st.bar_chart(tag_df)
            else:
                st.info("Not enough data for segmentation.")
        except Exception:
            pass
        st.markdown("### Leads Summary (Top 50)")
        leads = get_leads(st.session_state.user['id'], limit=50)
        if leads:
            st.dataframe(leads, use_container_width=True)
        else:
            st.info("No lead data to display.")
    elif current_page == "Settings":
        st.markdown("## ⚙️ Settings")
        st.markdown("### Suppression List Editor")
        sup = load_suppression_list(st.session_state.user['id'])
        sup_text = "\n".join(sorted(sup)) if sup else ""
        edited = st.text_area("Suppressed emails (one per line)", value=sup_text, height=200)
        if st.button("Save Suppression List"):
            path = f"suppression_list_{st.session_state.user['id']}.txt"
            try:
                with open(path, 'w') as f:
                    for line in edited.splitlines():
                        line = line.strip()
                        if line:
                            f.write(line + "\n")
                st.success("Suppression list saved.")
            except Exception as e:
                st.error(f"Failed to save: {e}")
        st.markdown("### Saved Filters")
        filters_file = f"saved_filters_{st.session_state.user['id']}.json"
        def _load_saved_filters():
            try:
                if os.path.exists(filters_file):
                    with open(filters_file, 'r') as f:
                        return json.load(f)
            except Exception:
                return {}
            return {}
        def _save_filters(name: str, payload: dict):
            data = _load_saved_filters()
            data[name] = payload
            with open(filters_file, 'w') as f:
                json.dump(data, f)
        new_name = st.text_input("Filter name")
        if st.button("Save current filters"):
            # reuse latest filters typed in Lead Management by reading session_state if available
            payload = {
                'name_query': st.session_state.get('name_query',''),
                'city': st.session_state.get('city_filter',''),
                'country': st.session_state.get('country_filter',''),
                'tag': st.session_state.get('tag_filter',''),
            }
            if new_name:
                try:
                    _save_filters(new_name, payload)
                    st.success("Saved filter.")
                except Exception as e:
                    st.error(f"Failed to save filter: {e}")
            else:
                st.info("Enter a filter name to save.")
        saved = _load_saved_filters()
        if saved:
            pick = st.selectbox("Apply saved filter", list(saved.keys()))
            if st.button("Apply"):
                sel = saved.get(pick,{})
                st.session_state['name_query'] = sel.get('name_query','')
                st.session_state['city_filter'] = sel.get('city','')
                st.session_state['country_filter'] = sel.get('country','')
                st.session_state['tag_filter'] = sel.get('tag','')
                st.success("Applied. Go to Lead Management to see results.")
        st.markdown("### Scheduler Heartbeat")
        enable_sched = st.checkbox("Enable background scheduler heartbeat", value=True)
        if enable_sched:
            try:
                st_autorefresh(interval=15000, key="scheduler_heartbeat")
            except Exception:
                pass
            try:
                processed = process_scheduled_jobs(max_jobs=50)
                if processed:
                    st.info(f"Processed {processed} scheduled jobs.")
            except Exception:
                pass
    elif current_page == "Admin":
        st.markdown("## 👑 Admin Panel")
        if st.session_state.user.get('role','user') != 'admin':
            st.error("Admin access required.")
        else:
            st.markdown("### User Management")
            users = list_users()
            if users:
                import pandas as pd
                udf = pd.DataFrame(users)
                st.dataframe(udf, use_container_width=True)
                uid = st.number_input("User ID", min_value=1, step=1)
                new_role = st.selectbox("New role", ["user", "manager", "admin"])
                if st.button("Update Role"):
                    if update_user_role(int(uid), new_role):
                        st.success("Role updated.")
                    else:
                        st.error("Failed to update role.")
            st.markdown("### Deliverability Tools")
            b_email = st.text_input("Mark email as bounced/complaint")
            if st.button("Mark Bounce") and b_email:
                try:
                    _suppress_email_for_user(st.session_state.user['id'], b_email)
                    _mark_email_bounced(b_email)
                    st.success("Email marked as bounced and suppressed.")
                except Exception as e:
                    st.error(f"Failed: {e}")
            st.markdown("### DKIM/SPF Helper")
            st.info("Set up SPF: v=spf1 include:_spf.google.com ~all\nSet up DKIM: add TXT record from your email provider.\nUse warm-up pacing: limit sends to small batches per day and increase slowly.")
            st.markdown("#### DNS Checks (no backend)")
            d_domain = st.text_input("Domain for SPF/DKIM checks", placeholder="example.com")
            colc1, colc2 = st.columns(2)
            with colc1:
                if st.button("Check SPF") and d_domain:
                    res = check_spf_record(d_domain)
                    if res.get('ok'):
                        st.success(f"SPF: {res.get('spf')}")
                    else:
                        st.error(f"SPF not ok: {res.get('error','unknown')}")
            with colc2:
                selector = st.text_input("DKIM selector", value="default")
                if st.button("Check DKIM") and d_domain and selector:
                    res = check_dkim_record(d_domain, selector)
                    if res.get('ok'):
                        st.success(f"DKIM: {res.get('dkim')}")
                    else:
                        st.error(f"DKIM not ok: {res.get('error','unknown')}")
            st.markdown("#### Provider Webhook Simulation")
            st.caption("Simulate provider events locally without a backend deployment.")
            ev_type = st.selectbox("Event Type", ["bounce", "complaint", "spam_report"]) 
            ev_email = st.text_input("Recipient Email")
            if st.button("Process Simulated Event") and ev_email:
                outcome = process_webhook_event(st.session_state.user['id'], { 'type': ev_type, 'email': ev_email })
                st.success(f"Result: {outcome}")

# Main application
def main():
    """Main application function"""
    # Initialize database
    init_database()
    # Process due scheduled jobs opportunistically on each run
    try:
        process_scheduled_jobs(max_jobs=25)
    except Exception:
        pass
    
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None
    
    # Show appropriate page
    if st.session_state.authenticated:
        show_main_app()
    else:
        show_login_page()

if __name__ == "__main__":
    main()
