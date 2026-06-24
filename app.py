import streamlit as st
import anthropic
import requests
import json
import tempfile
import os
from pathlib import Path
import csv
import io
from datetime import datetime
import time

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Criba · Ecuador Chequea",
    page_icon="🧐",
    layout="centered"
)

# ── Textos de interfaz ────────────────────────────────────────────────────────
UI_TEXTS = {
    "es": {
        "subtitle": "Extrae lo que vale verificar",
        "description": "**Criba** es una herramienta de asistencia para periodistas y fact-checkers. Analiza audios o transcripciones y extrae automáticamente los claims con potencial verificable: cifras, declaraciones atribuidas y afirmaciones sobre hechos concretos.",
        "app_lang_label": "Idioma de la interfaz",
        "audio_lang_label": "Idioma del audio",
        "how_to_title": "📖 Cómo usar Criba",
        "how_to": """
**Opción 1 — Subir audio**
1. Selecciona el idioma de la interfaz y el idioma del audio
2. Sube tu archivo (MP3, WAV o M4A, hasta 200MB)
3. Indica si necesitas traducción de los claims
4. Haz clic en **Transcribir y extraer claims**
5. Espera 1-3 minutos mientras se procesa

**Opción 2 — Pegar transcripción**
1. Copia el texto transcrito (en YouTube: tres puntos → *Mostrar transcripción*)
2. Pégalo en el campo de texto
3. Haz clic en **Extraer claims**

**Resultados**
- Cada claim aparece clasificado como **Cifra**, **Declaración** o **Hecho**
- Si viene de audio, verás el **minuto aproximado** en que aparece
- Se incluye **contexto de fondo** con fuentes y enlaces
- Se muestran **verificaciones previas** de Ecuador Chequea y otros fact-checkers
- Puedes exportar todo en TXT o CSV
""",
        "method_title": "🔬 Metodología",
        "method": """
**¿Cómo funciona Criba?**

Criba combina tres tecnologías para identificar y enriquecer claims verificables:

**1. Transcripción automática (AssemblyAI)**
Si subes un archivo de audio, Criba lo envía a AssemblyAI, que usa modelos de reconocimiento de voz para transcribir el contenido con timestamps por palabra.

**2. Extracción y clasificación de claims (Claude · Anthropic)**
El texto se analiza con un modelo de lenguaje que distingue entre afirmaciones verificables y opiniones, promesas o valoraciones subjetivas. Cada claim se clasifica en tres categorías:
- **Cifra** — dato numérico, porcentaje, estadística o ranking
- **Declaración** — afirmación atribuida a una persona sobre un hecho concreto
- **Hecho** — afirmación sobre un evento, record o comparación verificable

**3. Búsqueda de verificaciones previas**
Para cada claim, Criba consulta dos fuentes:
- **Ecuador Chequea** — búsqueda directa en ecuadorchequea.com vía Google Custom Search
- **Google Fact Check Tools API** — base de datos global de verificaciones con esquema ClaimReview

El contexto de fondo se genera con búsqueda web en tiempo real para ofrecer fuentes y enlaces actualizados.

**Limitaciones importantes**
Criba es una herramienta de asistencia, no de verificación. La transcripción puede contener errores con nombres propios, tecnicismos o audio de baja calidad. La extracción puede omitir algunos claims o incluir falsos positivos. El contexto debe tratarse como punto de partida, no como conclusión. **La decisión editorial siempre corresponde al periodista o fact-checker.**
""",
        "tab_audio": "🎙️ Subir audio",
        "tab_text": "📋 Pegar transcripción",
        "tip_youtube": '💡 <strong>¿Tienes un video de YouTube?</strong> Descarga el audio gratis en <a href="https://cobalt.tools" target="_blank">cobalt.tools</a> — pega el enlace, selecciona "audio" y descarga el MP3.',
        "upload_label": "MP3, WAV, M4A · Máximo 200MB",
        "translate_label": "Traducir claims al español",
        "btn_transcribe": "🧐 Transcribir y extraer claims",
        "btn_extract": "🧐 Extraer claims",
        "paste_placeholder": "Pega aquí el texto transcrito…",
        "paste_tip": '💡 <strong>En YouTube:</strong> abre el video → clic en los tres puntos (···) → <em>Mostrar transcripción</em> → selecciona todo → copia y pega aquí.',
        "warn_no_file": "Sube un archivo de audio para continuar.",
        "warn_no_text": "Pega una transcripción para continuar.",
        "warn_short_text": "El texto es muy corto. Pega la transcripción completa.",
        "spinner_transcribe": "🎙️ Transcribiendo audio… esto puede tomar 1-2 minutos.",
        "spinner_claims": "👀 Identificando y clasificando claims verificables…",
        "found_claims": "claims verificables encontrados",
        "new_query": "← Nueva consulta",
        "context_title": "**Contexto de fondo**",
        "verif_title": "**Verificaciones relacionadas**",
        "no_verif": "*No se encontraron verificaciones previas.*",
        "minute_label": "**Minuto:**",
        "original_label": "**Cita original:**",
        "warning_human": "⚠️ <strong>Verificación humana obligatoria.</strong> Criba identifica claims con potencial verificable. La decisión editorial, el contraste de fuentes y la conclusión final siempre corresponden al periodista o fact-checker.",
        "export_title": "**Exportar resultados**",
        "btn_txt": "📄 Descargar TXT",
        "btn_csv": "📊 Descargar CSV",
        "tag_labels": {"cifra": "Cifra", "declaracion": "Declaración", "hecho": "Hecho"},
        "footer": "Criba · Ecuador Chequea · ChequeaLab",
    },
    "en": {
        "subtitle": "Extract what's worth verifying",
        "description": "**Criba** is an assistance tool for journalists and fact-checkers. It analyzes audio files or transcripts and automatically extracts claims with verification potential: figures, attributed statements, and assertions about concrete facts.",
        "app_lang_label": "Interface language",
        "audio_lang_label": "Audio language",
        "how_to_title": "📖 How to use Criba",
        "how_to": """
**Option 1 — Upload audio**
1. Select the interface language and the audio language
2. Upload your file (MP3, WAV or M4A, up to 200MB)
3. Indicate if you need claims translated
4. Click **Transcribe and extract claims**
5. Wait 1-3 minutes while it processes

**Option 2 — Paste transcript**
1. Copy the transcript text (on YouTube: three dots → *Show transcript*)
2. Paste it into the text field
3. Click **Extract claims**

**Results**
- Each claim is classified as **Figure**, **Statement** or **Fact**
- For audio files, you'll see the **approximate minute** where it appears
- A **background context** with sources and links is included
- **Prior fact-checks** from Ecuador Chequea and other fact-checkers are shown
- You can export everything as TXT or CSV
""",
        "method_title": "🔬 Methodology",
        "method": """
**How does Criba work?**

Criba combines three technologies to identify and enrich verifiable claims:

**1. Automatic transcription (AssemblyAI)**
When you upload an audio file, Criba sends it to AssemblyAI, which uses speech recognition models to transcribe the content with per-word timestamps.

**2. Claim extraction and classification (Claude · Anthropic)**
The text is analyzed with a language model that distinguishes between verifiable claims and opinions, promises, or subjective assessments. Each claim is classified into three categories:
- **Figure** — numerical data, percentage, statistic, or ranking
- **Statement** — claim attributed to a person about a concrete fact
- **Fact** — assertion about an event, record, or verifiable comparison

**3. Prior fact-check search**
For each claim, Criba queries two sources:
- **Ecuador Chequea** — direct search on ecuadorchequea.com via Google Custom Search
- **Google Fact Check Tools API** — global fact-check database using ClaimReview schema

Background context is generated with real-time web search to provide updated sources and links.

**Important limitations**
Criba is an assistance tool, not a verification tool. Transcription may contain errors with proper names, technical terms, or low-quality audio. Extraction may miss some claims or include false positives. Context should be treated as a starting point, not a conclusion. **Editorial decisions always rest with the journalist or fact-checker.**
""",
        "tab_audio": "🎙️ Upload audio",
        "tab_text": "📋 Paste transcript",
        "tip_youtube": '💡 <strong>Have a YouTube video?</strong> Download the audio for free at <a href="https://cobalt.tools" target="_blank">cobalt.tools</a> — paste the link, select "audio" and download the MP3.',
        "upload_label": "MP3, WAV, M4A · Up to 200MB",
        "translate_label": "Translate claims to Spanish",
        "btn_transcribe": "🧐 Transcribe and extract claims",
        "btn_extract": "🧐 Extract claims",
        "paste_placeholder": "Paste the transcript here…",
        "paste_tip": '💡 <strong>On YouTube:</strong> open the video → click the three dots (···) → <em>Show transcript</em> → select all → copy and paste here.',
        "warn_no_file": "Please upload an audio file to continue.",
        "warn_no_text": "Please paste a transcript to continue.",
        "warn_short_text": "The text is too short. Please paste the full transcript.",
        "spinner_transcribe": "🎙️ Transcribing audio… this may take 1-2 minutes.",
        "spinner_claims": "👀 Identifying and classifying verifiable claims…",
        "found_claims": "verifiable claims found",
        "new_query": "← New query",
        "context_title": "**Background context**",
        "verif_title": "**Related fact-checks**",
        "no_verif": "*No prior fact-checks found.*",
        "minute_label": "**Minute:**",
        "original_label": "**Original quote:**",
        "warning_human": "⚠️ <strong>Human verification required.</strong> Criba identifies claims with verification potential. Editorial decisions, source checking, and final conclusions always rest with the journalist or fact-checker.",
        "export_title": "**Export results**",
        "btn_txt": "📄 Download TXT",
        "btn_csv": "📊 Download CSV",
        "tag_labels": {"cifra": "Figure", "declaracion": "Statement", "hecho": "Fact"},
        "footer": "Criba · Ecuador Chequea · ChequeaLab",
    },
    "pt": {
        "subtitle": "Extrai o que vale verificar",
        "description": "**Criba** é uma ferramenta de assistência para jornalistas e fact-checkers. Analisa áudios ou transcrições e extrai automaticamente as afirmações com potencial verificável: números, declarações atribuídas e afirmações sobre fatos concretos.",
        "app_lang_label": "Idioma da interface",
        "audio_lang_label": "Idioma do áudio",
        "how_to_title": "📖 Como usar o Criba",
        "how_to": """
**Opção 1 — Enviar áudio**
1. Selecione o idioma da interface e o idioma do áudio
2. Envie seu arquivo (MP3, WAV ou M4A, até 200MB)
3. Indique se precisa de tradução das afirmações
4. Clique em **Transcrever e extrair afirmações**
5. Aguarde 1-3 minutos enquanto é processado

**Opção 2 — Colar transcrição**
1. Copie o texto transcrito (no YouTube: três pontos → *Mostrar transcrição*)
2. Cole no campo de texto
3. Clique em **Extrair afirmações**

**Resultados**
- Cada afirmação é classificada como **Número**, **Declaração** ou **Fato**
- Para áudios, você verá o **minuto aproximado** em que aparece
- Inclui **contexto de fundo** com fontes e links
- São exibidas **verificações anteriores** do Ecuador Chequea e outros fact-checkers
- Você pode exportar tudo em TXT ou CSV
""",
        "method_title": "🔬 Metodologia",
        "method": """
**Como funciona o Criba?**

O Criba combina três tecnologias para identificar e enriquecer afirmações verificáveis:

**1. Transcrição automática (AssemblyAI)**
Ao enviar um arquivo de áudio, o Criba o envia ao AssemblyAI, que usa modelos de reconhecimento de voz para transcrever o conteúdo com timestamps por palavra.

**2. Extração e classificação de afirmações (Claude · Anthropic)**
O texto é analisado com um modelo de linguagem que distingue entre afirmações verificáveis e opiniões, promessas ou avaliações subjetivas. Cada afirmação é classificada em três categorias:
- **Número** — dado numérico, porcentagem, estatística ou ranking
- **Declaração** — afirmação atribuída a uma pessoa sobre um fato concreto
- **Fato** — afirmação sobre um evento, recorde ou comparação verificável

**3. Busca de verificações anteriores**
Para cada afirmação, o Criba consulta duas fontes:
- **Ecuador Chequea** — busca direta em ecuadorchequea.com via Google Custom Search
- **Google Fact Check Tools API** — banco de dados global de verificações com esquema ClaimReview

O contexto de fundo é gerado com busca web em tempo real para fornecer fontes e links atualizados.

**Limitações importantes**
O Criba é uma ferramenta de assistência, não de verificação. A transcrição pode conter erros com nomes próprios, termos técnicos ou áudio de baixa qualidade. A extração pode omitir algumas afirmações ou incluir falsos positivos. O contexto deve ser tratado como ponto de partida, não como conclusão. **A decisão editorial sempre cabe ao jornalista ou fact-checker.**
""",
        "tab_audio": "🎙️ Enviar áudio",
        "tab_text": "📋 Colar transcrição",
        "tip_youtube": '💡 <strong>Tem um vídeo do YouTube?</strong> Baixe o áudio gratuitamente em <a href="https://cobalt.tools" target="_blank">cobalt.tools</a> — cole o link, selecione "áudio" e baixe o MP3.',
        "upload_label": "MP3, WAV, M4A · Máximo 200MB",
        "translate_label": "Traduzir afirmações para o espanhol",
        "btn_transcribe": "🧐 Transcrever e extrair afirmações",
        "btn_extract": "🧐 Extrair afirmações",
        "paste_placeholder": "Cole aqui o texto transcrito…",
        "paste_tip": '💡 <strong>No YouTube:</strong> abra o vídeo → clique nos três pontos (···) → <em>Mostrar transcrição</em> → selecione tudo → copie e cole aqui.',
        "warn_no_file": "Envie um arquivo de áudio para continuar.",
        "warn_no_text": "Cole uma transcrição para continuar.",
        "warn_short_text": "O texto é muito curto. Cole a transcrição completa.",
        "spinner_transcribe": "🎙️ Transcrevendo áudio… isso pode levar 1-2 minutos.",
        "spinner_claims": "👀 Identificando e classificando afirmações verificáveis…",
        "found_claims": "afirmações verificáveis encontradas",
        "new_query": "← Nova consulta",
        "context_title": "**Contexto de fundo**",
        "verif_title": "**Verificações relacionadas**",
        "no_verif": "*Nenhuma verificação anterior encontrada.*",
        "minute_label": "**Minuto:**",
        "original_label": "**Citação original:**",
        "warning_human": "⚠️ <strong>Verificação humana obrigatória.</strong> O Criba identifica afirmações com potencial verificável. A decisão editorial, a verificação de fontes e a conclusão final sempre cabem ao jornalista ou fact-checker.",
        "export_title": "**Exportar resultados**",
        "btn_txt": "📄 Baixar TXT",
        "btn_csv": "📊 Baixar CSV",
        "tag_labels": {"cifra": "Número", "declaracion": "Declaração", "hecho": "Fato"},
        "footer": "Criba · Ecuador Chequea · ChequeaLab",
    }
}

LANG_OPTIONS = {"Español": "es", "English": "en", "Português": "pt"}
AUDIO_LANG_CODES = {"Español": "es", "English": "en", "Português": "pt"}

# ── Estilos ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { max-width: 760px; margin: 0 auto; }
    .criba-header {
        display: flex; align-items: center; gap: 1rem;
        padding-bottom: 1.5rem; border-bottom: 1px solid #e5e5e5;
        margin-bottom: 1.5rem;
    }
    .logo-box {
        width: 48px; height: 48px; border-radius: 10px;
        background: #EEEDFE; display: flex; align-items: center;
        justify-content: center; font-size: 24px; flex-shrink: 0;
    }
    .criba-title { font-size: 24px; font-weight: 600; margin: 0; color: #1a1a1a; }
    .criba-sub { font-size: 14px; color: #666; margin: 2px 0 0; }
    .badge {
        display: inline-block; font-size: 11px; padding: 3px 10px;
        border-radius: 20px; font-weight: 500; margin-right: 6px;
    }
    .badge-purple { background: #EEEDFE; color: #3C3489; }
    .badge-gray { background: #F1EFE8; color: #444441; }
    .tag {
        display: inline-block; font-size: 11px; font-weight: 600;
        padding: 3px 10px; border-radius: 20px; margin-right: 8px;
        text-transform: uppercase; letter-spacing: 0.4px;
    }
    .tag-cifra { background: #E1F5EE; color: #085041; }
    .tag-declaracion { background: #EEEDFE; color: #3C3489; }
    .tag-hecho { background: #FAEEDA; color: #633806; }
    .warning-box {
        background: #EEEDFE; border-radius: 8px; padding: 12px 16px;
        margin-top: 1.5rem; font-size: 13px; color: #26215C;
        border-left: 3px solid #7F77DD;
    }
    .tip-box {
        background: #F1EFE8; border-radius: 8px; padding: 12px 16px;
        margin-bottom: 1rem; font-size: 13px; color: #444441;
        border-left: 3px solid #999;
    }
    .source-chip {
        display: inline-flex; align-items: center; gap: 6px;
        background: #f5f5f5; border-radius: 6px;
        padding: 5px 10px; font-size: 12px; color: #333;
        text-decoration: none; margin-top: 6px; margin-right: 6px;
    }
    .source-chip-ec {
        display: inline-flex; align-items: center; gap: 6px;
        background: #EEEDFE; border-radius: 6px;
        padding: 5px 10px; font-size: 12px; color: #3C3489;
        text-decoration: none; margin-top: 6px; margin-right: 6px;
        font-weight: 500;
    }
    .original-quote {
        font-size: 13px; color: #666; font-style: italic;
        border-left: 2px solid #ddd; padding-left: 10px; margin-top: 4px;
    }
    .footer-bar {
        text-align: center; font-size: 12px; color: #999;
        padding-top: 2rem; margin-top: 2rem;
        border-top: 1px solid #eee;
    }
</style>
""", unsafe_allow_html=True)

# ── Estado inicial ────────────────────────────────────────────────────────────
if "app_lang" not in st.session_state:
    st.session_state.app_lang = "es"
if "transcription" not in st.session_state:
    st.session_state.transcription = ""
if "claims" not in st.session_state:
    st.session_state.claims = []
if "step" not in st.session_state:
    st.session_state.step = 1
if "words" not in st.session_state:
    st.session_state.words = []

# ── Selector de idioma de interfaz (siempre visible) ─────────────────────────
lang_col, _ = st.columns([1, 3])
with lang_col:
    app_lang_choice = st.selectbox(
        "🌐",
        list(LANG_OPTIONS.keys()),
        index=list(LANG_OPTIONS.values()).index(st.session_state.app_lang),
        label_visibility="collapsed"
    )
    st.session_state.app_lang = LANG_OPTIONS[app_lang_choice]

T = UI_TEXTS[st.session_state.app_lang]

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="criba-header">
    <div class="logo-box">⚗️</div>
    <div>
        <p class="criba-title">Criba</p>
        <p class="criba-sub">{T['subtitle']}</p>
        <a href="https://ecuadorchequea.com" target="_blank" class="badge badge-purple" style="text-decoration:none;">Ecuador Chequea</a>
        <a href="https://chequealab.com" target="_blank" class="badge badge-gray" style="text-decoration:none;">ChequeaLab</a>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(T["description"])

with st.expander(T["how_to_title"]):
    st.markdown(T["how_to"])

with st.expander(T["method_title"]):
    st.markdown(T["method"])

st.markdown("---")

# ── Clientes ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_anthropic_client():
    return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

@st.cache_resource
def get_google_api_key():
    return st.secrets["GOOGLE_API_KEY"]

def get_assemblyai_key():
    return st.secrets["ASSEMBLYAI_API_KEY"]

CUSTOM_SEARCH_CX = "b31919749081e4a43"

# ── Transcripción ─────────────────────────────────────────────────────────────
def transcribe_audio_file(audio_bytes: bytes, filename: str, lang_code: str) -> tuple:
    api_key = get_assemblyai_key()
    headers_auth = {"authorization": api_key}

    upload_response = requests.post(
        "https://api.assemblyai.com/v2/upload",
        headers=headers_auth,
        data=audio_bytes,
        timeout=120
    )
    if upload_response.status_code != 200:
        raise ValueError("Error subiendo el archivo. Intenta de nuevo.")

    audio_url = upload_response.json()["upload_url"]

    transcript_response = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers={**headers_auth, "content-type": "application/json"},
        json={"audio_url": audio_url, "language_code": lang_code, "format_text": True}
    )
    if transcript_response.status_code != 200:
        raise ValueError("Error iniciando la transcripción.")

    transcript_id = transcript_response.json()["id"]
    polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"

    for _ in range(120):
        poll = requests.get(polling_url, headers=headers_auth)
        data = poll.json()
        status = data.get("status")
        if status == "completed":
            text = data.get("text", "")
            if not text:
                raise ValueError("La transcripción no produjo texto.")
            return text, data.get("words", [])
        elif status == "error":
            raise ValueError(f"Error en transcripción: {data.get('error')}")
        time.sleep(2)

    raise ValueError("La transcripción tardó demasiado.")


def find_timestamp_for_claim(claim_text: str, words: list):
    if not words:
        return None
    claim_words = claim_text.lower().split()
    if not claim_words:
        return None
    first_word = claim_words[0].strip('",.')
    for w in words:
        if w.get("text", "").lower().strip('",.:') == first_word:
            start_ms = w.get("start", 0)
            total_seconds = start_ms // 1000
            return f"{total_seconds // 60}:{total_seconds % 60:02d}"
    return None


# ── Extracción y traducción ───────────────────────────────────────────────────
def extract_claims(transcription: str, audio_lang: str, translate_to_es: bool) -> list:
    client = get_anthropic_client()
    lang_map = {"es": "español", "en": "inglés", "pt": "portugués"}
    lang_name = lang_map.get(audio_lang, "español")

    translate_instruction = ""
    if translate_to_es and audio_lang != "es":
        translate_instruction = '\n      "texto_traducido": "traducción al español del claim (solo si el audio no es en español)",'

    prompt = f"""Analyze this transcription in {lang_name} and extract only the claims that have verifiable potential with factual evidence.

INCLUDE:
- Figures and statistics (percentages, numbers, rankings, economic data)
- Statements attributed to people about concrete facts
- Assertions about verifiable facts (records, comparisons, firsts)

EXCLUDE:
- Future promises or commitments
- Opinions, qualifiers, or value judgments
- Religious beliefs
- Plans or intentions without concrete figures

Return a JSON with this exact format:
{{
  "claims": [
    {{
      "texto": "exact quote of the claim in the original language",{translate_instruction}
      "tipo": "cifra",
      "verificable": true,
      "contexto_minuto": null
    }}
  ]
}}

"tipo" must be one of: "cifra", "declaracion", "hecho".
Return ONLY valid JSON, no extra text, no backticks.

TRANSCRIPTION:
{transcription}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    return data.get("claims", [])


# ── Búsqueda de verificaciones ────────────────────────────────────────────────
def build_search_query(claim_text: str) -> str:
    stopwords = {"que", "en", "el", "la", "los", "las", "de", "del", "un", "una", "con",
                 "por", "para", "era", "fue", "es", "se", "su", "sus", "al", "le", "lo",
                 "y", "o", "a", "e", "the", "is", "are", "was", "were", "of", "in", "on",
                 "at", "to", "for", "with", "that", "this", "and", "or"}
    words = claim_text.lower().split()
    keywords = [w.strip('",.:;()') for w in words if w.strip('",.:;()') not in stopwords and len(w) > 3]
    return " ".join(keywords[:6])


def search_ecuador_chequea(query: str) -> list:
    api_key = get_google_api_key()
    short_query = build_search_query(query)
    params = {"key": api_key, "cx": CUSTOM_SEARCH_CX, "q": short_query, "num": 3}
    results = []
    try:
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        if response.status_code == 200:
            for item in response.json().get("items", []):
                results.append({
                    "org": "Ecuador Chequea",
                    "titulo": item.get("title", ""),
                    "url": item.get("link", ""),
                    "fecha": "",
                    "fuente": "ecuadorchequea"
                })
    except Exception:
        pass
    return results


def search_factcheck_tools(query: str) -> list:
    api_key = get_google_api_key()
    params = {"query": query, "key": api_key, "languageCode": "es", "pageSize": 5}
    results = []
    try:
        response = requests.get("https://factchecktools.googleapis.com/v1alpha1/claims:search", params=params, timeout=10)
        if response.status_code == 200:
            for claim in response.json().get("claims", []):
                for review in claim.get("claimReview", []):
                    name = review.get("publisher", {}).get("name", "")
                    results.append({
                        "org": name,
                        "titulo": review.get("title", claim.get("text", "")),
                        "url": review.get("url", ""),
                        "fecha": review.get("reviewDate", "")[:10] if review.get("reviewDate") else "",
                        "fuente": "factcheck"
                    })
    except Exception:
        pass
    return results


def search_all_verificaciones(query: str) -> list:
    ec_results = search_ecuador_chequea(query)
    fc_results = search_factcheck_tools(query)
    ec_from_fc = [r for r in fc_results if "ecuador" in r.get("org", "").lower() or "chequea" in r.get("org", "").lower()]
    otros = [r for r in fc_results if r not in ec_from_fc]
    seen_urls = set()
    combined = []
    for r in ec_results + ec_from_fc + otros:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            combined.append(r)
    return combined[:4]


def get_context(claim_text: str) -> str:
    client = get_anthropic_client()
    prompt = f"""Busca información sobre este claim y responde en UNA sola oración con qué dice la fuente más relevante que encuentres. Incluye el enlace entre paréntesis al final.

Si no encuentras nada confiable, responde exactamente: "Sin contexto verificable en fuentes oficiales."

Reglas estrictas:
- Solo UNA oración
- Sin negritas
- Sin elaboraciones ni notas
- El enlace va entre paréntesis al final

Ejemplo: "Según la Fiscalía, Glas tenía arresto domiciliario desde octubre de 2023 (fiscalia.gob.ec/...)."

Claim: {claim_text}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    return " ".join(text_parts).strip() if text_parts else "Sin contexto verificable en fuentes oficiales."


# ── Exportación ───────────────────────────────────────────────────────────────
def export_csv(claims: list) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["tipo", "minuto", "texto", "texto_traducido", "contexto", "fuentes"])
    writer.writeheader()
    for c in claims:
        fuentes = "; ".join([r.get("url", "") for r in c.get("verificaciones", [])])
        writer.writerow({
            "tipo": c.get("tipo", ""),
            "minuto": c.get("minuto", ""),
            "texto": c.get("texto", ""),
            "texto_traducido": c.get("texto_traducido", ""),
            "contexto": c.get("contexto", ""),
            "fuentes": fuentes
        })
    return output.getvalue()


def export_txt(claims: list, T: dict) -> str:
    lines = [f"CRIBA · Ecuador Chequea\nExportado: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n{'─'*50}\n"]
    for i, c in enumerate(claims, 1):
        minuto = f" [min. {c['minuto']}]" if c.get("minuto") else ""
        lines.append(f"{i}. [{c.get('tipo','').upper()}]{minuto} {c.get('texto','')}")
        if c.get("texto_traducido"):
            lines.append(f"   Traducción: {c['texto_traducido']}")
        if c.get("contexto"):
            lines.append(f"   Contexto: {c['contexto']}")
        for v in c.get("verificaciones", []):
            lines.append(f"   Fuente: {v.get('org','')} — {v.get('url','')}")
        lines.append("")
    lines.append("La verificación final corresponde siempre al periodista o fact-checker.")
    return "\n".join(lines)


# ── Paso 1: Input ─────────────────────────────────────────────────────────────
if st.session_state.step == 1:

    col1, col2 = st.columns(2)
    with col1:
        audio_lang_choice = st.selectbox(T["audio_lang_label"], list(LANG_OPTIONS.keys()))
    audio_lang_code = LANG_OPTIONS[audio_lang_choice]

    needs_translation = False
    if audio_lang_code != "es":
        needs_translation = st.checkbox(T["translate_label"], value=True)

    tab1, tab2 = st.tabs([T["tab_audio"], T["tab_text"]])

    with tab1:
        st.markdown(f'<div class="tip-box">{T["tip_youtube"]}</div>', unsafe_allow_html=True)

        uploaded = st.file_uploader(
            T["upload_label"],
            type=["mp3", "wav", "m4a"],
            label_visibility="collapsed"
        )

        if st.button(T["btn_transcribe"], type="primary", use_container_width=True, key="btn_audio"):
            if not uploaded:
                st.warning(T["warn_no_file"])
            else:
                with st.spinner(T["spinner_transcribe"]):
                    try:
                        transcription, words = transcribe_audio_file(uploaded.read(), uploaded.name, audio_lang_code)
                        st.session_state.transcription = transcription
                        st.session_state.words = words
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        st.stop()

                with st.spinner(T["spinner_claims"]):
                    try:
                        claims_raw = extract_claims(transcription, audio_lang_code, needs_translation)
                        enriched = []
                        for claim in claims_raw:
                            minuto = find_timestamp_for_claim(claim["texto"], st.session_state.words)
                            verificaciones = search_all_verificaciones(claim.get("texto_traducido") or claim["texto"])
                            contexto = get_context(claim.get("texto_traducido") or claim["texto"])
                            enriched.append({**claim, "minuto": minuto, "verificaciones": verificaciones, "contexto": contexto})
                        st.session_state.claims = enriched
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    with tab2:
        st.markdown(f'<div class="tip-box">{T["paste_tip"]}</div>', unsafe_allow_html=True)

        texto_input = st.text_area(
            "transcript",
            height=250,
            placeholder=T["paste_placeholder"],
            label_visibility="collapsed"
        )

        if st.button(T["btn_extract"], type="primary", use_container_width=True, key="btn_texto"):
            if not texto_input.strip():
                st.warning(T["warn_no_text"])
            elif len(texto_input.strip()) < 50:
                st.warning(T["warn_short_text"])
            else:
                st.session_state.transcription = texto_input.strip()
                st.session_state.words = []
                with st.spinner(T["spinner_claims"]):
                    try:
                        claims_raw = extract_claims(texto_input.strip(), audio_lang_code, needs_translation)
                        enriched = []
                        for claim in claims_raw:
                            verificaciones = search_all_verificaciones(claim.get("texto_traducido") or claim["texto"])
                            contexto = get_context(claim.get("texto_traducido") or claim["texto"])
                            enriched.append({**claim, "minuto": None, "verificaciones": verificaciones, "contexto": contexto})
                        st.session_state.claims = enriched
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

# ── Paso 2: Resultados ────────────────────────────────────────────────────────
elif st.session_state.step == 2:
    claims = st.session_state.claims
    T = UI_TEXTS[st.session_state.app_lang]

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown(f"**{len(claims)} {T['found_claims']}**")
    with col_b:
        if st.button(T["new_query"], use_container_width=True):
            st.session_state.step = 1
            st.session_state.claims = []
            st.session_state.transcription = ""
            st.session_state.words = []
            st.rerun()

    for claim in claims:
        tipo = claim.get("tipo", "hecho")
        tag_label = T["tag_labels"].get(tipo, tipo.capitalize())
        texto_display = claim.get("texto_traducido") or claim.get("texto", "")

        with st.expander(f'[{tag_label.upper()}] {texto_display}'):

            if claim.get("texto_traducido") and claim.get("texto"):
                st.markdown(T["original_label"])
                st.markdown(f'<div class="original-quote">{claim["texto"]}</div>', unsafe_allow_html=True)

            if claim.get("minuto"):
                st.markdown(f'{T["minute_label"]} {claim["minuto"]}')

            if claim.get("contexto"):
                st.markdown(T["context_title"])
                st.markdown(claim["contexto"])

            verificaciones = claim.get("verificaciones", [])
            if verificaciones:
                st.markdown(T["verif_title"])
                for v in verificaciones:
                    org = v.get("org", "Fuente")
                    titulo = v.get("titulo", "")
                    url = v.get("url", "#")
                    fecha = v.get("fecha", "")
                    fecha_str = f" · {fecha}" if fecha else ""
                    chip_class = "source-chip-ec" if v.get("fuente") == "ecuadorchequea" or "ecuador" in org.lower() else "source-chip"
                    icon = "✅" if chip_class == "source-chip-ec" else "🔗"
                    st.markdown(f'<a href="{url}" target="_blank" class="{chip_class}">{icon} {org}{fecha_str} — {titulo[:60]}...</a>', unsafe_allow_html=True)
            else:
                st.markdown(T["no_verif"])

    st.markdown(f'<div class="warning-box">{T["warning_human"]}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(T["export_title"])
    col1, col2 = st.columns(2)
    txt_content = export_txt(claims, T)
    csv_content = export_csv(claims)

    with col1:
        st.download_button(T["btn_txt"], data=txt_content, file_name=f"criba_{datetime.now().strftime('%Y%m%d_%H%M')}.txt", mime="text/plain", use_container_width=True)
    with col2:
        st.download_button(T["btn_csv"], data=csv_content, file_name=f"criba_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv", use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="footer-bar">{T["footer"]}</div>', unsafe_allow_html=True)
