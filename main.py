import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import dotenv
from janome.tokenizer import Tokenizer
from datetime import datetime, timezone
import requests

dotenv.load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECREST_KEY")

tokenizer = Tokenizer(mmap=False)

title = os.getenv("TITLE")
description = os.getenv("DESCRIPTION")
site_key = os.getenv("TURNSTILE_SITEKEY")

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("DB_NAME")]
users_col = db["Users"]
memos_col = db["Memos"]
memos_col.create_index("createdAt", expireAfterSeconds=86400)
memos_col.update_many({"createdAt": {"$exists": False}}, {"$set": {"createdAt": datetime.now(timezone.utc)}})

def extract_keywords(text):
    tokens = tokenizer.tokenize(text)
    keywords = set()
    for token in tokens:
        part_of_speech = token.part_of_speech.split(',')[0]
        if part_of_speech in ['名詞', '動詞', '形容詞']:
            keywords.add(token.base_form)
    return keywords

@app.route('/')
def index():
    if 'username' not in session or 'code' not in session:
        user = users_col.find_one({"username": session.get('username'), "code": session.get('code')})
        if not user:
            return redirect(url_for('login'))
    return render_template("sky.html", username=session.get('username'), title=title, description=description)

@app.get('/login')
def login():
    if 'username' in session and 'code' in session:
        user = users_col.find_one({"username": session.get('username'), "code": session.get('code')})
        if user:
            return redirect(url_for('index'))
    return render_template("login.html", title=title, description=description, site_key=site_key)

@app.post('/login')
def login_post():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        return render_template("login.html", error="ユーザー名とパスワードを入力してください", title=title, description=description, site_key=site_key)

    turnstile = request.form.get('cf-turnstile-response')
    if not turnstile:
        return render_template("login.html", error="トークンがありません", title=title, description=description, site_key=site_key)

    url = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    payload = {'secret': os.getenv("TURNSTILE_SECRET"), 'response': turnstile, "remoteip": request.remote_addr}
    r = requests.post(url, data=payload)
    j = r.json()
    if j["success"] != True:
        return render_template("login.html", error="検証に失敗しました。", title=title, description=description, site_key=site_key)

    code = secrets.token_urlsafe(100)

    user = users_col.find_one({"username": username})
    
    if user:
        if check_password_hash(user['password'], password):
            session['username'] = username
            session['code'] = code
            users_col.update_one({
                "username": username
            }, {
                "$set": {
                    "code": code
                }
            })
            return redirect(url_for('index'))
        else:
            return render_template("login.html", error="その名前は既に使用されているか、パスワードが違います。", title=title, description=description, site_key=site_key)
    else:
        hashed_password = generate_password_hash(password)
        users_col.insert_one({
            "username": username,
            "password": hashed_password,
            "code": code
        })
        session['username'] = username
        session['code'] = code
        return redirect(url_for('index'))

@app.get('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.get('/terms')
def terms():
    return render_template("terms.html", title=title, description=description)

@app.get('/privacy')
def privacy():
    return render_template("privacy.html", title=title, description=description)

@app.get('/api/memos')
def get_memos():
    if 'username' not in session or 'code' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    user = users_col.find_one({"username": session.get('username'), "code": session.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    query = request.args.get('q', '')
    
    filter_query = {"username": session['username']}
    if query:
        filter_query["text"] = {"$regex": query, "$options": "i"}
    user_memos = list(memos_col.find(filter_query))
    
    user_keywords = set()
    for memo in user_memos:
        if 'keywords' in memo:
            user_keywords.update(memo['keywords'])
        else:
            keywords = list(extract_keywords(memo['text']))
            user_keywords.update(keywords)
            memos_col.update_one({"_id": memo["_id"]}, {"$set": {"keywords": keywords}})
            memo['keywords'] = keywords

    public_memos = []
    if user_keywords:
        public_filter = {
            "username": {"$ne": session['username']},
            "is_public": True,
            "keywords": {"$in": list(user_keywords)}
        }
        if query:
            public_filter["text"] = {"$regex": query, "$options": "i"}
        
        public_memos = list(memos_col.find(public_filter))

    min_public_memos = 10
    if len(public_memos) < min_public_memos:
        needed = min_public_memos - len(public_memos)
        existing_public_ids = {memo["_id"] for memo in public_memos}
        
        complementary_filter = {
            "username": {"$ne": session['username']},
            "is_public": True
        }
        if existing_public_ids:
            complementary_filter["_id"] = {"$nin": list(existing_public_ids)}
        if query:
            complementary_filter["text"] = {"$regex": query, "$options": "i"}
            
        complementary_memos = list(
            memos_col.find(complementary_filter)
            .sort("createdAt", -1)
            .limit(needed)
        )
        public_memos.extend(complementary_memos)

    all_memos = user_memos + public_memos
    
    memos_with_ids = []
    for memo in all_memos:
        memo['_id'] = str(memo['_id'])
        if 'keywords' not in memo:
            memo['keywords'] = list(extract_keywords(memo['text']))
        memos_with_ids.append(memo)

    connections = []
    for i in range(len(memos_with_ids)):
        for j in range(i + 1, len(memos_with_ids)):
            keywords1 = set(memos_with_ids[i]['keywords'])
            keywords2 = set(memos_with_ids[j]['keywords'])
            
            intersection = keywords1.intersection(keywords2)
            if intersection:
                connections.append([i, j])

    return jsonify({
        "memos": memos_with_ids,
        "connections": connections
    })

@app.post('/api/memos')
def add_memo():
    if 'username' not in session or 'code' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    user = users_col.find_one({"username": session.get('username'), "code": session.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    if not data or 'text' not in data:
        return jsonify({"error": "Missing text"}), 400
    
    text = data['text']
    is_public = data.get('is_public', False)
    keywords = list(extract_keywords(text))
    
    memos_col.insert_one({
        "username": session['username'],
        "text": text,
        "is_public": is_public,
        "keywords": keywords,
        "createdAt": datetime.now(timezone.utc)
    })
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run("0.0.0.0", port=5000, debug=False)
