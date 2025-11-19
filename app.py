from flask import Flask, redirect, request, jsonify, render_template
from dotenv import load_dotenv
import requests
import urllib.parse
import os
import base64
import sqlite3
from sqlite3 import IntegrityError
from flask import g, current_app, Response

load_dotenv()

app = Flask(__name__)
app.config.setdefault('DATABASE', os.path.join(app.root_path, 'favorites.db'))

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id TEXT NOT NULL UNIQUE,
        name TEXT,
        artist TEXT,
        preview_url TEXT,
        external_url TEXT,
        image_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()

@app.cli.command('init-db')
def init_db_command():
    """Run: flask init-db"""
    init_db()
    print('Initialized the database.')

def init_app(app):
    # アプリケーションコンテキストが破棄されるときにDB接続を閉じる
    app.teardown_appcontext(close_db)
    # flask init-db コマンドを登録
    app.cli.add_command(init_db_command)
    # アプリケーションコンテキスト内でデータベースを初期化
    with app.app_context():
        init_db()

def row_to_dict(row):
    return {k: row[k] for k in row.keys()}

my_id = os.getenv('SPOTIFY_CLIENT_ID')
my_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

def get_token():
    token_url = "https://accounts.spotify.com/api/token"
    auth = base64.b64encode(f"{my_id}:{my_secret}".encode()).decode()
    response = requests.post(
        token_url,
        data = {"grant_type" : "client_credentials"}, 
        headers = {"Authorization": f"Basic {auth}"}
    )
    return response.json()["access_token"]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/player')
def player():
    track_id = request.args.get('track_id')
    return render_template('player.html', track_id=track_id)

@app.route('/search',methods=["GET"])
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "No search query provided"}), 400
    
    token = get_token()
    url = f"https://api.spotify.com/v1/search?q={query}&type=track&limit=50"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    tracks = []

    for item in data.get("tracks", {}).get("items", []):
        tracks.append({
            "id": item["id"],
            "name": item["name"],
            "artist": item["artists"][0]["name"],
            "preview_url": item["preview_url"],
            "external_url": item["external_urls"]["spotify"],
            "image": item["album"]["images"][1]["url"] if item["album"]["images"] else None
        })

    return jsonify(tracks)

@app.route('/popular', methods=["GET"])
def popular():
    token = get_token()
    url = "https://api.spotify.com/v1/browse/new-releases?limit=50"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    albums = []

    for item in data.get("albums", {}).get("items", []):
        albums.append({
            "id": item["id"],
            "name": item["name"],
            "artist": item["artists"][0]["name"],
            "external_url": item["external_urls"]["spotify"],
            "image": item["images"][1]["url"] if item["images"] else None
        })

    return jsonify(albums)

@app.route('/favorites', methods=["POST"])
def favorite():
    data = request.get_json() or {}
    track_id = data.get('id')
    if not track_id:
        return jsonify({"error": "track_id(id) required"}), 400

    # 受け取れるフィールドを安全に取り出す
    name = data.get('name')
    artist = data.get('artist')
    preview_url = data.get('preview_url')
    external_url = data.get('external_url')
    image_url = data.get('image')

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO favorites (track_id, name, artist, preview_url, external_url, image_url) VALUES (?, ?, ?, ?, ?, ?)",
            (track_id, name, artist, preview_url, external_url, image_url)
        )
        db.commit()
    except IntegrityError:
        # 既に存在する場合は既存レコードを返す（冪等性）
        row = db.execute("SELECT * FROM favorites WHERE track_id = ?", (track_id,)).fetchone()
        return jsonify(row_to_dict(row)), 200

    row = db.execute("SELECT * FROM favorites WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201

@app.route('/favorites', methods=['GET'])
def list_favorites():
    db = get_db()
    rows = db.execute("SELECT * FROM favorites ORDER BY created_at DESC").fetchall()
    
    favorites = []
    for r in rows:
        favorites.append({
            "id": r["id"], # データベースの内部ID
            "track_id": r["track_id"], # ★★★ track_id を正しく含める ★★★
            "name": r["name"],
            "artist": r["artist"],
            "preview_url": r["preview_url"],
            "external_url": r["external_url"],
            "image": r["image_url"]
        })
        
    return jsonify(favorites), 200

@app.route('/favorites/<track_id>', methods=['DELETE'])
def delete_favorite(track_id):
    db = get_db()
    # プレースホルダーに値を正しく渡す
    cur = db.execute("DELETE FROM favorites WHERE track_id = ?", [track_id])
    db.commit()
    if cur.rowcount == 0:
        # 削除対象が見つからなかった場合
        return jsonify({"error": "not found"}), 404
    # 削除成功
    return Response(status=204)

@app.route('/search_history', methods=['POST'])
def add_search_history():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'query required'}), 400
    db = get_db()
    db.execute(
        "INSERT INTO search_history (query) VALUES (?)",
        (query,)
    )
    db.commit()
    return jsonify({'status': 'ok'}), 201

@app.route('/search_history', methods=['GET'])
def get_search_history():
    db = get_db()
    rows = db.execute(
        "SELECT query FROM search_history ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    return jsonify([row['query'] for row in rows])

init_app(app)

if __name__ == '__main__':
    app.run(debug=True)