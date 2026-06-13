# scraper.py
import os
import re
import json
import asyncio
import random
import sys
import httpx
from bs4 import BeautifulSoup
from google import genai
from motor.motor_asyncio import AsyncIOMotorClient
from telethon import TelegramClient, events
from dotenv import load_dotenv
from urllib.parse import urlparse

# --- Config ---
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()
API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MONGO_URI = os.getenv('MONGO_URI')

# Clients
genai_client = genai.Client(api_key=GEMINI_API_KEY)
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client['deal_db']
deals_collection = db['deals']
state_collection = db['channel_state']

# Indexes (Run once on startup)
async def ensure_indexes():
    await deals_collection.create_index("original_link", unique=True)
    await deals_collection.create_index([("discount_percentage", -1), ("extracted_at", -1)])
    await deals_collection.create_index("status")
    await state_collection.create_index("chat_id", unique=True)

TARGET_GROUPS = [
    -1001659536566, -1001334236392, -1002324044471, -1001391583159,
    -1002891052461, -1002865773247, -1001201589228, -1001486606418
]

telegram_client = TelegramClient('deal_session', API_ID, API_HASH)
semaphore = asyncio.Semaphore(10) # Concurrency limit

# --- Helpers ---

def clean_price(price_str):
    """Extracts float from '₹1,299', 'Rs. 1299', '1299.00'"""
    if not price_str: return None
    # Remove currency symbols, commas, spaces
    cleaned = re.sub(r'[^\d.]', '', str(price_str))
    try: return float(cleaned)
    except: return None

def calculate_discount(current, original):
    if current and original and original > current:
        return round(((original - current) / original) * 100)
    return 0

# --- 1. VERIFICATION & SCRAPING ---

async def verify_and_fetch(url):
    """Single network call: Verifies liveness + Returns HTML for parsing."""
    async with semaphore:
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ]
        death_keywords = ["out of stock", "sold out", "unavailable", "product not found", "currently unavailable", "404", "page not found"]
        
        try:
            await asyncio.sleep(random.uniform(0.3, 0.8)) # Polite delay
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                headers = {"User-Agent": random.choice(ua_list), "Referer": "https://www.google.com/"}
                resp = await client.get(url, headers=headers)
                
                if resp.status_code >= 400: return False, None, f"HTTP {resp.status_code}"
                content_lower = resp.text.lower()
                if any(kw in content_lower for kw in death_keywords): return False, None, "OOS Keyword"
                
                return True, resp.text, str(resp.url) # Return final URL after redirects
        except Exception as e:
            return False, None, str(e)

def extract_image_from_html(html, base_url):
    """Robust image extraction: JSON-LD -> OG:Image -> Site Selectors -> First large IMG"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. JSON-LD (Schema.org) - Most reliable
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get('@type') in ['Product', 'ItemPage']:
                    img = item.get('image')
                    if img: return img[0] if isinstance(img, list) else img
        except: pass

    # 2. Open Graph / Twitter Cards
    og = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'twitter:image'})
    if og and og.get('content'): return og['content']

    # 3. Site Specific Selectors
    domain = urlparse(base_url).netloc.lower()
    selectors = {
        'amazon': '#landingImage, #imgBlkFront, #imgTagWrapperId img',
        'flipkart': 'img._396cs4, img._2r_T1I, ._1AtVbE img', # Classes change often, generic fallback below
        'myntra': '.image-grid-image, .pdp-img',
        'ajio': '.prod-img, .image-grid img',
        'nykaa': '.css-1v41ww4 img, .product-image img',
    }
    for key, sel in selectors.items():
        if key in domain:
            tag = soup.select_one(sel)
            if tag and tag.get('src'): return tag['src']

    # 4. Generic Fallback: Largest <img> in main content area (heuristic)
    # Avoid logos/icons by checking dimensions if present, else first big one
    main_area = soup.find('main') or soup.find(id='content') or soup.body
    if main_area:
        imgs = main_area.find_all('img', src=True)
        # Filter tracking pixels / tiny icons
        valid_imgs = [i for i in imgs if not any(bad in i['src'] for bad in ['pixel', 'tracking', 'logo', 'icon', 'sprite', '.svg', 'base64'])]
        if valid_imgs: return valid_imgs[0]['src']

    return None

async def scrape_fallback_data(url, html):
    """Extracts Name, Price, Image from HTML when AI fails."""
    url = str(url)
    soup = BeautifulSoup(html, 'html.parser')
    data = {"product_name": None, "sale_price": None, "original_price": None, "image_url": None}
    
    # Image (Universal)
    data['image_url'] = extract_image_from_html(html, url)

    # Name & Price - Site Specific
    domain = urlparse(url).netloc.lower()
    
    if 'amazon' in domain:
        title_tag = soup.find(id='productTitle')
        if title_tag: data['product_name'] = title_tag.get_text(strip=True)
        
        # Price logic: Try .a-price .a-offscreen (current), then .a-text-price .a-offscreen (original)
        current_tag = soup.select_one('.a-price .a-offscreen')
        if current_tag: data['sale_price'] = clean_price(current_tag.get_text())
        
        original_tag = soup.select_one('.a-text-price .a-offscreen, #listPrice, #priceblock_ourprice')
        if original_tag: data['original_price'] = clean_price(original_tag.get_text())
        # Fallback: If no original price, assume current is discounted? No, leave null.

    elif 'flipkart' in domain:
        title_tag = soup.find('span', class_='B_NuCI') or soup.find('h1', class_='yhB1nd')
        if title_tag: data['product_name'] = title_tag.get_text(strip=True)
        
        # Flipkart prices often in meta tags or specific divs
        # Current price
        current_tag = soup.find('div', class_='_30jeq3') or soup.select_one('meta[itemprop="price"]')
        if current_tag: data['sale_price'] = clean_price(current_tag.get('content') or current_tag.get_text())
        
        # Original price (strikethrough)
        original_tag = soup.find('div', class_='_3I9_wc') or soup.find('div', class_='_1uv9Cb')
        if original_tag: data['original_price'] = clean_price(original_tag.get_text())

    # Generic Meta Tag Fallback (Schema.org / Product)
    if not data['sale_price']:
        price_meta = soup.find('meta', itemprop='price') or soup.find('meta', property='product:price:amount')
        if price_meta: data['sale_price'] = clean_price(price_meta.get('content'))
    
    if not data['original_price']:
        # Look for strikethrough text usually containing original price
        strike = soup.find(['s', 'strike', 'del'])
        if strike: data['original_price'] = clean_price(strike.get_text())

    # Final Name Fallback
    if not data['product_name']:
        h1 = soup.find('h1')
        if h1: data['product_name'] = h1.get_text(strip=True)
    
    if not data['product_name'] and soup.title:
        data['product_name'] = soup.title.string.split('|')[0].split('-')[0].strip()

    return data

# --- 2. AI PARSING ---

AI_PROMPT = """
You are a deal extraction engine. Analyze the Telegram message text and return ONLY a valid JSON object.
Keys required: 
- product_name (string, clean title)
- sale_price (number, current selling price)
- original_price (number, MRP/Strikethrough price)
- discount_percentage (number, calculated if possible)
- currency (string, default "INR")
- image_url (string, direct image link if mentioned in text, else null)
- product_url (string, the canonical product URL if identifiable from text, else null)

Rules:
1. If a value is not found, use null. Do not guess.
2. Prices must be numbers (e.g., 1299 not "₹1,299").
3. discount_percentage = round((original - sale) / original * 100).
4. Ignore referral/affiliate params in URLs.
Text: {text}
"""

async def ai_parse_deal(text):
    try:
        response = genai_client.models.generate_content(
            model='gemini-1.5-flash', # Use specific stable model
            contents=AI_PROMPT.format(text=text[:4000]) # Limit context
        )
        raw = response.text.strip()
        # Robust JSON extraction
        start, end = raw.find('{'), raw.rfind('}')
        if start != -1 and end != -1:
            return json.loads(raw[start:end+1])
    except Exception as e:
        print(f"⚠️ AI Error: {e}")
    return None

# --- 3. PIPELINE ORCHESTRATION ---

def extract_links(text):
    urls = re.findall(r'https?://[^\s<>"\']+', text)
    return [u for u in urls if 't.me/' not in u and 'wa.me' not in u]

def slice_text(text, links):
    segments, remaining = [], text
    for link in links:
        parts = remaining.split(link, 1)
        segments.append((parts[0].strip(), link))
        remaining = parts[1] if len(parts) > 1 else ""
    return segments

async def handle_single_deal(description, link):
    # 1. Verify & Fetch HTML
    is_valid, html, final_url = await verify_and_fetch(link)
    if not is_valid: return f"🗑️ Dead: {link}"

    # 2. AI Parse (Primary)
    deal = await ai_parse_deal(description)
    
    # 3. Fallback Scrape (Secondary) - Merge with AI
    if not deal or not deal.get('product_name') or not deal.get('sale_price'):
        fallback = await scrape_fallback_data(final_url, html)
        if deal: deal.update({k: v for k, v in fallback.items() if v and not deal.get(k)})
        else: deal = fallback

    # 4. ENRICHMENT & VALIDATION (The Gatekeeper)
    if not deal: return f"❌ Parse Fail: {link}"
    
    # Ensure prices are floats
    deal['sale_price'] = clean_price(deal.get('sale_price'))
    deal['original_price'] = clean_price(deal.get('original_price'))
    
    # Calculate Discount if missing
    if not deal.get('discount_percentage'):
        deal['discount_percentage'] = calculate_discount(deal['sale_price'], deal['original_price'])

    # 🛑 HARD FILTER: Must have Name, Sale Price, and Discount > 0 (or at least a price)
    # Adjust `discount_percentage > 0` to `>= 0` if you want free items/price drops without % shown
    if not deal.get('product_name') or not deal.get('sale_price') or deal.get('discount_percentage', 0) <= 0:
        return f"🚫 Rejected (Invalid Data): {deal.get('product_name')} | Price: {deal.get('sale_price')} | Disc: {deal.get('discount_percentage')}"

    # 5. Construct Final Document
    doc = {
        "product_name": deal['product_name'][:200], # Limit length
        "sale_price": deal['sale_price'],
        "original_price": deal['original_price'],
        "discount_percentage": deal['discount_percentage'],
        "currency": deal.get('currency', 'INR'),
        "image_url": deal.get('image_url'),
        "original_link": link,
        "canonical_link": final_url,
        "affiliate_link": f"https://earnkaro.com/affiliate/conversion?url={final_url}", # TODO: Real API
        "source_text": description[:500],
        "status": "verified",
        "extracted_at": asyncio.get_event_loop().time(), # Or datetime.utcnow()
    }

    # 6. Atomic Upsert
    try:
        await deals_collection.update_one(
            {"original_link": link}, 
            {"$set": doc}, 
            upsert=True
        )
        return f"✅ Saved: {doc['product_name']} ({doc['discount_percentage']}% OFF)"
    except Exception as e:
        return f"💾 DB Error: {e}"

async def process_message(event):
    if not event.text: return
    links = extract_links(event.text)
    if not links: return

    segments = slice_text(event.text, links)
    tasks = [handle_single_deal(desc, link) for desc, link in segments]
    results = await asyncio.gather(*tasks)
    
    for r in results: print(r)
    
    # Update Checkpoint
    await state_collection.update_one(
        {'chat_id': event.chat_id}, 
        {'$set': {'last_id': event.id}}, 
        upsert=True
    )

# --- 4. RECOVERY & MAIN ---

async def recover_missed():
    print("🔄 Recovery Phase Started...")
    for chat in TARGET_GROUPS:
        state = await state_collection.find_one({'chat_id': chat})
        last_id = state['last_id'] if state else 0
        print(f"  Scanning {chat} from {last_id}...")
        async for msg in telegram_client.iter_messages(chat, min_id=last_id, limit=500): # Safety limit
            await process_message(msg)
    print("✅ Recovery Done. Live Mode Active.")

@telegram_client.on(events.NewMessage(chats=TARGET_GROUPS))
async def handler(event): await process_message(event)

async def main():
    await ensure_indexes()
    try: await mongo_client.admin.command('ping'); print("📡 MongoDB OK")
    except Exception as e: print(f"🚨 Mongo Fail: {e}"); return

    await recover_missed()
    print("🤖 Listening...")
    await telegram_client.run_until_disconnected()

with telegram_client:
    telegram_client.loop.run_until_complete(main())