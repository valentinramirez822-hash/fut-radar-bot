import cloudscraper
from bs4 import BeautifulSoup
import requests
import re
import time
import os

# --- 1. TUS DATOS DE TELEGRAM ---
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8908344399:AAGeC35sIxMJZ3pFhyr3seUfp24KftyJcLU")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1656016116")
IMPUESTO_EA = 0.05

# --- 2. CONFIGURACIÓN DE MEDIAS + NOMBRES REFERENCIA ---
CONFIG_MEDIAS = {
    84: {"venta_esperada": 2400, "ganancia_minima": 450, "ejemplos": "Exequiel Palacios, Maddison, Bennacer"},
    85: {"venta_esperada": 6200, "ganancia_minima": 900, "ejemplos": "Diogo Jota, Stones, Milinkovic-Savic"},
    86: {"venta_esperada": 10800, "ganancia_minima": 1400, "ejemplos": "Alexis Mac Allister, Grimaldo, Tah"},
    87: {"venta_esperada": 15500, "ganancia_minima": 2000, "ejemplos": "Dibu Martínez, Lautaro Martínez, Bruno Fernandes"},
    88: {"venta_esperada": 22500, "ganancia_minima": 2800, "ejemplos": "Bernardo Silva, Irene Paredes, Oblak"}
}

# --- 3. RADAR ESPECIAL: "THE GALLERY" (CARTAS PLATA & CUELLOS DE BOTELLA) ---
# Las cartas Plata de ligas principales suelen tener picos de 1.500 a 4.500 monedas
# cuando la gente completa clubes en The Gallery, pero a la madrugada o en apertura
# de sobres de plata caen por puja a 350 - 700 monedas.
RADAR_GALLERY_PLATAS = [
    {
        "nicho": "Platas Premier League / LaLiga (Clubes sin Oro en ese puesto)",
        "nombres_clave": "Laterales (LB/RB) y Centrales (CB) Plata Raros de clubes mitad de tabla",
        "compra_puja_max": 650,
        "compra_snipe_max": 800,
        "venta_gallery": 1800
    },
    {
        "nicho": "Platas Liga Profesional Argentina / Libertadores (Links & Gallery)",
        "nombres_clave": "Arqueros (GK) y Extremos (LM/RM/LW/RW) Plata Raros",
        "compra_puja_max": 450,
        "compra_snipe_max": 600,
        "venta_gallery": 1300
    },
    {
        "nicho": "Platas Serie A / Bundesliga / Ligue 1 (Clubes recién ascendidos)",
        "nombres_clave": "Jugadores de clubes con 80% plantilla de Plata (cuello de botella)",
        "compra_puja_max": 500,
        "compra_snipe_max": 700,
        "venta_gallery": 1600
    }
]

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    datos = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    respuesta = requests.post(url, data=datos)
    if respuesta.status_code == 200:
        print("✅ ¡Reporte con Radar The Gallery enviado a tu Telegram!")
    else:
        print("❌ Error de Telegram:", respuesta.text)

def convertir_precio(texto):
    if not texto:
        return 0
    t = str(texto).upper().replace(",", "").replace(" ", "").strip()
    match = re.search(r'(\d+\.?\d*)([KM]?)', t)
    if not match:
        return 0
    valor = float(match.group(1))
    mult = match.group(2)
    if mult == "K":
        return int(valor * 1000)
    elif mult == "M":
        return int(valor * 1000000)
    return int(valor)

def crear_navegador():
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'darwin', 'mobile': False}
    )
    return scraper

def extraer_jugadores_futgg_futbin(scraper, url, min_p, max_p):
    """Extrae nombres y precios reales de las tablas web"""
    encontrados = []
    try:
        resp = scraper.get(url, timeout=10)
        if resp.status_code == 200:
            sopa = BeautifulSoup(resp.text, "html.parser")
            for a in sopa.select("a.player_name_players_table, a[href*='/players/']"):
                nombre = a.get_text(strip=True)
                if not nombre or len(nombre) < 3 or nombre.isdigit():
                    continue
                fila = a.find_parent("tr") or a.find_parent("div")
                if fila:
                    texto_fila = " ".join(fila.stripped_strings)
                    precios = re.findall(r'\b\d+(?:\.\d+)?K\b|\b\d{1,3}(?:,\d{3})+\b|\b[3-9]\d{2,3}\b', texto_fila.upper())
                    for p in precios:
                        val = convertir_precio(p)
                        if min_p <= val <= max_p:
                            if not any(n == nombre for n, _ in encontrados):
                                encontrados.append((nombre, val))
                            break
                if len(encontrados) >= 4:
                    break
    except Exception:
        pass
    return encontrados

def escanear_platas_gallery(scraper):
    """Busca cartas Plata (65-74) que hoy están cotizando alto por The Gallery"""
    print("🥈 Escaneando mercado de Platas para The Gallery...")
    url_platas = "https://www.futbin.com/players?page=1&version=silver_all&ps_price=1200-8000&sort=ps_price&order=asc"
    return extraer_jugadores_futgg_futbin(scraper, url_platas, 1100, 9000)

def ejecutar_radar():
    scraper = crear_navegador()
    platas_vivas = escanear_platas_gallery(scraper)

    mensaje = "⚡ <b>RADAR FUT: THE GALLERY + MEDIAS (375K)</b> ⚡\n\n"

    # --- SECCIÓN 1: THE GALLERY (CARTAS PLATA) ---
    mensaje += "🥈 <b>ESPECIAL 'THE GALLERY' (Caza de Platas):</b>\n"
    mensaje += "<i>La gente paga fortunas en Compra Ya por platas para completar álbumes, pero nadie las puja.</i>\n\n"

    if platas_vivas:
        nombres_platas_str = ", ".join([f"<b>{n}</b> ({p:,})" for n, p in platas_vivas[:4]])
        mensaje += f"🔥 <b>Platas caras detectadas hoy en web:</b>\n{nombres_platas_str}\n👉 <i>Buscalas en puja abierta a menos de la mitad de ese valor.</i>\n\n"

    for item in RADAR_GALLERY_PLATAS:
        neto = int(item["venta_gallery"] * (1 - IMPUESTO_EA))
        ganancia_neta = neto - item["compra_puja_max"]
        mensaje += (
            f"🎯 <b>{item['nicho']}</b>\n"
            f"   👤 Qué buscar: <i>{item['nombres_clave']}</i>\n"
            f"   🔨 Pujar masivo hasta: <b>{item['compra_puja_max']}</b> | Snipe: <b>{item['compra_snipe_max']}</b>\n"
            f"   📈 Vender (Compra Ya): <b>{item['venta_gallery']:,}</b> (Limpio: <b>+{ganancia_neta:,}</b> c/u)\n\n"
        )

    # --- SECCIÓN 2: MEDIAS CON NOMBRES ---
    mensaje += "📊 <b>RADAR DE MEDIAS (Con Nombres Objetivo):</b>\n"
    for media, reglas in CONFIG_MEDIAS.items():
        venta = reglas["venta_esperada"]
        ganancia_min = reglas["ganancia_minima"]
        techo = int(venta * (1 - IMPUESTO_EA)) - ganancia_min
        
        url_m = f"https://www.futbin.com/players?page=1&version=gold_nr&player_rating={media}-{media}&sort=ps_price&order=asc"
        vivos = extraer_jugadores_futgg_futbin(scraper, url_m, 650, 90000)

        if vivos:
            top_nombre, top_precio = vivos[0]
            otros = ", ".join([n for n, _ in vivos[1:3]])
            if top_precio <= techo:
                mensaje += (
                    f"🟢 <b>¡COMPRAR MEDIA {media}!</b> -> <b>{top_nombre}</b> está a <b>{top_precio:,}</b> "
                    f"(Techo: {techo:,} | Otros: {otros})\n"
                )
            else:
                mensaje += (
                    f"🛡️ <b>Media {media} (No comprar caro hoy)</b>: <b>{top_nombre}</b> está en {top_precio:,}. "
                    f"Esperar a que baje de <b>{techo:,}</b> <i>(Mirar también: {otros})</i>\n"
                )
        else:
            mensaje += (
                f"🛡️ <b>Media {media}</b>: Gatillo de compra &lt; <b>{techo:,}</b> monedas "
                f"(Vender en {venta:,})\n   👟 <i>Cartas filtro: {reglas['ejemplos']}</i>\n"
            )
        time.sleep(0.3)

    enviar_telegram(mensaje)

if __name__ == "__main__":
    ejecutar_radar()
