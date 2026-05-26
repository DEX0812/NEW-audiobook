import os
import re
import uuid
import asyncio
import warnings
import concurrent.futures
import subprocess
import shutil
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from pydub import AudioSegment
import edge_tts

# Suppress EbookLib user warnings (e.g., about missing spine, DC namespace, etc.)
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

async def tts_chunk(text: str, voice: str, output_path: str):
    """
    Asynchronously invokes edge-tts to synthesize text chunk to an MP3.
    """
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def run_async(coro):
    """
    Helper function to run async coroutines safely from synchronous code,
    preventing 'Event loop is already running' errors in environments like Streamlit.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        # Running inside an existing event loop: delegate to a background thread
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        # No event loop running in the thread, run standard asyncio execution
        return asyncio.run(coro)

def chunk_text(text: str, max_chars: int = 4000) -> list:
    """
    Splits the extracted text into manageable chunks of max_chars.
    Ensures it splits cleanly at sentence boundaries (.!?) so sentences aren't cut in half.
    
    Args:
        text (str): The clean raw text to be chunked.
        max_chars (int): The maximum character length of each chunk.
        
    Returns:
        list: A list of string chunks, each <= max_chars.
    """
    if not text:
        return []
    
    # Normalize multiple whitespace characters into single spaces
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Split text by sentence boundaries (using positive lookbehind to preserve punctuation)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = []
    current_len = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sentence_len = len(sentence)
        
        # Handle cases where a single sentence is extremely long (exceeds max_chars)
        if sentence_len > max_chars:
            # Flush current chunk first if it contains text
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0
                
            # Split the ultra-long sentence by character limits
            start = 0
            while start < sentence_len:
                end = start + max_chars
                # Find last space in the slice to break cleanly at word level if possible
                if end < sentence_len:
                    last_space = sentence.rfind(' ', start, end)
                    if last_space > start:
                        end = last_space
                
                chunks.append(sentence[start:end].strip())
                start = end
            continue
            
        # Normal sentences fitting within limits
        # Check if adding the next sentence exceeds the max limit (+1 for joining space)
        if current_len + sentence_len + (1 if current_chunk else 0) > max_chars:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_len = sentence_len
        else:
            current_chunk.append(sentence)
            current_len += sentence_len + (1 if len(current_chunk) > 1 else 0)
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

def scrape_novel_to_epub(url: str, max_chapters: int = 5, progress_callback=None) -> str:
    """
    Scrapes a web novel from a given URL using web-novel-scraper,
    saving it to a temporary EPUB file.
    
    Args:
        url (str): The Table of Contents URL of the web novel.
        max_chapters (int): The maximum chapters to scrape (defaults to 5 to keep things fast).
        progress_callback (callable): A progress reporting callback.
        
    Returns:
        str: Absolute path to the generated EPUB file.
    """
    if progress_callback:
        progress_callback(0.02, "Initializing novel scraper project...")
        
    # Generate unique ID for this scrape run to avoid collisions
    unique_id = str(uuid.uuid4())[:8]
    novel_title = f"ScrapedNovel_{unique_id}"
    
    # Store inside our project temp directory
    temp_novel_dir = os.path.join(os.getcwd(), "temp_uploads", f"novel_{unique_id}")
    os.makedirs(temp_novel_dir, exist_ok=True)
    
    try:
        # Step 1: Create the novel project
        if progress_callback:
            progress_callback(0.20, f"Connecting to {url} and creating scraper metadata...")
            
        cmd_create = [
            "python", "-m", "web_novel_scraper",
            "-nb", temp_novel_dir,
            "create-novel",
            "-t", novel_title,
            "--toc-main-url", url
        ]
        
        # Run process
        result_create = subprocess.run(
            cmd_create,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        # Step 2: Download chapters and save to EPUB
        if progress_callback:
            progress_callback(0.50, f"Scraping chapters from novel (Max Limit: {max_chapters}). This may take a minute...")
            
        cmd_save = [
            "python", "-m", "web_novel_scraper",
            "-nb", temp_novel_dir,
            "save-novel-to-epub",
            "-t", novel_title,
            "--sync-toc",
            "--end-chapter", str(max_chapters)
        ]
        
        result_save = subprocess.run(
            cmd_save,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        # Step 3: Locate the generated EPUB file in the novel folder
        if progress_callback:
            progress_callback(0.90, "Locating generated EPUB book...")
            
        epub_files = [f for f in os.listdir(temp_novel_dir) if f.endswith(".epub")]
        if not epub_files:
            raise FileNotFoundError("Scraper finished but no .epub file was created in the output directory.")
            
        # Copy the epub file up to the temp_uploads folder directly for easier processing
        generated_epub_name = epub_files[0]
        src_epub_path = os.path.join(temp_novel_dir, generated_epub_name)
        
        dest_epub_name = f"{novel_title}.epub"
        dest_epub_path = os.path.join(os.getcwd(), "temp_uploads", dest_epub_name)
        
        shutil.copy2(src_epub_path, dest_epub_path)
        
        if progress_callback:
            progress_callback(1.0, f"Successfully scraped novel! Saved as {dest_epub_name}")
            
        return dest_epub_path
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr or e.stdout or str(e)
        raise RuntimeError(f"Novel scraper process failed: {error_msg}")
    finally:
        # Cleanup the scraper raw HTML directories to save server space
        try:
            shutil.rmtree(temp_novel_dir)
        except Exception:
            pass

def process_epub(file_path: str, voice: str = 'en-US-AriaNeural', progress_callback=None) -> dict:
    """
    Processes an EPUB file, synthesizes individual text chunks to audio via edge-tts,
    and stitches them together into a final Audiobook file.
    
    Args:
        file_path (str): Path to the uploaded EPUB file.
        voice (str): The voice model to be used by edge-tts (default: 'en-US-AriaNeural').
        progress_callback (callable): A callback to update progress in Streamlit.
                                      Should accept (percent: float, status_text: str).
                                      
    Returns:
        dict: A dictionary containing book metadata, clean text, and output audiobook file path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File at {file_path} not found.")
        
    if progress_callback:
        progress_callback(0.05, "Opening EPUB file...")
        
    # Read the EPUB book
    book = epub.read_epub(file_path)
    
    # Extract Title metadata
    title = "Untitled Book"
    metadata_title = book.get_metadata('DC', 'title')
    if metadata_title:
        title = metadata_title[0][0]
        
    # Extract Author metadata
    author = "Unknown Author"
    metadata_creator = book.get_metadata('DC', 'creator')
    if metadata_creator:
        author = metadata_creator[0][0]
        
    if progress_callback:
        progress_callback(0.10, f"Reading spine structure of '{title}'...")
        
    # Get document items (chapters / pages)
    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    total_items = len(items)
    
    if total_items == 0:
        raise ValueError("The uploaded EPUB contains no document items.")
        
    raw_texts = []
    
    # 1. Extraction phase (10% to 25%)
    for idx, item in enumerate(items):
        if item is None:
            continue
        item_name = item.get_name()
        percent = 0.10 + (0.15 * ((idx + 1) / total_items))
        if progress_callback:
            progress_callback(percent, f"Extracting text from item {idx + 1}/{total_items}: {item_name}...")
            
        try:
            html_content = item.get_content()
            if not html_content:
                continue
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script_or_style in soup(["script", "style"]):
                script_or_style.decompose()
                
            # Get text and clean it
            text = soup.get_text()
            
            # Clean up line endings/spacing
            lines = (line.strip() for line in text.splitlines())
            chunks_lines = (phrase.strip() for line in lines for phrase in line.split("  "))
            cleaned_text = '\n'.join(chunk for chunk in chunks_lines if chunk)
            
            if cleaned_text:
                raw_texts.append(cleaned_text)
        except Exception:
            continue
            
    if progress_callback:
        progress_callback(0.26, "Joining extracted chapters and processing sentence-aware chunks...")
        
    full_text = "\n\n".join(raw_texts)
    chunks = chunk_text(full_text, max_chars=4000)
    total_chunks = len(chunks)
    
    if total_chunks == 0:
        raise ValueError("No readable text could be extracted from the EPUB file.")
        
    # Set up dedicated unique temporary audio chunks folder
    unique_id = str(uuid.uuid4())[:8]
    chunks_dir = os.path.join(os.path.dirname(file_path), f"audio_chunks_{unique_id}")
    os.makedirs(chunks_dir, exist_ok=True)
    
    chunk_files = []
    
    # 2. Voice synthesis phase (30% to 80%)
    for idx, chunk in enumerate(chunks):
        percent = 0.30 + (0.50 * ((idx + 1) / total_chunks))
        if progress_callback:
            progress_callback(percent, f"Generating speech synthesis (edge-tts) for chunk {idx + 1}/{total_chunks}...")
            
        chunk_file_path = os.path.join(chunks_dir, f"chunk_{idx:04d}.mp3")
        try:
            run_async(tts_chunk(chunk, voice, chunk_file_path))
            chunk_files.append(chunk_file_path)
        except Exception as e:
            # Clean up what has been generated so far before raising error
            for f in chunk_files:
                try: os.remove(f)
                except Exception: pass
            try: os.rmdir(chunks_dir)
            except Exception: pass
            raise RuntimeError(f"Error generating voice snippet for chunk {idx+1}: {str(e)}")
            
    # 3. Concatenation phase (80% to 95%)
    if progress_callback:
        progress_callback(0.80, "Syntheses complete. Concatenating audio snippets...")
        
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_audio_path = os.path.join(os.path.dirname(file_path), f"{base_name}.mp3")
    
    # Try using Pydub first
    pydub_success = False
    try:
        combined_audio = AudioSegment.empty()
        total_files = len(chunk_files)
        
        for idx, chunk_file in enumerate(chunk_files):
            percent = 0.80 + (0.10 * ((idx + 1) / total_files))
            if progress_callback:
                progress_callback(percent, f"Stitching audio chunk {idx + 1}/{total_files} (Pydub)...")
            
            if os.path.exists(chunk_file):
                segment = AudioSegment.from_mp3(chunk_file)
                combined_audio += segment
                
        if progress_callback:
            progress_callback(0.92, f"Exporting stitched audiobook (Pydub): {base_name}.mp3...")
            
        combined_audio.export(output_audio_path, format="mp3")
        pydub_success = True
    except Exception as pydub_err:
        if progress_callback:
            progress_callback(0.82, "Pydub/FFmpeg not found. Falling back to robust direct binary stream merging...")
            
        try:
            total_files = len(chunk_files)
            with open(output_audio_path, "wb") as dest:
                for idx, chunk_file in enumerate(chunk_files):
                    percent = 0.82 + (0.13 * ((idx + 1) / total_files))
                    if progress_callback:
                        progress_callback(percent, f"Merging stream chunk {idx + 1}/{total_files} (Binary)...")
                    if os.path.exists(chunk_file):
                        with open(chunk_file, "rb") as src:
                            dest.write(src.read())
        except Exception as binary_err:
            # Clean up and raise error
            for f in chunk_files:
                try: os.remove(f)
                except Exception: pass
            try: os.rmdir(chunks_dir)
            except Exception: pass
            raise RuntimeError(f"Failed to stitch MP3 files using both Pydub and binary fallback: {str(binary_err)}")
        
    # 4. Cleanup phase (96% to 100%)
    if progress_callback:
        progress_callback(0.98, "Cleaning up temporary chunk files...")
        
    for chunk_file in chunk_files:
        try:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)
        except Exception:
            pass
            
    try:
        os.rmdir(chunks_dir)
    except Exception:
        pass
        
    if progress_callback:
        progress_callback(1.0, "Audiobook generated successfully!")
        
    return {
        "title": title,
        "author": author,
        "full_text": full_text,
        "chunks": chunks,
        "total_chars": len(full_text),
        "total_chunks": total_chunks,
        "audio_path": output_audio_path
    }
