import os
import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profile = db.relationship('Profile', backref='user', uselist=False, cascade='all, delete-orphan')
    searches = db.relationship('SearchHistory', backref='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Profile(db.Model):
    __tablename__ = 'profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    
    education_level = db.Column(db.String(50), nullable=True)  # e.g., 'EFZ', 'HF', 'Maturität'
    min_workload = db.Column(db.Integer, default=80)
    interests = db.Column(db.Text, nullable=True)  # Stored as JSON string
    allow_quereinstieg = db.Column(db.Boolean, default=True)
    
    def get_interests_list(self):
        if self.interests:
            try:
                return json.loads(self.interests)
            except:
                return []
        return []
        
    def set_interests_list(self, interests_list):
        self.interests = json.dumps(interests_list)

class SearchHistory(db.Model):
    __tablename__ = 'search_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    results_summary = db.Column(db.Text, nullable=True)  # JSON string of stats/summary
    results_json = db.Column(db.Text, nullable=True)     # Full JSON of scraped jobs
