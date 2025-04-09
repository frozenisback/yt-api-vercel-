from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid
import requests
import hashlib
import glob
import shutil

app = Flask(__name__)

# Base directory using /tmp (Render free plan uses ephemeral storage)
BASE_TEMP_DIR = "/tmp"

# Directory for storing temporary download files (will be cleared after each request)
TEMP_DOWNLOAD_DIR = os.path.join(BASE_TEMP_DIR, "download")
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)

# Directory for storing cached audio files (persists until container restart)
CACHE_DIR = os.path.join(BASE_TEMP_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Directory for storing cached video files separately
CACHE_VIDEO_DIR = os.path.join(BASE_TEMP_DIR, "cache_video")
os.makedirs(CACHE_VIDEO_DIR, exist_ok=True)

# Maximum cache size in bytes (adjusted to 500MB for Render free plan)
MAX_CACHE_SIZE = 500 * 1024 * 1024  # 500MB

# Path to your cookies file (if needed)
COOKIES_FILE = "cookies.txt"  # Replace with your actual cookies file path if required

# Remove the external search API URL since we are now searching directly on YouTube
# SEARCH_API_URL = "https://odd-block-a945.tenopno.workers.dev/search?title="

def get_cache_key(video_url):
    """Generate a cache key from the video URL."""
    return hashlib.md5(video_url.encode('utf-8')).hexdigest()

def get_directory_size(directory):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
    return total_size

def check_cache_size_and_cleanup():
    """Check combined cache size and remove all cache files if it exceeds the threshold."""
    total_size = get_directory_size(CACHE_DIR) + get_directory_size(CACHE_VIDEO_DIR)
    if total_size > MAX_CACHE_SIZE:
        for cache_dir in [CACHE_DIR, CACHE_VIDEO_DIR]:
            for file in os.listdir(cache_dir):
                file_path = os.path.join(cache_dir, file)
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")

def download_audio(video_url):
    """
    Download audio from the given YouTube video URL with caching.
    If the audio file was previously downloaded, return the cached file.
    """
    cache_key = get_cache_key(video_url)
    cached_files = glob.glob(os.path.join(CACHE_DIR, f"{cache_key}.*"))
    if cached_files:
        return cached_files[0]

    unique_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
    ydl_opts = {
        'format': 'worstaudio/worst',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'cookiefile': COOKIES_FILE,
        'socket_timeout': 60,
        'max_memory': 450000,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            ext = info.get("ext", "m4a")
            cached_file_path = os.path.join(CACHE_DIR, f"{cache_key}.{ext}")
            shutil.move(downloaded_file, cached_file_path)
            check_cache_size_and_cleanup()  # Check cache size after adding a new file
            return cached_file_path
        except Exception as e:
            raise Exception(f"Error downloading audio: {e}")

def resolve_spotify_link(url):
    """
    If the URL is a Spotify link, use an external service to find the corresponding YouTube link.
    Otherwise, return the URL unchanged.
    """
    if "spotify.com" in url:
        # You may need to implement your own Spotify resolution if desired.
        # For now, raise an exception.
        raise Exception("Spotify links are not supported in this version.")
    return url

def download_video(video_url):
    """
    Download video (with audio) from the given YouTube video URL in 240p and worst audio quality with caching.
    If the video file was previously downloaded, return the cached file.
    """
    cache_key = hashlib.md5((video_url + "_video").encode('utf-8')).hexdigest()
    cached_files = glob.glob(os.path.join(CACHE_VIDEO_DIR, f"{cache_key}.*"))
    if cached_files:
        return cached_files[0]

    unique_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
    ydl_opts = {
        'format': 'bestvideo[height<=144]+worstaudio/worst',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'cookiefile': COOKIES_FILE,
        'socket_timeout': 60,
        'max_memory': 450000,
        'merge_output_format': 'mp4',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            cached_file_path = os.path.join(CACHE_VIDEO_DIR, f"{cache_key}.mp4")
            shutil.move(downloaded_file, cached_file_path)
            check_cache_size_and_cleanup()  # Check cache size after adding a new file
            return cached_file_path
        except Exception as e:
            raise Exception(f"Error downloading video: {e}")

@app.route('/search', methods=['GET'])
def search_video():
    """
    Search for a YouTube video directly using yt_dlp's ytsearch feature.
    Returns a list of up to 5 search results with title, video URL, duration, and thumbnail.
    """
    try:
        query = request.args.get('title')
        if not query:
            return jsonify({"error": "The 'title' parameter is required"}), 400

        # Use yt_dlp with the ytsearch protocol.
        search_query = f"ytsearch5:{query}"
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'extract_flat': True  # returns a list of video entries without further processing
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(search_query, download=False)
        
        results = []
        # Iterate over the returned entries.
        for entry in search_results.get('entries', []):
            title = entry.get('title')
            video_id = entry.get('id')
            if not video_id:
                continue
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            # Duration may be available in seconds; if not, you may leave it as None.
            duration = entry.get('duration')
            thumbnail = entry.get('thumbnail')
            results.append({
                "title": title,
                "url": video_url,
                "duration": duration,
                "thumbnail": thumbnail
            })
        
        if not results:
            return jsonify({"error": "No videos found for the given query"}), 404
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/vdown', methods=['GET'])
def download_video_endpoint():
    """
    Download video from a YouTube video URL (or search by title) in 240p with worst audio.
    Works similarly to the /download endpoint, but returns the video file.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')

        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400

        if video_title and not video_url:
            # Here you could call your search endpoint or use the search function directly.
            # For simplicity, using the search logic here:
            search_query = f"ytsearch1:{video_title}"
            ydl_opts = {
                'quiet': True,
                'skip_download': True,
                'extract_flat': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(search_query, download=False)
            entries = search_results.get('entries', [])
            if not entries:
                return jsonify({"error": "No videos found for the given query"}), 404
            video_url = f"https://www.youtube.com/watch?v={entries[0].get('id')}"

        if video_url and "spotify.com" in video_url:
            video_url = resolve_spotify_link(video_url)

        cached_file_path = download_video(video_url)

        return send_file(
            cached_file_path,
            as_attachment=True,
            download_name=os.path.basename(cached_file_path)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temporary download files only (not the caches)
        for file in os.listdir(TEMP_DOWNLOAD_DIR):
            file_path = os.path.join(TEMP_DOWNLOAD_DIR, file)
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Error deleting file {file_path}: {cleanup_error}")

@app.route('/download', methods=['GET'])
def download_audio_endpoint():
    """
    Download audio from a YouTube video URL or search for it by title and download.
    Utilizes caching so repeated downloads for the same video are avoided.
    Also supports Spotify links by resolving them.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')

        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400

        if video_title and not video_url:
            search_query = f"ytsearch1:{video_title}"
            ydl_opts = {
                'quiet': True,
                'skip_download': True,
                'extract_flat': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(search_query, download=False)
            entries = search_results.get('entries', [])
            if not entries:
                return jsonify({"error": "No videos found for the given query"}), 404
            video_url = f"https://www.youtube.com/watch?v={entries[0].get('id')}"

        if video_url and "spotify.com" in video_url:
            video_url = resolve_spotify_link(video_url)

        cached_file_path = download_audio(video_url)

        return send_file(
            cached_file_path,
            as_attachment=True,
            download_name=os.path.basename(cached_file_path)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temporary download files only (not the caches)
        for file in os.listdir(TEMP_DOWNLOAD_DIR):
            file_path = os.path.join(TEMP_DOWNLOAD_DIR, file)
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Error deleting file {file_path}: {cleanup_error}")

@app.route('/')
def home():
    return """
    <h1>🎶 YouTube Audio Downloader API</h1>
    <p>Use this API to search and download audio from YouTube videos.</p>
    <p><strong>Endpoints:</strong></p>
    <ul>
        <li><strong>/search</strong>: Search for a video by title (now using direct YouTube search via yt_dlp).</li>
        <li><strong>/download</strong>: Download audio by URL or search for a title and download.</li>
        <li><strong>/vdown</strong>: Download video (240p + worst audio) by URL or search for a title and download.</li>
    </ul>
    <p>Examples:</p>
    <ul>
        <li>Search: <code>/search?title=Your%20Favorite%20Song</code></li>
        <li>Download by URL (audio): <code>/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ</code></li>
        <li>Download by Title (audio): <code>/download?title=Your%20Favorite%20Song</code></li>
        <li>Download by URL (video): <code>/vdown?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ</code></li>
    </ul>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)


