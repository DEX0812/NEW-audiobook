import sys
import os
import urllib.parse
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 1. Solve Vercel Read-Only restriction
# Vercel serverless environment is read-only except for /tmp.
# By shifting directory to /tmp, the relative paths used inside
# converter.py (e.g. os.getcwd() + "/temp_uploads") resolve to writeable paths.
if os.environ.get("VERCEL") or "VERCEL" in os.environ:
    os.chdir("/tmp")

# Create local temp_uploads dir in active working dir
os.makedirs(os.path.join(os.getcwd(), "temp_uploads"), exist_ok=True)

# 2. Add root path to sys.path so we can import converter.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from converter import process_epub, scrape_novel_to_epub
except ImportError as e:
    raise ImportError(f"Could not import converter.py: {str(e)}")

app = FastAPI(title="EchoBook API", description="Serverless backend for Audiobook Maker")

# 3. Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConvertRequest(BaseModel):
    url: str
    max_chapters: int = 5
    voice: str = "en-US-AriaNeural"

def cleanup_files(epub_path: str, mp3_path: str = None):
    """
    Cleans up local temporary files to save serverless instance storage space.
    """
    try:
        if epub_path and os.path.exists(epub_path):
            os.remove(epub_path)
        # We do not delete the mp3_path immediately as it needs to be sent in the response,
        # but the serverless runtime will discard it after the function terminates.
    except Exception:
        pass

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "EchoBook API", "cwd": os.getcwd()}

@app.get("/api/voices")
def get_voices():
    return {
        "en-US-AriaNeural": "Aria (US Female - Standard)",
        "en-US-GuyNeural": "Guy (US Male - Standard)",
        "en-US-JennyNeural": "Jenny (US Female - Premium Natural)",
        "en-GB-SoniaNeural": "Sonia (UK Female - British)",
        "en-GB-RyanNeural": "Ryan (UK Male - British)",
        "en-AU-NatashaNeural": "Natasha (Australia Female - Australian)",
        "en-IN-NeerjaNeural": "Neerja (India Female - Indian)"
    }

@app.post("/api/convert")
async def convert_novel(req: ConvertRequest, background_tasks: BackgroundTasks):
    if not req.url:
        raise HTTPException(status_code=400, detail="Web Novel Table of Contents URL is required.")
        
    try:
        # Step 1: Scrape novel to local temporary EPUB file
        # The scrape_novel_to_epub function will output files to writeable directory (/tmp)
        temp_epub_path = scrape_novel_to_epub(
            url=req.url,
            max_chapters=req.max_chapters,
            progress_callback=None  # None in serverless API, progress handled via client-side animations
        )
        
        # Step 2: Convert the temporary EPUB file to Audiobook chunks and stitch them
        result = process_epub(
            file_path=temp_epub_path,
            voice=req.voice,
            progress_callback=None
        )
        
        # Step 3: Register background cleanup task for EPUB file
        background_tasks.add_task(cleanup_files, temp_epub_path)
        
        # Verify the mp3 file exists
        if not os.path.exists(result["audio_path"]):
            raise HTTPException(status_code=500, detail="Failed to locate generated audiobook file on disk.")
            
        # Step 4: Stream response with custom metadata headers
        safe_title = urllib.parse.quote(result["title"])
        safe_author = urllib.parse.quote(result["author"])
        
        headers = {
            "X-Audiobook-Title": safe_title,
            "X-Audiobook-Author": safe_author,
            "X-Audiobook-Total-Chars": str(result["total_chars"]),
            "X-Audiobook-Total-Chunks": str(result["total_chunks"]),
            "Access-Control-Expose-Headers": "X-Audiobook-Title, X-Audiobook-Author, X-Audiobook-Total-Chars, X-Audiobook-Total-Chunks"
        }
        
        return FileResponse(
            path=result["audio_path"],
            media_type="audio/mpeg",
            filename=f"{result['title']}.mp3",
            headers=headers
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")

# 4. Conditionally mount static files for local testing
# This maps the public/ directory to / locally, mirroring Vercel's CDN routing.
if not os.environ.get("VERCEL"):
    from fastapi.staticfiles import StaticFiles
    try:
        app.mount("/", StaticFiles(directory="public", html=True), name="public")
    except Exception as mount_err:
        print(f"Warning: Could not mount static files directory: {str(mount_err)}")

