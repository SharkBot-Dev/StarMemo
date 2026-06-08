import os
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import dotenv
import tinysegmenter
from datetime import datetime, timezone
import requests
import db
import roles

dotenv.load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECREST_KEY")

title = os.getenv("TITLE")
description = os.getenv("DESCRIPTION")
site_key = os.getenv("TURNSTILE_SITEKEY")

db.memos_col.create_index("createdAt", expireAfterSeconds=86400)
db.memos_col.update_many({"createdAt": {"$exists": False}}, {"$set": {"createdAt": datetime.now(timezone.utc)}})

def extract_keywords(text):
    tokens = tinysegmenter.tokenize(text)
    keywords = set()
    for token in tokens:
        keywords.add(token)
    return keywords

def validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "パスワードは8文字以上必要です。"
    return None

@app.route('/')
def index():
    if 'code' not in request.cookies:
        user = db.users_col.find_one({"code": request.cookies.get('code')})
        if not user:
            return redirect(url_for('login'))
    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return redirect(url_for('login'))
    return render_template("sky.html", username=user['username'], title=title, description=description)

@app.get('/login')
def login():
    if 'code' in request.cookies:
        user = db.users_col.find_one({"code": request.cookies.get('code')})
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

    user = db.users_col.find_one({"username": username})
    
    if user:
        if check_password_hash(user['password'], password):
            db.users_col.update_one({
                "username": username
            }, {
                "$set": {
                    "code": code
                }
            })
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('code', code, secure=True, httponly=True)
            return resp
        else:
            return render_template("login.html", error="その名前は既に使用されているか、パスワードが違います。", title=title, description=description, site_key=site_key)
    else:
        pw_error = validate_password(password)
        if pw_error:
            return render_template("login.html", error=pw_error, title=title, description=description, site_key=site_key)

        hashed_password = generate_password_hash(password)
        db.users_col.insert_one({
            "username": username,
            "password": hashed_password,
            "code": code,
            "roles": ["user"]
        })
        resp = make_response(redirect(url_for('index')))
        resp.set_cookie('code', code, secure=True, httponly=True)
        return resp

@app.get('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('code', secure=True, httponly=True)
    return resp

@app.get('/terms')
def terms():
    return render_template("terms.html", title=title, description=description)

@app.get('/privacy')
def privacy():
    return render_template("privacy.html", title=title, description=description)

@app.get('/forbidden')
def forbidden():
    return render_template("forbidden.html", title=title, description=description)

@app.get('/change-password')
def change_password():
    if 'code' not in request.cookies:
        return redirect(url_for('login'))

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return redirect(url_for('login'))

    return render_template("change_password.html", title=title, description=description)

@app.post('/change-password')
def change_password_post():
    if 'code' not in request.cookies:
        return redirect(url_for('login'))

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return redirect(url_for('login'))

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not check_password_hash(user['password'], current_password):
        return render_template("change_password.html", error="現在のパスワードが違います。", title=title, description=description)

    if new_password != confirm_password:
        return render_template("change_password.html", error="新しいパスワードと確認用パスワードが一致しません。", title=title, description=description)

    pw_error = validate_password(new_password)
    if pw_error:
        return render_template("change_password.html", error=pw_error, title=title, description=description)

    hashed_password = generate_password_hash(new_password)
    db.users_col.update_one(
        {"username": user['username']},
        {"$set": {"password": hashed_password}}
    )

    return redirect(url_for('index'))

@app.get('/admin')
def admin():
    if 'code' not in request.cookies:
        return redirect(url_for('login'))
        
    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return redirect(url_for('login'))
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return "Forbidden", 403

    return render_template("admin.html", title=title, description=description)

@app.get('/api/memos')
def get_memos():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401
        
    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    query = request.args.get('q', '')
    
    filter_query = {"username": user['username']}
    if query:
        filter_query["text"] = {"$regex": query, "$options": "i"}
    user_memos = list(db.memos_col.find(filter_query))
    
    user_keywords = set()
    for memo in user_memos:
        if 'keywords' in memo:
            user_keywords.update(memo['keywords'])
        else:
            keywords = list(extract_keywords(memo['text']))
            user_keywords.update(keywords)
            db.memos_col.update_one({"_id": memo["_id"]}, {"$set": {"keywords": keywords}})
            memo['keywords'] = keywords

    public_memos = []
    if user_keywords:
        public_filter = {
            "username": {"$ne": user['username']},
            "is_public": True,
            "keywords": {"$in": list(user_keywords)}
        }
        if query:
            public_filter["text"] = {"$regex": query, "$options": "i"}
        
        public_memos = list(db.memos_col.find(public_filter))

    min_public_memos = 50
    if len(public_memos) < min_public_memos:
        needed = min_public_memos - len(public_memos)
        existing_public_ids = {memo["_id"] for memo in public_memos}
        
        complementary_filter = {
            "username": {"$ne": user['username']},
            "is_public": True
        }
        if existing_public_ids:
            complementary_filter["_id"] = {"$nin": list(existing_public_ids)}
        if query:
            complementary_filter["text"] = {"$regex": query, "$options": "i"}
            
        complementary_memos = list(
            db.memos_col.find(complementary_filter)
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
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401
        
    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    if not data or 'text' not in data:
        return jsonify({"error": "Missing text"}), 400
    
    text = data['text']
    is_public = data.get('is_public', False)
    keywords = list(extract_keywords(text))
    
    db.memos_col.insert_one({
        "username": user['username'],
        "text": text,
        "is_public": is_public,
        "keywords": keywords,
        "createdAt": datetime.now(timezone.utc)
    })
    return jsonify({"success": True})

@app.delete('/api/memos/<memo_id>')
def delete_memo(memo_id):
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 3):
        return jsonify({"error": "Forbidden"}), 403

    db.memos_col.delete_one({"_id": memo_id})
    return jsonify({"success": True})

@app.post('/api/ban')
def set_ban():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 5):
        return jsonify({"error": "Forbidden"}), 403
    
    role = request.json.get('role')
    if not role in roles.ROLES:
        return jsonify({"error": "BadRequest"}), 400

    db.users_col.update_one({
        "username": request.json.get('username')
    }, {
        "$set": {
            "roles": ["ban"]
        }
    })

    return jsonify({"success": True})

@app.delete('/api/ban')
def remove_ban():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 5):
        return jsonify({"error": "Forbidden"}), 403
    
    role = request.json.get('role')
    if not role in roles.ROLES:
        return jsonify({"error": "BadRequest"}), 400

    db.users_col.update_one({
        "username": request.json.get('username')
    }, {
        "$set": {
            "roles": ["user"]
        }
    })

    return jsonify({"success": True})

@app.get('/api/roles/user')
def get_user_roles():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    has_admin_permission = roles.any_permission(user.get('roles', ['user']), 6)
    has_delete_permission = roles.any_permission(user.get('roles', ['user']), 3)
    has_view_permission = roles.any_permission(user.get('roles', ['user']), 1)
    has_create_permission = roles.any_permission(user.get('roles', ['user']), 2)
    
    return jsonify({
        "success": True, 
        "roles": user.get('roles', ['user']),
        "has_admin_permission": has_admin_permission,
        "has_delete_permission": has_delete_permission,
        "has_view_permission": has_view_permission,
        "has_create_permission": has_create_permission
    })

@app.post('/api/roles/user')
def add_user_roles():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return jsonify({"error": "Forbidden"}), 403
    
    role = request.json.get('role')
    if not role in roles.ROLES:
        return jsonify({"error": "BadRequest"}), 400

    db.users_col.update_one({
        "username": request.json.get('username')
    }, {
        "$addToSet": {
            "roles": role
        }
    })

    return jsonify({"success": True})

@app.delete('/api/roles/user')
def remove_user_roles():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return jsonify({"error": "Forbidden"}), 403
    
    role = request.json.get('role')
    if not role in roles.ROLES:
        return jsonify({"error": "BadRequest"}), 400

    db.users_col.update_one({
        "username": request.json.get('username')
    }, {
        "$pull": {
            "roles": role
        }
    })

    return jsonify({"success": True})

@app.get('/api/roles')
def get_roles():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return jsonify({"error": "Forbidden"}), 403

    roles_data = {}
    for name, data in roles.ROLES.items():
        roles_data[name] = {
            "permissions": list(data["permissions"]),
            "description": data["description"]
        }
    
    permissions_data = {str(k): v for k, v in roles.PERMISSIONS.items()}

    return jsonify({
        "success": True,
        "roles": roles_data,
        "permissions": permissions_data
    })

@app.post('/api/roles')
def create_role_endpoint():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return jsonify({"error": "Forbidden"}), 403

    data = request.json
    name = data.get('name')
    permissions = data.get('permissions', [])
    description = data.get('description', '')

    if not name:
        return jsonify({"error": "Name is required"}), 400

    try:
        permissions = [int(p) for p in permissions]
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid permissions format"}), 400

    success = roles.create_role(name, permissions, description)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Role already exists or database error"}), 400

@app.put('/api/roles/<role_name>')
def update_role_endpoint(role_name):
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return jsonify({"error": "Forbidden"}), 403

    data = request.json
    permissions = data.get('permissions', [])
    description = data.get('description', '')

    try:
        permissions = [int(p) for p in permissions]
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid permissions format"}), 400

    success = roles.update_role(role_name, permissions, description)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Failed to update role"}), 400

@app.delete('/api/roles/<role_name>')
def delete_role_endpoint(role_name):
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return jsonify({"error": "Forbidden"}), 403

    success = roles.delete_role(role_name)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Failed to delete role"}), 400

@app.get('/api/users')
def list_users():
    if 'code' not in request.cookies:
        return jsonify({"error": "Unauthorized"}), 401

    user = db.users_col.find_one({"code": request.cookies.get('code')})
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    if not roles.any_permission(user.get('roles', ['user']), 6):
        return jsonify({"error": "Forbidden"}), 403

    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    skip = (page - 1) * limit

    total_users = db.users_col.count_documents({})
    
    users = list(db.users_col.find({}, {"username": 1, "roles": 1}).skip(skip).limit(limit))
    users_list = []
    for u in users:
        users_list.append({
            "username": u.get("username"),
            "roles": u.get("roles", ["user"])
        })

    return jsonify({
        "success": True,
        "users": users_list,
        "total_users": total_users,
        "page": page,
        "limit": limit
    })

if __name__ == "__main__":
    app.run("0.0.0.0", port=5000, debug=False)
