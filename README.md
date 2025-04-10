# Smart Job Alert System

This system automatically searches for job listings on LinkedIn and Indeed, analyzes them using AI, and sends matching jobs to your WhatsApp.

## Features

- Scrapes job listings from LinkedIn and Indeed
- Uses Groq AI to analyze job descriptions and match them to your resume
- Sends personalized job alerts via WhatsApp
- Can be scheduled to run automatically

## Setup

1. Make sure you have Python installed (3.8 or higher)
2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
3. Configure your `.env` file with your API credentials:
   ```
   TWILIO_ACCOUNT_SID=your_twilio_sid
   TWILIO_AUTH_TOKEN=your_twilio_token
   TWILIO_PHONE_NUMBER=whatsapp:+14155238886
   USER_PHONE_NUMBER=whatsapp:+your_number
   GROQ_API_KEY=your_groq_api_key
   GROQ_MODEL=llama3-70b-8192
   ```

## Usage

### Run Manually

To run the job alert system once:

```
python try.py
```

### Schedule Automatic Runs

#### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create a new Basic Task
3. Set the trigger (e.g., daily at 9 AM)
4. For the action, select "Start a program"
5. Browse to your Python executable (e.g., `C:\Python310\python.exe`)
6. Add arguments: `schedule_job_alerts.py`
7. Set the start in directory to your project folder

## Troubleshooting

### Twilio Message Limit

The free Twilio account has a daily message limit. If you hit this limit, you'll see an error message. To send more messages:

1. Upgrade your Twilio account
2. Or reduce the number of jobs you're processing by adjusting the score threshold

### Web Scraping Issues

If the script fails to scrape job listings, it might be due to changes in the website structure. Try updating the CSS selectors in the scraping functions.

## Customization

- Edit your resume in the `user_resume` variable
- Change job search keywords in the `search_keyword` variable
- Adjust the match score threshold (currently 70%) to get more or fewer alerts
