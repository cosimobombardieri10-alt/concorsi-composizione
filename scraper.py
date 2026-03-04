#!/usr/bin/env python3
"""
Scraper settimanale — Concorsi di Composizione
Gira su GitHub Actions ogni lunedì e aggiorna index.html
"""

import json, re, time, os
from datetime import datetime, date
from bs4 import BeautifulSoup
import requests

# ─────────────────────────────────────────────
# HEADERS per sembrare un browser reale
# ─────────────────────────────────────────────
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# ─────────────────────────────────────────────
# FONTI DA SCRAPARE
# ─────────────────────────────────────────────
SOURCES = [
    {'url': 'https://www.musicalchairs.info/composer/competitions?sort=cd', 'parser': 'musicalchairs'},
    {'url': 'https://scorefol.io/opportunities',                            'parser': 'scorefolio'},
    {'url': 'https://live-composers.pantheonsite.io/',                      'parser': 'livecomposers'},
    {'url': 'https://composersforum.org/opportunities',                     'parser': 'acf'},
    {'url': 'http://www.cidim.it/cidim/content/314710',                     'parser': 'cidim'},
    {'url': 'https://iawm.org/snm-competition/',                            'parser': 'iawm'},
    {'url': 'https://nycemf.org/',                                          'parser': 'nycemf'},
]

# ─────────────────────────────────────────────
# MESI per parsing date
# ─────────────────────────────────────────────
MONTHS_EN = {
    'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
    'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
    'january':1,'february':2,'march':3,'april':4,'june':6,
    'july':7,'august':8,'september':9,'october':10,'november':11,'december':12
}
MONTHS_IT = {
    'gen':1,'feb':2,'mar':3,'apr':4,'mag':5,'giu':6,
    'lug':7,'ago':8,'set':9,'ott':10,'nov':11,'dic':12,
    'gennaio':1,'febbraio':2,'marzo':3,'aprile':4,'maggio':5,'giugno':6,
    'luglio':7,'agosto':8,'settembre':9,'ottobre':10,'novembre':11,'dicembre':12
}

def parse_date(text):
    """Tenta di estrarre una data dal testo. Ritorna oggetto date o None."""
    if not text:
        return None
    text = text.strip().lower()
    # Formato: 27 Mar 2026 / 27 March 2026
    m = re.search(r'(\d{1,2})\s+([a-z]+)\s+(20\d\d)', text)
    if m:
        d, mo, y = int(m.group(1)), m.group(2), int(m.group(3))
        month = MONTHS_EN.get(mo) or MONTHS_IT.get(mo)
        if month:
            try:
                return date(y, month, d)
            except ValueError:
                pass
    # Formato: March 27, 2026
    m = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(20\d\d)', text)
    if m:
        mo, d, y = m.group(1), int(m.group(2)), int(m.group(3))
        month = MONTHS_EN.get(mo)
        if month:
            try:
                return date(y, month, d)
            except ValueError:
                pass
    return None

def format_deadline(d):
    """Formatta data come '27 Mar 2026'"""
    months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    return f"{d.day} {months[d.month-1]} {d.year}"

def urgency(d):
    """Calcola urgenza dalla data."""
    if not d:
        return 'open'
    diff = (d - date.today()).days
    if diff < 0:
        return 'expired'
    if diff < 30:
        return 'hot'
    if diff < 90:
        return 'soon'
    return 'open'

def guess_category(text):
    """Indovina la categoria dalla descrizione."""
    t = text.lower()
    if re.search(r'electro|acousm|fixed.?media|dsp|computer.?music', t):
        return 'electro'
    if re.search(r'grant|fellowship|award|fund|prize', t):
        return 'grant'
    if re.search(r'orchestra|symphon|philharmon', t):
        return 'orch'
    if re.search(r'choir|choral|chorus|satb|a.?cappella', t):
        return 'choral'
    if re.search(r'wind.?band|brass.?band|fanfare|concert.?band', t):
        return 'mixed'
    if re.search(r'vocal|voice|soprano|tenor|mezzo|baritone|bass', t):
        return 'vocal'
    if re.search(r'\bsolo\b|piano\s+solo|violin\s+solo|flute\s+solo', t):
        return 'solo'
    return 'chamb'

def normalize_key(title):
    """Chiave di deduplicazione."""
    return re.sub(r'[^a-z0-9]', '', title.lower())[:45]

def fetch(url, timeout=25):
    """Scarica una pagina web."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  ⚠ Fetch fallito ({url[:60]}): {e}")
        return None

# ─────────────────────────────────────────────
# PARSER PER OGNI FONTE
# ─────────────────────────────────────────────

def parse_musicalchairs(html):
    """Parser per musicalchairs.info"""
    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()
    
    for a in soup.find_all('a', href=re.compile(r'/competitions/\d+')):
        title = a.get_text(strip=True)
        if len(title) < 10 or len(title) > 200:
            continue
        key = normalize_key(title)
        if key in seen:
            continue
        seen.add(key)
        
        href = a.get('href', '')
        link = href if href.startswith('http') else f'https://www.musicalchairs.info{href}'
        
        # Cerca la deadline nel contesto circostante
        row = a.find_parent(['tr', 'li', 'div', 'article']) or a.parent
        row_text = row.get_text(' ', strip=True) if row else ''
        
        dl_match = re.search(
            r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d\d)',
            row_text, re.IGNORECASE
        )
        deadline_str = dl_match.group(0) if dl_match else 'Verify deadline'
        dl_date = parse_date(deadline_str)
        
        if dl_date and dl_date < date.today():
            continue  # già scaduto
        
        is_free = bool(re.search(r'no\s+fee|free\s+entry|gratuito', row_text, re.IGNORECASE))
        
        results.append({
            'cat': guess_category(title + ' ' + row_text),
            'title': title,
            'org': 'Via Musical Chairs',
            'badge': 'Competition',
            'deadline': format_deadline(dl_date) if dl_date else deadline_str,
            'urgency': urgency(dl_date),
            'free': is_free,
            'flag': '🌍',
            'link': link,
            'prize': '',
            'forces': '',
            'age': '',
            'nationality': 'International',
            'notes': '',
            'source': 'musicalchairs'
        })
    
    print(f"  Musical Chairs: {len(results)} concorsi trovati")
    return results

def parse_generic(html, source_name, base_url=''):
    """Parser generico per siti con struttura heading + paragrafo."""
    soup = BeautifulSoup(html, 'lxml')
    results = []
    seen = set()
    
    # Prova sia h2 che h3 che h4
    for heading in soup.find_all(['h2', 'h3', 'h4']):
        title = heading.get_text(strip=True)
        if len(title) < 8 or len(title) > 180:
            continue
        
        # Salta intestazioni di navigazione comuni
        skip_words = ['menu', 'navigation', 'footer', 'header', 'search', 'contact',
                      'home', 'about', 'subscribe', 'newsletter', 'login', 'follow us']
        if any(w in title.lower() for w in skip_words):
            continue
        
        key = normalize_key(title)
        if key in seen:
            continue
        seen.add(key)
        
        # Contesto: sezione/articolo/div genitore
        container = heading.find_parent(['article', 'section', '.card', '.item', '.opportunity'])
        if not container:
            container = heading.parent
        
        ctx = container.get_text(' ', strip=True) if container else ''
        
        # Cerca deadline nel testo
        dl_match = re.search(
            r'(?:deadline|scadenza|entro il|closing date)[:\s]+([A-Za-z]+ \d{1,2},?\s*20\d\d|\d{1,2}\s+[A-Za-z]+\s+20\d\d)',
            ctx, re.IGNORECASE
        )
        if not dl_match:
            dl_match = re.search(
                r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d\d)',
                ctx, re.IGNORECASE
            )
        
        deadline_raw = dl_match.group(1) if dl_match else 'Verify deadline'
        dl_date = parse_date(deadline_raw)
        
        if dl_date and dl_date < date.today():
            continue  # scaduto
        
        # Cerca link
        link_el = container.find('a', href=True) if container else None
        if not link_el:
            link_el = heading.find('a', href=True)
        
        if link_el:
            href = link_el['href']
            if href.startswith('http'):
                link = href
            elif href.startswith('/'):
                link = base_url.rstrip('/') + href
            else:
                link = href
        else:
            continue  # senza link non è utile
        
        is_free = bool(re.search(r'no\s+fee|free\s+entry|gratuito|no\s+cost', ctx, re.IGNORECASE))
        
        # Cerca premio
        prize_match = re.search(r'(\$[\d,]+|€[\d,]+|£[\d,]+|¥[\d,]+|\d+\s*(?:USD|EUR|GBP))', ctx)
        prize = prize_match.group(0) if prize_match else ''
        
        results.append({
            'cat': guess_category(title + ' ' + ctx),
            'title': title,
            'org': source_name,
            'badge': 'Competition',
            'deadline': format_deadline(dl_date) if dl_date else deadline_raw,
            'urgency': urgency(dl_date),
            'free': is_free,
            'flag': '🌍',
            'link': link,
            'prize': prize,
            'forces': '',
            'age': '',
            'nationality': 'International',
            'notes': '',
            'source': source_name.lower().replace(' ', '')
        })
    
    print(f"  {source_name}: {len(results)} concorsi trovati")
    return results

# ─────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────

def scrape_all():
    """Scarica tutte le fonti e restituisce la lista completa."""
    all_results = []
    
    for src in SOURCES:
        print(f"→ Scarico {src['url'][:60]}...")
        html = fetch(src['url'])
        if not html:
            continue
        
        if src['parser'] == 'musicalchairs':
            results = parse_musicalchairs(html)
        elif src['parser'] == 'cidim':
            results = parse_generic(html, 'CIDIM', 'http://www.cidim.it')
        elif src['parser'] == 'acf':
            results = parse_generic(html, 'American Composers Forum', 'https://composersforum.org')
        elif src['parser'] == 'livecomposers':
            results = parse_generic(html, 'Live Composers', 'https://live-composers.pantheonsite.io')
        elif src['parser'] == 'scorefolio':
            results = parse_generic(html, 'Scorefolio', 'https://scorefol.io')
        elif src['parser'] == 'iawm':
            results = parse_generic(html, 'IAWM', 'https://iawm.org')
        elif src['parser'] == 'nycemf':
            results = parse_generic(html, 'NYCEMF', 'https://nycemf.org')
        else:
            results = parse_generic(html, src['parser'], src['url'])
        
        all_results.extend(results)
        time.sleep(2)  # pausa tra le richieste — rispettoso verso i server
    
    return all_results

def merge_with_baseline(scraped, baseline):
    """
    Unisce i dati dello scraping con il baseline fisso.
    - Baseline ha sempre priorità per i concorsi già presenti
    - Aggiunge solo concorsi genuinamente nuovi
    - Rimuove i concorsi scaduti
    """
    today = date.today()
    
    # Indice dei concorsi del baseline
    known_keys = set(normalize_key(c['title']) for c in baseline)
    
    # Filtra baseline: rimuovi scaduti
    active_baseline = []
    for c in baseline:
        dl = parse_date(c.get('deadline', ''))
        if dl and dl < today:
            continue  # scaduto
        active_baseline.append(c)
    
    # Aggiungi solo nuovi dal scraping
    new_items = []
    for c in scraped:
        key = normalize_key(c['title'])
        if key not in known_keys and len(key) >= 5:
            known_keys.add(key)
            new_items.append(c)
    
    total = active_baseline + new_items
    
    # Ordina: prima per urgenza (hot → soon → open), poi per deadline
    urgency_order = {'hot': 0, 'soon': 1, 'open': 2}
    def sort_key(c):
        u = urgency_order.get(c.get('urgency', 'open'), 2)
        dl = parse_date(c.get('deadline', ''))
        dl_ts = dl.toordinal() if dl else 99999
        return (u, dl_ts)
    
    total.sort(key=sort_key)
    
    print(f"\n📊 Risultato:")
    print(f"   Baseline attivi: {len(active_baseline)}")
    print(f"   Nuovi trovati:   {len(new_items)}")
    print(f"   Totale finale:   {len(total)}")
    
    return total

# ─────────────────────────────────────────────
# LEGGI BASELINE DA index.html
# ─────────────────────────────────────────────

def extract_baseline_from_html(html_path):
    """Estrae il BASELINE_DATA dal file index.html esistente."""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    marker = 'const BASELINE_DATA = '
    start = content.find(marker)
    if start == -1:
        print("  ⚠ BASELINE_DATA non trovato in index.html")
        return []
    
    start += len(marker)
    # Trova il ] di chiusura dell'array
    depth = 0
    i = start
    while i < len(content):
        if content[i] == '[':
            depth += 1
        elif content[i] == ']':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    
    try:
        data = json.loads(content[start:end])
        print(f"  Baseline estratto: {len(data)} concorsi")
        return data
    except json.JSONDecodeError as e:
        print(f"  ⚠ Errore parsing baseline: {e}")
        return []

# ─────────────────────────────────────────────
# AGGIORNA index.html
# ─────────────────────────────────────────────

def update_html(html_path, new_data):
    """Sostituisce BASELINE_DATA in index.html con i nuovi dati."""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    marker = 'const BASELINE_DATA = '
    start = content.find(marker)
    if start == -1:
        print("  ⚠ Impossibile aggiornare: marker non trovato")
        return False
    
    array_start = start + len(marker)
    depth = 0
    i = array_start
    while i < len(content):
        if content[i] == '[':
            depth += 1
        elif content[i] == ']':
            depth -= 1
            if depth == 0:
                array_end = i + 1
                break
        i += 1
    
    new_json = json.dumps(new_data, ensure_ascii=False, separators=(',', ':'))
    new_content = content[:array_start] + new_json + content[array_end:]
    
    # Aggiorna anche il timestamp di aggiornamento
    today_str = datetime.now().strftime('%d %B %Y')
    new_content = re.sub(
        r'(id="updDate">)[^<]*(</span>)',
        f'\\g<1>{today_str}\\g<2>',
        new_content
    )
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  ✓ index.html aggiornato ({len(new_data)} concorsi)")
    return True

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 55)
    print(f"  Scraper Concorsi — {datetime.now().strftime('%d %B %Y %H:%M')}")
    print("=" * 55)
    
    html_file = 'index.html'
    
    if not os.path.exists(html_file):
        print(f"  ⚠ {html_file} non trovato!")
        exit(1)
    
    print("\n1. Estrazione baseline da index.html...")
    baseline = extract_baseline_from_html(html_file)
    
    print("\n2. Scraping fonti online...")
    scraped = scrape_all()
    
    print("\n3. Fusione dati...")
    final_data = merge_with_baseline(scraped, baseline)
    
    print("\n4. Aggiornamento index.html...")
    success = update_html(html_file, final_data)
    
    if success:
        print("\n✅ Completato con successo!")
    else:
        print("\n❌ Aggiornamento fallito.")
        exit(1)
