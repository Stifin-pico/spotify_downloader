import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp as youtube_dl
import sys
import threading
import json
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TPE2, TDRC, TRCK
import tempfile
import time
import subprocess
import shutil
from pathlib import Path

# User-visible text variables
title = "Spotify Downloader (MORE DEJ PÍSNIČKY)"
menu_customize = "Přizbůsobit (i'm not like others-)"
menu_set_background_image = "Dej si obrázek na pozadí"
menu_set_background_color = "Solid barva na pozadí"
menu_reset_settings = "Zpátky normalní nastavení"
label_url = "Spotify NEBO YouTube odkaz"
label_destination = "Kam to chceš?:"
button_browse = "Ukaž soubory!"
button_download = "Dej to sem! (stáhnout)"

# Spotify API credentials
SPOTIPY_CLIENT_ID = 'a64d1e915ed4406ba8120508c25529fd'
SPOTIPY_CLIENT_SECRET = '3eba9655c0404c6395705b49ef2ee77f'

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID,
                                                           client_secret=SPOTIPY_CLIENT_SECRET))

# Global metadata registry for aggressive metadata preservation
metadata_registry = {}

def print_alert(type, message):
    """Print alerts in a format that Electron can parse"""
    print(f"ALERT:{type}:{message}", flush=True)

def is_youtube_url(url):
    """Check if URL is a YouTube URL"""
    youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com']
    return any(domain in url for domain in youtube_domains)

def extract_id_from_url(spotify_url):
    """Extract Spotify ID and type from URL"""
    if 'track/' in spotify_url:
        track_id = spotify_url.split('track/')[1].split('?')[0]
        return 'track', track_id
    elif 'album/' in spotify_url:
        album_id = spotify_url.split('album/')[1].split('?')[0]
        return 'album', album_id
    elif 'playlist/' in spotify_url:
        playlist_id = spotify_url.split('playlist/')[1].split('?')[0]
        return 'playlist', playlist_id
    else:
        raise ValueError("Unsupported Spotify URL format")

def sanitize_filename(filename):
    """Sanitize filename for safe file system storage"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename

def get_track_info(url):
    """Extract track/album information from Spotify URL without downloading"""
    try:
        if is_youtube_url(url):
            # For YouTube, try to extract title
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                uploader = info.get('uploader', 'Unknown')
                return f"YOUTUBE_INFO:{title}|{uploader}"
        
        # Handle Spotify URLs
        url_type, spotify_id = extract_id_from_url(url)
        
        if url_type == 'track':
            track = sp.track(spotify_id)
            title = track['name']
            artist = track['artists'][0]['name']
            return f"TRACK_INFO:{title}|{artist}"
            
        elif url_type == 'album':
            album = sp.album(spotify_id)
            album_name = album['name']
            artist = album['artists'][0]['name']
            track_count = album['total_tracks']
            return f"ALBUM_INFO:{album_name}|{artist}|{track_count} tracks"
            
        elif url_type == 'playlist':
            playlist = sp.playlist(spotify_id)
            playlist_name = playlist['name']
            owner = playlist['owner']['display_name']
            track_count = playlist['tracks']['total']
            return f"PLAYLIST_INFO:{playlist_name}|{owner}|{track_count} tracks"
            
    except Exception as e:
        return f"ERROR:Unable to fetch info: {str(e)}"

def store_metadata_in_registry(filename_base, title, artist, album=None):
    """Store metadata in global registry using sanitized filename as key"""
    sanitized_key = sanitize_filename(filename_base)
    metadata_registry[sanitized_key] = {
        'title': title,
        'artist': artist,
        'album': album or 'Unknown Album',
        'stored_at': time.time()
    }
    print(f"REGISTRY: Stored metadata for '{sanitized_key}': {title} by {artist}")

def get_metadata_from_registry(filename_base):
    """Retrieve metadata from global registry"""
    sanitized_key = sanitize_filename(filename_base)
    if sanitized_key in metadata_registry:
        metadata = metadata_registry[sanitized_key]
        print(f"REGISTRY: Retrieved metadata for '{sanitized_key}'")
        return metadata
    
    # Try fuzzy matching for slight filename variations
    for key in metadata_registry.keys():
        if sanitized_key.lower() in key.lower() or key.lower() in sanitized_key.lower():
            metadata = metadata_registry[key]
            print(f"REGISTRY: Fuzzy matched '{sanitized_key}' to '{key}'")
            return metadata
    
    print(f"REGISTRY: No metadata found for '{sanitized_key}'")
    return None

def force_metadata_assignment(file_path, title, artist, album):
    """Aggressively force metadata assignment using multiple attempts"""
    print(f"FORCE: Starting aggressive metadata assignment for {os.path.basename(file_path)}")
    
    success = False
    attempts = 0
    max_attempts = 5
    
    while not success and attempts < max_attempts:
        attempts += 1
        print(f"FORCE: Attempt {attempts}/{max_attempts}")
        
        try:
            # Method 1: Standard mutagen approach
            audio_file = MP3(file_path, ID3=ID3)
            
            # Ensure ID3 tag exists
            if audio_file.tags is None:
                audio_file.add_tags()
                print(f"FORCE: Added new ID3 tags")
            
            # Force set all metadata fields
            audio_file.tags.add(TIT2(encoding=3, text=title))
            audio_file.tags.add(TPE1(encoding=3, text=artist))
            audio_file.tags.add(TALB(encoding=3, text=album))
            audio_file.tags.add(TPE2(encoding=3, text=artist))  # Album artist
            
            # Save with maximum compatibility
            audio_file.save(v2_version=3, v1=2)
            
            # Verify the metadata was actually written
            verification_file = MP3(file_path)
            if (verification_file.tags and 
                verification_file.tags.get('TIT2') and 
                str(verification_file.tags.get('TIT2').text[0]) == title):
                print(f"FORCE: SUCCESS! Metadata verified for attempt {attempts}")
                success = True
            else:
                print(f"FORCE: Verification failed for attempt {attempts}")
                time.sleep(0.5)  # Brief pause before retry
                
        except Exception as e:
            print(f"FORCE: Attempt {attempts} failed: {e}")
            time.sleep(0.5)
    
    if success:
        print(f"FORCE: Metadata assignment completed successfully!")
    else:
        print(f"FORCE: Failed to assign metadata after {max_attempts} attempts")
    
    return success

def detect_metadata_tools():
    """Detect available external metadata CLI tools"""
    tools = {
        'kid3-cli': shutil.which('kid3-cli') is not None,
        'eyeD3': shutil.which('eyeD3') is not None,
        'id3v2': shutil.which('id3v2') is not None,
        'mid3v2': shutil.which('mid3v2') is not None,
        'ffmpeg': shutil.which('ffmpeg') is not None
    }
    
    available = [tool for tool, available in tools.items() if available]
    print(f"TOOLS: Available external metadata tools: {available}")
    return tools

def apply_metadata_with_kid3(file_path, title, artist, album):
    """Apply metadata using kid3-cli"""
    try:
        commands = [
            ['kid3-cli', '-c', f'set title "{title}"', file_path],
            ['kid3-cli', '-c', f'set artist "{artist}"', file_path],
            ['kid3-cli', '-c', f'set album "{album}"', file_path]
        ]
        
        for cmd in commands:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                print(f"TOOL: kid3-cli error: {result.stderr}")
                return False
        
        print(f"TOOL: kid3-cli successfully applied metadata")
        return True
    except Exception as e:
        print(f"TOOL: kid3-cli failed: {e}")
        return False

def apply_metadata_with_eyeD3(file_path, title, artist, album):
    """Apply metadata using eyeD3"""
    try:
        cmd = [
            'eyeD3',
            '--title', title,
            '--artist', artist,
            '--album', album,
            '--remove-all-comments',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"TOOL: eyeD3 successfully applied metadata")
            return True
        else:
            print(f"TOOL: eyeD3 error: {result.stderr}")
            return False
    except Exception as e:
        print(f"TOOL: eyeD3 failed: {e}")
        return False

def apply_metadata_with_id3v2(file_path, title, artist, album):
    """Apply metadata using id3v2"""
    try:
        cmd = [
            'id3v2',
            '--TIT2', title,
            '--TPE1', artist,
            '--TALB', album,
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"TOOL: id3v2 successfully applied metadata")
            return True
        else:
            print(f"TOOL: id3v2 error: {result.stderr}")
            return False
    except Exception as e:
        print(f"TOOL: id3v2 failed: {e}")
        return False

def apply_metadata_with_mid3v2(file_path, title, artist, album):
    """Apply metadata using mid3v2"""
    try:
        cmd = [
            'mid3v2',
            '--TIT2', title,
            '--TPE1', artist,
            '--TALB', album,
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"TOOL: mid3v2 successfully applied metadata")
            return True
        else:
            print(f"TOOL: mid3v2 error: {result.stderr}")
            return False
    except Exception as e:
        print(f"TOOL: mid3v2 failed: {e}")
        return False

def apply_metadata_with_ffmpeg(file_path, title, artist, album):
    """Apply metadata using ffmpeg"""
    try:
        temp_file = file_path + '.tmp.mp3'
        cmd = [
            'ffmpeg',
            '-i', file_path,
            '-c', 'copy',
            '-metadata', f'title={title}',
            '-metadata', f'artist={artist}',
            '-metadata', f'album={album}',
            '-y',  # Overwrite output file
            temp_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            # Replace original file with metadata-updated version
            os.replace(temp_file, file_path)
            print(f"TOOL: ffmpeg successfully applied metadata")
            return True
        else:
            print(f"TOOL: ffmpeg error: {result.stderr}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return False
    except Exception as e:
        print(f"TOOL: ffmpeg failed: {e}")
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def ultimate_metadata_assignment(file_path, title, artist, album):
    """Ultimate metadata assignment using Python + external tools"""
    print(f"ULTIMATE: Starting ultimate metadata assignment for {os.path.basename(file_path)}")
    
    # First try aggressive Python approach
    if force_metadata_assignment(file_path, title, artist, album):
        return True
    
    print("ULTIMATE: Python approach failed, trying external tools...")
    
    # Get available external tools
    available_tools = detect_metadata_tools()
    
    # Try external tools in order of preference
    tool_functions = [
        ('kid3-cli', apply_metadata_with_kid3),
        ('eyeD3', apply_metadata_with_eyeD3),
        ('mid3v2', apply_metadata_with_mid3v2),
        ('id3v2', apply_metadata_with_id3v2),
        ('ffmpeg', apply_metadata_with_ffmpeg)
    ]
    
    for tool_name, tool_function in tool_functions:
        if available_tools.get(tool_name, False):
            print(f"ULTIMATE: Trying {tool_name}...")
            if tool_function(file_path, title, artist, album):
                print(f"ULTIMATE: SUCCESS with {tool_name}!")
                return True
    
    print("ULTIMATE: All methods failed!")
    return False

def ultra_force_metadata_from_registry(download_dir):
    """Ultra-aggressive metadata forcing using registry data"""
    global metadata_registry
    
    try:
        mp3_files = [f for f in os.listdir(download_dir) if f.endswith('.mp3')]
        print(f"ULTRA: Starting ultra-aggressive metadata forcing for {len(mp3_files)} files")
        print(f"ULTRA: Registry contains {len(metadata_registry)} entries")
        
        forced_count = 0
        for mp3_file in mp3_files:
            file_path = os.path.join(download_dir, mp3_file)
            filename_base = os.path.splitext(mp3_file)[0]
            
            # Try to get metadata from registry
            metadata = get_metadata_from_registry(filename_base)
            if metadata:
                print(f"ULTRA: Forcing metadata for {mp3_file}")
                if ultimate_metadata_assignment(file_path, metadata['title'], metadata['artist'], metadata['album']):
                    forced_count += 1
                    print(f"ULTRA: Successfully forced metadata for {mp3_file}")
                else:
                    print(f"ULTRA: Failed to force metadata for {mp3_file}")
            else:
                print(f"ULTRA: No registry data for {mp3_file}")
        
        print(f"ULTRA: Forced metadata for {forced_count}/{len(mp3_files)} files")
        
    except Exception as e:
        print(f"ULTRA: Error during ultra-force operation: {e}")

def download_youtube_video(url, download_dir):
    """Download YouTube video and convert to MP3"""
    print(f"INFO: Starting YouTube download for: {url}")
    
    # Define potential FFmpeg paths
    ffmpeg_paths = [
        'ffmpeg',  # System PATH
        'ffmpeg.exe',  # System PATH (Windows)
        os.path.join(os.getcwd(), 'ffmpeg.exe'),  # Current directory
        r'C:\ffmpeg\bin\ffmpeg.exe',  # Common Windows location
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',  # Another common location
    ]
    
    ffmpeg_location = None
    for path in ffmpeg_paths:
        try:
            # Test if ffmpeg is accessible
            result = subprocess.run([path, '-version'], capture_output=True, timeout=5, text=True)
            if result.returncode == 0:
                if path in ['ffmpeg', 'ffmpeg.exe']:
                    ffmpeg_location = None  # Use system PATH
                else:
                    ffmpeg_location = os.path.dirname(path)
                print(f"INFO: Found FFmpeg at: {path}")
                break
        except Exception as e:
            print(f"DEBUG: FFmpeg test failed for {path}: {e}")
            continue
    
    if not ffmpeg_location and 'ffmpeg' not in [os.path.basename(p) for p in ffmpeg_paths if os.path.basename(p) in ['ffmpeg', 'ffmpeg.exe']]:
        print("ERROR: FFmpeg not found in any location!")
        print("ERROR: Cannot convert audio to MP3 format!")
        print("ERROR: Please install FFmpeg or place it in the project folder")
        return  # Exit early if no FFmpeg found
    
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'writethumbnail': False,
        'writeinfojson': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
    }
    
    if ffmpeg_location:
        ydl_opts['ffmpeg_location'] = ffmpeg_location
    
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            # Get video info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown Title')
            uploader = info.get('uploader', 'Unknown Artist')
            
            # Store in registry
            sanitized_title = sanitize_filename(title)
            store_metadata_in_registry(sanitized_title, title, uploader)
            
            print(f"INFO: Downloading: {title} by {uploader}")
            
            # Download the video
            ydl.download([url])
            
            print(f"SUCCESS: Downloaded YouTube video: {title}")
            
            # Apply ultra-aggressive metadata forcing
            ultra_force_metadata_from_registry(download_dir)
            
    except Exception as e:
        print(f"ERROR: Failed to download YouTube video: {str(e)}")

def download_spotify_track(track_id, download_dir):
    """Download a single Spotify track"""
    try:
        track = sp.track(track_id)
        title = track['name']
        artist = track['artists'][0]['name']
        album = track['album']['name']
        
        # Store metadata in registry
        sanitized_filename = sanitize_filename(f"{artist} - {title}")
        store_metadata_in_registry(sanitized_filename, title, artist, album)
        
        print(f"INFO: Searching for: {artist} - {title}")
        
        search_query = f"{artist} {title}"
        youtube_url = search_youtube(search_query)
        
        if youtube_url:
            print(f"INFO: Found YouTube match: {youtube_url}")
            download_youtube_video(youtube_url, download_dir)
        else:
            print(f"ERROR: No YouTube match found for: {artist} - {title}")
            
    except Exception as e:
        print(f"ERROR: Failed to download track {track_id}: {str(e)}")

def search_youtube(query):
    """Search YouTube for a query and return the first result URL"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch1:',
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(query, download=False)
            
            if 'entries' in search_results and search_results['entries']:
                video_url = search_results['entries'][0]['webpage_url']
                return video_url
            else:
                return None
                
    except Exception as e:
        print(f"ERROR: YouTube search failed: {str(e)}")
        return None

def download_spotify_album(album_id, download_dir):
    """Download all tracks from a Spotify album"""
    try:
        album = sp.album(album_id)
        album_name = album['name']
        album_artist = album['artists'][0]['name']
        
        print(f"INFO: Downloading album: {album_name} by {album_artist}")
        
        tracks = album['tracks']['items']
        for track in tracks:
            track_id = track['id']
            download_spotify_track(track_id, download_dir)
            
    except Exception as e:
        print(f"ERROR: Failed to download album {album_id}: {str(e)}")

def download_spotify_playlist(playlist_id, download_dir):
    """Download all tracks from a Spotify playlist"""
    try:
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']
        
        print(f"INFO: Downloading playlist: {playlist_name}")
        
        tracks = playlist['tracks']['items']
        for item in tracks:
            if item['track'] and item['track']['id']:
                track_id = item['track']['id']
                download_spotify_track(track_id, download_dir)
                
    except Exception as e:
        print(f"ERROR: Failed to download playlist {playlist_id}: {str(e)}")

def download_music(url, destination):
    """Main download function"""
    try:
        if not os.path.exists(destination):
            os.makedirs(destination)
            
        if is_youtube_url(url):
            download_youtube_video(url, destination)
        else:
            # Handle Spotify URLs
            url_type, spotify_id = extract_id_from_url(url)
            
            if url_type == 'track':
                download_spotify_track(spotify_id, destination)
            elif url_type == 'album':
                download_spotify_album(spotify_id, destination)
            elif url_type == 'playlist':
                download_spotify_playlist(spotify_id, destination)
                
        print("DOWNLOAD_COMPLETE")
        
    except Exception as e:
        print(f"ERROR: Download failed: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python spotify.py <url> <destination>")
        sys.exit(1)
    
    url = sys.argv[1]
    destination = sys.argv[2]
    
    download_music(url, destination)