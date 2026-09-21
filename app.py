import os
import re
from collections import Counter
import pandas as pd
import spacy
import streamlit as st
from supabase import Client, create_client
from langdetect import detect
import docx  # Make sure 'python-docx' is in your requirements.txt

# 1. KONFIGURACJA STRONY
st.set_page_config(
    page_title="Korpus Językowy — Irena Jerzemowska",
    layout="wide",
    initial_sidebar_state="expanded"
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
    </style>
""", unsafe_allow_html=True)

# 2. POŁĄCZENIE Z SUPABASE (Z BEZPIECZNA OBSŁUGĄ BŁĘDÓW)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", None)
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", None)

@st.cache_resource
def init_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None

supabase = init_supabase()
BUCKET_NAME = "corpus-files"

# 3. ŁADOWANIE MODELI NLP
@st.cache_resource
def load_nlp_models():
    return {
        "en": spacy.load("en_core_web_sm"),
        "pl": spacy.load("pl_core_news_sm")
    }

nlp_models = load_nlp_models()

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

# HELPERY CONVERTING AND CLOUD
def extract_text_from_file(file) -> str:
    """Konwertuje pliki .txt i .docx na czysty tekst."""
    if file.name.endswith(".docx"):
        doc = docx.Document(file)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    else:
        return file.getvalue().decode("utf-8", errors="ignore")

def upload_to_cloud(file_bytes: bytes, folder: str, filename: str):
    if not supabase:
        st.sidebar.error("Supabase nie jest połączony! Sprawdź Secrets.")
        return
    
    # Save .docx as .txt in Supabase for consistent reading
    clean_filename = filename.rsplit('.', 1)[0] + ".txt"
    path = f"{folder}/{clean_filename}"
    
    try:
        supabase.storage.from_(BUCKET_NAME).remove([path])
    except Exception:
        pass
        
    supabase.storage.from_(BUCKET_NAME).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": "text/plain;charset=utf-8"}
    )

@st.cache_data(ttl=60)
def load_cloud_corpora(folder: str):
    texts = {}
    if not supabase:
        return texts
    try:
        files = supabase.storage.from_(BUCKET_NAME).list(folder)
        for f in files:
            name = f.get("name", "")
            if name.endswith(".txt"):
                file_path = f"{folder}/{name}"
                res = supabase.storage.from_(BUCKET_NAME).download(file_path)
                texts[name] = res.decode("utf-8", errors="ignore")
    except Exception as e:
        st.sidebar.error(f"Nie można połączyć z bazą Supabase. Sprawdź URL w Secrets. ({e})")
    return texts

def detect_language(text):
    try:
        lang = detect(text[:1000])
        return "pl" if lang == "pl" else "en"
    except Exception:
        return "en"

def generate_ngrams(text, n):
    words = re.findall(r'\b\w+\b', text.lower())
    return [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]

# BANER
st.markdown("""
    <div class="main-header">
        <h1>Korpus Językowy — Irena Jerzemowska</h1>
        <p>Analiza Dyskursu Multimodalnego i Perswazji w Branży Beauty (Dwujęzyczny Korpus: PL & EN)</p>
    </div>
""", unsafe_allow_html=True)

# SIDEBAR
st.sidebar.markdown("### 📥 Import Danych (Chmura)")
corpus_type = st.sidebar.radio("Wybierz typ korpusu:", ["Mikrokorpus", "Makrokorpus"])

uploaded_files = st.sidebar.file_uploader(
    "Wgraj transkrypcje (.txt, .docx):", 
    type=["txt", "docx"], 
    accept_multiple_files=True
)

if uploaded_files:
    target_folder = "dane_mikro" if corpus_type == "Mikrokorpus" else "dane_makro"
    for file in uploaded_files:
        try:
            text_content = extract_text_from_file(file)
            upload_to_cloud(text_content.encode("utf-8"), target_folder, file.name)
        except Exception as e:
            st.sidebar.error(f"Błąd przetwarzania pliku {file.name}: {e}")
            
    st.sidebar.success(f"Zapisano {len(uploaded_files)} plik(ów) w chmurze!")
    st.cache_data.clear()

st.sidebar.divider()
st.sidebar.markdown("### 🔍 Konfiguracja")
active_corpus = st.sidebar.selectbox("Aktywny korpus:", ["Mikrokorpus", "Makrokorpus"])

target_folder = "dane_mikro" if active_corpus == "Mikrokorpus" else "dane_makro"
target_data = load_cloud_corpora(target_folder)

# ZAKŁADKI
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔎 KWIC Concordance", 
    "🔥 Słownik Przesady (PL + EN)", 
    "📊 N-gramy (Frazy)", 
    "🏷️ Lematyzacja NLP", 
    "📂 Pliki Korpusu"
])

# 1. KWIC
with tab1:
    st.markdown(f"#### Wyszukiwarka konkordancji (PL + EN) — **{active_corpus}**")
    if not target_data:
        st.info("Baza danych jest pusta. Wgraj pliki .txt lub .docx w panelu bocznym.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Szukana fraza / lemat:", "", placeholder="np. obsessed, hit, sponsored, cudo...")
        with col2:
            context_size = st.slider("Kontekst (słowa):", 3, 15, 6)
        
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
                            "Dokument": doc_name,
                            "Język": "🇵🇱 PL" if lang == "pl" else "🇺🇸🇬🇧 EN",
                            "Kontekst lewy": left,
                            "Słowo kluczowe": word,
                            "Kontekst prawy": right
                        })
            
            if results:
                st.markdown(f"**Liczba trafień:** `{len(results)}`")
                df_kwic = pd.DataFrame(results)
                st.dataframe(df_kwic, use_container_width=True, hide_index=True)
                csv = df_kwic.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Pobierz wyniki KWIC (CSV)", csv, "kwic_results.csv", "text/csv")
            else:
                st.warning("Brak wyników.")

# 2. SŁOWNIK PRZESADY
with tab2:
    st.markdown("#### Jednoczesna Analiza Wyolbrzymień i Perswazji (PL & EN)")
    if not target_data:
        st.info("Baza danych jest pusta.")
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
                    "Język": lang_label,
                    "Słowo / Fraza kluczowa": kw,
                    "Liczba wystąpień": count,
                    "Gęstość (na 1000 słów)": round(density, 2)
                })
        
        df_hyperbole = pd.DataFrame(counts).sort_values(by="Liczba wystąpień", ascending=False)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(df_hyperbole, use_container_width=True, hide_index=True)
        with col2:
            st.metric("Łączna liczba słów w korpusie", total_word_count)
            top_word = df_hyperbole.iloc[0]["Słowo / Fraza kluczowa"] if not df_hyperbole.empty else "Brak"
            st.metric("Najczęstsza hiperbola (PL/EN)", top_word)

# 3. N-GRAMY
with tab3:
    st.markdown("#### Analiza N-gramów w całym korpusie dwujęzycznym")
    if target_data:
        n_choice = st.radio("Długość frazy:", [2, 3, 4], format_func=lambda x: f"{x}-gramy")
        combined_text = " ".join(target_data.values())
        ngrams = generate_ngrams(combined_text, n_choice)
        ngram_counts = Counter(ngrams).most_common(20)
        
        df_ngrams = pd.DataFrame(ngram_counts, columns=["Fraza / N-gram", "Częstość występowania"])
        st.dataframe(df_ngrams, use_container_width=True, hide_index=True)
    else:
        st.info("Baza danych jest pusta.")

# 4. LEMATYZACJA AUTOMATYCZNA
with tab4:
    st.markdown("#### Automatyczna Lematyzacja NLP")
    if target_data:
        selected_doc = st.selectbox("Wybierz transkrypcję do analizy:", list(target_data.keys()))
        if selected_doc:
            text_content = target_data[selected_doc]
            detected_lang = detect_language(text_content)
            lang_name = "Polski 🇵🇱" if detected_lang == "pl" else "Angielski 🇺🇸🇬🇧"
            
            st.caption(f"Wykryty język pliku: **{lang_name}** (Model: `{nlp_models[detected_lang].meta['name']}`)")
            
            with st.spinner("Przetwarzanie tekstu..."):
                doc = nlp_models[detected_lang](text_content)
                tokens_data = [
                    {"Słowo": token.text, "Lemat": token.lemma_, "Część mowy (POS)": token.pos_}
                    for token in doc if not token.is_punct and not token.is_space
                ]
                df_tokens = pd.DataFrame(tokens_data)
                st.dataframe(df_tokens, use_container_width=True, hide_index=True)
    else:
        st.info("Baza danych jest pusta.")

# 5. PLIKI KORPUSU
with tab5:
    st.markdown("#### Podgląd transkrypcji z automatycznym wykrywaniem języka")
    if target_data:
        for name, text in target_data.items():
            lang = detect_language(text)
            flag = "🇵🇱 PL" if lang == "pl" else "🇺🇸🇬🇧 EN"
            with st.expander(f"📄 {name} [{flag}]"):
                st.text_area("Treść pliku:", text, height=200, key=f"prev_{name}")
    else:
        st.write("Brak plików.")
