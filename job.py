import os
import time
import logging
import requests
import streamlit as st
import pandas as pd
import numpy as np
import re
import tempfile
import json
from bs4 import BeautifulSoup
from twilio.rest import Client
from groq import Groq
from datetime import datetime
import random
from dotenv import load_dotenv
from urllib.parse import quote
import PyPDF2
import docx
import sqlite3
import schedule
import threading

# --- Load Environment Variables ---
load_dotenv()

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('job_alerts')

# --- API Credentials ---
# Twilio Credentials
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
from_whatsapp = os.getenv('TWILIO_PHONE_NUMBER')
to_whatsapp = os.getenv('USER_PHONE_NUMBER')

# Groq Settings
groq_api_key = os.getenv('GROQ_API_KEY')
groq_model = os.getenv('GROQ_MODEL', 'llama3-70b-8192')

# --- Database Setup ---
def init_db():
    """
    Initialize the SQLite database with necessary tables if they don't exist.
    Creates users, jobs, and matches tables.
    """
    conn = sqlite3.connect('job_alerts.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        phone TEXT,
        resume_text TEXT,
        search_keywords TEXT,
        locations TEXT,
        min_score INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create jobs table
    c.execute('''
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        title TEXT,
        company TEXT,
        location TEXT,
        description TEXT,
        link TEXT,
        source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create matches table
    c.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        job_id TEXT,
        score INTEGER,
        sent BOOLEAN DEFAULT FALSE,
        sent_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (job_id) REFERENCES jobs (id)
    )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

# --- Resume Parsing Functions ---
def extract_text_from_pdf(file):
    """
    Extract text content from a PDF file.
    
    Args:
        file: A file-like object containing PDF data
        
    Returns:
        str: Extracted text from the PDF
    """
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        st.error(f"Error extracting text from PDF: {e}")
        return ""

def extract_text_from_docx(file):
    """
    Extract text content from a DOCX file.
    
    Args:
        file: Path to a DOCX file
        
    Returns:
        str: Extracted text from the DOCX
    """
    try:
        doc = docx.Document(file)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {e}")
        st.error(f"Error extracting text from DOCX: {e}")
        return ""

def extract_text_from_file(uploaded_file):
    """
    Extract text from various file formats (PDF, DOCX, TXT).
    
    Args:
        uploaded_file: Streamlit uploaded file object
        
    Returns:
        str: Extracted text from the file
    """
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_file_path = temp_file.name
    
    # Extract text based on file type
    try:
        if uploaded_file.name.endswith('.pdf'):
            with open(temp_file_path, 'rb') as file:
                text = extract_text_from_pdf(file)
        elif uploaded_file.name.endswith('.docx'):
            text = extract_text_from_docx(temp_file_path)
        elif uploaded_file.name.endswith('.txt'):
            with open(temp_file_path, 'r', encoding='utf-8') as file:
                text = file.read()
        else:
            st.error("Unsupported file format. Please upload PDF, DOCX, or TXT.")
            text = ""
    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)
    
    return text

def extract_keywords_from_resume(resume_text):
    """
    Use Groq AI to extract relevant job titles/roles from a resume.
    
    Args:
        resume_text: The text content of a resume
        
    Returns:
        list: List of extracted job titles/keywords
    """
    # Configure Groq client
    try:
        groq_client = Groq(api_key=groq_api_key)
    except Exception as e:
        logger.error(f"Groq setup error: {e}")
        st.error(f"Groq setup error: {e}")
        return ["AI Engineer", "Data Scientist"]
    
    prompt = (
        f"Extract the top 5 job titles/roles this person would be qualified for based on their resume:\n\n"
        f"{resume_text[:2000]}\n\n"
        f"Return ONLY a comma-separated list of job titles with no explanation or additional text."
    )
    
    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=groq_model,
            temperature=0.2
        )
        keywords = response.choices[0].message.content.strip()
        # Clean up and return as a list
        keywords_list = [k.strip() for k in keywords.split(',')]
        return keywords_list
    except Exception as e:
        logger.error(f"Error extracting keywords: {e}")
        st.error(f"Error extracting keywords: {e}")
        return ["AI Engineer", "Data Scientist"]

# --- User Management Functions ---
def add_user(name, email, phone, resume_text, search_keywords, locations, min_score=70):
    """
    Add a new user to the database or update if email already exists.
    
    Args:
        name: User's full name
        email: User's email address (unique identifier)
        phone: User's WhatsApp number
        resume_text: Text content of user's resume
        search_keywords: List of job titles to search for
        locations: List of locations to search in
        min_score: Minimum match score threshold (default: 70)
        
    Returns:
        int: User ID
    """
    conn = sqlite3.connect('job_alerts.db')
    c = conn.cursor()
    
    try:
        c.execute(
            "INSERT INTO users (name, email, phone, resume_text, search_keywords, locations, min_score) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, email, phone, resume_text, json.dumps(search_keywords), json.dumps(locations), min_score)
        )
        conn.commit()
        user_id = c.lastrowid
        logger.info(f"Added new user: {name} ({email})")
    except sqlite3.IntegrityError:
        # Update existing user
        c.execute(
            "UPDATE users SET name=?, phone=?, resume_text=?, search_keywords=?, locations=?, min_score=? WHERE email=?",
            (name, phone, resume_text, json.dumps(search_keywords), json.dumps(locations), min_score, email)
        )
        conn.commit()
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        user_id = c.fetchone()[0]
        logger.info(f"Updated existing user: {name} ({email})")
    
    conn.close()
    return user_id

def get_all_users():
    """
    Retrieve all users from the database.
    
    Returns:
        list: List of user dictionaries
    """
    conn = sqlite3.connect('job_alerts.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT * FROM users")
    users = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return users

# --- Job Scraping Functions ---
def get_headers():
    """
    Generate random user agent headers to avoid scraping detection.
    
    Returns:
        dict: Headers dictionary with User-Agent
    """
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0'
    ]
    return {'User-Agent': random.choice(user_agents)}

def make_request(url, max_retries=3):
    """
    Make an HTTP request with retry logic and exponential backoff.
    
    Args:
        url: URL to request
        max_retries: Maximum number of retry attempts (default: 3)
        
    Returns:
        Response object or None if all retries fail
    """
    headers = get_headers()
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response
            logger.warning(f"Request failed with status {response.status_code}: {url}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request attempt {attempt+1} failed: {e}")
        
        # Exponential backoff
        if attempt < max_retries - 1:
            sleep_time = 2 ** attempt + random.uniform(0, 1)
            time.sleep(sleep_time)
    
    return None

def scrape_linkedin_jobs(keyword, location):
    """
    Scrape job listings from LinkedIn.
    
    Args:
        keyword: Job title or keyword to search for
        location: Location to search in
        
    Returns:
        list: List of job dictionaries
    """
    url = f'https://www.linkedin.com/jobs/search/?keywords={quote(keyword)}&location={quote(location)}'
    
    response = make_request(url)
    if not response:
        logger.error(f"Failed to fetch LinkedIn jobs for {keyword} in {location}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    jobs = []

    for job in soup.select('.base-card')[:5]:
        try:
            title = job.select_one('h3').text.strip()
            company = job.select_one('h4').text.strip()
            location = job.select_one('.job-search-card__location').text.strip()
            link = job.select_one('a')['href']
            job_id = f"linkedin-{link.split('/')[-2]}"
            
            jobs.append({
                "id": job_id,
                "source": "LinkedIn", 
                "title": title, 
                "company": company, 
                "location": location, 
                "link": link
            })
        except Exception as e:
            logger.error(f"LinkedIn parse error: {e}")
    
    logger.info(f"Found {len(jobs)} LinkedIn jobs for '{keyword}' in '{location}'")
    return jobs

def scrape_indeed_jobs(keyword, location):
    """
    Scrape job listings from Indeed.
    
    Args:
        keyword: Job title or keyword to search for
        location: Location to search in
        
    Returns:
        list: List of job dictionaries
    """
    url = f'https://in.indeed.com/jobs?q={quote(keyword)}&l={quote(location)}'
    
    response = make_request(url)
    if not response:
        logger.error(f"Failed to fetch Indeed jobs for {keyword} in {location}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    jobs = []

    for job in soup.select('.job_seen_beacon')[:5]:
        try:
            title = job.select_one('h2 a').text.strip()
            company = job.select_one('.companyName').text.strip()
            location = job.select_one('.companyLocation').text.strip()
            job_path = job.select_one('h2 a')['href']
            link = 'https://in.indeed.com' + job_path
            job_id = f"indeed-{job_path.split('jk=')[-1].split('&')[0]}"
            
            jobs.append({
                "id": job_id,
                "source": "Indeed", 
                "title": title, 
                "company": company, 
                "location": location, 
                "link": link
            })
        except Exception as e:
            logger.error(f"Indeed parse error: {e}")
    
    logger.info(f"Found {len(jobs)} Indeed jobs for '{keyword}' in '{location}'")
    return jobs

def fetch_job_description(link):
    """
    Fetch and extract the job description from a job listing page.
    
    Args:
        link: URL of the job listing
        
    Returns:
        str: Job description text
    """
    response = make_request(link)
    if not response:
        return "N/A"
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Try multiple potential selectors
    selectors = [
        'section', 'div.description', 'div.jobsearch-jobDescriptionText',
        'div.job-description', '[data-automation="jobDescription"]',
        'div.job_description', 'div.jobDescriptionText'
    ]
    
    for selector in selectors:
        desc_tag = soup.select_one(selector)
        if desc_tag:
            return desc_tag.get_text(strip=True)[:2000]
    
    # Fallback: get the main content area
    main_content = soup.find('main') or soup.find('article') or soup.find('body')
    if main_content:
        return main_content.get_text(strip=True)[:2000]
    
    return "N/A"

# --- Job Storage Functions ---
def save_job(job, description):
    """
    Save or update a job in the database.
    
    Args:
        job: Job dictionary with details
        description: Job description text
    """
    conn = sqlite3.connect('job_alerts.db')
    c = conn.cursor()
    
    try:
        c.execute(
            "INSERT OR REPLACE INTO jobs (id, title, company, location, description, link, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job['id'], job['title'], job['company'], job['location'], description, job['link'], job['source'])
        )
        conn.commit()
        logger.info(f"Saved job: {job['title']} at {job['company']}")
    except Exception as e:
        logger.error(f"Error saving job: {e}")
    finally:
        conn.close()

# --- Job Matching Functions ---
def get_match_score(job_title, job_description, resume_text):
    """
    Calculate a match score between a job and a resume using Groq AI.
    
    Args:
        job_title: Title of the job
        job_description: Description of the job
        resume_text: Text content of the resume
        
    Returns:
        int: Match score (0-100)
    """
    try:
        groq_client = Groq(api_key=groq_api_key)
    except Exception as e:
        logger.error(f"Groq setup error: {e}")
        return 50
    
    prompt = (
        f"Resume:\n{resume_text[:1500]}\n\n"
        f"Job Title: {job_title}\n\n"
        f"Job Description: {job_description[:500]}...\n\n"
        f"Evaluate how well this profile matches the job. "
        f"Consider skills, experience, and qualifications required. "
        f"Give a score (0-100) and a brief justification in this format: "
        f"Score: [number]\nJustification: [1-2 sentence explanation]"
    )
    
    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=groq_model,
            temperature=0.2
        )
        content = response.choices[0].message.content
        
        # Parse score from response
        if "Score:" in content:
            score_text = content.split("Score:")[1].split("\n")[0].strip()
            score = int(''.join(filter(str.isdigit, score_text)))
            return min(max(score, 0), 100)
        else:
            # Fallback parsing
            score = int(''.join(filter(str.isdigit, content[:20])))
            return min(max(score, 0), 100)
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        return 50

def analyze_job_with_groq(job_title, company, location, description, resume_text):
    """
    Generate an AI analysis of why a job matches a resume.
    
    Args:
        job_title: Title of the job
        company: Company name
        location: Job location
        description: Job description
        resume_text: Resume text content
        
    Returns:
        str: Analysis text
    """
    try:
        groq_client = Groq(api_key=groq_api_key)
    except Exception as e:
        logger.error(f"Groq setup error: {e}")
        return "Job analysis not available."
    
    prompt = (
        f"Resume:\n{resume_text[:1000]}\n\n"
        f"Job:\n{job_title} at {company}, {location}\n\n"
        f"Description:\n{description[:1000]}\n\n"
        "Respond with:\n"
        "1. 🔎 Brief job summary (1 sentence)\n"
        "2. 💡 Why this candidate should apply (1-2 specific points matching their skills)\n"
        "3. ✅ 2 pros of this role\n"
        "4. ⚠️ 1 potential challenge or consideration\n"
        "Respond in a concise format suitable for WhatsApp, total under 300 characters."
    )
    
    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=groq_model,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"JD analysis error: {e}")
        return "Job analysis not available due to technical issues."

def save_match(user_id, job_id, score):
    """
    Save a match between a user and a job in the database.
    
    Args:
        user_id: User ID
        job_id: Job ID
        score: Match score
    """
    conn = sqlite3.connect('job_alerts.db')
    c = conn.cursor()
    
    try:
        c.execute(
            "INSERT OR REPLACE INTO matches (user_id, job_id, score) VALUES (?, ?, ?)",
            (user_id, job_id, score)
        )
        conn.commit()
        logger.info(f"Saved match: User {user_id} - Job {job_id} - Score {score}%")
    except Exception as e:
        logger.error(f"Error saving match: {e}")
    finally:
        conn.close()

def mark_match_as_sent(user_id, job_id):
    """
    Mark a job match as sent in the database.
    
    Args:
        user_id: User ID
        job_id: Job ID
    """
    conn = sqlite3.connect('job_alerts.db')
    c = conn.cursor()
    
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "UPDATE matches SET sent = TRUE, sent_at = ? WHERE user_id = ? AND job_id = ?",
            (current_time, user_id, job_id)
        )
        conn.commit()
        logger.info(f"Marked match as sent: User {user_id} - Job {job_id}")
    except Exception as e:
        logger.error(f"Error marking match as sent: {e}")
    finally:
        conn.close()

# --- WhatsApp Notification Functions ---
def format_whatsapp_message(job_title, company, location, source, score, analysis, link):
    """
    Format a WhatsApp message for a job match.
    
    Args:
        job_title: Title of the job
        company: Company name
        location: Job location
        source: Source of the job listing (e.g., LinkedIn, Indeed)
        score: Match score
        analysis: AI analysis of the job match
        link: Job application link
        
    Returns:
        str: Formatted WhatsApp message
    """
    current_date = datetime.now().strftime("%d %b %Y")
    
    message = (
        f"🚀 *New Job Match - {current_date}*\n\n"
        f"📌 *{job_title}*\n"
        f"🏢 {company}\n"
        f"📍 {location}\n"
        f"🌐 {source}\n"
        f"📊 *Match Score:* {score}%\n\n"
        f"{analysis}\n\n"
        f"🔗 Apply here: {link}\n\n"
        f"Reply with 'MORE' for similar jobs or 'STOP' to unsubscribe."
    )
    
    return message

def send_whatsapp_message(to_number, message):
    """
    Send a WhatsApp message using Twilio.
    
    Args:
        to_number: Recipient's WhatsApp number
        message: Message content
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            from_=from_whatsapp,
            body=message,
            to=to_whatsapp
        )
        logger.info(f"Sent WhatsApp message to {to_number}")
        return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
        return False

# --- Main Job Matching Function ---
def match_jobs_with_user(user_id):
    """
    Match jobs with a specific user and send notifications for good matches.
    
    Args:
        user_id: User ID to match jobs for
    """
    conn = sqlite3.connect('job_alerts.db')
    c = conn.cursor()
    
    # Get user details
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        logger.warning(f"User {user_id} not found")
        return
    
    # Get user's resume text
    resume_text = user[4]
    
    # Get all jobs
    c.execute("SELECT * FROM jobs")
    jobs = c.fetchall()
    
    for job in jobs:
        # Get job details
        job_title = job[1]
        company = job[2]
        location = job[3]
        description = job[4]
        link = job[5]
        
        # Get match score
        score = get_match_score(job_title, description, resume_text)
        
        # If score is above threshold
        if score >= user[7]:  # user[7] is min_score
            # Check if match already exists
            c.execute("SELECT * FROM matches WHERE user_id=? AND job_id=?", (user_id, job[0]))
            if not c.fetchone():
                # Save match
                save_match(user_id, job[0], score)
                
                # Get analysis
                analysis = analyze_job_with_groq(job_title, company, location, description, resume_text)
                
                # Format and send WhatsApp message
                message = format_whatsapp_message(job_title, company, location, job[6], score, analysis, link)
                if send_whatsapp_message(to_whatsapp, message):
                    mark_match_as_sent(user_id, job[0])
    
    conn.close()

# --- Background Job Processing ---
def run_job_scraper():
    """
    Main function to run the job scraper for all users.
    Fetches jobs, calculates matches, and sends notifications.
    """
    users = get_all_users()
    
    if not users:
        logger.info("No users in database")
        return
    
    for user in users:
        try:
            # Parse JSON strings back to lists
            search_keywords = json.loads(user['search_keywords'])
            locations = json.loads(user['locations'])
            min_score = user['min_score']
            
            logger.info(f"Processing jobs for user: {user['name']} ({user['email']})")
            
            for keyword in search_keywords:
                for location in locations:
                    # Get jobs from multiple sources
                    all_jobs = scrape_linkedin_jobs(keyword, location) + scrape_indeed_jobs(keyword, location)
                    logger.info(f"Found {len(all_jobs)} jobs for '{keyword}' in '{location}'")
                    
                    for job in all_jobs:
                        # Fetch description
                        description = fetch_job_description(job['link'])
                        save_job(job, description)
                        
                        # Calculate match score
                        score = get_match_score(job['title'], description, user['resume_text'])
                        save_match(user['id'], job['id'], score)
                        
                        # Send notification for good matches
                        if score >= min_score:
                            analysis = analyze_job_with_groq(
                                job['title'], job['company'], job['location'], 
                                description, user['resume_text']
                            )
                            
                            message = format_whatsapp_message(
                                job['title'], job['company'], job['location'],
                                job['source'], score, analysis, job['link']
                            )
                            
                            if send_whatsapp_message(user['phone'], message):
                                logger.info(f"✅ Sent job alert to {user['name']}: {job['title']} ({score}%)")
                                mark_match_as_sent(user['id'], job['id'])
                            
                            # Add delay between messages
                            time.sleep(random.uniform(2, 5))
        except Exception as e:
            logger.error(f"Error processing user {user['id']}: {e}")

# --- Scheduled Task Function ---
def run