import streamlit as st
import os
from converter import process_epub, scrape_novel_to_epub

# Set page configuration with a modern look and custom title/icon
st.set_page_config(
    page_title="EchoBook - EPUB to Audiobook Converter",
    page_icon="🎧",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom premium CSS styling for a modern, glassmorphism aesthetic
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
    
    /* Main container styling */
    .main .block-container {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        padding-top: 3rem;
        padding-bottom: 3rem;
    }
    
    /* Gradient Title */
    .title-container {
        text-align: center;
        margin-bottom: 2rem;
    }
    .gradient-text {
        font-size: 3.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #FF6B6B 0%, #4D96FF 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        font-size: 1.15rem;
        color: #6c757d;
        font-weight: 400;
        margin-top: 0;
        line-height: 1.5;
    }
    
    /* Elegant card styling */
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 24px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.05);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        margin-top: 15px;
        margin-bottom: 20px;
    }
    
    /* Custom divider line with gradient */
    .gradient-divider {
        height: 4px;
        background: linear-gradient(90deg, rgba(255,107,107,1) 0%, rgba(77,150,255,1) 100%);
        border-radius: 10px;
        margin: 1.5rem auto;
        width: 80px;
    }
    
    /* Centered footer */
    .footer {
        text-align: center;
        margin-top: 4rem;
        font-size: 0.85rem;
        color: #8c8c8c;
    }
    
    /* Wave animation placeholder */
    .wave-container {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 6px;
        height: 40px;
        margin: 20px 0;
    }
    .wave-bar {
        width: 4px;
        height: 10px;
        background-color: #4D96FF;
        border-radius: 2px;
        animation: quiet 1.2s ease-in-out infinite alternate;
    }
    .wave-bar:nth-child(2) { animation-delay: 0.2s; height: 22px; background-color: #6C5DD3; }
    .wave-bar:nth-child(3) { animation-delay: 0.4s; height: 32px; background-color: #FF6B6B; }
    .wave-bar:nth-child(4) { animation-delay: 0.6s; height: 18px; background-color: #FF8E53; }
    .wave-bar:nth-child(5) { animation-delay: 0.8s; height: 10px; background-color: #4D96FF; }
    
    @keyframes quiet {
        0% { transform: scaleY(0.4); }
        100% { transform: scaleY(1.5); }
    }
</style>
""", unsafe_allow_html=True)

# Title & Description Header
st.markdown("""
<div class="title-container">
    <div class="gradient-text">🎧 EchoBook</div>
    <div class="subtitle">Transform your EPUB eBooks into high-quality, immersive Audiobooks</div>
    <div class="gradient-divider"></div>
</div>
""", unsafe_allow_html=True)

# Create a local directory for temporary uploads
TEMP_DIR = os.path.join(os.getcwd(), "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

# Voice narration configuration
st.markdown("### ⚙ Voice Configuration")
VOICES = {
    "Aria (US Female - Standard)": "en-US-AriaNeural",
    "Guy (US Male - Standard)": "en-US-GuyNeural",
    "Jenny (US Female - Premium Natural)": "en-US-JennyNeural",
    "Sonia (UK Female - British)": "en-GB-SoniaNeural",
    "Ryan (UK Male - British)": "en-GB-RyanNeural",
    "Natasha (Australia Female - Australian)": "en-AU-NatashaNeural",
    "Neerja (India Female - Indian)": "en-IN-NeerjaNeural"
}

selected_voice_label = st.selectbox(
    "Choose your narrator voice:",
    options=list(VOICES.keys()),
    index=0,
    help="Select the AI-powered text-to-speech voice model for your audiobook."
)
selected_voice = VOICES[selected_voice_label]

st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

# Novel scraper configuration
st.markdown("### 📚 Web Novel Details")
novel_url = st.text_input(
    "Enter Novel URL (e.g., FreeWebNovel, Fanmtl, RoyalRoad):",
    placeholder="https://freewebnovel.com/some-novel-toc.html",
    help="Provide the main Table of Contents (TOC) page URL of the web novel."
)

max_chapters = st.slider(
    "Number of chapters to scrape and convert:",
    min_value=1,
    max_value=50,
    value=5,
    help="Select how many chapters to scrape and convert starting from the first chapter. Keep this value small for faster testing."
)

st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

# Add a processing action trigger
if st.button("🚀 Start Processing", use_container_width=True):
    if not novel_url:
        st.warning("Please enter a valid Web Novel URL to begin.")
    else:
        # Create overall progress bar and task status placeholders
        progress_bar = st.progress(0.0)
        status_text_placeholder = st.empty()
        
        # Scaling progress function
        # Phase 1: Scraping: 0% to 25% of overall bar
        # Phase 2: Conversion/TTS: 25% to 100% of overall bar
        def update_scrape_progress(percent, status_text):
            scaled_percent = percent * 0.25
            progress_bar.progress(scaled_percent)
            status_text_placeholder.markdown(f"**Status (Phase 1/2):** {status_text}")
            
        def update_tts_progress(percent, status_text):
            scaled_percent = 0.25 + (percent * 0.75)
            progress_bar.progress(scaled_percent)
            status_text_placeholder.markdown(f"**Status (Phase 2/2):** {status_text}")
            
        try:
            # Scraper alert message
            st.markdown("""
            <div class="glass-card" style="border-left: 4px solid #FF8E53; margin-bottom: 10px; margin-top: 10px;">
                <h5 style='color: #FF8E53; margin: 0 0 5px 0;'>🌐 Phase 1: Web Scraping</h5>
                <p style='margin: 0; font-size: 0.9rem;'>Scraping novel from web... this may take a minute depending on the length.</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Step 1: Scrape novel to local temporary EPUB file
            temp_epub_path = scrape_novel_to_epub(
                url=novel_url,
                max_chapters=max_chapters,
                progress_callback=update_scrape_progress
            )
            
            # Step 2: Convert the temporary EPUB file to Audiobook chunks
            result = process_epub(
                file_path=temp_epub_path,
                voice=selected_voice,
                progress_callback=update_tts_progress
            )
            
            # Clear progress feedback components upon completion
            progress_bar.empty()
            status_text_placeholder.empty()
            
            # Display detailed extracted eBook metadata card
            st.markdown(f"""
            <div class="glass-card" style="border-left: 4px solid #4D96FF;">
                <h4 style='color: #4D96FF; margin: 0 0 10px 0;'>📖 Audiobook Generated Successfully</h4>
                <div style='margin-bottom: 8px;'><strong>Title:</strong> {result['title']}</div>
                <div style='margin-bottom: 8px;'><strong>Author:</strong> {result['author']}</div>
                <div style='margin-bottom: 8px;'><strong>Selected Voice:</strong> {selected_voice_label}</div>
                <div style='margin-bottom: 8px;'><strong>Total Characters:</strong> {result['total_chars']:,}</div>
                <div style='margin-bottom: 8px;'><strong>Audiobook Chunks:</strong> {result['total_chunks']} (max 4000 chars per chunk)</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Direct in-browser audiobook playback and download
            st.markdown("### 🎧 Play & Download Audiobook")
            
            if os.path.exists(result['audio_path']):
                with open(result['audio_path'], "rb") as audio_file:
                    audio_bytes = audio_file.read()
                
                # Audio player widget
                st.audio(audio_bytes, format="audio/mp3")
                
                # Download button
                st.download_button(
                    label="📥 Download Audiobook (.mp3)",
                    data=audio_bytes,
                    file_name=f"{result['title']}.mp3",
                    mime="audio/mp3",
                    use_container_width=True
                )
            else:
                st.error("Generated audiobook file could not be located on disk.")
            
            # Interactive speech chunk preview accordion
            with st.expander("🔍 Preview Audiobook Chunks", expanded=False):
                st.markdown("Below is a sample of the text chunks prepared for the text-to-speech engine:")
                for i, chunk in enumerate(result['chunks'][:5]):
                    st.markdown(f"**Chunk {i+1}** (Length: {len(chunk)} characters)")
                    st.info(chunk[:350] + "..." if len(chunk) > 350 else chunk)
                if len(result['chunks']) > 5:
                    st.write(f"*... and {len(result['chunks']) - 5} more chunks generated.*")
            
            # Cleanup the scraped EPUB file to save disk space
            try:
                if os.path.exists(temp_epub_path):
                    os.remove(temp_epub_path)
            except Exception:
                pass
                
        except Exception as e:
            progress_bar.empty()
            status_text_placeholder.empty()
            st.error(f"An error occurred during processing: {str(e)}")

# Premium branding footer
st.markdown("""
<div class="footer">
    EchoBook Audiobook Maker • Built using Streamlit & Python
</div>
""", unsafe_allow_html=True)
