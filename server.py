#!/usr/bin/env python3
"""
server.py
=========
Web-Frontend für JobScraper. Startet per Klick, zeigt einen
(nicht ganz ernst gemeinten) Fortschrittsbalken und öffnet die
Ergebnisse automatisch.

Starten:
    source .venv/bin/activate
    pip install flask
    python3 server.py
    → http://localhost:5001
"""

import json
import queue
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, redirect, request, send_file

# Import scraper functions directly – no subprocess needed
sys.path.insert(0, str(Path(__file__).parent))
from JobScraper import (
    scrape, filter_jobs, save_csv, save_json, generate_html,
)

app = Flask(__name__)

FILT_DIR = Path("filtered_results")
RAW_DIR  = Path("results")
_run_lock = threading.Lock()


# ── Start-Seite ───────────────────────────────────────────────────────────────
START_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JobScraper — Starte die Suche</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,700;0,9..144,900;1,9..144,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --cream:#F5F0E8; --ink:#1A1510; --rust:#C4502A; --sage:#5A7A5A;
    --gold:#C9974A; --sand:#E8DEC8; --mist:#D4CFC5; --card:#FDFAF4;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--cream);color:var(--ink);font-family:'DM Sans',sans-serif;
       font-weight:300;min-height:100vh;display:flex;flex-direction:column}

  /* grain */
  body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:999;opacity:.5;
    background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E")}

  header{padding:4rem 5vw 3rem;border-bottom:1px solid var(--mist)}
  .eyebrow{font-size:.72rem;letter-spacing:.25em;text-transform:uppercase;
           color:var(--rust);font-weight:500;margin-bottom:1rem;
           animation:fadeUp .5s ease forwards}
  h1{font-family:'Fraunces',serif;font-size:clamp(2.5rem,7vw,6rem);
     font-weight:900;line-height:.95;letter-spacing:-.03em;
     animation:fadeUp .6s ease .1s both}
  h1 em{font-style:italic;font-weight:300;color:var(--rust)}
  .subtitle{margin-top:1.2rem;color:#6B6155;font-size:.95rem;
            animation:fadeUp .6s ease .2s both}

  /* form card */
  .card{background:var(--card);border:1px solid var(--mist);border-radius:6px;
        padding:2.5rem;max-width:520px;margin:3rem 5vw;
        animation:fadeUp .6s ease .3s both;box-shadow:0 4px 24px rgba(26,21,16,.06)}
  .field{margin-bottom:1.5rem}
  .field label{display:block;font-size:.72rem;letter-spacing:.2em;
               text-transform:uppercase;color:var(--rust);font-weight:500;
               margin-bottom:.5rem}
  .field input{width:100%;padding:.65rem 1rem;border:1px solid var(--mist);
               background:var(--cream);border-radius:4px;font-family:'DM Sans',sans-serif;
               font-size:.95rem;color:var(--ink);outline:none;transition:border-color .2s}
  .field input:focus{border-color:var(--rust)}
  .field .hint{font-size:.72rem;color:#9A8E82;margin-top:.35rem}

  #start-btn{width:100%;padding:1rem;background:var(--ink);color:var(--cream);
             border:none;border-radius:4px;font-family:'Fraunces',serif;
             font-size:1.15rem;font-weight:700;cursor:pointer;
             transition:background .2s,transform .15s;letter-spacing:-.01em}
  #start-btn:hover{background:var(--rust);transform:translateY(-2px)}
  #start-btn:disabled{background:var(--mist);cursor:default;transform:none}

  /* progress section */
  #progress-section{display:none;max-width:620px;margin:0 5vw 4rem;
                    animation:fadeUp .5s ease both}
  .stage-row{display:flex;align-items:center;gap:1rem;margin-bottom:2rem}
  .stage-icon{font-size:2.8rem;animation:wiggle 1.5s infinite}
  .stage-info h2{font-family:'Fraunces',serif;font-size:1.6rem;font-weight:700;
                 letter-spacing:-.02em}
  .stage-info p{font-size:.8rem;color:#6B6155;margin-top:.2rem;letter-spacing:.05em;
                text-transform:uppercase}

  /* THE progress bar */
  .track-wrap{position:relative;margin-bottom:.6rem}
  .track{height:52px;background:var(--sand);border-radius:30px;overflow:visible;
         border:2px solid var(--mist);position:relative}
  .fill{height:100%;background:linear-gradient(90deg,var(--rust),var(--gold));
        border-radius:28px;width:0%;transition:width .6s cubic-bezier(.4,0,.2,1);
        position:relative}
  .mascot{position:absolute;right:-22px;top:50%;transform:translateY(-50%);
          font-size:2rem;filter:drop-shadow(0 2px 4px rgba(0,0,0,.2));
          animation:bounce .6s infinite alternate}
  .pct{position:absolute;right:.8rem;top:50%;transform:translateY(-50%);
       font-family:'Fraunces',serif;font-size:1.1rem;font-weight:700;
       color:var(--ink);pointer-events:none;mix-blend-mode:multiply}

  .funny-msg{font-size:.9rem;color:var(--rust);font-style:italic;
             min-height:1.4em;transition:opacity .4s;margin-bottom:1.2rem}

  .stats-row{display:flex;gap:2rem;font-size:.78rem;color:#6B6155;
             letter-spacing:.05em;text-transform:uppercase;margin-bottom:1.5rem}
  .stats-row span{display:flex;align-items:center;gap:.4rem}

  /* log */
  .log-box{background:var(--ink);color:#9BE;font-family:monospace;font-size:.75rem;
           border-radius:4px;padding:.8rem 1rem;max-height:120px;overflow-y:auto;
           line-height:1.6;opacity:.85}
  .log-box p{margin:0}

  /* done card */
  #done-section{display:none;max-width:520px;margin:0 5vw 4rem;
                animation:fadeUp .5s ease both}
  .done-card{background:var(--card);border:2px solid var(--sage);border-radius:6px;
             padding:2rem;text-align:center}
  .done-icon{font-size:3.5rem;margin-bottom:1rem;animation:pop .4s ease}
  .done-card h2{font-family:'Fraunces',serif;font-size:1.6rem;font-weight:700;
                margin-bottom:.5rem}
  .done-card p{color:#6B6155;font-size:.9rem;margin-bottom:1.5rem}
  .done-stats{display:flex;justify-content:center;gap:2.5rem;margin-bottom:1.5rem}
  .done-stat strong{font-family:'Fraunces',serif;font-size:2rem;font-weight:700;
                    display:block;color:var(--rust)}
  .done-stat span{font-size:.68rem;letter-spacing:.15em;text-transform:uppercase;
                  color:#9A8E82}
  .view-btn{display:inline-block;padding:.7rem 2rem;background:var(--ink);
            color:var(--cream);text-decoration:none;border-radius:100px;
            font-family:'DM Sans',sans-serif;font-weight:500;font-size:.9rem;
            transition:background .2s,transform .15s}
  .view-btn:hover{background:var(--rust);transform:translateY(-2px)}
  .reset-btn{margin-top:1rem;display:block;font-size:.75rem;color:#9A8E82;
             cursor:pointer;background:none;border:none;text-decoration:underline}

  footer{margin-top:auto;border-top:1px solid var(--mist);padding:1.2rem 5vw;
         background:var(--sand);font-size:.72rem;color:#9A8E82;
         display:flex;justify-content:space-between;align-items:center}
  .footer-logo{font-family:'Fraunces',serif;font-size:1rem;font-weight:700;
               color:var(--ink);font-style:italic}

  @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
  @keyframes wiggle{0%,100%{transform:rotate(-5deg)}50%{transform:rotate(5deg)}}
  @keyframes bounce{from{transform:translateY(-50%) scale(1)}
                    to{transform:translateY(-62%) scale(1.1)}}
  @keyframes pop{0%{transform:scale(.5)}80%{transform:scale(1.2)}100%{transform:scale(1)}}

  @media(max-width:600px){
    .card{margin:2rem 4vw} #progress-section,#done-section{margin:0 4vw 3rem}
    .stats-row{flex-wrap:wrap;gap:1rem}
  }
</style>
</head>
<body>

<header>
  <div class="eyebrow">JobScraper &middot; Detailhandel EFZ Profil</div>
  <h1>Jobs <em>finden</em><br>auf Knopfdruck</h1>
  <p class="subtitle">Scrapt jobs.ch &mdash; filtert &mdash; generiert HTML &mdash; fertig.</p>
</header>

<div class="card" id="form-card">
  <div class="field">
    <label for="location">Stadt / Region</label>
    <input type="text" id="location" value="winterthur" placeholder="z.B. winterthur, zurich">
  </div>
  <div class="field">
    <label for="max_pages">Max. Seiten <small style="text-transform:none;letter-spacing:0">(leer = alle)</small></label>
    <input type="number" id="max_pages" placeholder="z.B. 5 (zum Testen)" min="1">
    <div class="hint">Jede Seite = 1 Sek. Wartezeit. Winterthur hat ~74 Seiten.</div>
  </div>
  <button id="start-btn" onclick="startScraping()">&#x1F50D;&nbsp; Stellen suchen</button>
</div>

<!-- Progress view -->
<div id="progress-section">
  <div class="stage-row">
    <div class="stage-icon" id="stage-icon">&#x1F50D;</div>
    <div class="stage-info">
      <h2 id="stage-title">Starte&hellip;</h2>
      <p id="stage-sub">Initialisierung</p>
    </div>
  </div>

  <div class="track-wrap">
    <div class="track">
      <div class="fill" id="fill">
        <span class="mascot" id="mascot">&#x1F43F;&#xFE0F;</span>
      </div>
    </div>
    <div class="pct" id="pct-label">0%</div>
  </div>

  <div class="funny-msg" id="funny-msg">Aufwärmen der virtuellen Maschine&hellip; &#x2615;</div>

  <div class="stats-row">
    <span id="stat-pages">&#x1F4C4; 0 Seiten</span>
    <span id="stat-jobs">&#x1F4BC; 0 Jobs</span>
    <span id="stat-filtered">&#x2714;&#xFE0F; &mdash; relevant</span>
  </div>

  <div class="log-box" id="log-box"><p style="color:#6B9">Warte auf Scraper&hellip;</p></div>
</div>

<!-- Done view -->
<div id="done-section">
  <div class="done-card">
    <div class="done-icon">&#x1F389;</div>
    <h2>Fertig!</h2>
    <p>Der Scraper hat seine Arbeit getan. Hier sind deine Ergebnisse:</p>
    <div class="done-stats">
      <div class="done-stat"><strong id="done-total">0</strong><span>Geprüft</span></div>
      <div class="done-stat"><strong id="done-kept">0</strong><span>Passend</span></div>
      <div class="done-stat"><strong id="done-easy">0</strong><span>Easy Apply</span></div>
    </div>
    <a href="#" id="view-link" class="view-btn" target="_blank">
      &#x1F440;&nbsp; Stellen ansehen
    </a>
    <button class="reset-btn" onclick="resetToStart()">&#x21A9; Neue Suche starten</button>
  </div>
</div>

<footer>
  <div class="footer-logo">JobScraper</div>
  <div>Lokal &middot; jobs.ch &middot; Detailhandel EFZ</div>
</footer>

<script>
// ── Funny message banks per stage ────────────────────────────────────────────
const MSGS = {
  start: [
    "Klopfe h\u00f6flich an den jobs.ch-Server\u2026 🚪",
    "Schminke den User-Agent\u2026 💄",
    "\u00DCberzeuge jobs.ch, dass wir Menschen sind\u2026 🤖",
    "Erwecke den Scraper aus dem Winterschlaf\u2026 💤",
  ],
  scraping: [
    "Politely stealing data since 2024\u2026 📋",
    "Seite {page}/{total}: Sammle Jobs wie ein Eichh\u00f6rnchen N\u00fcsse 🐿\uFE0F",
    "Ich schw\u00f6re, ich bin kein Bot. Ehrlich. Wirklich. 🤔",
    "Schon wieder eine Seite\u2026 wir h\u00f6ren gleich auf\u2026 vielleicht\u2026 📄",
    "Lade Seite {page} herunter\u2026 bitte warten \u23F3",
    "Bereits {jobs} Jobs eingesackt, noch {left} Seiten 💼",
    "Der Server antwortet\u2026 irgendwann\u2026 hoffentlich\u2026 🌍",
    "Seite {page} von {total}: der Scraper ist unaufhaltsam 🚀",
  ],
  workload: [
    "Entferne 20%-Stellen\u2026 Pensum-Check! \u23F1",
    "Filtere alles unter 80% aus\u2026 Vollzeit oder nichts! 💪",
    "Tsch\u00fcss, Minijobs! 👋",
  ],
  keywords: [
    "Auf Wiedersehen, Neurochirurgen! 🧠👋",
    "Tsch\u00fcss, Raketeningenieure! 🚀👋",
    "Keine Stellen f\u00fcr Kernkraft-Betreiber heute\u2026 \u2622\uFE0F",
    "Entferne alles mit '10 Jahre Erfahrung f\u00fcr Einsteiger'\u2026 🙄",
    "Polymechaniker? Danke, weiter. 🔩",
  ],
  relevance: [
    "Suche passende Stellen\u2026 🔍",
    "Pr\u00fcfe Relevanz-Keywords\u2026 📝",
    "Behalte nur die Guten! \u2B50",
  ],
  dedup: [
    "Entferne doppelte Stellen\u2026 📸",
    "Einmal reicht! Duplikate fliegen raus\u2026 🙆",
  ],
  generating: [
    "Pinsel schwingen f\u00fcr dein HTML-Kunstwerk\u2026 🎨",
    "W\u00e4hle die perfekte Schriftart\u2026 Es ist Fraunces. Nat\u00fcrlich. \u2712\uFE0F",
    "Bastle ein HTML so sch\u00f6n, dass sogar Picasso neidisch w\u00e4re\u2026 🖼\uFE0F",
    "CSS-Magie\u2026 \u2728",
  ],
};

const STAGE_ICONS = {
  start:      "🔍",
  scraping:   "📄",
  workload:   "\u23F1",
  keywords:   "\u2702\uFE0F",
  relevance:  "🔎",
  dedup:      "📸",
  generating: "🎨",
  done:       "\u2705",
};
const STAGE_TITLES = {
  start:      "Scraper startet\u2026",
  scraping:   "Lade Seiten herunter",
  workload:   "Pensum-Filter",
  keywords:   "Ausschluss-Filter",
  relevance:  "Relevanz-Check",
  dedup:      "Deduplizierung",
  generating: "Generiere HTML",
  done:       "Fertig!",
};

let _msgTimer = null;
let _currentStage = 'start';
let _pageData = { page: 0, total: 0, jobs: 0 };
let _filteredCount = 0;
let _msgIdx = 0;

function pickMsg(stage) {
  const bank = MSGS[stage] || MSGS.start;
  const tpl = bank[_msgIdx % bank.length];
  _msgIdx++;
  return tpl
    .replace('{page}',  _pageData.page)
    .replace('{total}', _pageData.total)
    .replace('{jobs}',  _pageData.jobs)
    .replace('{left}',  Math.max(0, _pageData.total - _pageData.page));
}

function setStage(stage) {
  _currentStage = stage;
  _msgIdx = 0;
  document.getElementById('stage-icon').textContent  = STAGE_ICONS[stage] || "🔍";
  document.getElementById('stage-title').textContent = STAGE_TITLES[stage] || stage;
  document.getElementById('stage-sub').textContent   = '';
  showNextMsg();
}

function showNextMsg() {
  const el = document.getElementById('funny-msg');
  el.style.opacity = '0';
  setTimeout(() => {
    el.textContent = pickMsg(_currentStage);
    el.style.opacity = '1';
  }, 300);
}

function setProgress(pct) {
  document.getElementById('fill').style.width = pct + '%';
  document.getElementById('pct-label').textContent = pct + '%';
  // Hide mascot at 0%, keep visible otherwise
  document.getElementById('mascot').style.display = pct > 2 ? 'block' : 'none';
}

function addLog(msg) {
  const box = document.getElementById('log-box');
  const p = document.createElement('p');
  p.textContent = msg;
  box.appendChild(p);
  // Keep last 12 lines
  while (box.children.length > 12) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

function updatePageStats(page, total, jobs) {
  _pageData = { page, total, jobs };
  document.getElementById('stat-pages').textContent =
    '📄 ' + page + (total ? '/' + total : '') + ' Seiten';
  document.getElementById('stat-jobs').textContent = '💼 ' + jobs + ' Jobs';
}

function updateFilterStat(remaining) {
  _filteredCount = remaining;
  document.getElementById('stat-filtered').textContent =
    '\u2714\uFE0F ' + remaining + ' relevant';
}

let _evtSource = null;

function startScraping() {
  const location  = document.getElementById('location').value.trim() || 'winterthur';
  const maxPages  = document.getElementById('max_pages').value.trim();

  document.getElementById('form-card').style.display    = 'none';
  document.getElementById('progress-section').style.display = 'block';
  document.getElementById('done-section').style.display  = 'none';

  setStage('start');
  setProgress(2);
  document.getElementById('start-btn').disabled = true;

  // Rotate funny messages every 3.5s
  _msgTimer = setInterval(() => showNextMsg(), 3500);

  let url = '/scrape?location=' + encodeURIComponent(location);
  if (maxPages) url += '&max_pages=' + encodeURIComponent(maxPages);

  _evtSource = new EventSource(url);

  _evtSource.addEventListener('found', e => {
    const d = JSON.parse(e.data);
    setStage('scraping');
    setProgress(5);
    updatePageStats(1, d.total_pages, 0);
    addLog('📊 Gefunden: ' + d.total + ' Jobs auf ' + d.total_pages + ' Seiten (' + d.location + ')');
  });

  _evtSource.addEventListener('page', e => {
    const d = JSON.parse(e.data);
    setProgress(d.progress);
    updatePageStats(d.page, d.total_pages, d.jobs_so_far);
    if (d.page % 5 === 0) addLog('📄 Seite ' + d.page + '/' + d.total_pages + ' geladen (' + d.jobs_so_far + ' Jobs bisher)');
  });

  _evtSource.addEventListener('scrape_done', e => {
    const d = JSON.parse(e.data);
    setProgress(62);
    addLog('\u2705 Scraping abgeschlossen: ' + d.jobs + ' einzigartige Jobs');
    setStage('workload');
  });

  _evtSource.addEventListener('stage', e => {
    const d = JSON.parse(e.data);
    setStage(d.stage);
    setProgress(d.progress);
    if (d.stage === 'workload')   addLog('\u23F1 Pensum-Filter: ' + d.remaining + ' verbleibend (' + d.excluded + ' ausgeschlossen)');
    if (d.stage === 'keywords')  addLog('\u2702\uFE0F Keyword-Filter: ' + d.remaining + ' verbleibend (' + d.excluded + ' ausgeschlossen)');
    if (d.stage === 'relevance') { addLog('🔎 Relevanz-Check: ' + d.remaining + ' verbleibend (' + d.excluded + ' ausgeschlossen)'); updateFilterStat(d.remaining); }
    if (d.stage === 'dedup')     { addLog('📸 Deduplizierung: ' + d.kept + ' finale Stellen'); updateFilterStat(d.kept); }
    if (d.stage === 'generating') addLog('🎨 Generiere HTML\u2026');
  });

  _evtSource.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    clearInterval(_msgTimer);
    _evtSource.close();

    setStage('done');
    setProgress(100);
    document.getElementById('mascot').textContent = '🎉';
    document.getElementById('funny-msg').textContent = 'Fertig! Deine Traumjobs warten\u2026 🎉';
    addLog('🎉 HTML gespeichert: ' + d.html_name);

    // Show done section after short delay
    setTimeout(() => {
      document.getElementById('progress-section').style.display = 'none';
      const ds = document.getElementById('done-section');
      ds.style.display = 'block';
      document.getElementById('done-total').textContent = d.stats.total  || 0;
      document.getElementById('done-kept').textContent  = d.stats.kept   || 0;
      document.getElementById('done-easy').textContent  = d.easy_count   || 0;
      document.getElementById('view-link').href = '/results/' + encodeURIComponent(d.html_name);
    }, 1200);
  });

  _evtSource.addEventListener('error_msg', e => {
    clearInterval(_msgTimer);
    const d = JSON.parse(e.data);
    document.getElementById('funny-msg').textContent = '\u274C Fehler: ' + d.msg;
    document.getElementById('funny-msg').style.color = 'var(--rust)';
    addLog('\u274C ' + d.msg);
    if (_evtSource) _evtSource.close();
  });

  _evtSource.onerror = () => {
    // SSE done (stream closed) – normal after completion
    if (_evtSource) _evtSource.close();
  };
}

function resetToStart() {
  document.getElementById('form-card').style.display    = 'block';
  document.getElementById('progress-section').style.display = 'none';
  document.getElementById('done-section').style.display  = 'none';
  document.getElementById('start-btn').disabled = false;
  setProgress(0);
  document.getElementById('log-box').innerHTML = '<p style="color:#6B9">Warte auf Scraper\u2026</p>';
  document.getElementById('stat-pages').textContent = '📄 0 Seiten';
  document.getElementById('stat-jobs').textContent  = '💼 0 Jobs';
  document.getElementById('stat-filtered').textContent = '\u2714\uFE0F \u2014 relevant';
  document.getElementById('mascot').textContent = '🐿\uFE0F';
  clearInterval(_msgTimer);
}
</script>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return START_HTML


@app.route("/scrape")
def scrape_sse():
    location     = (request.args.get("location") or "winterthur").strip() or "winterthur"
    max_pages_s  = (request.args.get("max_pages") or "").strip()
    max_pages    = int(max_pages_s) if max_pages_s.isdigit() else None

    def generate():
        if not _run_lock.acquire(blocking=False):
            yield f"event: error_msg\ndata: {json.dumps({'msg': 'Scraper läuft bereits – bitte warten!'})}\n\n"
            return

        progress_q: queue.Queue = queue.Queue()
        result: dict = {}

        def on_progress(event_type: str, **kwargs):
            progress_q.put((event_type, kwargs))

        def run_scraper():
            try:
                raw_jobs = scrape(location, max_pages, progress_fn=on_progress)

                if not raw_jobs:
                    progress_q.put(("error_msg", {"msg": "Keine Jobs gefunden"}))
                    return

                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                stem = f"jobs_{location}_{ts}"

                RAW_DIR.mkdir(parents=True, exist_ok=True)
                save_csv(raw_jobs,  RAW_DIR / f"{stem}.csv")
                save_json(raw_jobs, RAW_DIR / f"{stem}.json")

                filtered, stats = filter_jobs(raw_jobs, verbose=False, progress_fn=on_progress)

                on_progress("stage", stage="generating",
                            remaining=len(filtered), excluded=0)

                FILT_DIR.mkdir(parents=True, exist_ok=True)
                save_json(filtered, FILT_DIR / f"{stem}_filtered.json")

                html_name = f"jobs_{location}_{ts}.html"
                generate_html(filtered, stats, location, FILT_DIR / html_name)

                easy_count = sum(1 for j in filtered if j.get('easy_apply'))
                result.update(html_name=html_name, stats=stats, easy_count=easy_count)
                progress_q.put(("done", {
                    "html_name": html_name,
                    "stats": stats,
                    "easy_count": easy_count,
                }))

            except Exception as exc:
                progress_q.put(("error_msg", {"msg": f"{type(exc).__name__}: {exc}"}))
            finally:
                progress_q.put(("__sentinel__", {}))

        t = threading.Thread(target=run_scraper, daemon=True)
        t.start()

        _PROGRESS_MAP = {
            "found":      5,
            "scrape_done": 62,
        }
        _STAGE_PROGRESS = {
            "workload":   65,
            "keywords":   72,
            "relevance":  78,
            "dedup":      83,
            "generating": 90,
        }

        try:
            while True:
                try:
                    event_type, data = progress_q.get(timeout=25)
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    continue

                if event_type == "__sentinel__":
                    break

                # Compute progress percentage
                if event_type == "page":
                    page  = data.get("page", 1)
                    total = data.get("total_pages", 1)
                    data["progress"] = 5 + int(55 * page / max(total, 1))
                elif event_type == "stage":
                    data["progress"] = _STAGE_PROGRESS.get(data.get("stage", ""), 80)
                else:
                    data["progress"] = _PROGRESS_MAP.get(event_type, 0)

                yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                if event_type in ("done", "error_msg"):
                    break
        finally:
            _run_lock.release()

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/results/<path:filename>")
def serve_result(filename):
    filepath = FILT_DIR / filename
    if not filepath.exists():
        return "Datei nicht gefunden", 404
    return send_file(filepath.resolve())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5001
    url  = f"http://localhost:{port}"
    print(f"\n\U0001F680  JobScraper-Frontend startet auf {url}")
    print("   Drücke Ctrl+C zum Beenden.\n")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
