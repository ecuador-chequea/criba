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
import re

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Criba · Ecuador Chequea",
    page_icon="🔎",
    layout="centered"
)

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
    .source-chip {
        display: inline-flex; align-items: center; gap: 6px;
        background: #f5f5f5; border-radius: 6px;
        padding: 5px 10px; font-size: 12px; color: #333;
        text-decoration: none; margin-top: 6px; margin-right: 6px;
    }
    .footer-bar {
        text-align: center; font-size: 12px; color: #999;
        padding-top: 2rem; margin-top: 2rem;
        border-top: 1px solid #eee;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="criba-header">
    <div class="logo-box">⚗️</div>
    <div>
        <p class="criba-title">Criba</p>
        <p class="criba-sub">Extrae lo que vale verificar</p>
        <span class="badge badge-purple">Ecuador Chequea</span>
        <span class="badge badge-gray">ChequeaLab</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Clientes ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_anthropic_client():
    return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

@st.cache_resource
def get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

@st.cache_resource
def get_google_api_key():
    return st.secrets["GOOGLE_API_KEY"]

# ── Funciones YouTube ─────────────────────────────────────────────────────────

def extract_video_id(url: str):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:embed\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_transcript_api(video_id: str):
    """Extrae subtítulos con youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        
        # Intentar español primero, luego cualquier idioma
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['es', 'es-419', 'es-EC'])
        except NoTranscriptFound:
            # Buscar cualquier transcript disponible
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(
                transcript_list._manually_created_transcripts or 
                list(transcript_list._generated_transcripts.keys())
            ).fetch()
        
        text = ' '.join([t['text'] for t in transcript])
        text = text.replace('\n', ' ').strip()
        return text if len(text) > 50 else None
        
    except Exception:
        return None


def process_youtube_url(url: str) -> str:
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError("URL de YouTube no válida.")

    st.info("🔍 Buscando subtítulos del video…")
    transcript = get_transcript_api(video_id)
    if transcript:
        st.success("✅ Subtítulos obtenidos correctamente.")
        return transcript

    raise ValueError(
        "No se encontraron subtítulos en este video. "
        "Para videos sin subtítulos, descarga el audio y súbelo directamente como archivo MP3."
    )


# ── Transcripción de archivo ──────────────────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    client = get_openai_client()
    suffix = Path(filename).suffix or '.mp3'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="es"
            )
        return response.text
    finally:
        os.unlink(tmp_path)


# ── Extracción de claims ──────────────────────────────────────────────────────

def extract_claims(transcription: str, language: str = "es") -> list:
    client = get_anthropic_client()
    lang_map = {"es": "español", "en": "inglés", "pt": "portugués"}
    lang_name = lang_map.get(language, "español")

    prompt = f"""Analiza esta transcripción en {lang_name} y extrae únicamente los claims que tienen potencial verificable con evidencia factual.

INCLUYE:
- Cifras y estadísticas (porcentajes, números, rankings, datos económicos)
- Declaraciones atribuidas a personas sobre hechos concretos
- Afirmaciones sobre hechos verificables (records, primeros lugares, comparaciones)

EXCLUYE absolutamente:
- Promesas o compromisos futuros
- Opiniones, calificativos o adjetivos valorativos
- Creencias religiosas o afirmaciones de fe
- Intenciones o planes sin cifras concretas

Para cada claim devuelve un JSON con este formato exacto:
{{
  "claims": [
    {{
      "texto": "cita exacta del claim",
      "tipo": "cifra",
      "verificable": true,
      "contexto_minuto": null
    }}
  ]
}}

El campo "tipo" solo puede ser: "cifra", "declaracion" o "hecho".
Devuelve SOLO el JSON válido, sin texto adicional, sin backticks.

TRANSCRIPCIÓN:
{transcription}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    return data.get("claims", [])


def search_factchecks(query: str) -> list:
    api_key = get_google_api_key()
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    params = {"query": query, "key": api_key, "languageCode": "es", "pageSize": 3}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            for claim in data.get("claims", []):
                for review in claim.get("claimReview", []):
                    publisher = review.get("publisher", {})
                    name = publisher.get("name", "")
                    if "Lupa" in name:
                        continue
                    results.append({
                        "org": name,
                        "titulo": review.get("title", claim.get("text", "")),
                        "url": review.get("url", ""),
                        "fecha": review.get("reviewDate", "")[:10] if review.get("reviewDate") else ""
                    })
            return results[:2]
    except Exception:
        pass
    return []


def get_context(claim_text: str) -> str:
    client = get_anthropic_client()
    prompt = f"""Proporciona contexto factual breve (máximo 2 oraciones) sobre este claim, citando la fuente oficial. Si no tienes información confiable, di "No se encontró contexto verificable en fuentes oficiales."

Claim: {claim_text}

Formato: explicación directa con fuente entre paréntesis. Ejemplo: "Según el INEC, la tasa fue X% en Y (INEC, 2024)."
"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()


def export_csv(claims: list) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["tipo", "texto", "contexto", "fuentes"])
    writer.writeheader()
    for c in claims:
        fuentes = "; ".join([r.get("url", "") for r in c.get("verificaciones", [])])
        writer.writerow({"tipo": c.get("tipo", ""), "texto": c.get("texto", ""), "contexto": c.get("contexto", ""), "fuentes": fuentes})
    return output.getvalue()


def export_txt(claims: list) -> str:
    lines = [f"CRIBA · Ecuador Chequea\nExportado: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n{'─'*50}\n"]
    for i, c in enumerate(claims, 1):
        lines.append(f"{i}. [{c.get('tipo','').upper()}] {c.get('texto','')}")
        if c.get("contexto"):
            lines.append(f"   Contexto: {c['contexto']}")
        for v in c.get("verificaciones", []):
            lines.append(f"   Fuente: {v.get('org','')} — {v.get('url','')}")
        lines.append("")
    lines.append("⚠ La verificación final corresponde siempre al periodista o fact-checker.")
    return "\n".join(lines)


# ── Estado ────────────────────────────────────────────────────────────────────
if "transcription" not in st.session_state:
    st.session_state.transcription = ""
if "claims" not in st.session_state:
    st.session_state.claims = []
if "step" not in st.session_state:
    st.session_state.step = 1

# ── Paso 1: Input ─────────────────────────────────────────────────────────────
if st.session_state.step == 1:

    col1, col2, col3 = st.columns(3)
    with col1:
        lang = st.selectbox("Idioma del audio", ["Español", "English", "Português"])
    lang_code = {"Español": "es", "English": "en", "Português": "pt"}[lang]

    st.markdown("#### Sube tu archivo de audio o video")
    uploaded = st.file_uploader("Formatos soportados", type=["mp3", "mp4", "wav", "m4a", "mov", "ogg"], label_visibility="collapsed")

    st.markdown("**O pega una URL de YouTube**")
    url_input = st.text_input("URL", placeholder="https://youtube.com/watch?v=...", label_visibility="collapsed")

    if st.button("⚗️ Transcribir y extraer claims", type="primary", use_container_width=True):
        if not uploaded and not url_input.strip():
            st.warning("Sube un archivo o pega una URL para continuar.")
        else:
            with st.spinner("Procesando…"):
                try:
                    if uploaded:
                        st.info("🎙️ Transcribiendo con Whisper…")
                        transcription = transcribe_audio(uploaded.read(), uploaded.name)
                    else:
                        transcription = process_youtube_url(url_input.strip())
                    st.session_state.transcription = transcription
                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.stop()

            with st.spinner("Identificando y clasificando claims verificables…"):
                try:
                    claims_raw = extract_claims(transcription, lang_code)
                    enriched = []
                    for claim in claims_raw:
                        verificaciones = search_factchecks(claim["texto"])
                        contexto = get_context(claim["texto"])
                        enriched.append({**claim, "verificaciones": verificaciones, "contexto": contexto})
                    st.session_state.claims = enriched
                    st.session_state.step = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al extraer claims: {str(e)}")

# ── Paso 2: Resultados ────────────────────────────────────────────────────────
elif st.session_state.step == 2:
    claims = st.session_state.claims

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.markdown(f"**{len(claims)} claims verificables encontrados**")
    with col_b:
        if st.button("← Nueva consulta", use_container_width=True):
            st.session_state.step = 1
            st.session_state.claims = []
            st.session_state.transcription = ""
            st.rerun()

    tag_labels = {"cifra": "Cifra", "declaracion": "Declaración", "hecho": "Hecho"}

    for i, claim in enumerate(claims):
        tipo = claim.get("tipo", "hecho")
        tag_label = tag_labels.get(tipo, tipo.capitalize())

        with st.expander(f'[{tag_label.upper()}] {claim["texto"]}'):
            if claim.get("contexto"):
                st.markdown("**Contexto de fondo**")
                st.markdown(claim["contexto"])

            verificaciones = claim.get("verificaciones", [])
            if verificaciones:
                st.markdown("**Verificaciones relacionadas**")
                for v in verificaciones:
                    org = v.get("org", "Fuente")
                    titulo = v.get("titulo", "Ver verificación")
                    url = v.get("url", "#")
                    fecha = v.get("fecha", "")
                    fecha_str = f" · {fecha}" if fecha else ""
                    st.markdown(f'<a href="{url}" target="_blank" class="source-chip">🔗 {org}{fecha_str} — {titulo[:60]}...</a>', unsafe_allow_html=True)
            else:
                st.markdown("*No se encontraron verificaciones previas en bases de datos de fact-checkers.*")

    st.markdown("""
    <div class="warning-box">
    ⚠️ <strong>Verificación humana obligatoria.</strong> Criba identifica claims con potencial verificable. 
    La decisión editorial, el contraste de fuentes y la conclusión final siempre corresponden al periodista o fact-checker.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Exportar resultados**")
    col1, col2, col3 = st.columns(3)
    txt_content = export_txt(claims)
    csv_content = export_csv(claims)

    with col1:
        st.download_button("📄 Descargar TXT", data=txt_content, file_name=f"criba_{datetime.now().strftime('%Y%m%d_%H%M')}.txt", mime="text/plain", use_container_width=True)
    with col2:
        st.download_button("📊 Descargar CSV", data=csv_content, file_name=f"criba_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv", use_container_width=True)
    with col3:
        st.download_button("📑 Descargar PDF", data=txt_content.encode(), file_name=f"criba_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf", mime="application/pdf", use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer-bar">
    Criba · Ecuador Chequea · ChequeaLab
</div>
""", unsafe_allow_html=True)
