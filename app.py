from dotenv import load_dotenv
load_dotenv()
import os, re, json, shutil, hashlib, textwrap, subprocess, requests, imageio_ffmpeg, streamlit as st
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title='VibeGood & PulseGoods Command Center', page_icon='⚡', layout='wide', initial_sidebar_state='expanded')

# --- CUSTOM PRO DARK-MODE SAAS UI STYLING ---
st.markdown("""
<style>
  .stApp { background-color: #0b0d12; color: #f3f4f6; }
  header[data-testid="stHeader"] { background: rgba(11, 13, 18, 0.85); }
  section[data-testid="stSidebar"] { background-color: #11141c; border-right: 1px solid #1f2430; }
  .hero-banner {
    background: linear-gradient(135deg, #141824 0%, #1a1f2e 100%);
    border: 1px solid #262d3d;
    border-radius: 16px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .hero-title { font-size: 1.65rem; font-weight: 800; margin: 0; color: #ffffff; }
  .hero-sub { color: #9ca3af; font-size: 0.92rem; margin-top: 4px; }
  .store-card-vg {
    background: linear-gradient(180deg, rgba(255,107,53,0.12) 0%, #131722 100%);
    border: 1px solid rgba(255,107,53,0.4);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
  }
  .store-card-pg {
    background: linear-gradient(180deg, rgba(0,180,255,0.12) 0%, #131722 100%);
    border: 1px solid rgba(0,180,255,0.4);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
  }
  .kpi-box {
    background: #131722;
    border: 1px solid #222836;
    border-radius: 12px;
    padding: 0.9rem 1.1rem;
    text-align: center;
  }
  .kpi-num { font-size: 1.45rem; font-weight: 800; color: #fff; }
  .kpi-lbl { font-size: 0.75rem; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }
  div.stButton > button {
    border-radius: 10px;
    font-weight: 700;
    padding: 0.65rem 1rem;
    border: 1px solid #2d3548;
  }
</style>
""", unsafe_allow_html=True)

SEO_KEYWORDS = 'home decor, pet toys, trending products, gift ideas, wedding gifts, aesthetic room decor, viral gadgets, unique gifts, interactive cat toys, smart home accessories, TikTok trending finds, housewarming gifts'

STORES = {
    'vibegood': {
        'domain': 'vibegood.shop',
        'folder': 'stores/vibegood',
        'logo': 'vibegoodlogo.jpg',
        'accent': '#ff6b35',
        'accent2': '#ff9f1c',
        'card_class': 'store-card-vg',
        'badge_text': 'COZY HOME DECOR & LIFESTYLE',
        'keywords': ['led flame diffuser', 'led vanity mirror', 'desk lamp', 'car ambient light', 'facial massager'],
        'tone': 'cozy, aesthetic, mood-boosting, high-CTR lifestyle'
    },
    'pulsesupply': {
        'domain': 'pulsegoods.co',
        'folder': 'stores/pulsesupply',
        'logo': 'pulsegoodslogo.jpg',
        'accent': '#00b4ff',
        'accent2': '#00e5ff',
        'card_class': 'store-card-pg',
        'badge_text': 'VIRAL GADGETS, KITCHEN & PET TECH',
        'keywords': ['mini portable blender', 'electric frother', 'rc stunt car', 'smart cat toy', 'mini thermal printer'],
        'tone': 'punchy, clever, problem-solving, viral TikTok gadget'
    }
}

for k, cfg in STORES.items():
    for sub in ['final_products', 'post_queue', 'products', 'api']:
        os.makedirs(f"{cfg['folder']}/{sub}", exist_ok=True)

# --- SIDEBAR ---
st.sidebar.markdown("### ⚙️ Engine & API Keys")
cj_email = st.sidebar.text_input('CJdropshipping Email', value=os.getenv('CJ_EMAIL', ''), placeholder='you@email.com')
cj_api_key = st.sidebar.text_input('CJ API Key', type='password', value=os.getenv('CJ_API_KEY', ''), placeholder='Paste CJ API Key')
ai_mode = st.sidebar.selectbox('AI Copy & SEO Writer', ['Built-In Smart Template ($0)', 'Local Ollama (Offline/$0)', 'Gemini Free API Key'])
gemini_key = st.sidebar.text_input('Gemini API Key', type='password') if 'Gemini' in ai_mode else ''

st.sidebar.divider()
st.sidebar.markdown("### 🧹 Auto-Prune Slow Sellers")
max_days_no_sale = st.sidebar.slider('Remove 0-sale items after (days)', 1, 30, 7)
auto_prune_on_open = st.sidebar.checkbox('Auto-remove slow sellers on startup', value=True)

st.sidebar.divider()
st.sidebar.markdown("### ▲ Vercel & Social Auto-Post")
auto_git_push = st.sidebar.checkbox('Auto git push to Vercel on SELL', value=False)
auto_webhook = st.sidebar.text_input('Make / n8n Webhook URL', placeholder='https://make.com...')

def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:50] or 'product'

def get_next_prime_time():
    now = datetime.now()
    for h in (11, 15, 19, 21):
        candidate = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate > now + timedelta(minutes=15):
            return candidate
    return (now + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)

def load_catalog(store_key):
    path = f"{STORES[store_key]['folder']}/catalog.json"
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_catalog(store_key, items):
    path = f"{STORES[store_key]['folder']}/catalog.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2)

def git_deploy(msg):
    try:
        subprocess.run(['git', 'add', '.'], check=True)
        subprocess.run(['git', 'commit', '-m', msg], check=True)
        subprocess.run(['git', 'push'], check=True)
        return 'Deployed live to Vercel!'
    except Exception as e:
        return f'Saved locally (Git skipped: {e})'

def render_product_page_html(store_key, item):
    cfg = STORES[store_key]
    year = datetime.now().year
    slug = item.get('slug') or slugify(item['copy']['headline'])
    bullets = ''.join([f'<li>{b}</li>' for b in item['copy']['bullets']])
    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1.0' />
  <title>{item['copy']['headline']} | {cfg['domain']}</title>
  <meta name='description' content='{item['copy']['meta_description']}' />
  <meta name='keywords' content='{item['copy']['seo_keywords']}, {SEO_KEYWORDS}' />
  <meta name='robots' content='index, follow, max-image-preview:large' />
  <link rel='canonical' href='https://{cfg['domain']}/products/{slug}.html' />
  <meta name='copyright' content='Copyright {year} {cfg['domain']}. All rights reserved. Registry ID: {item['copyright_id']}' />
  <meta property='og:title' content='{item['copy']['headline']} — {cfg['domain']}' />
  <meta property='og:description' content='{item['copy']['meta_description']}' />
  <meta property='og:image' content='{item['product']['image']}' />
  <meta property='og:url' content='https://{cfg['domain']}/products/{slug}.html' />
  <meta property='og:type' content='product' />
  <meta name='twitter:card' content='summary_large_image' />
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    body {{ background: #101216; color: #f4f4f6; line-height: 1.6; }}
    .bar {{ background: linear-gradient(90deg, {cfg['accent']}, {cfg['accent2']}); color: #101216; text-align: center; font-weight: 800; padding: 10px; font-size: 0.85rem; }}
    header {{ text-align: center; padding: 1.5rem 1rem; border-bottom: 1px solid #232730; }}
    header a {{ color: #f4f4f6; text-decoration: none; font-size: 1.7rem; font-weight: 800; }}
    header img {{ height: 50px; border-radius: 10px; vertical-align: middle; margin-right: 10px; }}
    .wrap {{ max-width: 880px; margin: 2.5rem auto; padding: 0 1.25rem; display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 2rem; align-items: center; }}
    .wrap img {{ width: 100%; border-radius: 16px; border: 1px solid #262a34; }}
    .badge {{ display: inline-block; background: rgba(255,255,255,0.08); color: {cfg['accent2']}; font-size: 0.75rem; font-weight: 700; padding: 4px 10px; border-radius: 999px; margin-bottom: 12px; }}
    h1 {{ font-size: 1.8rem; line-height: 1.25; margin-bottom: 0.75rem; }}
    .price {{ font-size: 1.75rem; font-weight: 800; margin-bottom: 1rem; }}
    .compare {{ color: #8e95a5; text-decoration: line-through; font-size: 1.05rem; margin-left: 8px; }}
    ul {{ padding-left: 1.2rem; color: #d4d8e2; margin-bottom: 1.5rem; }}
    .btn {{ display: block; text-align: center; background: linear-gradient(90deg, {cfg['accent']}, {cfg['accent2']}); color: #101216; font-weight: 800; padding: 1rem; border-radius: 10px; text-decoration: none; }}
    .back {{ display: inline-block; margin-top: 1rem; color: #8e95a5; text-decoration: none; font-size: 0.9rem; }}
    footer {{ text-align: center; padding: 2rem 1rem; color: #8e95a5; font-size: 0.82rem; border-top: 1px solid #232730; margin-top: 3rem; }}
  </style>
</head>
<body>
  <div class='bar'>FAST 2–5 DAY US SHIPPING • 30-DAY MONEY-BACK GUARANTEE</div>
  <header>
    <a href='../index.html'><img src='../{cfg['logo']}' alt='{cfg['domain']}' onerror='this.style.display="none"' />{cfg['domain']}</a>
  </header>
  <main class='wrap'>
    <img src='{item['product']['image']}' alt='{item['copy']['headline']}' />
    <div>
      <span class='badge'>IN STOCK • SHIPS FROM US</span>
      <h1>{item['copy']['headline']}</h1>
      <div class='price'>${item['product']['retail']:.2f} <span class='compare'>${item['product']['compare']:.2f}</span></div>
      <ul>{bullets}</ul>
      <a href='{item['square_link']}' class='btn' target='_blank' rel='noopener'>Buy Now — ${item['product']['retail']:.2f}</a>
      <a href='../index.html' class='back'>← View All Trending Finds on {cfg['domain']}</a>
    </div>
  </main>
© {year} {cfg['domain']}. All Rights Reserved. Protected Copy & Metadata (SHA-256: {item['copyright_id']}).

"""
def update_sitemap_xml(store_key, items):
    cfg = STORES[store_key]
    today = datetime.now().strftime('%Y-%m-%d')
    urls = [f"  <url><loc>https://{cfg['domain']}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for item in items:
        slug = item.get('slug') or slugify(item['copy']['headline'])
        urls.append(f"  <url><loc>https://{cfg['domain']}/products/{slug}.html</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>")
    xml = "<?xml version='1.0' encoding='UTF-8'?>\n<urlset xmlns='http://sitemaps.org'>\n" + "\n".join(urls) + "\n</urlset>"
    with open(f"{cfg['folder']}/sitemap.xml", 'w', encoding='utf-8') as sf:
        sf.write(xml)

def rebuild_full_storefront(store_key, items):
cfg = STORES[store_key]
prod_dir = f"{cfg['folder']}/products"
active_slugs = set()
for item in items:
slug = item.get('slug') or slugify(item['copy']['headline'])
item['slug'] = slug
active_slugs.add(f'{slug}.html')
with open(f'{prod_dir}/{slug}.html', 'w', encoding='utf-8') as pf:
pf.write(render_product_page_html(store_key, item))
for fn in os.listdir(prod_dir):
if fn not in active_slugs:
os.remove(os.path.join(prod_dir, fn))
year = datetime.now().year
if not items:
main_section = f"""
Curated Home Decor, Pet Toys, Trending Products & Unique Gift Ideas
Discover viral home decor, cozy lighting, interactive pet toys, trending gadgets, gift ideas, and wedding gifts at {cfg['domain']}. Fast 2–5 day US warehouse delivery.

Home DecorPet ToysTrending ProductsGift IdeasWedding Gifts

"""
else:
cards_html = ''
for item in reversed(items):
slug = item['slug']
bullets = ''.join([f'{b}' for b in item['copy']['bullets']])
cards_html += f"""


<img src='{item['product']['image']}' alt='{item['copy']['headline']}' />

US WAREHOUSE • 2–5 DAY DELIVERY
{item['copy']['headline']}
${item['product']['retail']:.2f} ${item['product']['compare']:.2f}
{bullets}



<a href='{item['square_link']}' class='btn' target='_blank' rel='noopener'>Buy Now — ${item['product']['retail']:.2f}
View Full Details →

"""
main_section = f"{cards_html}"
desc = f"Shop viral home decor, pet toys, trending products, gift ideas, and wedding gifts at {cfg['domain']}. Fast 2-5 day US shipping."
index_html = f"""




{cfg['domain']} | Home Decor, Pet Toys, Trending Products & Gift Ideas

<meta name='keywords' content='{SEO_KEYWORDS}, {cfg['domain']}' />
* {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
body {{ background: #101216; color: #f4f4f6; line-height: 1.5; }}
.bar {{ background: linear-gradient(90deg, {cfg['accent']}, {cfg['accent2']}); color: #101216; text-align: center; font-weight: 800; padding: 10px; font-size: 0.85rem; }}
header {{ text-align: center; padding: 2rem 1rem; border-bottom: 1px solid #232730; }}
header img {{ height: 64px; border-radius: 12px; vertical-align: middle; margin-right: 12px; }}
.brand {{ font-size: 1.9rem; font-weight: 800; vertical-align: middle; }}
.hero {{ max-width: 780px; margin: 3.5rem auto; padding: 2.5rem 1.5rem; background: #181b22; border: 1px solid #262a34; border-radius: 18px; text-align: center; }}
.hero h1 {{ font-size: 1.85rem; margin-bottom: 1rem; }}
.hero p {{ color: #a1a1aa; font-size: 1rem; margin-bottom: 1.5rem; }}
.tags {{ display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center; }}
.tag {{ background: rgba(255,255,255,0.06); color: {cfg['accent2']}; font-size: 0.8rem; font-weight: 700; padding: 6px 14px; border-radius: 999px; }}
.grid {{ max-width: 1060px; margin: 2.5rem auto; padding: 0 1.25rem; display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 2rem; }}
.card {{ background: #181b22; border: 1px solid #262a34; border-radius: 16px; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between; }}
.card img {{ width: 100%; height: 290px; object-fit: cover; }}
.body {{ padding: 1.5rem; }}
.badge {{ display: inline-block; background: rgba(255,255,255,0.08); color: {cfg['accent2']}; font-size: 0.72rem; font-weight: 700; padding: 4px 10px; border-radius: 999px; margin-bottom: 10px; }}
.price {{ font-size: 1.55rem; font-weight: 800; margin: 0.5rem 0 1rem; }}
.compare {{ color: #8e95a5; text-decoration: line-through; font-size: 0.95rem; margin-left: 8px; }}
ul {{ padding-left: 1.2rem; color: #d4d8e2; font-size: 0.92rem; line-height: 1.6; }}
.btn {{ display: block; text-align: center; background: linear-gradient(90deg, {cfg['accent']}, {cfg['accent2']}); color: #101216; font-weight: 800; padding: 0.95rem; border-radius: 10px; text-decoration: none; }}
footer {{ text-align: center; padding: 2rem 1rem; color: #8e95a5; font-size: 0.82rem; border-top: 1px solid #232730; margin-top: 3rem; }}



FAST 2–5 DAY US SHIPPING • 30-DAY MONEY-BACK GUARANTEE
<img src='{cfg['logo']}' alt='{cfg['domain']} logo' />
{cfg['domain']}

{main_section}
© {year} {cfg['domain']}. All Rights Reserved. • Home Decor, Pet Toys, Trending Products & Gift Ideas.

"""
with open(f"{cfg['folder']}/index.html", 'w', encoding='utf-8') as f:
f.write(index_html)
    update_sitemap_xml(store_key, items)
def prune_slow_sellers(store_key, days_limit):
catalog = load_catalog(store_key)
if not catalog:
return 0
cutoff = datetime.now() - timedelta(days=days_limit)
kept = [x for x in catalog if not (x.get('sales_count', 0) == 0 and datetime.fromisoformat(x.get('listed_at', datetime.now().isoformat())) < cutoff)]
removed = len(catalog) - len(kept)
if removed > 0:
save_catalog(store_key, kept)
rebuild_full_storefront(store_key, kept)
return removed
@st.cache_data(ttl=3600)
def get_cj_token(email, api_key):
if not email or not api_key:
return None
res = requests.post('cjdropshipping.com', json={'email': email, 'apiKey': api_key}, timeout=15).json()
return res.get('data', {}).get('accessToken')
def resolve_cj_variant_id(token, pid):
try:
res = requests.get('cjdropshipping.com', headers={'CJ-Access-Token': token}, params={'pid': pid}, timeout=15).json()
variants = res.get('data', {}).get('variants', [])
if variants:
return variants[0].get('vid') or pid
except Exception:
pass
return pid
def fetch_best_us_product(token, keywords, existing_pids):
if not token:
return None
headers = {'CJ-Access-Token': token}
for kw in keywords:
res = requests.get('cjdropshipping.com', headers=headers, params={'productNameEn': kw, 'countryCode': 'US', 'pageNum': 1, 'pageSize': 10}, timeout=15).json()
for item in res.get('data', {}).get('list', []):
pid = item.get('pid')
if pid and pid not in existing_pids:
vid = resolve_cj_variant_id(token, pid)
cost = float(str(item.get('sellPrice', '8.99')).split('-')[0].strip())
retail = float(f'{int(max(cost * 3.2, 22.99))}.99')
return {'pid': pid, 'vid': vid, 'name': item.get('productNameEn'), 'image': item.get('productImage'), 'cost': cost, 'retail': retail, 'compare': round(retail * 1.45, 2), 'category': kw}
return None
def generate_ai_assets(product, store_cfg):
prompt = f"Product: {product['name']} (Retail: ${product['retail']}) | Store: {store_cfg['domain']} | Tone: {store_cfg['tone']}. Return strictly JSON with keys: headline, meta_description (155 chars SEO), seo_keywords (comma string), bullets (list of 4), tiktok_hook, caption, hashtags (max 5)."
if 'Ollama' in ai_mode:
try:
r = requests.post('http://localhost:11434/api/generate', json={'model': 'llama3', 'prompt': prompt, 'format': 'json', 'stream': False}, timeout=25)
return json.loads(r.json()['response'])
except Exception:
pass
elif 'Gemini' in ai_mode and gemini_key:
try:
r = requests.post(f'googleapis.com{gemini_key}', json={'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'responseMimeType': 'application/json'}}, timeout=20)
return json.loads(r.json()['candidates'][0]['content']['parts'][0]['text'])
except Exception:
pass
return {
'headline': product['name'][:52],
'meta_description': f"Shop {product['name'][:55]} at {store_cfg['domain']} — top trending products, home decor, pet toys, gift ideas & wedding gifts with fast US shipping.",
'seo_keywords': f"{product['category']}, {SEO_KEYWORDS}, {store_cfg['domain']}",
'bullets': ['Fast 2-5 business day US warehouse delivery', 'Sleek, space-saving design built for everyday use', 'Perfect for home decor, trending gifts & daily upgrades', 'Backed by our 30-day satisfaction guarantee'],
'tiktok_hook': f"POV: You upgraded your setup for under ${int(product['retail']) + 1}",
'caption': f"The {product['category']} everyone is talking about. Fast US shipping at {store_cfg['domain']}",
'hashtags': '#tiktokmademebuyit #viralproducts #homedecor #giftideas #usshipping'
}
def create_vertical_reel(image_url, hook_text, domain, out_mp4):
canvas = Image.new('RGB', (1080, 1920), (16, 18, 22))
try:
resp = requests.get(image_url, timeout=15)
prod_img = Image.open(BytesIO(resp.content)).convert('RGB').resize((920, 920))
canvas.paste(prod_img, (80, 480))
except Exception:
pass
draw = ImageDraw.Draw(canvas)
try:
font_big = ImageFont.truetype('arialbd.ttf', 56)
font_cta = ImageFont.truetype('arialbd.ttf', 48)
except Exception:
font_big = font_cta = ImageFont.load_default()
wrapped_hook = '\n'.join(textwrap.wrap(hook_text, width=26))
draw.rounded_rectangle([(60, 160), (1020, 420)], radius=30, fill=(28, 32, 40))
draw.multiline_text((540, 290), wrapped_hook, fill=(255, 255, 255), font=font_big, anchor='mm', align='center')
draw.rounded_rectangle([(120, 1480), (960, 1620)], radius=30, fill=(255, 107, 53))
draw.text((540, 1550), f'Shop Now -> {domain}', fill=(16, 18, 22), font=font_cta, anchor='mm')
frame_path = out_mp4.replace('.mp4', '_frame.png')
canvas.save(frame_path)
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ffmpeg_exe, '-y', '-loop', '1', '-i', frame_path, '-vf', 'zoompan=z="min(zoom+0.0012,1.15)":d=168:s=1080x1920:fps=24', '-c:v', 'libx264', '-t', '7', '-pix_fmt', 'yuv420p', out_mp4], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if auto_prune_on_open and 'pruned_once' not in st.session_state:
total_pruned = sum(prune_slow_sellers(sk, max_days_no_sale) for sk in STORES)
st.session_state['pruned_once'] = True
if total_pruned > 0 and auto_git_push:
git_deploy(f'Auto-remove {total_pruned} slow-selling items')

--- TOP HERO BANNER ---

token = get_cj_token(cj_email, cj_api_key)
api_status = "🟢 CJ API Connected" if token else "🟡 Demo Mode (Add CJ API Key in Left Sidebar)"
next_post = get_next_prime_time().strftime('%I:%M %p')
st.markdown(f"""


⚡ Dual-Store Dropship & Traffic Command Center
vibegood.shop & pulsegoods.co • Auto-SEO Pages • Square Fulfillment • Prime-Time Reel Generator


{api_status}
Next Prime Post Window: {next_post}


""", unsafe_allow_html=True)
col1, col2 = st.columns(2, gap="large")
for idx, (store_key, cfg) in enumerate(STORES.items()):
with (col1 if idx == 0 else col2):
catalog = load_catalog(store_key)
total_sales = sum(x.get('sales_count', 0) for x in catalog)
st.markdown(f"""

{cfg['badge_text']}
{cfg['domain']}

""", unsafe_allow_html=True)
k1, k2, k3 = st.columns(3)
k1.markdown(f"{len(catalog)}Live Pages", unsafe_allow_html=True)
k2.markdown(f"{total_sales}Orders", unsafe_allow_html=True)
k3.markdown(f"2–5dUS Ship", unsafe_allow_html=True)
st.write("")
sq_link = st.text_input(f"Square Payment Link ({cfg['domain']})", value='square.link', key=f'sq_{store_key}')
staging_dir = f"{cfg['folder']}/final_products"
staged_meta_path = f'{staging_dir}/staged_package.json'
if st.button(f"⚡ Generate & Stage Best US Product ({cfg['domain']})", key=f'gen_{store_key}', use_container_width=True):
with st.spinner('Scanning CJ US warehouse, writing SEO copy & rendering 1080x1920 Reel...'):
existing_pids = {x['product']['pid'] for x in catalog}
prod = fetch_best_us_product(token, cfg['keywords'], existing_pids) if token else {
'pid': f'DEMO-{len(catalog)+1}', 'vid': f'DEMO-VID-{len(catalog)+1}',
'name': f"Trending {cfg['keywords'][len(catalog)%len(cfg['keywords'])].title()}",
'image': 'placehold.co',
'cost': 7.50, 'retail': 29.99, 'compare': 44.99, 'category': cfg['keywords'][0]
}
copy_data = generate_ai_assets(prod, cfg)
year = datetime.now().year
c_hash = hashlib.sha256(f"{cfg['domain']}|{copy_data['headline']}|{year}".encode()).hexdigest()[:16].upper()
slug = slugify(copy_data['headline'])
pkg = {
'store': store_key, 'domain': cfg['domain'], 'slug': slug,
'listed_at': datetime.now().isoformat(), 'sales_count': 0,
'product': prod, 'copy': copy_data, 'square_link': sq_link,
'copyright_id': c_hash,
'staged_html': f'{staging_dir}/review_sales_page.html',
'staged_mp4': f'{staging_dir}/staged_reel.mp4'
}
with open(pkg['staged_html'], 'w', encoding='utf-8') as f:
f.write(render_product_page_html(store_key, pkg))
create_vertical_reel(prod['image'], copy_data['tiktok_hook'], cfg['domain'], pkg['staged_mp4'])
with open(staged_meta_path, 'w', encoding='utf-8') as f:
json.dump(pkg, f, indent=2)
st.rerun()
if os.path.exists(staged_meta_path):
with open(staged_meta_path, 'r', encoding='utf-8') as f:
pkg = json.load(f)
st.info(f"📂 Staged File: {os.path.abspath(pkg['staged_html'])}")
tab_prev, tab_vid, tab_seo = st.tabs(["🖥️ Sales Page Preview", "🎬 Auto-Generated Reel", "🔍 SEO & Copyright"])
with tab_prev:
with open(pkg['staged_html'], 'r', encoding='utf-8') as hf:
st.components.v1.html(hf.read(), height=420, scrolling=True)
with tab_vid:
if os.path.exists(pkg['staged_mp4']):
st.video(pkg['staged_mp4'])
st.caption(f"Hook: {pkg['copy']['tiktok_hook']} | Tags: {pkg['copy']['hashtags']}")
with tab_seo:
st.write(f"Slug: /products/{pkg['slug']}.html")
st.write(f"Meta Description: {pkg['copy']['meta_description']}")
st.write(f"CJ Variant ID: {pkg['product'].get('vid')} | Profit Margin: ${pkg['product']['retail'] - pkg['product']['cost']:.2f}")
st.code(f"Copyright © {datetime.now().year} {cfg['domain']} | SHA-256: {pkg['copyright_id']}")
b_sell, b_del = st.columns(2)
if b_sell.button(f"✅ SELL (Publish to {cfg['domain']})", key=f'sell_{store_key}', use_container_width=True):
pkg['listed_at'] = datetime.now().isoformat()
catalog.append(pkg)
save_catalog(store_key, catalog)
rebuild_full_storefront(store_key, catalog)
prime_dt = get_next_prime_time()
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
queued_mp4 = f"{cfg['folder']}/post_queue/post_{ts}.mp4"
if os.path.exists(pkg['staged_mp4']):
shutil.copy(pkg['staged_mp4'], queued_mp4)
payload = {
'domain': cfg['domain'], 'product_url': f"https://{cfg['domain']}/products/{pkg['slug']}.html",
'scheduled_prime_time': prime_dt.strftime('%Y-%m-%d %I:%M %p'),
'product_title': pkg['copy']['headline'], 'retail_price': pkg['product']['retail'],
'cj_vid': pkg['product'].get('vid'), 'hook': pkg['copy']['tiktok_hook'],
'caption': pkg['copy']['caption'], 'hashtags': pkg['copy']['hashtags'],
'video_file': os.path.abspath(queued_mp4)
}
with open(f"{cfg['folder']}/post_queue/post_{ts}.json", 'w', encoding='utf-8') as pf:
json.dump(payload, pf, indent=2)
if auto_webhook:
try:
requests.post(auto_webhook, json=payload, timeout=10)
except Exception:
pass
deploy_status = git_deploy(f"Publish {pkg['copy']['headline']} to {cfg['domain']}") if auto_git_push else 'Saved locally'
for fn in os.listdir(staging_dir):
os.remove(os.path.join(staging_dir, fn))
st.success(f"🚀 Live on {cfg['domain']} | {deploy_status} | Next Prime Post: {prime_dt.strftime('%I:%M %p')}")
if b_del.button("🗑️ DELETE (Discard)", key=f'del_{store_key}', use_container_width=True):
for fn in os.listdir(staging_dir):
os.remove(os.path.join(staging_dir, fn))
st.rerun()
if catalog:
with st.expander(f"📦 Manage Live Products ({len(catalog)})"):
if st.button(f"🧹 Remove Slow Sellers Now (0 sales > {max_days_no_sale}d)", key=f'prune_{store_key}'):
removed = prune_slow_sellers(store_key, max_days_no_sale)
if removed and auto_git_push:
git_deploy(f"Prune {removed} slow sellers on {cfg['domain']}")
st.rerun()
for i, live_item in enumerate(catalog):
c_name, c_rm = st.columns([4, 1])
c_name.write(f"{i+1}. {live_item['copy']['headline']} (${live_item['product']['retail']:.2f}) • Sales: {live_item.get('sales_count', 0)}")
if c_rm.button("Remove", key=f'rm_{store_key}_{i}'):
catalog.pop(i)
save_catalog(store_key, catalog)
rebuild_full_storefront(store_key, catalog)
if auto_git_push:
git_deploy(f"Remove item from {cfg['domain']}")
st.rerun()



