# Authomatical Article Generator

This project automatically generates SEO-friendly articles using **OpenRouter API** and publishes them as drafts on a WordPress site, including a generated featured image.

## 🚀 Features
- Generate structured articles (title, chapters, intro, conclusion).
- Publish drafts to WordPress via REST API.
- Upload and assign featured images automatically.
- Retry mechanism for API calls.

## 📦 Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/odriew3j/authomatical.git
   cd authomatical

    Create and activate a virtual environment:

python -m venv venv
source venv/bin/activate   # Linux / Mac
venv\Scripts\activate      # Windows

Install dependencies:

pip install -r requirements.txt

Create a .env file in the project root:

OPENROUTER_API_KEY=your_openrouter_key
WORDPRESS_URL=https://yourwordpress.com
WORDPRESS_USER=your_username
WORDPRESS_PASSWORD=your_password
MAX_RETRIES=3
TIMEOUT=30

Run the script:

    python app.py

⚠️ Notes

    Ensure WordPress REST API is enabled and credentials are correct.

    Do not commit your .env file (already included in .gitignore).

    OpenRouter does not currently support direct image generation (/images/generate). You may need another provider (e.g., Replicate, Stability AI)