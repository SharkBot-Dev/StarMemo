import os
from pymongo import MongoClient
import dotenv
import db

PERMISSIONS = {
    1: {"name": "投稿の閲覧"},
    2: {"name": "投稿の作成"},
    3: {"name": "投稿の削除"},
    4: {"name": "メンバーのミュート"},
    5: {"name": "メンバーのBan"},
    6: {"name": "ロール管理"},
}

DEFAULT_ROLES = {
    "owner": {
        "permissions": [1, 2, 3, 4, 5, 6],
        "description": "オーナー権限があります。"
    },
    "admin": {
        "permissions": [1, 2, 3, 4, 5, 6],
        "description": "管理者権限があります。"
    },
    "moderator": {
        "permissions": [1, 2, 3, 4, 5],
        "description": "モデレーター権限があります。"
    },
    "sub_moderator": {
        "permissions": [1, 2, 3, 4],
        "description": "副モデレーター権限があります。"
    },
    "user": {
        "permissions": [1, 2],
        "description": "通常のユーザーです"
    },
    "mute": {
        "permissions": [1], 
        "description": "投稿が行えません。"
    },
    "ban": {
        "permissions": [],
        "description": "投稿、閲覧などほとんどのことが行えません。"
    },
}

def load_roles_from_db():
    if db.roles_col is None:
        return {k: {"permissions": set(v["permissions"]), "description": v["description"]} for k, v in DEFAULT_ROLES.items()}
    
    try:
        if db.roles_col.count_documents({}) == 0:
            documents = []
            for name, data in DEFAULT_ROLES.items():
                documents.append({
                    "name": name,
                    "permissions": list(data["permissions"]),
                    "description": data["description"]
                })
            db.roles_col.insert_many(documents)
        
        db_roles = {}
        for doc in db.roles_col.find():
            db_roles[doc["name"]] = {
                "permissions": set(doc.get("permissions", [])),
                "description": doc.get("description", "")
            }
        return db_roles
    except Exception as e:
        print(f"Error loading roles from DB, using defaults: {e}")
        return {k: {"permissions": set(v["permissions"]), "description": v["description"]} for k, v in DEFAULT_ROLES.items()}

class RolesDict:
    def __contains__(self, item):
        roles_data = load_roles_from_db()
        return item in roles_data

    def __getitem__(self, key):
        roles_data = load_roles_from_db()
        return roles_data[key]

    def get(self, key, default=None):
        roles_data = load_roles_from_db()
        return roles_data.get(key, default)

    def __iter__(self):
        roles_data = load_roles_from_db()
        return iter(roles_data)

    def keys(self):
        roles_data = load_roles_from_db()
        return roles_data.keys()

    def items(self):
        roles_data = load_roles_from_db()
        return roles_data.items()

    def values(self):
        roles_data = load_roles_from_db()
        return roles_data.values()

ROLES = RolesDict()

def get_role(role: str = "user"):
    return ROLES.get(role)

def is_permission(role: str, required_permission_id: int) -> bool:
    role_info = get_role(role)
    if not role_info:
        return False
    return required_permission_id in role_info["permissions"]

def any_permission(roles: list[str], required_permission_id: int) -> bool:
    for r in roles:
        role_info = get_role(r)
        if role_info and required_permission_id in role_info["permissions"]:
            return True
    return False

def create_role(name: str, permissions: list[int], description: str) -> bool:
    if db.roles_col is None:
        return False
    try:
        if db.roles_col.find_one({"name": name}):
            return False
        db.roles_col.insert_one({
            "name": name,
            "permissions": [int(p) for p in permissions],
            "description": description
        })
        return True
    except Exception as e:
        print(f"Error creating role {name}: {e}")
        return False

def update_role(name: str, permissions: list[int], description: str) -> bool:
    if db.roles_col is None:
        return False
    try:
        result = db.roles_col.update_one(
            {"name": name},
            {"$set": {
                "permissions": [int(p) for p in permissions],
                "description": description
            }}
        )
        return result.modified_count > 0 or result.matched_count > 0
    except Exception as e:
        print(f"Error updating role {name}: {e}")
        return False

def delete_role(name: str) -> bool:
    if db.roles_col is None:
        return False
    try:
        db.roles_col.delete_one({"name": name})
        if db.users_col is not None:
            db.users_col["Users"].update_many({}, {"$pull": {"roles": name}})
        return True
    except Exception as e:
        print(f"Error deleting role {name}: {e}")
        return False