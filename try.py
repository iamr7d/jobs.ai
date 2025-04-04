import os
import time
import requests
from bs4 import BeautifulSoup
from twilio.rest import Client
from groq import Groq
from datetime import datetime

# --- Load Environment Variables ---
from dotenv import load_dotenv
load_dotenv()

# --- Twilio Setup ---
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_client = Client(account_sid, auth_token)
from_whatsapp = os.getenv('TWILIO_PHONE_NUMBER')
to_whatsapp = os.getenv('USER_PHONE_NUMBER')

# --- Groq Setup ---
client = Groq(api_key=os.getenv('GROQ_API_KEY'))

# --- Job Search Config ---
search_keyword = "AI Engineer"
search_location = "India"
headers = {'User-Agent': 'Mozilla/5.0'}

# --- Targeted Roles ---
job_roles = [
    "AI Engineer", "ML Engineer", "Data Scientist", "NLP Engineer",
    "Generative AI Engineer", "AI Research Intern", "Deep Learning Engineer",
    "Computer Vision Engineer", "AI Developer", "AI Researcher"
]

# --- User Resume ---
user_resume = """
Rahulraj P V | AI R&D Engineer | M.Tech in Artificial Intelligence

Skills: Python, Machine Learning, Deep Learning, Generative AI, NLP, Computer Vision, Film Analytics

Experience:
- Developed an AI-driven film analysis tool
- Built India’s first generative AI radio, Maadhuri
- Researched blockchain for agriculture

Looking for: AI/ML roles, Research Internships, Generative Media Engineering roles
"""

# --- Scoring Function ---
def get_match_score(job_title, resume_text):
    prompt = (
        f"Resume:\n{resume_text}\n\n"
        f"Evaluate how well this profile matches the job title: '{job_title}'. "
        f"Give a score (0-100) and 1-sentence justification."
    )
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=os.getenv('GROQ_MODEL', 'llama3-70b-8192')
        )
        content = response.choices[0].message.content
        score = int(''.join(filter(str.isdigit, content)))
        return min(max(score, 0), 100)
    except Exception as e:
        print(f"⚠️ Scoring error: {e}")
        return 50

# --- Groq JD Analysis ---
def analyze_job_with_groq(job, resume_text):
    prompt = (
        f"Resume:\n{resume_text}\n\n"
        f"Job:\n{job['title']} at {job['company']}, {job['location']}\n\n"
        f"Description:\n{job.get('description', 'N/A')}\n\n"
        "Respond with:\n"
        "1. 🔎 Short job summary\n"
        "2. 💡 Why this user should apply\n"
        "3. ✅ 2-3 pros of this role\n"
        "4. ⚠️ Any cons or red flags\n"
        "Use a concise tone, suitable for WhatsApp."
    )
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=os.getenv('GROQ_MODEL', 'llama3-70b-8192')
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"⚠️ JD analysis error: {e}")
        return "📝 Summary not available."

# --- Fetch Description from Job Link ---
def fetch_job_description(link):
    try:
        response = requests.get(link, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        desc_tag = (
            soup.find('section') or
            soup.find('div', class_='description') or
            soup.find('div', class_='jobsearch-jobDescriptionText')
        )
        return desc_tag.get_text(strip=True)[:1500] if desc_tag else "N/A"
    except Exception as e:
        print(f"⚠️ Description fetch error ({link}): {e}")
        return "N/A"

# --- LinkedIn Scraper ---
def scrape_linkedin_jobs():
    url = f'https://www.linkedin.com/jobs/search/?keywords={search_keyword}&location={search_location}'
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    jobs = []

    for job in soup.select('.base-card')[:5]:
        try:
            title = job.select_one('h3').text.strip()
            company = job.select_one('h4').text.strip()
            location = job.select_one('.job-search-card__location').text.strip()
            link = job.select_one('a')['href']
            jobs.append({"source": "LinkedIn", "title": title, "company": company, "location": location, "link": link})
        except Exception as e:
            print(f"⚠️ LinkedIn parse error: {e}")
    return jobs

# --- Indeed Scraper ---
def scrape_indeed_jobs():
    url = f'https://in.indeed.com/jobs?q={search_keyword.replace(" ", "+")}&l={search_location.replace(" ", "+")}'
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    jobs = []

    for job in soup.select('.job_seen_beacon')[:5]:
        try:
            title = job.select_one('h2 a').text.strip()
            company = job.select_one('.companyName').text.strip()
            location = job.select_one('.companyLocation').text.strip()
            link = 'https://in.indeed.com' + job.select_one('h2 a')['href']
            jobs.append({"source": "Indeed", "title": title, "company": company, "location": location, "link": link})
        except Exception as e:
            print(f"⚠️ Indeed parse error: {e}")
    return jobs

# --- Send Jobs ---
def send_jobs():
    all_jobs = scrape_linkedin_jobs() + scrape_indeed_jobs()
    if not all_jobs:
        print("❌ No jobs found.")
        return

    print(f"🔍 {len(all_jobs)} jobs found at {datetime.now().strftime('%H:%M:%S')}.")

    for job in all_jobs:
        job["description"] = fetch_job_description(job["link"])
        score = get_match_score(job["title"], user_resume)

        if score >= 70:
            analysis = analyze_job_with_groq(job, user_resume)
            message = (
                f"🚀 *New Job Match!*\n"
                f"📌 *{job['title']}*\n"
                f"🏢 {job['company']}\n"
                f"📍 {job['location']}\n"
                f"🌐 Source: {job['source']}\n"
                f"📊 *AI Match Score:* {score}%\n"
                f"🔗 {job['link']}\n\n"
                f"{analysis}"
            )
            try:
                twilio_client.messages.create(from_=from_whatsapp, to=to_whatsapp, body=message)
                print(f"✅ Sent: {job['title']} ({score}%)")
                time.sleep(2)
            except Exception as e:
                if "exceeded" in str(e) and "limit" in str(e):
                    print(f"❌ Message limit exceeded: You've reached Twilio's daily message limit")
                    print(f"💡 Tip: Upgrade your Twilio account to send more messages")
                else:
                    print(f"❌ Failed to send message: {e}")
        else:
            print(f"⏭️ Skipped: {job['title']} (Score: {score}%)")

# --- Entry Point ---
if __name__ == "__main__":
    print("💼 Smart Job Alert System Started...\n")
    send_jobs()
