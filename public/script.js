// Front-end controller for EchoBook

async function startConversion() {
    const voiceSelect = document.getElementById("voice-select");
    const novelUrlInput = document.getElementById("novel-url");
    const maxChaptersInput = document.getElementById("max-chapters");
    const submitBtn = document.getElementById("submit-btn");
    const progressCard = document.getElementById("progress-card");
    const resultCard = document.getElementById("result-card");

    const voice = voiceSelect.value;
    const url = novelUrlInput.value.trim();
    const maxChapters = parseInt(maxChaptersInput.value);

    if (!url) {
        alert("Please enter a valid Table of Contents URL first.");
        return;
    }

    // 1. Reset UI States
    resultCard.classList.add("hidden");
    progressCard.classList.remove("hidden");
    submitBtn.disabled = true;
    submitBtn.querySelector("span").innerText = "⌛ Processing...";

    // Reset Progress Phases
    const p1 = document.getElementById("phase-1");
    const p2 = document.getElementById("phase-2");
    const p3 = document.getElementById("phase-3");
    
    p1.className = "phase-indicator active";
    p2.className = "phase-indicator";
    p3.className = "phase-indicator";

    // 2. Micro-animation state transitions (simulated for serverless response waiting)
    // Serverless runs are monolithic responses, so we animate phases dynamically to keep user engaged.
    const scrapeDesc = document.getElementById("phase-1-desc");
    scrapeDesc.innerText = `Connecting to web novel source and scraping first ${maxChapters} chapters...`;

    let activePhase = 1;
    const timer1 = setTimeout(() => {
        if (activePhase === 1) {
            p1.className = "phase-indicator completed";
            p2.className = "phase-indicator active";
            activePhase = 2;
        }
    }, 4500); // Shift to TTS after 4.5 seconds

    const timer2 = setTimeout(() => {
        if (activePhase === 2) {
            p2.className = "phase-indicator completed";
            p3.className = "phase-indicator active";
            activePhase = 3;
        }
    }, 18000); // Shift to stitching after 18 seconds (standard neural voices processing chunk size)

    // 3. Fire conversion API request
    try {
        const response = await fetch("/api/convert", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                url: url,
                max_chapters: maxChapters,
                voice: voice
            })
        });

        // Clear timers
        clearTimeout(timer1);
        clearTimeout(timer2);

        if (!response.ok) {
            const errorJson = await response.json().catch(() => ({ detail: "Unknown server error occurred." }));
            throw new Error(errorJson.detail || "Server error while processing audiobook.");
        }

        // Complete all progress phases
        p1.className = "phase-indicator completed";
        p2.className = "phase-indicator completed";
        p3.className = "phase-indicator completed";

        // 4. Retrieve Custom Metadata Headers
        // Headers are URL-encoded by the FastAPI backend to safely handle custom unicode characters (like author/book names).
        const titleHeader = response.headers.get("X-Audiobook-Title") || "Untitled Book";
        const authorHeader = response.headers.get("X-Audiobook-Author") || "Unknown Author";
        const totalChars = response.headers.get("X-Audiobook-Total-Chars") || "0";
        const totalChunks = response.headers.get("X-Audiobook-Total-Chunks") || "0";

        const decodedTitle = decodeURIComponent(titleHeader);
        const decodedAuthor = decodeURIComponent(authorHeader);

        // 5. Populate Result Metadata
        document.getElementById("res-title").innerText = decodedTitle;
        document.getElementById("res-author").innerText = decodedAuthor;
        document.getElementById("res-voice").innerText = voiceSelect.options[voiceSelect.selectedIndex].text;
        document.getElementById("res-chars").innerText = parseInt(totalChars).toLocaleString();
        document.getElementById("res-chunks").innerText = totalChunks;

        // 6. Generate Audio Stream
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        
        // Mount to audio player
        const audioElement = document.getElementById("audio-element");
        audioElement.src = audioUrl;
        audioElement.load();

        // Mount download button
        const downloadLink = document.getElementById("download-link");
        downloadLink.href = audioUrl;
        downloadLink.download = `${decodedTitle}.mp3`;

        // Hide Loader, Display Player Card
        setTimeout(() => {
            progressCard.classList.add("hidden");
            resultCard.classList.remove("hidden");
            // Scroll to results
            resultCard.scrollIntoView({ behavior: "smooth" });
        }, 600);

    } catch (error) {
        console.error(error);
        alert(`❌ Processing Failed:\n${error.message}`);
        progressCard.classList.add("hidden");
    } finally {
        // Re-enable form
        submitBtn.disabled = false;
        submitBtn.querySelector("span").innerText = "🚀 Start Processing";
    }
}
