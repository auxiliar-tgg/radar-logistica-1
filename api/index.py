import re
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Dominios de directorios genéricos que ignoraremos para quedarnos solo con empresas reales
DOMINIOS_EXCLUIDOS = (
    'yelp.', 'yellowpages.', 'paginasamarillas.', 'facebook.', 'linkedin.',
    'instagram.', 'twitter.', 'x.com', 'youtube.', 'wikipedia.', 'dnb.',
    'zoominfo.', 'kompass.', 'thomasnet.', 'manta.', 'bbb.org', 'indeed.'
)

def extraer_datos_de_web(url):
    """Entra a la web oficial de la empresa y extrae teléfonos y correos reales."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    correos = set()
    telefono = "No disponible públicamente"

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            sopa = BeautifulSoup(resp.text, 'html.parser')
            texto = sopa.get_text(" ")

            # 1. Buscar correos en texto visible
            patron_correo = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
            for c in re.findall(patron_correo, texto):
                if not c.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.js', '.css')):
                    correos.add(c.lower())

            # 2. Buscar enlaces mailto: y tel:
            for a in sopa.find_all('a', href=True):
                href = a['href']
                if 'mailto:' in href:
                    c = href.replace('mailto:', '').split('?')[0].strip()
                    if '@' in c:
                        correos.add(c.lower())
                elif 'tel:' in href and telefono == "No disponible públicamente":
                    tel_limpio = href.replace('tel:', '').strip()
                    if len(re.sub(r'\D', '', tel_limpio)) >= 7:
                        telefono = tel_limpio

            # 3. Si no hubo enlace tel:, buscar patrón telefónico estándar en el texto
            if telefono == "No disponible públicamente":
                match_tel = re.search(r'(\+?\d{1,3}[\s.-]?)?\(?\d{2,3}\)?[\s.-]?\d{3,4}[\s.-]?\d{4}', texto)
                if match_tel:
                    telefono = match_tel.group(0).strip()

    except Exception:
        pass

    return telefono, list(correos)[:3]

@app.route('/api/buscar', methods=['GET'])
def buscar_empresas():
    estado = request.args.get('estado', '')
    pais = request.args.get('pais', '')
    region = request.args.get('region', 'US_CA')

    if not estado:
        return jsonify({"error": "Falta el parámetro de ubicación"}), 400

    if region == "US_CA":
        query = f'manufacturing importer exporter company "{estado}" {pais} contact email'
    else:
        query = f'empresa manufacturera importadora exportadora "{estado}" {pais} contacto correo'

    empresas_reales = []
    urls_vistas = set()

    try:
        # Búsqueda gratuita en la web sin API Key
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=15))

        for res in resultados:
            url = res.get('href', '')
            titulo = res.get('title', '').split('|')[0].split('-')[0].strip()

            # Filtrar directorios y quedarnos solo con sitios web propios de empresas
            if not url or any(dom in url.lower() for dom in DOMINIOS_EXCLUIDOS):
                continue

            dominio_base = url.split('/')[2] if len(url.split('/')) > 2 else url
            if dominio_base in urls_vistas:
                continue
            urls_vistas.add(dominio_base)

            telefono, correos = extraer_datos_de_web(url)
            if not correos:
                correos = [f"Sitio web ({dominio_base})"]

            giro = "Manufactura / Comercio Exterior" if region == "MX_CENTRO" else "Manufacturing / International Trade"
            actividad = "Imp / Exp" if region == "US_CA" else "Fabricante / Imp"

            empresas_reales.append({
                "nombre": titulo[:60],
                "giro": giro,
                "telefono": telefono,
                "correos": correos,
                "actividad": actividad
            })

            # Limitar a 7 empresas por consulta para respetar el tiempo límite gratuito de Vercel (10s)
            if len(empresas_reales) >= 7:
                break

    except Exception as e:
        return jsonify({"error": f"Error en búsqueda abierta: {str(e)}"}), 500

    return jsonify(empresas_reales)