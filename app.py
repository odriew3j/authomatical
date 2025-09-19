import os
import requests
import json
import time
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# -------- Config --------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
WORDPRESS_URL = os.getenv("WORDPRESS_URL")
WORDPRESS_USER = os.getenv("WORDPRESS_USER")
WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
TIMEOUT = int(os.getenv("TIMEOUT", 30))

# -------- Step 1: User input --------
keywords = input("Enter keywords (comma-separated): ")
num_chapters = int(input("Number of chapters: "))
max_words = int(input("Max words count: "))

# -------- Helper function to call OpenRouter with retry --------
def openrouter_chat(messages, model="gpt-4o-mini", max_tokens=500):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}

    for attempt in range(MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            res.raise_for_status()
            return res.json()
        except (requests.exceptions.RequestException, requests.exceptions.ConnectionError) as e:
            print(f"[Retry {attempt + 1}/{MAX_RETRIES}] OpenRouter error: {e}")
            time.sleep(2)  # wait before retry
    raise Exception("OpenRouter request failed after retries.")

def openrouter_image(prompt, size="1792x1024"):
    url = "https://openrouter.ai/api/v1/images/generate"  # مسیر جدید
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": size
    }

    for attempt in range(MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            res.raise_for_status()
            return res.json()
        except (requests.exceptions.RequestException, requests.exceptions.ConnectionError) as e:
            print(f"[Retry {attempt + 1}/{MAX_RETRIES}] OpenRouter Image error: {e}")
            time.sleep(2)
    raise Exception("OpenRouter image request failed after retries.")

# -------- Step 2: Create article structure --------
prompt_structure = f"""
Write a SEO-friendly article based on the topic "{keywords}".
Output only valid JSON with the following structure:

{{
  "title": "",
  "subtitle": "",
  "introduction": "",
  "conclusions": "",
  "imagePrompt": "",
  "chapters": [
    {{
      "title": "",
      "prompt": ""
    }}
  ]
}}

- Use {num_chapters} chapters.
- Output only valid JSON.
- Use HTML for bold, italic, lists; no Markdown.
- Chapters must be related and fluent.
"""

article_response = openrouter_chat(
    messages=[{"role": "user", "content": prompt_structure}],
    model="gpt-4o-mini",
    max_tokens=1000
)

article_json = json.loads(article_response['choices'][0]['message']['content'])
print("Article structure created.")

# -------- Step 3: Generate chapter texts with chunking --------
chapter_texts = []
words_per_chunk = max_words // num_chapters
for chapter in article_json['chapters']:
    prompt_chapter = f"""
Write a chapter for the article titled "{article_json['title']}".
Topic: {keywords}
Chapter title: {chapter['title']}
Prompt: {chapter['prompt']}

- Just return plain HTML text.
- No Markdown.
- Length: ~{words_per_chunk} words.
"""
    # Retry and chunk handling inside openrouter_chat
    res = openrouter_chat(
        messages=[{"role": "user", "content": prompt_chapter}],
        model="gpt-4o-mini",
        max_tokens=1024  # smaller chunk to prevent disconnect
    )
    chapter_texts.append({
        "title": chapter['title'],
        "content": res['choices'][0]['message']['content']
    })

# -------- Step 4: Merge final article --------
final_article = article_json['introduction'] + "<br><br>"
for ch in chapter_texts:
    final_article += f"<strong>{ch['title']}</strong><br><br>{ch['content']}<br><br>"
final_article += f"<strong>Conclusions</strong><br><br>{article_json['conclusions']}"

# -------- Step 5: Post to WordPress with retry --------
wp_auth = (WORDPRESS_USER, WORDPRESS_PASSWORD)
post_data = {"title": article_json['title'], "content": final_article, "status": "draft"}

for attempt in range(MAX_RETRIES):
    try:
        res = requests.post(
            f"{WORDPRESS_URL}/wp-json/wp/v2/posts",
            auth=wp_auth,
            json=post_data,
            timeout=TIMEOUT
        )
        if res.status_code == 201:
            post_id = res.json()["id"]
            print(f"Draft created successfully! Post ID: {post_id}")
            break
        else:
            print(f"[Retry {attempt + 1}] Error creating draft: {res.text}")
    except requests.exceptions.RequestException as e:
        print(f"[Retry {attempt + 1}] WordPress request error: {e}")
    time.sleep(2)
else:
    raise Exception("Failed to create WordPress post after retries.")

# -------- Step 6: Generate Featured Image and upload --------
prompt_image = f"Generate a photographic image for the article titled: {article_json['title']}. Prompt: {article_json['imagePrompt']}, photography, realistic, sigma 85mm f/1.4"
image_resp = openrouter_image(prompt_image)
image_data = requests.get(image_resp['data'][0]['url'], timeout=TIMEOUT).content

for attempt in range(MAX_RETRIES):
    try:
        files = {'file': ('featured.jpg', image_data, 'image/jpeg')}
        res_img = requests.post(f"{WORDPRESS_URL}/wp-json/wp/v2/media", auth=wp_auth, files=files, timeout=TIMEOUT)
        if res_img.status_code == 201:
            media_id = res_img.json()["id"]
            # Set image as featured
            requests.post(f"{WORDPRESS_URL}/wp-json/wp/v2/posts/{post_id}", auth=wp_auth, json={"featured_media": media_id}, timeout=TIMEOUT)
            print("Featured image uploaded and assigned.")
            break
        else:
            print(f"[Retry {attempt + 1}] Error uploading image: {res_img.text}")
    except requests.exceptions.RequestException as e:
        print(f"[Retry {attempt + 1}] Image upload error: {e}")
    time.sleep(2)

print("Workflow completed successfully!")
