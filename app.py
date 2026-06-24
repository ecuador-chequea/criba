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
    .minute-badge {
        display: inline-block; font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 20px;
        background: #F1EFE8; color: #633806; margin-left: 8px;
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
def get_google_api_key():
    return st.secrets["GOOGLE_API_KEY"]

def get_assemblyai_key():
    return st.secrets["ASSEMBLYAI_API_KEY"]

CUSTOM_SEARCH_CX = "b31919749081e4a43"

# ── Transcripción con AssemblyAI ──────────────────────────────────────────────

def transcribe_audio_file(audio_bytes: bytes, filename: str) -> tuple:
    """Devuelve (texto, lista de words con timestamps)"""
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
        json={
            "audio_url": audio_url,
            "language_code": "es",
            "word_boost": [],
            "format_text": True
        }
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
                raise ValueError("La transcripción no produjo texto. Verifica que el audio tenga voz.")
            words = data.get("words", [])
            return text, words
        elif status == "error":
            raise ValueError(f"Error en transcripción: {data.get('error')}")
        time.sleep(2)

    raise ValueError("La transcripción tardó demasiado. Intenta con un archivo más corto.")


def find_timestamp_for_claim(claim_text: str, words: list) -> str | None:
    """Busca el minuto aproximado de un claim en la lista de words de AssemblyAI."""
    if not words:
        return None

    claim_words = claim_text.lower().split()
    if not claim_words:
        return None

    # Buscar la primera palabra del claim en la lista de words
    first_word = claim_words[0].strip('",.')
    for i, w in enumerate(words):
        word_text = w.get("text", "").lower().strip('",.')
        if word_text == first_word:
            start_ms = w.get("start", 0)
            total_seconds = start_ms // 1000
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}:{seconds:02d}"

    return None


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


# ── Búsqueda de verificaciones ────────────────────────────────────────────────

def search_factcheck_tools(query: str) -> list:
    """Busca en Google Fact Check Tools API (ClaimReview global)."""
    api_key = get_google_api_key()
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    params = {"query": query, "key": api_key, "languageCode": "es", "pageSize": 5}
    results = []
    try:
        response = requests.get(url, params=params, timeout=10)
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


def search_ecuador_chequea(query: str) -> list:
    """Busca en ecuadorchequea.com usando Google Custom Search API."""
    api_key = get_google_api_key()
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": CUSTOM_SEARCH_CX,
        "q": query,
        "num": 3
    }
    results = []
    try:
        response = requests.get(url, params=params, timeout=10)
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


def search_all_verificaciones(query: str) -> list:
    """Combina ambas fuentes, deduplicando por URL. Ecuador Chequea primero."""
    ec_results = search_ecuador_chequea(query)
    fc_results = search_factcheck_tools(query)

    # Separar Ecuador Chequea de otros en fc_results
    ec_from_fc = [r for r in fc_results if "ecuador" in r.get("org", "").lower() or "chequea" in r.get("org", "").lower()]
    otros = [r for r in fc_results if r not in ec_from_fc]

    # Combinar: EC primero (sin duplicar URLs)
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


# ── Exportación ───────────────────────────────────────────────────────────────

def export_csv(claims: list) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["tipo", "minuto", "texto", "contexto", "fuentes"])
    writer.writeheader()
    for c in claims:
        fuentes = "; ".join([r.get("url", "") for r in c.get("verificaciones", [])])
        writer.writerow({
            "tipo": c.get("tipo", ""),
            "minuto": c.get("minuto", ""),
            "texto": c.get("texto", ""),
            "contexto": c.get("contexto", ""),
            "fuentes": fuentes
        })
    return output.getvalue()


def export_txt(claims: list) -> str:
    lines = [f"CRIBA · Ecuador Chequea\nExportado: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n{'─'*50}\n"]
    for i, c in enumerate(claims, 1):
        minuto = f" [min. {c['minuto']}]" if c.get("minuto") else ""
        lines.append(f"{i}. [{c.get('tipo','').upper()}]{minuto} {c.get('texto','')}")
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
if "words" not in st.session_state:
    st.session_state.words = []

# ── Paso 1: Input ─────────────────────────────────────────────────────────────
if st.session_state.step == 1:

    col1, col2, col3 = st.columns(3)
    with col1:
        lang = st.selectbox("Idioma del audio", ["Español", "English", "Português"])
    lang_code = {"Español": "es", "English": "en", "Português": "pt"}[lang]

    tab1, tab2 = st.tabs(["🎙️ Subir audio o video", "📋 Pegar transcripción"])

    with tab1:
        st.markdown("""
        <div class="tip-box">
        💡 <strong>¿Tienes un video de YouTube?</strong> Descarga el audio gratis en 
        <a href="https://cobalt.tools" target="_blank">cobalt.tools</a> — pega el enlace, 
        selecciona "audio" y descarga el MP3. O copia la transcripción de YouTube y pégala en la pestaña de al lado.
        </div>
        """, unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "MP3, MP4, WAV, M4A, MOV, OGG · Máximo 200MB",
            type=["mp3", "mp4", "wav", "m4a", "mov", "ogg"],
            label_visibility="collapsed"
        )

        if st.button("⚗️ Transcribir y extraer claims", type="primary", use_container_width=True, key="btn_audio"):
            if not uploaded:
                st.warning("Sube un archivo de audio o video para continuar.")
            else:
                with st.spinner("🎙️ Transcribiendo audio… esto puede tomar 1-2 minutos."):
                    try:
                        transcription, words = transcribe_audio_file(uploaded.read(), uploaded.name)
                        st.session_state.transcription = transcription
                        st.session_state.words = words
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        st.stop()

                with st.spinner("🔍 Identificando y clasificando claims verificables…"):
                    try:
                        claims_raw = extract_claims(transcription, lang_code)
                        enriched = []
                        for claim in claims_raw:
                            minuto = find_timestamp_for_claim(claim["texto"], st.session_state.words)
                            verificaciones = search_all_verificaciones(claim["texto"])
                            contexto = get_context(claim["texto"])
                            enriched.append({
                                **claim,
                                "minuto": minuto,
                                "verificaciones": verificaciones,
                                "contexto": contexto
                            })
                        st.session_state.claims = enriched
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al extraer claims: {str(e)}")

    with tab2:
        st.markdown("""
        <div class="tip-box">
        💡 <strong>En YouTube:</strong> abre el video → clic en los tres puntos (···) → 
        <em>Mostrar transcripción</em> → selecciona todo el texto → copia y pega aquí.
        </div>
        """, unsafe_allow_html=True)

        texto_input = st.text_area(
            "Transcripción",
            height=250,
            placeholder="Pega aquí el texto transcrito…",
            label_visibility="collapsed"
        )

        if st.button("⚗️ Extraer claims", type="primary", use_container_width=True, key="btn_texto"):
            if not texto_input.strip():
                st.warning("Pega una transcripción para continuar.")
            elif len(texto_input.strip()) < 50:
                st.warning("El texto es muy corto. Pega la transcripción completa.")
            else:
                st.session_state.transcription = texto_input.strip()
                st.session_state.words = []
                with st.spinner("🔍 Identificando y clasificando claims verificables…"):
                    try:
                        claims_raw = extract_claims(texto_input.strip(), lang_code)
                        enriched = []
                        for claim in claims_raw:
                            verificaciones = search_all_verificaciones(claim["texto"])
                            contexto = get_context(claim["texto"])
                            enriched.append({
                                **claim,
                                "minuto": None,
                                "verificaciones": verificaciones,
                                "contexto": contexto
                            })
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
            st.session_state.words = []
            st.rerun()

    tag_labels = {"cifra": "Cifra", "declaracion": "Declaración", "hecho": "Hecho"}

    for i, claim in enumerate(claims):
        tipo = claim.get("tipo", "hecho")
        tag_label = tag_labels.get(tipo, tipo.capitalize())
        minuto = claim.get("minuto")
        minuto_str = f' <span class="minute-badge">⏱ {minuto}</span>' if minuto else ""

        with st.expander(f'[{tag_label.upper()}] {claim["texto"]}'):

            if minuto:
                st.markdown(f"**Minuto:** {minuto}")

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
                    chip_class = "source-chip-ec" if v.get("fuente") == "ecuadorchequea" or "ecuador" in org.lower() else "source-chip"
                    icon = "✅" if chip_class == "source-chip-ec" else "🔗"
                    st.markdown(f'<a href="{url}" target="_blank" class="{chip_class}">{icon} {org}{fecha_str} — {titulo[:60]}...</a>', unsafe_allow_html=True)
            else:
                st.markdown("*No se encontraron verificaciones previas.*")

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
