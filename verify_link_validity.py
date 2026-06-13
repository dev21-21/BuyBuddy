import os
import re
import json
import asyncio
import random
import httpx # Asynchronous requests
import google.generativeai as genai
from pymongo import MongoClient
from telethon import TelegramClient, events
from dotenv import load_dotenv

# 1. Setup and Config
load_dotenv()
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MONGO_URI = os.getenv('MONGO_URI')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

mongo_client = MongoClient(MONGO_URI)
db = mongo_client['deal_db']
deals_collection = db['deals']
state_collection = db['channel_state']

TARGET_GROUPS = [
  -1001659536566,
  -1001334236392,
  -1002324044471,
  -1001391583159,
  -1002891052461,
  -1002865773247,
  -1001201589228,
  -1001486606418
]
client = TelegramClient('deal_session', API_ID, API_HASH)

# -------------------------------------------------------------------------
# VALIDATION LAYER (The "Filter")
# -------------------------------------------------------------------------

async def verify_link_validity(url):
    async with semaphore:
        user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"]
        death_keywords = ["out of stock", "sold out", "unavailable", "product not found"]
        
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as async_client:
                headers = {"User-Agent": random.choice(user_agents)}
                response = await async_client.get(url, headers=headers)
                
                print(f"🔍 Checking {url} | Status: {response.status_code}") # DEBUG LOG
                
                if response.status_code >= 400:
                    return False, f"HTTP Error {response.status_code}"
                
                content = response.text.lower()
                for keyword in death_keywords:
                    if keyword in content:
                        return False, f"Found keyword: {keyword}"
                
                return True, "Valid"
        except Exception as e:
            return False, f"Connection Error: {str(e)}"

# -------------------------------------------------------------------------
# PIPELINE TOOLS
# -------------------------------------------------------------------------

def extract_all_links(text):
    url_pattern = r'https?://[^\s]+'
    return [link for link in re.findall(url_pattern, text) if 't.me/' not in link and 'wa.me' not in link]

def slice_text_by_links(text, links):
    segments = []
    remaining_text = text
    for link in links:
        parts = remaining_text.split(link, 1)
        segments.append((parts[0].strip(), link))
        remaining_text = parts[1] if len(parts) > 1 else ""
    return segments

async def ai_parse_deal(text):
    prompt = f"Analyze this deal text and return ONLY a JSON object with keys: product_name, discount_percentage (number), current_price, original_price, currency. Text: {text}"
    try:
        response = model.generate_content(prompt)
        print(f"🤖 AI Response for text [{text[:30]}...]: {response.text}") # DEBUG LOG
        
        text_response = response.text.strip()
        start_index = text_response.find('{')
        end_index = text_response.rfind('}')
        
        if start_index != -1 and end_index != -1:
            json_text = text_response[start_index:end_index+1]
            return json.loads(json_text)
        return None
    except Exception as e:
        print(f"❌ AI JSON Error: {e}")
        return None
async def process_message(event):
    text = event.text
    if not text: return

    links = extract_all_links(text)
    if not links: return

    deal_segments = slice_text_by_links(text, links)
    
    for description, link in deal_segments:
        # --- STEP 1: Verify if link is still valid BEFORE processing ---
        is_valid, reason = await verify_link_validity(link)
        if not is_valid:
            print(f"❌ Skipping Expired Deal: {link} (Reason: {reason})")
            continue

        # --- STEP 2: AI Parsing ---
        deal_data = await ai_parse_deal(description)
        if deal_data:
            deal_data['original_link'] = link
            deal_data['affiliate_link'] = f"https://earnkaro.com/affiliate/conversion?url={link}"
            deals_collection.update_one({'original_link': link}, {'$set': deal_data}, upsert=True)
            print(f"✅ Saved Valid Deal: {deal_data['product_name']}")

    # UPDATE CHECKPOINT
    chat_id = event.chat_id
    state_collection.update_one({'chat_id': chat_id}, {'$set': {'last_id': event.id}}, upsert=True)

# -------------------------------------------------------------------------
# RECOVERY & MAIN
# -------------------------------------------------------------------------

async def recover_missed_messages():
    print("\n🔄 Starting Recovery Phase with Validation...")
    for chat in TARGET_GROUPS:
        state = state_collection.find_one({'chat_id': chat})
        last_id = state['last_id'] if state else 0
        print(f"Checking {chat} from ID {last_id}...")
        async for message in client.iter_messages(chat, min_id=last_id):
            await process_message(message)
    print("✅ Recovery Complete.\n")

@client.on(events.NewMessage(chats=TARGET_GROUPS))
async def my_event_handler(event):
    await process_message(event)

async def main():
    await recover_missed_messages()
    print("Bot is now listening for deals... (Press Ctrl+C to stop)")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())