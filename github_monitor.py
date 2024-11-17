import requests
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time
from dotenv import load_dotenv
import os
import re
from datetime import datetime
from pytz import timezone

load_dotenv()

# Configuration
GITHUB_REPO = "cvrve/New-Grad-2025"  # Format: "username/repository"
EMAIL_SENDER = os.getenv("EMAIL")
EMAIL_RECEIVER = os.getenv("EMAIL")
EMAIL_PASSWORD = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
SMTP_SERVER = "smtp.gmail.com"  # E.g., "smtp.gmail.com" for Gmail
SMTP_PORT = 587  # Common SMTP port for TLS
CHECK_INTERVAL = 3600  # Check every hour (in seconds)
LAST_COMMIT_FILE = "last_commit_sha.txt"

url_pattern = re.compile(r'^\+?\s*"url":\s*"(.*?)"', re.MULTILINE)
company_pattern = re.compile(r'^\+?\s*"company_name":\s*"(.*?)"', re.MULTILINE)
title_pattern = re.compile(r'^\+?\s*"title":\s*"(.*?)"', re.MULTILINE)
locations_pattern = re.compile(r'^\+?\s*"locations":\s*\[(.*?)\]', re.MULTILINE | re.DOTALL)


def extract_job_details(commit_content):
    url = url_pattern.search(commit_content).group(1) if url_pattern.search(commit_content) else None
    company_name = company_pattern.search(commit_content).group(1) if company_pattern.search(commit_content) else None
    title = title_pattern.search(commit_content).group(1) if title_pattern.search(commit_content) else None
    
    # Use the improved pattern to capture all locations, even if they're on multiple lines
    locations_match = locations_pattern.search(commit_content)
    if locations_match:
        locations_raw = locations_match.group(1)
        locations_cleaned = re.sub(r'\+?\s*', '', locations_raw)
        # print("cleaned locs: ", locations_cleaned)
        locations = [loc.strip().strip('"') for loc in locations_cleaned.split("\",\"") if loc.strip()]
    else:
        locations = []

    return {
        "Company Name": company_name,
        "Title": title,
        "URL": url,
        "Locations": locations
    }

def load_last_commit_sha():
    try:
        with open(LAST_COMMIT_FILE, "r") as file:
            return file.read().strip()
    except FileNotFoundError:
        print("Last commit file not found. Starting from the latest commit.")
        return None
    
def save_last_commit_sha(commit_sha):
    with open(LAST_COMMIT_FILE, "w") as file:
        file.write(commit_sha)

# Global variable to store the last seen commit SHA
last_commit_sha = None

def get_new_commits():
    last_commit_sha = load_last_commit_sha()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits"
    response = requests.get(url)
    
    if response.status_code == 200:
        commits = response.json()
        new_commits = []
        print(type(commits))

        count = 0
        
        # Collect all commits up to the last seen commit
        for com in commits:
            count += 1
            commit_message = com['commit']['message']
            commit_dict = {
                "sha": com['sha'],
                "message": commit_message
            }
            if commit_message.startswith("added listing: "):
                commit_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{com['sha']}"
                commit_response = requests.get(commit_url)
                commit_info = commit_response.json()
                commit_content = commit_info['files'][0]['patch']

                print(commit_content + "\n\n")

                # extract company name, title, url, locations
                job_details = extract_job_details(commit_content)

                print("Company:", job_details["Company Name"])
                print("Title:", job_details["Title"])
                print("URL:", job_details["URL"])
                print("Locations:", job_details["Locations"])

                commit_dict = {
                    "sha": com['sha'],
                    "message": commit_message,
                    "company": job_details["Company Name"],
                    "title": job_details["Title"],
                    "url": job_details["URL"],
                    "locations": job_details["Locations"]
                }

            commit_sha = com['sha']
            if commit_sha == last_commit_sha:
                break
            new_commits.append(commit_dict)
        
        print(f"Processed {count} commits.")
        # Update the last commit SHA if there are new commits
        if new_commits:
            last_commit_sha = new_commits[-1]['sha']
            save_last_commit_sha(last_commit_sha)
            return new_commits[::]  
    else:
        print("Failed to retrieve repository data.")
    return []

def send_email(subject, message):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = subject

    msg.attach(MIMEText(message, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Use TLS
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
            print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    global last_commit_sha
    print("Starting GitHub monitor...")

    while True:
        new_commits = get_new_commits()
        
        if new_commits:
            est = timezone('US/Eastern')
            current_time = datetime.now(est).strftime('%d-%m-%Y %H:%M:%S %Z')
            email_subject = f"New Commits in cvrve GitHub Repository! - {current_time}"
            email_message = "The following new commits were made:\n\n"
            
            for commit in new_commits:
                email_message += f"- Commit Message: {commit['message']}\n  Company: {commit['company']}\n  Title: {commit['title']}\n  Locations: {commit['locations']}\n  URL: {commit['url']}\n\n"
            
            send_email(email_subject, email_message)
            print("New commits detected and email sent.")
        
        # Wait for the next check
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()