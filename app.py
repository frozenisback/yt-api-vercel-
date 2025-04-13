import os
import requests
from http.cookiejar import MozillaCookieJar
from flask import Flask, request, jsonify
from youtube_search import YoutubeSearch

# ----- Load Cookies from a Netscape Cookie File and Patch requests.get -----
cookie_file = 'cookies.txt'
if os.path.exists(cookie_file):
    cookie_jar = MozillaCookieJar(cookie_file)
    # Load cookies from the file; ignore discard and expiration for demo purposes
    cookie_jar.load(ignore_discard=True, ignore_expires=True)
    
    # Create a session and assign the loaded cookies
    session = requests.Session()
    session.cookies = cookie_jar

    # Preserve the original requests.get function
    original_get = requests.get

    def get_with_cookies(url, **kwargs):
        # Ensure that cookies are passed with each GET request
        kwargs.setdefault("cookies", session.cookies)
        return original_get(url, **kwargs)

    # Replace requests.get with our custom version
    requests.get = get_with_cookies

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"message": "✅ YouTube Search API is alive!"})

@app.route('/search', methods=['GET'])
def search():
    # Retrieve and validate the 'title' query parameter.
    title = request.args.get('title', '').strip()
    if not title:
        return jsonify({"error": "Missing 'title' query parameter."}), 400

    try:
        # Perform the YouTube search (limit to 10 results)
        results = YoutubeSearch(title, max_results=10).to_dict()

        if not results:
            return jsonify({"error": "No results found."}), 404

        # Use only the first video result
        first_video = results[0]
        video_data = {
            "title": first_video.get("title"),
            # The thumbnails field is returned as a list; we take the first thumbnail.
            "thumbnail": first_video.get("thumbnails", [None])[0],
            "duration": first_video.get("duration"),
            # Construct the full video URL using the provided URL suffix.
            "link": "https://www.youtube.com" + first_video.get("url_suffix", "")
        }

        return jsonify(video_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Use the port specified in environment variables or default to 5000.
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 so the server is accessible externally.
    app.run(host='0.0.0.0', port=port, debug=True)


