# AutoContent & Product Worker for WooCommerce

[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-2.3.2-green)](https://flask.palletsprojects.com/)
[![Redis](https://img.shields.io/badge/redis-7.0-orange)](https://redis.io/)

**Author:** Mohammad Mousavi
**Company:** Online Digital View

---

## 🔹 Project Overview

This project is a **web-based automation system** for managing content and product publishing:

1. **Article Generator:**

   * Accepts keywords and parameters via a web form.
   * Uses AI (OpenRouterClient) to generate article content and SEO meta.
   * Publishes articles to WordPress automatically.

2. **Product Publisher:**

   * Accepts product details including title, price, category, tags, images, and keywords.
   * Uses AI to generate product descriptions and SEO meta.
   * Publishes products to WooCommerce/WordPress automatically.

3. **Background Worker System:**

   * Jobs are queued in Redis Streams.
   * Dedicated Python workers consume the jobs and perform publishing tasks.
   * Supports temporary storage in Redis for recovery.

4. **Web Dashboard:**

   * Flask app provides a dashboard to manage articles and products.
   * Separate forms for article and product submissions.
   * Displays queued job status.

---

## 📂 Project Structure

```
authomatical/
├── clients/              # API clients (WordPress, OpenRouter)
├── messaging/            # Redis broker for queue management
├── modules/              # Business logic modules (article, product)
├── services/             # Flask web app
│   ├── blueprints/       # Blueprint routes for articles/products
│   └── templates/        # HTML templates for web forms
├── utils/                # Helpers and utility functions
├── workers/              # Background workers (article & product)
├── venv/                 # Python virtual environment
├── config.py             # Configuration (Redis, WordPress, etc.)
├── app.py                # Flask app entry point
├── requirements.txt
└── README.md
```

---

## ⚡ Features

* **AI-Powered Content Creation:** Automatically generate article/product descriptions and SEO metadata.
* **WooCommerce Integration:** Direct publishing to WooCommerce products.
* **Redis Queues:** Reliable job management with acknowledgment.
* **Web Interface:** Submit new jobs for articles or products.
* **Extensible Worker Architecture:** Easy to add new workers (e.g., for social media, emails, or other automations).

---

## 🛠 Installation

1. **Clone the repository:**

```bash
git clone https://github.com/odriew3j/authomatical.git
cd authomatical
```

2. **Create virtual environment:**

```bash
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux / Mac
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Set up `.env` or `config.py`:**

* Configure WordPress credentials: `WORDPRESS_USER`, `WORDPRESS_PASSWORD`, `WORDPRESS_URL`
* Redis URL: `REDIS_URL`
* AI client API key (OpenRouter or similar)
* Optional: timeout, max retries, etc.

5. **Start Redis Server** (if not running):

```bash
redis-server
```

---

## 🚀 Running the Application

### 1. Start Flask Web App

```bash
python services/web_app.py
```

* Open `http://127.0.0.1:5000` to see the **dashboard**.
* Navigate to **Articles** or **Products** to submit jobs.

### 2. Start Workers

#### Article Worker

```bash
python workers/article_worker.py
```

#### Product Worker

```bash
python workers/product_worker.py
```

> Workers will continuously listen to Redis Streams and process queued jobs.

---

## 📝 Usage

### Article Submission

* Fields: keywords, chapters, max\_words, tone, audience
* AI generates the content and SEO meta.
* Article is published to WordPress automatically.

### Product Submission

* Fields: title, price, sale\_price, category, brand, tags, images, keywords, tone, audience
* AI generates product description and SEO meta.
* Product is published to WooCommerce automatically.

---

## ⚙️ Configuration

* **RedisBroker:** Redis Streams for job queueing
* **WordPressClient:** Handles posts and media upload
* **OpenRouterClient:** Generates AI content
* **Workers:** Consume queued jobs and publish content
* **Flask Blueprints:** `/articles` and `/products` for web forms

---

## ✅ Best Practices

* Always run workers separately from Flask server.
* Keep WordPress credentials secure.
* Use environment variables for sensitive information.
* Validate job data before submission.
* Optional: Monitor Redis streams to track failed jobs.

---

## 📚 Future Enhancements

* Add authentication for dashboard.
* Add job status tracking.
* Support for multiple WordPress/WooCommerce instances.
* Integrate with social media posting.
* Desktop client using PyQt/Tkinter or Electron.

---

## 📄 License

This project is licensed under the **MIT License** – free to use, modify, and distribute.
Add a `LICENSE` file with the following:

```
MIT License

Copyright (c) 2025 Mohammad Mousavi

Permission is hereby granted, free of charge, to any person obtaining a copy...
```