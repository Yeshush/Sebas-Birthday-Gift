#!/usr/bin/env python3
"""
server.py
=========
Web-Frontend für JobScraper. Startet per Klick, zeigt einen
(nicht ganz ernst gemeinten) Fortschrittsbalken und öffnet die
Ergebnisse automatisch.

Starten:
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 server.py
    → http://localhost:5001
"""

import json
import queue
import re
import sys
import threading
import webbrowser
import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, Response, redirect, request, send_file, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import scraper functions directly
BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))
from JobScraper import (
    scrape, filter_jobs, save_csv, save_json, generate_html,
)
from database import db, User, Profile, SearchHistory

load_dotenv()

app = Flask(__name__)

# -- App Configuration --
# Use SQLite locally by default, or DATABASE_URL if on Railway
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///jobscraper.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql+psycopg://", 1)
elif app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgresql://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgresql://", "postgresql+psycopg://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-me')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

db.init_app(app)
jwt = JWTManager(app)

# Output directories should be relative to the CURRENT WORKING DIRECTORY
FILT_DIR = Path("filtered_results")
RAW_DIR  = Path("results")
_run_lock = threading.Lock()

# Auto-create tables and seed "seba" user
with app.app_context():
    db.create_all()
    # Seed user "seba"
    if not User.query.filter_by(username='seba').first():
        seba = User(username='seba')
        seba.set_password('seba123') # Default password for the requested Seba user
        db.session.add(seba)
        db.session.commit()
        
        # Add profile for seba
        seba_profile = Profile(
            user_id=seba.id,
            education_level='EFZ',
            min_workload=80,
            allow_quereinstieg=True
        )
        seba_profile.set_interests_list(["detailhandel", "verkauf", "lager", "gastro"])
        db.session.add(seba_profile)
        db.session.commit()
        print("✅ Seeded user 'seba' into database.")

# ── API Routes (Authentication) ───────────────────────────────────────────────

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"msg": "Username and password required"}), 400
        
    user = User.query.filter_by(username=data.get('username')).first()
    if not user or not user.check_password(data.get('password')):
        return jsonify({"msg": "Bad username or password"}), 401
        
    access_token = create_access_token(identity=str(user.id))
    return jsonify(access_token=access_token, username=user.username)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"msg": "Username and password required"}), 400
        
    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "Username already exists"}), 400
        
    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    
    # Create empty profile
    new_profile = Profile(user_id=new_user.id)
    db.session.add(new_profile)
    db.session.commit()
    
    access_token = create_access_token(identity=str(new_user.id))
    return jsonify(access_token=access_token, username=new_user.username), 201

@app.route('/api/me', methods=['GET'])
@jwt_required()
def me():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404
        
    profile = user.profile
    return jsonify({
        "username": user.username,
        "profile": {
            "education_level": profile.education_level,
            "min_workload": profile.min_workload,
            "interests": profile.get_interests_list(),
            "allow_quereinstieg": profile.allow_quereinstieg
        }
    })

@app.route('/api/history', methods=['GET'])
@jwt_required()
def history():
    current_user_id = get_jwt_identity()
    searches = SearchHistory.query.filter_by(user_id=current_user_id).order_by(SearchHistory.timestamp.desc()).all()
    
    return jsonify([{
        "id": s.id,
        "location": s.location,
        "timestamp": s.timestamp.isoformat(),
        "summary": json.loads(s.results_summary) if s.results_summary else {}
    } for s in searches])

@app.route('/api/history/<int:search_id>', methods=['GET'])
@jwt_required()
def history_detail(search_id):
    current_user_id = get_jwt_identity()
    search = SearchHistory.query.filter_by(id=search_id, user_id=current_user_id).first()
    
    if not search:
        return jsonify({"msg": "Search not found"}), 404
        
    return jsonify({
        "id": search.id,
        "location": search.location,
        "timestamp": search.timestamp.isoformat(),
        "summary": json.loads(search.results_summary) if search.results_summary else {},
        "results": json.loads(search.results_json) if search.results_json else []
    })

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    from flask import send_from_directory
    # If the request matches an API route, let Flask handle it
    if path.startswith('api/') or path == 'scrape' or path.startswith('results/'):
        pass # Will fall through or be caught by other routes if we don't return here, but flask needs it handled.
        # Actually better to handle it properly below
        
    dist_dir = os.path.join(app.root_path, 'frontend', 'dist')
    if path and os.path.exists(os.path.join(dist_dir, path)):
        return send_from_directory(dist_dir, path)
    else:
        return send_from_directory(dist_dir, 'index.html')


@app.route("/scrape")
def scrape_sse():
    _raw_location = (request.args.get("location") or "winterthur").strip()
    location = re.sub(r'[^a-z0-9\-]', '', _raw_location.lower())[:50] or "winterthur"
    max_pages_s  = (request.args.get("max_pages") or "").strip()
    max_pages    = int(max_pages_s) if max_pages_s.isdigit() else None
    
    token = request.args.get("token")
    if not token:
        return Response("event: error_msg\ndata: {\"msg\": \"No token provided\"}\n\n", mimetype="text/event-stream")

    # Decode token to get user profile
    from flask_jwt_extended import decode_token
    try:
        decoded = decode_token(token)
        user_id = decoded['sub']
    except Exception as e:
        return Response(f"event: error_msg\ndata: {json.dumps({'msg': 'Invalid token'})}\n\n", mimetype="text/event-stream")

    def generate():
        if not _run_lock.acquire(blocking=False):
            yield f"event: error_msg\ndata: {json.dumps({'msg': 'Scraper läuft bereits – bitte warten!'})}\n\n"
            return

        progress_q: queue.Queue = queue.Queue()
        result: dict = {}

        def on_progress(event_type: str, **kwargs):
            progress_q.put((event_type, kwargs))

        def run_scraper(app_context):
            with app_context:
                try:
                    user = User.query.get(user_id)
                    if not user:
                        progress_q.put(("error_msg", {"msg": "User not found"}))
                        return
                        
                    profile = user.profile
                    
                    # Convert DB Profile to dict for filter_jobs
                    profile_dict = {
                        'min_workload': profile.min_workload,
                        'allow_quereinstieg': profile.allow_quereinstieg,
                    }
                    
                    # Special logic for legacy 'seba' user
                    if user.username == 'seba':
                        # Leave include/exclude as None so JobScraper uses its legacy defaults
                        profile_dict['include_keywords'] = None
                        profile_dict['exclude_keywords'] = None
                        profile_dict['manual_exclude_titles'] = None
                    else:
                        # For generic users, construct simple include list based on interests
                        # Realistically you'd want a more robust mapping here
                        profile_dict['include_keywords'] = profile.get_interests_list()
                        profile_dict['exclude_keywords'] = [] # Start empty for custom users
                        profile_dict['manual_exclude_titles'] = []
                        if not profile.allow_quereinstieg:
                            profile_dict['exclude_keywords'].append("quereinsteig")
                            profile_dict['exclude_keywords'].append("quereinstieg")

                    raw_jobs = scrape(location, max_pages, progress_fn=on_progress)

                    if not raw_jobs:
                        progress_q.put(("error_msg", {"msg": "Keine Jobs gefunden"}))
                        return

                    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                    stem = f"jobs_{location}_{ts}"

                    RAW_DIR.mkdir(parents=True, exist_ok=True)
                    save_csv(raw_jobs,  RAW_DIR / f"{stem}.csv")
                    save_json(raw_jobs, RAW_DIR / f"{stem}.json")

                    filtered, stats = filter_jobs(raw_jobs, verbose=False, progress_fn=on_progress, profile=profile_dict)

                    on_progress("stage", stage="saving",
                                remaining=len(filtered), excluded=0)

                    FILT_DIR.mkdir(parents=True, exist_ok=True)
                    save_json(filtered, FILT_DIR / f"{stem}_filtered.json")

                    easy_count = sum(1 for j in filtered if j.get('easy_apply'))
                    
                    # Save search history to DB
                    new_history = SearchHistory(
                        user_id=user.id,
                        location=location,
                        results_summary=json.dumps({"total": stats['total'], "kept": stats['kept'], "easy": easy_count}),
                        results_json=json.dumps(filtered)
                    )
                    db.session.add(new_history)
                    db.session.commit()

                    result.update(stats=stats, easy_count=easy_count)
                    progress_q.put(("done", {
                        "stats": stats,
                        "easy_count": easy_count,
                        "search_id": new_history.id
                    }))

                except Exception as exc:
                    progress_q.put(("error_msg", {"msg": f"{type(exc).__name__}: {exc}"}))
                finally:
                    progress_q.put(("__sentinel__", {}))

        # Pass the Flask application context to the thread so it can access the DB
        t = threading.Thread(target=run_scraper, args=(app.app_context(),), daemon=True)
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
            "saving":     90,
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


from werkzeug.utils import secure_filename

@app.route("/results/<filename>")
def serve_result(filename):
    safe_name = secure_filename(filename)
    if not safe_name:
        return "Ungültiger Dateiname", 400
        
    filepath = FILT_DIR / safe_name
    
    # Verify the resolved path is still within FILT_DIR to prevent directory traversal
    try:
        if not filepath.resolve().is_relative_to(FILT_DIR.resolve()):
            return "Ungültiger Zugriff", 403
    except ValueError:
        pass
        
    if not filepath.exists():
        return "Datei nicht gefunden", 404
        
    return send_file(filepath.resolve())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Railway expects the application to listen on the port defined by the PORT environment variable.
    port = int(os.environ.get("PORT", 5001))
    url  = f"http://localhost:{port}"
    print(f"\n\U0001F680  JobScraper-Frontend startet auf Port {port}")
    print("   Drücke Ctrl+C zum Beenden.\n")
    
    # Only open browser if not running in a cloud environment (PORT env var is usually set there)
    if not os.environ.get("PORT"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
