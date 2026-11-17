import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Vercel inyectará automáticamente la clave que configures en su panel
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

def extraer_correos_de_web(url):
    if not url:
        return []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    correos_encontrados = set()
    try:
        respuesta = requests.get(url, headers=headers, timeout=5)
        if respuesta.status_code == 200:
            sopa = BeautifulSoup(respuesta.text, 'html.parser')
            patron = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
            for c in re.findall(patron, sopa.get_text()):
                if not c.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
                    correos_encontrados.add(c.lower())
            for enlace in sopa.find_all('a', href=True):
                if 'mailto:' in enlace['href']:
                    correo = enlace['href'].replace('mailto:', '').split('?')[0].strip()
                    if '@' in correo:
                        correos_encontrados.add(correo.lower())
    except Exception:
        pass
    return list(correos_encontrados)[:3]

@app.route('/api/buscar', methods=['GET'])
def buscar_empresas():
    if not GOOGLE_API_KEY:
        return jsonify({"error": "Falta configurar GOOGLE_API_KEY en Vercel"}), 500

    estado = request.args.get('estado', '')
    pais = request.args.get('pais', '')
    region = request.args.get('region', 'US_CA')
    
    if not estado:
        return jsonify({"error": "Falta el parámetro de ubicación"}), 400

    if region == "US_CA":
        query = f"manufacturing importers exporters wholesale companies in {estado} {pais}"
    else:
        query = f"empresas manufactureras importadoras exportadoras comercializadoras en {estado} {pais}"

    url_search = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    res_search = requests.get(url_search, params={"query": query, "key": GOOGLE_API_KEY}).json()
    lugares = res_search.get("results", [])
    
    empresas_reales = []

    # En la versión gratuita de Vercel las funciones tienen un límite de 10 segundos.
    # Procesamos las 8 mejores coincidencias para garantizar que nunca marque tiempo agotado (Timeout).
    for lugar in lugares[:8]:
        place_id = lugar.get("place_id")
        url_details = "https://maps.googleapis.com/maps/api/place/details/json"
        params_details = {
            "place_id": place_id,
            "fields": "name,formatted_phone_number,international_phone_number,website",
            "key": GOOGLE_API_KEY
        }
        detalle = requests.get(url_details, params=params_details).json().get("result", {})
        
        nombre = detalle.get("name", lugar.get("name"))
        telefono = detalle.get("international_phone_number") or detalle.get("formatted_phone_number") or "No disponible públicamente"
        sitio_web = detalle.get("website", "")
        
        correos = extraer_correos_de_web(sitio_web)
        if not correos:
            correos = [f"Formulario web ({sitio_web})" if sitio_web else "No disponible públicamente"]

        giro = "Manufactura / Comercialización" if region == "MX_CENTRO" else "Manufacturing / Wholesale"
        actividad = "Imp / Exp" if region == "US_CA" else "Fabricante / Imp"

        empresas_reales.append({
            "nombre": nombre,
            "giro": giro,
            "telefono": telefono,
            "correos": correos,
            "actividad": actividad
        })

    return jsonify(empresas_reales)