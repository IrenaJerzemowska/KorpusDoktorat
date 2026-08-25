import streamlit as st
import spacy
import pandas as pd
import re
import os

# Ustawienia strony
st.set_page_config(
    page_title="Korpus Językowy Irena Jerzemowska", 
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
            font-size: 1rem;
            font-weight: 400;
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

# Ładowanie modelu języka polskiego
@st.cache_resource
def load_nlp():
    return spacy.load("pl_core_news_sm")

nlp = load_nlp()

# Funkcja do wczytywania plików zapisanych na stałe na dysku
def load_saved_corpora(directory):
    texts = {}
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            filepath = os.path.join(directory, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                texts[filename] = f.read()
    return texts

# Baner Górny z nowym opisem pracy doktorskiej
st.markdown("""
    <div class="main-header">
        <h1>Korpus Językowy Irena Jerzemowska</h1>
        <p>Projekt Korpusu (Mikro i Makro) w ramach pracy doktorskiej</p>
    </div>
""", unsafe_allow_html=True)

# Sidebar - Zarządzanie danymi
st.sidebar.markdown("### 📥 Import Danych")
corpus_type = st.sidebar.radio("Wybierz typ korpusu:", ["Mikrokorpus", "Makrokorpus"])

uploaded_files = st.sidebar.file_uploader(
    "Wgraj pliki źródłowe (.txt):", 
    type=["txt"], 
    accept_multiple_files=True
)

# Zapisywanie plików na stałe na dysku serwera
if uploaded_files:
    target_dir = DIR_MIKRO if corpus_type == "Mikrokorpus" else DIR_MAKRO
    for file in uploaded_files:
        filepath = os.path.join(target_dir, file.name)
        with open(filepath, "wb") as f:
            f.write(file.getbuffer())
    st.sidebar.success(f"Zapisano na stałe {len(uploaded_files)} plik(ów)!")

st.sidebar.divider()
st.sidebar.markdown("### 🔍 Konfiguracja Szukania")
active_corpus = st.sidebar.selectbox("Aktywny korpus:", ["Mikrokorpus", "Makrokorpus"])

# Odczyt danych z folderów
target_dir = DIR_MIKRO if active_corpus == "Mikrokorpus" else DIR_MAKRO
target_data = load_saved_corpora(target_dir)

# Panel Główny
tab1, tab2, tab3 = st.tabs(["🔎 Wyszukiwarka Concordance (KWIC)", "📂 Pliki Korpusu", "📊 Analiza Lematyzacyjna"])

with tab1:
    st.markdown(f"#### Konkordancje w kontekście — **{active_corpus}**")
    
    if not target_data:
        st.info("Baza danych jest pusta. Użyj panelu bocznego po lewej stronie, aby załadować pliki .txt.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Szukana fraza / lemat:", "", placeholder="Wpisz słowo...")
        with col2:
            context_size = st.slider("Rozmiar kontekstu (słowa):", 3, 15, 6)
        
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
                df = pd.DataFrame(results)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Brak wyników dla podanej frazy.")

with tab2:
    st.markdown("#### Zbiór tekstów zapisanych na serwerze")
    if target_data:
        for name, text in target_data.items():
            with st.expander(f"📄 {name}"):
                st.text_area("Podgląd zawartości:", text, height=180, key=f"preview_{name}")
    else:
        st.write("Brak wgranych plików w tym korpusie.")

with tab3:
    st.markdown("#### Profil gramatyczno-lematyzacyjny (spaCy NLP)")
    if target_data:
        selected_doc = st.selectbox("Wybierz plik z bazy do analizy:", list(target_data.keys()))
        if selected_doc:
            doc = nlp(target_data[selected_doc])
            tokens_data = [
                {"Słowo w tekście": token.text, "Lemat (Forma bazowa)": token.lemma_, "Część mowy (POS)": token.pos_}
                for token in doc if not token.is_punct and not token.is_space
            ]
            st.dataframe(pd.DataFrame(tokens_data), use_container_width=True, hide_index=True)