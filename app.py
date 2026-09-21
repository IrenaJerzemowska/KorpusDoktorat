import os
import re
from collections import Counter
import pandas as pd
import spacy
import streamlit as st
from langdetect import detect
import docx
import json
from pathlib import Path
from datetime import datetime
import pytz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from io import BytesIO
import pickle

# ============================================================================
# 1. PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="Corpus — Irena Jerzemowska",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "PhD Corpus Analysis Tool — Multilingual (PL & EN)"
    }
)

st.markdown("""
    <style>
        .stApp { background-color: #f8fafc; color: #0f172a; font-family: 'Inter', sans-serif; }
        .main-header {
            background-color: #0f172a; color: #ffffff; padding: 1.5rem 2rem;
            border-radius: 8px; margin-bottom: 2rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .main-header h1 { color: #ffffff !important; font-size: 1.8rem !important; margin: 0 !important; }
        .main-header p { color: #94a3b8; margin: 0.4rem 0 0 0; font-size: 0.95rem; }
        [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 2px solid #e2e8f0; }
        .stTabs [aria-selected="true"] { background-color: #ffffff !important; color: #1e40af !important; border-bottom: 3px solid #1e40af !important; font-weight: 600; }
        .stButton>button { background-color: #1e40af; color: white; border-radius: 6px; }
        .contributor-box { background-color: #dbeafe; border-left: 4px solid #1e40af; padding: 1rem; border-radius: 6px; margin: 1rem 0; }
        .stats-box { background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 1rem; border-radius: 6px; }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# 2. GOOGLE DRIVE SETUP
# ============================================================================
GOOGLE_DRIVE_ENABLED = False
drive_service = None

@st.cache_resource
def init_google_drive():
    """Initialize Google Drive API"""
    global GOOGLE_DRIVE_ENABLED, drive_service
    
    try:
        # Try to get credentials from secrets
        if "google_service_account" in st.secrets:
            creds_dict = st.secrets["google_service_account"]
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            drive_service = build('drive', 'v3', credentials=credentials)
            GOOGLE_DRIVE_ENABLED = True
            return drive_service
    except Exception as e:
        print(f"⚠️ Google Drive initialization failed: {e}")
    
    return None

drive_service = init_google_drive()
GOOGLE_DRIVE_ENABLED = drive_service is not None

# ============================================================================
# 3. LOCAL STORAGE & METADATA
# ============================================================================
LOCAL_STORAGE_DIR = Path.home() / ".corpus_app_data"
LOCAL_STORAGE_DIR.mkdir(exist_ok=True)
METADATA_FILE = LOCAL_STORAGE_DIR / "metadata.json"

def load_metadata():
    """Load file upload metadata"""
    if METADATA_FILE.exists():
        try:
            return json.loads(METADATA_FILE.read_text())
        except:
            return {}
    return {}

def save_metadata(meta):
    """Save file upload metadata"""
    try:
        METADATA_FILE.write_text(json.dumps(meta, indent=2, default=str))
    except Exception as e:
        print(f"Error saving metadata: {e}")

def get_local_storage_path(corpus_type: str) -> Path:
    """Get local storage path for corpus type"""
    folder = LOCAL_STORAGE_DIR / ("mikro" if corpus_type == "Mikrokorpus" else "makro")
    folder.mkdir(exist_ok=True)
    return folder

def save_locally(text_content: str, filename: str, corpus_type: str, contributor: str = "Unknown"):
    """Save text to local storage with metadata"""
    try:
        folder = get_local_storage_path(corpus_type)
        clean_name = filename.replace('.docx', '.txt')
        filepath = folder / clean_name
        filepath.write_text(text_content, encoding='utf-8')
        
        # Track metadata
        meta = load_metadata()
        meta[clean_name] = {
            "uploaded_by": contributor,
            "timestamp": datetime.now(pytz.UTC).isoformat(),
            "corpus_type": corpus_type,
            "file_size": len(text_content),
            "word_count": len(re.findall(r'\b\w+\b', text_content))
        }
        save_metadata(meta)
        return True
    except Exception as e:
        st.error(f"❌ Błąd zapisu lokalnego: {e}")
        return False

def load_local_corpora(corpus_type: str) -> dict:
    """Load texts from local storage"""
    texts = {}
    try:
        folder = get_local_storage_path(corpus_type)
        for filepath in folder.glob("*.txt"):
            texts[filepath.name] = filepath.read_text(encoding='utf-8')
    except Exception as e:
        st.error(f"❌ Błąd odczytu lokalnego: {e}")
    return texts

# ============================================================================
# 4. GOOGLE DRIVE FUNCTIONS
# ============================================================================
def get_or_create_folder(folder_name: str) -> str:
    """Get or create a folder in Google Drive, returns folder ID"""
    try:
        # Check if folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=10
        ).execute()
        
        files = results.get('files', [])
        if files:
            return files[0]['id']
        
        # Create folder if it doesn't exist
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    except Exception as e:
        st.error(f"❌ Error with Google Drive folder: {e}")
        return None

def upload_to_google_drive(text_content: bytes, filename: str, folder_id: str) -> bool:
    """Upload file to Google Drive"""
    try:
        clean_filename = filename.rsplit('.', 1)[0] + ".txt"
        
        # Check if file exists and delete it
        query = f"name='{clean_filename}' and '{folder_id}' in parents and trashed=false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            drive_service.files().delete(fileId=files[0]['id']).execute()
        
        # Upload new file
        file_metadata = {
            'name': clean_filename,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(
            None,
            mimetype='text/plain',
            chunksize=1024 * 1024,
            resumable=True,
            stream=BytesIO(text_content)
        )
        
        # Create temp file for upload
        temp_file = LOCAL_STORAGE_DIR / clean_filename
        temp_file.write_bytes(text_content)
        
        media = MediaFileUpload(
            str(temp_file),
            mimetype='text/plain',
            resumable=True
        )
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        # Clean up temp file
        temp_file.unlink(missing_ok=True)
        return True
        
    except Exception as e:
        print(f"⚠️ Google Drive upload error: {e}")
        return False

def load_from_google_drive(folder_id: str) -> dict:
    """Load texts from Google Drive folder"""
    texts = {}
    try:
        query = f"'{folder_id}' in parents and trashed=false and mimeType='text/plain'"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=100
        ).execute()
        
        files = results.get('files', [])
        for file in files:
            if file['name'].endswith('.txt'):
                try:
                    request = drive_service.files().get_media(fileId=file['id'])
                    file_content = request.execute()
                    texts[file['name']] = file_content.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"⚠️ Error reading {file['name']}: {e}")
    except Exception as e:
        print(f"⚠️ Google Drive load error: {e}")
    return texts

def load_all_corpora(corpus_type: str) -> dict:
    """Load from Google Drive first, fall back to local"""
    if GOOGLE_DRIVE_ENABLED:
        folder_name = "Corpus_Mikro" if corpus_type == "Mikrokorpus" else "Corpus_Makro"
        folder_id = get_or_create_folder(folder_name)
        if folder_id:
            cloud_data = load_from_google_drive(folder_id)
            if cloud_data:
                return cloud_data
    
    return load_local_corpora(corpus_type)

# ============================================================================
# 5. NLP MODELS
# ============================================================================
@st.cache_resource
def load_nlp_models():
    try:
        return {
            "en": spacy.load("en_core_web_sm"),
            "pl": spacy.load("pl_core_news_sm")
        }
    except Exception as e:
        st.error(f"❌ Błąd ładowania modeli NLP: {e}")
        return {}

nlp_models = load_nlp_models()

# ============================================================================
# 6. HYPERBOLE DICTIONARY
# ============================================================================
HYPERBOLE_DICTIONARY = {
    "Angielski 🇺🇸🇬🇧": [
        "obsessed", "holy grail", "literally", "life-changing", "game-changer", 
        "insane", "iconic", "essential", "absolute", "unreal", "stunning", 
        "must-have", "perfection", "miracle", "flawless", "magic", "best ever"
    ],
    "Polski 🇵🇱": [
        "hit", "cudo", "sztos", "uwielbiam", "obłędny", "absolutny", "kosmos",
        "obowiązkowy", "zakochałam się", "przepiękny", "magia", "odmienił moje życie",
        "must have", "ideał", "najlepszy", "genialny", "obawiam się że"
    ]
}

# ============================================================================
# 7. HELPER FUNCTIONS
# ============================================================================
def extract_text_from_file(file) -> str:
    """Convert .txt and .docx files to plain text"""
    try:
        if file.name.endswith(".docx"):
            doc = docx.Document(file)
            text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            if not text.strip():
                raise ValueError("Dokument .docx jest pusty")
            return text
        else:
            content = file.getvalue().decode("utf-8", errors="ignore")
            if not content.strip():
                raise ValueError("Plik .txt jest pusty")
            return content
    except Exception as e:
        raise Exception(f"Błąd ekstrakcji tekstu: {str(e)}")

def detect_language(text):
    """Detect language"""
    try:
        lang = detect(text[:1000])
        return "pl" if lang == "pl" else "en"
    except Exception:
        return "en"

def generate_ngrams(text, n):
    """Generate n-grams"""
    words = re.findall(r'\b\w+\b', text.lower())
    return [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]

def get_corpus_stats(corpus_data: dict) -> dict:
    """Calculate corpus statistics"""
    combined = " ".join(corpus_data.values())
    words = re.findall(r'\b\w+\b', combined)
    unique_words = set(w.lower() for w in words)
    
    return {
        "total_files": len(corpus_data),
        "total_words": len(words),
        "unique_words": len(unique_words),
        "avg_words_per_file": len(words) // len(corpus_data) if corpus_data else 0,
        "languages": {
            "Polish": sum(1 for text in corpus_data.values() if detect_language(text) == "pl"),
            "English": sum(1 for text in corpus_data.values() if detect_language(text) == "en")
        }
    }

# ============================================================================
# 8. MAIN HEADER
# ============================================================================
st.markdown("""
    <div class="main-header">
        <h1>🔍 Corpus — Irena Jerzemowska</h1>
        <p>Analiza Dyskursu Multimodalnego i Perswazji w Branży Beauty</p>
    </div>
""", unsafe_allow_html=True)

# Storage status
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.markdown("### 📊 Shared Corpus Analysis")
with col2:
    if GOOGLE_DRIVE_ENABLED:
        st.success("☁️ Google Drive", icon="✅")
    else:
        st.info("💾 Local Storage", icon="ℹ️")
with col3:
    if st.button("🔄 Sync", help="Reload data from storage"):
        st.cache_data.clear()
        st.rerun()

# ============================================================================
# 9. SIDEBAR
# ============================================================================
st.sidebar.markdown("### 📥 Upload Corpus Files")

# Get contributor name
contributor = st.sidebar.text_input(
    "Your name (for tracking):",
    value="Anonymous",
    help="Who is uploading this file?"
)

corpus_type = st.sidebar.radio("Corpus type:", ["Mikrokorpus", "Makrokorpus"])

uploaded_files = st.sidebar.file_uploader(
    "Upload .txt or .docx files:",
    type=["txt", "docx"],
    accept_multiple_files=True,
    help="Upload Polish and English transcripts"
)

if uploaded_files:
    successful = 0
    failed = 0
    
    with st.sidebar:
        progress_bar = st.progress(0)
        status_text = st.empty()
    
    for idx, file in enumerate(uploaded_files):
        try:
            text_content = extract_text_from_file(file)
            
            # Save locally (always)
            local_saved = save_locally(text_content, file.name, corpus_type, contributor)
            
            # Try to save to Google Drive
            cloud_saved = False
            if GOOGLE_DRIVE_ENABLED:
                folder_name = "Corpus_Mikro" if corpus_type == "Mikrokorpus" else "Corpus_Makro"
                folder_id = get_or_create_folder(folder_name)
                if folder_id:
                    cloud_saved = upload_to_google_drive(text_content.encode("utf-8"), file.name, folder_id)
            
            if local_saved:
                successful += 1
                storage_info = "☁️+💾" if cloud_saved else "💾"
            else:
                failed += 1
                storage_info = "❌"
            
            progress = (idx + 1) / len(uploaded_files)
            progress_bar.progress(progress)
            status_text.text(f"{idx + 1}/{len(uploaded_files)} ({storage_info})")
            
        except Exception as e:
            st.sidebar.error(f"❌ **{file.name}**: {str(e)}")
            failed += 1
    
    progress_bar.empty()
    status_text.empty()
    
    if successful > 0:
        storage_mode = "w chmurze i lokalnie" if GOOGLE_DRIVE_ENABLED else "lokalnie"
        st.sidebar.success(f"✅ Loaded {successful} files by {contributor}! ({storage_mode})")
    if failed > 0:
        st.sidebar.error(f"❌ Failed: {failed} files")
    
    st.cache_data.clear()

st.sidebar.divider()
st.sidebar.markdown("### 🔍 Configuration")
active_corpus = st.sidebar.selectbox("Active Corpus:", ["Mikrokorpus", "Makrokorpus"])

target_data = load_all_corpora(active_corpus)

# Show contributors
if target_data:
    meta = load_metadata()
    contributors = set()
    for filename in target_data.keys():
        if filename in meta:
            contributors.add(meta[filename].get("uploaded_by", "Unknown"))
    
    if contributors:
        st.sidebar.markdown("#### 👥 Contributors")
        for contrib in sorted(contributors):
            st.sidebar.caption(f"✓ {contrib}")

if not target_data:
    st.sidebar.warning("⚠️ Corpus is empty. Upload files above.")

# ============================================================================
# 10. CORPUS STATISTICS
# ============================================================================
if target_data:
    st.sidebar.divider()
    st.sidebar.markdown("#### 📈 Corpus Stats")
    stats = get_corpus_stats(target_data)
    st.sidebar.metric("Files", stats["total_files"])
    st.sidebar.metric("Total Words", f"{stats['total_words']:,}")
    st.sidebar.metric("Unique Words", f"{stats['unique_words']:,}")

# ============================================================================
# 11. MAIN TABS
# ============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔎 KWIC Concordance",
    "🔥 Hyperboles (PL & EN)",
    "📊 N-grams",
    "🏷️ Lemmatization",
    "📂 Files"
])

# ============================================================================
# TAB 1: KWIC
# ============================================================================
with tab1:
    st.markdown(f"#### KWIC Concordance — **{active_corpus}**")
    if not target_data:
        st.info("📭 No corpus files. Upload above.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input(
                "Search phrase / lemma:",
                placeholder="e.g., obsessed, hit, sponsored, cudo...",
                help="Search is case-insensitive"
            )
        with col2:
            context_size = st.slider("Context (words):", 3, 15, 6)
        
        if query:
            results = []
            for doc_name, text in target_data.items():
                words = re.findall(r'\b\w+\b', text)
                lang = detect_language(text)
                for idx, word in enumerate(words):
                    if query.lower() in word.lower():
                        left = " ".join(words[max(0, idx - context_size):idx])
                        right = " ".join(words[idx + 1:idx + 1 + context_size])
                        results.append({
                            "File": doc_name,
                            "Language": "🇵🇱 PL" if lang == "pl" else "🇺🇸🇬🇧 EN",
                            "Left Context": left,
                            "Keyword": word,
                            "Right Context": right
                        })
            
            if results:
                st.markdown(f"**Hits:** {len(results)}")
                df_kwic = pd.DataFrame(results)
                st.dataframe(df_kwic, use_container_width=True, hide_index=True)
                csv = df_kwic.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download (CSV)", csv, "kwic_results.csv", "text/csv")
            else:
                st.warning("⚠️ No results found.")

# ============================================================================
# TAB 2: HYPERBOLES
# ============================================================================
with tab2:
    st.markdown("#### Hyperbole & Persuasion Analysis (PL & EN)")
    if not target_data:
        st.info("📭 No corpus files.")
    else:
        combined_text = " ".join(target_data.values()).lower()
        all_words = re.findall(r'\b\w+\b', combined_text)
        total_word_count = len(all_words)
        
        counts = []
        for lang_label, keywords in HYPERBOLE_DICTIONARY.items():
            for kw in keywords:
                count = len(re.findall(r'\b' + re.escape(kw) + r'\b', combined_text))
                density = (count / total_word_count * 1000) if total_word_count > 0 else 0
                counts.append({
                    "Language": lang_label,
                    "Term": kw,
                    "Frequency": count,
                    "Density (per 1000 words)": round(density, 2)
                })
        
        df_hyperbole = pd.DataFrame(counts).sort_values(by="Frequency", ascending=False)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(df_hyperbole, use_container_width=True, hide_index=True)
        with col2:
            st.metric("Total Corpus Words", total_word_count)
            top_word = df_hyperbole.iloc[0]["Term"] if not df_hyperbole.empty else "N/A"
            st.metric("Most Frequent Hyperbole", top_word)

# ============================================================================
# TAB 3: N-GRAMS
# ============================================================================
with tab3:
    st.markdown("#### N-gram Analysis")
    if target_data:
        n_choice = st.radio("Phrase length:", [2, 3, 4], format_func=lambda x: f"{x}-grams", horizontal=True)
        combined_text = " ".join(target_data.values())
        ngrams = generate_ngrams(combined_text, n_choice)
        ngram_counts = Counter(ngrams).most_common(25)
        
        df_ngrams = pd.DataFrame(ngram_counts, columns=["Phrase", "Frequency"])
        st.dataframe(df_ngrams, use_container_width=True, hide_index=True)
    else:
        st.info("📭 No corpus files.")

# ============================================================================
# TAB 4: LEMMATIZATION
# ============================================================================
with tab4:
    st.markdown("#### Automatic Lemmatization (NLP)")
    if target_data:
        selected_doc = st.selectbox("Select file for analysis:", list(target_data.keys()))
        if selected_doc:
            text_content = target_data[selected_doc]
            detected_lang = detect_language(text_content)
            lang_name = "Polish 🇵🇱" if detected_lang == "pl" else "English 🇺🇸🇬🇧"
            
            if detected_lang not in nlp_models:
                st.error(f"❌ NLP model for {lang_name} not available.")
            else:
                st.caption(f"Detected: **{lang_name}**")
                
                with st.spinner("Processing..."):
                    doc = nlp_models[detected_lang](text_content[:5000])
                    tokens_data = [
                        {"Word": token.text, "Lemma": token.lemma_, "POS": token.pos_}
                        for token in doc if not token.is_punct and not token.is_space
                    ]
                    df_tokens = pd.DataFrame(tokens_data)
                    st.dataframe(df_tokens, use_container_width=True, hide_index=True)
    else:
        st.info("📭 No corpus files.")

# ============================================================================
# TAB 5: FILES
# ============================================================================
with tab5:
    st.markdown("#### Corpus File Preview")
    if target_data:
        meta = load_metadata()
        for name, text in target_data.items():
            lang = detect_language(text)
            flag = "🇵🇱 PL" if lang == "pl" else "🇺🇸🇬🇧 EN"
            word_count = len(re.findall(r'\b\w+\b', text))
            
            # Get metadata
            file_meta = meta.get(name, {})
            contributor = file_meta.get("uploaded_by", "Unknown")
            timestamp = file_meta.get("timestamp", "")
            
            header = f"📄 {name} [{flag}] — {word_count:,} words"
            if contributor != "Unknown":
                header += f" (by {contributor})"
            
            with st.expander(header):
                # Show metadata
                if timestamp:
                    ts = datetime.fromisoformat(timestamp)
                    st.caption(f"Uploaded: {ts.strftime('%Y-%m-%d %H:%M UTC')}")
                
                # Show text
                st.text_area("Content:", text, height=250, key=f"prev_{name}", disabled=True)
                
                # Delete button
                if st.button(f"🗑️ Delete", key=f"del_{name}"):
                    try:
                        folder = get_local_storage_path(active_corpus)
                        (folder / name).unlink(missing_ok=True)
                        del meta[name]
                        save_metadata(meta)
                        st.success(f"✅ Deleted {name}")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
    else:
        st.write("📭 No files.")

# ============================================================================
# FOOTER
# ============================================================================
st.divider()
st.caption(
    f"📊 Corpus App | "
    f"Storage: {'☁️ Google Drive + 💾 Local' if GOOGLE_DRIVE_ENABLED else '💾 Local Only'} | "
    f"Language: PL & EN"
)
