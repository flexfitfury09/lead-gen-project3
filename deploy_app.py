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
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
import schedule
import yagmail
from email_validator import validate_email, EmailNotValidError

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
    conn = sqlite3.connect(DB_NAME)
    
    # Get lead count
            cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM leads WHERE user_id = ?", (user_id,))
    lead_count = cursor.fetchone()[0]
            
    # Get campaign count
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE user_id = ?", (user_id,))
    campaign_count = cursor.fetchone()[0]
    
    # Get email tracking data
            cursor.execute('''
        SELECT 
            COUNT(*) as total_emails,
            SUM(CASE WHEN status = 'Sent' THEN 1 ELSE 0 END) as sent_emails,
            SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened_emails,
            SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) as clicked_emails
        FROM email_tracking et
        JOIN campaigns c ON et.campaign_id = c.id
        WHERE c.user_id = ?
    ''', (user_id,))
    
    tracking_data = cursor.fetchone()
            conn.close()
            
            return {
        'lead_count': lead_count,
        'campaign_count': campaign_count,
        'total_emails': tracking_data[0] or 0,
        'sent_emails': tracking_data[1] or 0,
        'opened_emails': tracking_data[2] or 0,
        'clicked_emails': tracking_data[3] or 0
    }

# Email functions
def send_email_simulation(to_email: str, subject: str, content: str) -> bool:
    """Simulate email sending (for demo purposes)"""
    # In a real implementation, you would use SMTP here
    # For demo purposes, we'll just log the email
    print(f"Simulated email sent to {to_email}: {subject}")
    return True

def schedule_email_campaign(campaign_id: int, lead_ids: List[int], delay_minutes: int = 5):
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
            placeholders = ','.join(['?' for _ in lead_ids])
            cursor.execute(f"SELECT id, name, email, company FROM leads WHERE id IN ({placeholders})", lead_ids)
            leads = cursor.fetchall()
            
            sent_count = 0
            for lead in leads:
                lead_id, lead_name, lead_email, lead_company = lead
                
                # Personalize content
                personalized_content = content.replace('{name}', lead_name).replace('{company}', lead_company or '')
                
                # Send email (simulated)
                if send_email_simulation(lead_email, subject, personalized_content):
                    # Record in tracking table
                    cursor.execute('''
                        INSERT INTO email_tracking (campaign_id, lead_id, email, status, sent_at)
                        VALUES (?, ?, ?, 'Sent', CURRENT_TIMESTAMP)
                    ''', (campaign_id, lead_id, lead_email))
                    sent_count += 1
            
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
        
        pages = ["Home", "Lead Management", "Email Campaigns", "Analytics", "AI Assistant", "Settings"]
        current_page = st.selectbox("Choose a page", pages, key="nav_select")
        
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
    
    # Logout button
        if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()
    
    # Main Content
    if current_page == "Home":
        show_home_page()
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

def show_lead_management():
    """Show lead management interface"""
    st.markdown("## 👥 Lead Management")
    
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
                            st.warning(f"Error processing {row['name']}: {str(e)}")
    
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
        
        # Target leads
        leads_df = get_user_leads(st.session_state.user['id'])
        if not leads_df.empty:
            lead_options = leads_df['name'].tolist()
            selected_leads = st.multiselect("Select Target Leads", lead_options)
        else:
            selected_leads = []
            st.warning("No leads available. Please add leads first.")
        
        # Submit campaign
        if st.form_submit_button("🚀 Create Campaign", type="primary"):
            if campaign_name and subject_line and email_content and selected_leads:
                campaign_data = {
                    'name': campaign_name,
                    'subject': subject_line,
                    'content': email_content
                }
                
                if create_campaign(st.session_state.user['id'], campaign_data):
                    st.success("Campaign created successfully!")
                    
                    # Schedule emails
                    selected_lead_ids = leads_df[leads_df['name'].isin(selected_leads)]['id'].tolist()
                    
                    # Get the latest campaign ID
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM campaigns WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (st.session_state.user['id'],))
                    campaign_id = cursor.fetchone()[0]
                    conn.close()
                    
                    # Schedule campaign
                    schedule_email_campaign(campaign_id, selected_lead_ids, send_delay)
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
        st.slider("Email Send Rate (per minute)", 1, 10, 3)
    
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
