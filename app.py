from flask import Flask, redirect, request, jsonify, render_template
from dotenv import load_dotenv
import requests
import urllib.parse
import os
import base64

load_dotenv()

app = Flask(__name__)

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

@app.route('/search',methods=["GET"])
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "No search query provided"}), 400
    
    token = get_token()
    url = f"https://api.spotify.com/v1/search?q={query}&type=track&limit=5"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    tracks = []

    for item in data.get("tracks", {}).get("items", []):
        tracks.append({
            "name": item["name"],
            "artist": item["artists"][0]["name"],
            "preview_url": item["preview_url"],
            "external_url": item["external_urls"]["spotify"],
            "image": item["album"]["images"][1]["url"] if item["album"]["images"] else None
        })

    return jsonify(tracks)

if __name__ == '__main__':
    app.run(debug=True)