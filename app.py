import streamlit as st
import spacy
import pandas as pd
import re
import os
from collections import Counter

# Ustawienia strony
st.set_page_config(
    page_title="Korpus Językowy — Irena Jerzemowska", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS — Stylizowanie na wzór Sketch Engine
st.markdown("""
    <style>
        .stApp {
            background-color: #f8fafc;
            color: #0f172a;
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
        }
        .main-header {
            background-color: #0f172a;
            color: #ffffff;
            padding: 1.5rem 2rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .main-header h1 {
            color: #ffffff !important;
            font-size: 1.8rem !important;
            font-weight: 600 !important;
            margin: 0 !important;
        }
        .main-header p {
            color: #94a3b8;
            margin: 0.4rem 0 0 0;
            font-size: 0.95rem;
        }
        [data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            border-bottom: 2px solid #e2e8f0;
        }
        .stTabs [aria-selected="true"] {
            background-color: #ffffff !important;
            color: #1e40af !important;
            border-bottom: 3px solid #1e40af !important;
            font-weight: 600;
        }
        .stButton>button {
            background-color: #1e40af;
            color: white;
            border-radius: 6px;
        }
    </style>
""", unsafe_allow_html=True)

# Tworzenie stałych folderów na dysku
DIR_MIKRO = "dane_mikro"
DIR_MAKRO = "dane_makro"
os.makedirs(DIR_MIKRO, exist_ok=True)
os.makedirs(DIR_MAKRO, exist_ok=True)

LANGUAGE_MODELS = {
    "Angielski (USA / UK) 🇺🇸🇬🇧": "en_core_web_sm",
    "Polski 🇵🇱": "pl_core_news_sm"
}

# Słowniki wskaźników przesady i perswazji (Doktorat Beauty)
HYPERBOLE_DICTIONARY = {
    "Angielski (USA / UK) 🇺🇸🇬🇧": [
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

@st.cache_resource
def load_nlp_model(model_name):
    return spacy.load(model_name)

def load_saved_corpora(directory):
    texts = {}
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            filepath = os.path.join(directory, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                texts[filename] = f.read()
    return texts

def generate_ngrams(text, n):
    words = re.findall(r'\b\w+\b', text.lower())
    return [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]

# Baner Górny
st.markdown("""
    <div class="main-header">
        <h1>Korpus Językowy — Irena Jerzemowska</h1>
        <p>Analiza Dyskursu Multimodalnego i Perswazji w Branży Beauty (USA, UK, PL | 2016–2026)</p>
    </div>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.markdown("### 📥 Import Danych")
corpus_type = st.sidebar.radio("Wybierz typ korpusu:", ["Mikrokorpus", "Makrokorpus"])

uploaded_files = st.sidebar.file_uploader(
    "Wgraj transkrypcje (.txt):", 
    type=["txt"], 
    accept_multiple_files=True
)

if uploaded_files:
    target_dir = DIR_MIKRO if corpus_type == "Mikrokorpus" else DIR_MAKRO
    for file in uploaded_files:
        filepath = os.path.join(target_dir, file.name)
        with open(filepath, "wb") as f:
            f.write(file.getbuffer())
    st.sidebar.success(f"Zapisano {len(uploaded_files)} plik(ów)!")

st.sidebar.divider()
st.sidebar.markdown("### 🔍 Konfiguracja")
active_corpus = st.sidebar.selectbox("Aktywny korpus:", ["Mikrokorpus", "Makrokorpus"])
selected_lang_name = st.sidebar.selectbox("🌐 Język tekstu:", list(LANGUAGE_MODELS.keys()))

target_dir = DIR_MIKRO if active_corpus == "Mikrokorpus" else DIR_MAKRO
target_data = load_saved_corpora(target_dir)

# Zakładki
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔎 KWIC Concordance", 
    "🔥 Słownik Przesady", 
    "📊 N-gramy (Frazy)", 
    "🏷️ Lematyzacja NLP", 
    "📂 Pliki Korpusu"
])

# 1. KWIC
with tab1:
    st.markdown(f"#### Wyszukiwarka konkordancji w kontekście — **{active_corpus}**")
    if not target_data:
        st.info("Baza danych jest pusta. Wgraj pliki .txt w panelu bocznym.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Szukana fraza / lemat:", "", placeholder="np. obsessed, hit, sponsored...")
        with col2:
            context_size = st.slider("Kontekst (słowa):", 3, 15, 6)
        
        if query:
            results = []
            for doc_name, text in target_data.items():
                words = re.findall(r'\b\w+\b', text)
                for idx, word in enumerate(words):
                    if query.lower() in word.lower():
                        left = " ".join(words[max(0, idx - context_size):idx])
                        right = " ".join(words[idx + 1:idx + 1 + context_size])
                        results.append({
                            "Dokument": doc_name,
                            "Kontekst lewy": left,
                            "Słowo kluczowe": word,
                            "Kontekst prawy": right
                        })
            
            if results:
                st.markdown(f"**Liczba trafień:** `{len(results)}`")
                df_kwic = pd.DataFrame(results)
                st.dataframe(df_kwic, use_container_width=True, hide_index=True)
                
                # Eksport CSV
                csv = df_kwic.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Pobierz wyniki KWIC (CSV)", csv, "kwic_results.csv", "text/csv")
            else:
                st.warning("Brak wyników.")

# 2. SŁOWNIK PRZESADY
with tab2:
    st.markdown(f"#### Analiza Wyolbrzymień i Perswazji (*Hyperbole Detection*) — **{selected_lang_name}**")
    if not target_data:
        st.info("Baza danych jest pusta.")
    else:
        keywords = HYPERBOLE_DICTIONARY[selected_lang_name]
        combined_text = " ".join(target_data.values()).lower()
        all_words = re.findall(r'\b\w+\b', combined_text)
        total_word_count = len(all_words)
        
        counts = []
        for kw in keywords:
            count = len(re.findall(r'\b' + re.escape(kw) + r'\b', combined_text))
            density = (count / total_word_count * 1000) if total_word_count > 0 else 0
            counts.append({"Słowo / Fraza kluczowa": kw, "Liczba wystąpień": count, "Gęstość (na 1000 słów)": round(density, 2)})
        
        df_hyperbole = pd.DataFrame(counts).sort_values(by="Liczba wystąpień", ascending=False)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(df_hyperbole, use_container_width=True, hide_index=True)
        with col2:
            st.metric("Łączna liczba słów w korpusie", total_word_count)
            top_word = df_hyperbole.iloc[0]["Słowo / Fraza kluczowa"] if not df_hyperbole.empty else "Brak"
            st.metric("Najczęstsza hiperbola", top_word)

# 3. N-GRAMY
with tab3:
    st.markdown("#### Analiza powtarzalnych zwrotów i formuł (N-gramy)")
    if target_data:
        n_choice = st.radio("Długość frazy:", [2, 3, 4], format_func=lambda x: f"{x}-gramy (fraz {x}-wyrazowe)")
        combined_text = " ".join(target_data.values())
        ngrams = generate_ngrams(combined_text, n_choice)
        ngram_counts = Counter(ngrams).most_common(20)
        
        df_ngrams = pd.DataFrame(ngram_counts, columns=["Fraza / N-gram", "Częstość występowania"])
        st.dataframe(df_ngrams, use_container_width=True, hide_index=True)
    else:
        st.info("Baza danych jest pusta.")

# 4. LEMATYZACJA
with tab4:
    st.markdown(f"#### Analiza Lematyzacyjna (spaCy) — **{selected_lang_name}**")
    if target_data:
        selected_doc = st.selectbox("Wybierz transkrypcję do analizy:", list(target_data.keys()))
        if selected_doc:
            with st.spinner("Przetwarzanie tekstu..."):
                nlp = load_nlp_model(LANGUAGE_MODELS[selected_lang_name])
                doc = nlp(target_data[selected_doc])
                tokens_data = [
                    {"Słowo": token.text, "Lemat": token.lemma_, "Część mowy (POS)": token.pos_}
                    for token in doc if not token.is_punct and not token.is_space
                ]
                df_tokens = pd.DataFrame(tokens_data)
                st.dataframe(df_tokens, use_container_width=True, hide_index=True)
    else:
        st.info("Baza danych jest pusta.")

# 5. PLIKI
with tab5:
    st.markdown("#### Podgląd transkrypcji i adnotacji multimodalnych")
    if target_data:
        for name, text in target_data.items():
            with st.expander(f"📄 {name}"):
                st.text_area("Treść pliku:", text, height=200, key=f"prev_{name}")
    else:
        st.write("Brak plików.")
          
