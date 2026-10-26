import cloudscraper
from bs4 import BeautifulSoup
import requests
import re
import time
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# --- 1. TUS DATOS DE TELEGRAM ---
TOKEN = "8908344399:AAGeC35sIxMJZ3pFhyr3seUfp24KftyJcLU"
CHAT_ID = "1656016116"

IMPUESTO_EA = 0.05
ARCHIVO_AGENDA = "mi_agenda_fut.json"
PRESUPUESTO_INICIAL = 375000

# --- 2. REGLAS DE MERCADO ---
CONFIG_MEDIAS = {
    84: {"techo_compra": 1700, "venta_sbc": 2400, "target_fallback": "Exe Palacios / Maddison / Bennacer"},
    85: {"techo_compra": 4800, "venta_sbc": 6200, "target_fallback": "Stones / Diogo Jota / Vicario"},
    86: {"techo_compra": 8700, "venta_sbc": 10800, "target_fallback": "Mac Allister / Grimaldo / Tah"},
    87: {"techo_compra": 12600, "venta_sbc": 15500, "target_fallback": "Dibu Martínez / Lautaro / Odegaard"},
    88: {"techo_compra": 18500, "venta_sbc": 22500, "target_fallback": "Bernardo Silva / Oblak / Paredes"}
}

# --- 3. MOTOR DE AGENDA Y CONTABILIDAD ---
def cargar_agenda():
    if os.path.exists(ARCHIVO_AGENDA):
        try:
            with open(ARCHIVO_AGENDA, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return reiniciar_agenda()

def reiniciar_agenda():
    datos_base = {
        "monedas_liquidas": PRESUPUESTO_INICIAL,
        "ganancia_total_historica": 0,
        "operaciones_cerradas": 0,
        "proximo_id": 1,
        "inventario": [],
        "historial": []
    }
    guardar_agenda(datos_base)
    return datos_base

def guardar_agenda(datos):
    with open(ARCHIVO_AGENDA, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    datos = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    requests.post(url, data=datos)

# --- 4. FUNCIONES CONTABLES ---
def registrar_compra(cantidad, precio_unit, nombre_carta):
    ag = cargar_agenda()
    costo_total = cantidad * precio_unit
    id_op = ag["proximo_id"]
    
    break_even = int((precio_unit / (1 - IMPUESTO_EA)) + 49) // 50 * 50
    venta_sugerida = int((precio_unit * 1.18) + 49) // 50 * 50
    ganancia_est = int(venta_sugerida * (1 - IMPUESTO_EA) * cantidad) - costo_total

    tz_arg = timezone(timedelta(hours=-3))
    fecha_str = datetime.now(tz_arg).strftime("%d/%m %H:%M")

    nuevo_lote = {
        "id": id_op,
        "nombre": nombre_carta,
        "cantidad": cantidad,
        "precio_compra": precio_unit,
        "costo_total": costo_total,
        "fecha": fecha_str
    }

    ag["inventario"].append(nuevo_lote)
    ag["monedas_liquidas"] -= costo_total
    ag["proximo_id"] += 1
    guardar_agenda(ag)

    return (
        f"✅ <b>COMPRA REGISTRADA (Lote #{id_op})</b>\n\n"
        f"🃏 <b>Jugador:</b> {nombre_carta} (x{cantidad})\n"
        f"💸 <b>Compra unitaria:</b> {precio_unit:,} monedas\n"
        f"📦 <b>Inversión total lote:</b> {costo_total:,} monedas\n\n"
        f"⚠️ <b>No vender a menos de:</b> {break_even:,} (Empate post 5% EA)\n"
        f"🎯 <b>Venta sugerida (+15%):</b> {venta_sugerida:,} (Ganarías <b>+{ganancia_est:,}</b> limpias)\n\n"
        f"💰 <b>Monedas libres restantes:</b> {ag['monedas_liquidas']:,}\n"
        f"👉 <i>Cuando las vendas, mandá:</i> <code>/vendi {id_op} PRECIO</code>"
    )

def registrar_venta(id_lote, precio_venta_unit):
    ag = cargar_agenda()
    lote = next((item for item in ag["inventario"] if item["id"] == id_lote), None)
    
    if not lote:
        return f"❌ No encontré ningún lote activo con el ID <b>#{id_lote}</b>. Mandá <code>/agenda</code> para ver tus lotes."

    cantidad = lote["cantidad"]
    costo_total = lote["costo_total"]
    bruto_venta = cantidad * precio_venta_unit
    impuesto_total = int(bruto_venta * IMPUESTO_EA)
    neto_recibido = bruto_venta - impuesto_total
    ganancia_limpia = neto_recibido - costo_total
    roi = (ganancia_limpia / costo_total) * 100 if costo_total > 0 else 0

    ag["inventario"].remove(lote)
    ag["monedas_liquidas"] += neto_recibido
    ag["ganancia_total_historica"] += ganancia_limpia
    ag["operaciones_cerradas"] += 1

    ag["historial"].append({
        "nombre": lote["nombre"],
        "cantidad": cantidad,
        "compra": lote["precio_compra"],
        "venta": precio_venta_unit,
        "ganancia": ganancia_limpia
    })
    guardar_agenda(ag)

    icono = "🤑" if ganancia_limpia > 0 else "📉"
    signo = "+" if ganancia_limpia > 0 else ""

    return (
        f"{icono} <b>¡VENTA CERRADA! (Lote #{id_lote} - {lote['nombre']})</b>\n\n"
        f"• Compraste a: {lote['precio_compra']:,} c/u (Total: {costo_total:,})\n"
        f"• Vendiste a: {precio_venta_unit:,} c/u (Bruto: {bruto_venta:,})\n"
        f"• Impuesto EA (5%): -{impuesto_total:,} monedas\n"
        f"• <b>GANANCIA LIMPIA: {signo}{ganancia_limpia:,} monedas ({roi:.1f}%)</b>\n\n"
        f"🏦 <b>Monedas líquidas ahora:</b> <b>{ag['monedas_liquidas']:,}</b>\n"
        f"📈 <b>Ganancia histórica acumulada:</b> <b>+{ag['ganancia_total_historica']:,}</b>"
    )

def ver_resumen_agenda():
    ag = cargar_agenda()
    invertido = sum(item["costo_total"] for item in ag["inventario"])
    patrimonio_total = ag["monedas_liquidas"] + invertido

    txt = (
        f"📒 <b>MI AGENDA DE TRADEO FUT</b>\n\n"
        f"💎 <b>Patrimonio Total: {patrimonio_total:,} monedas</b>\n"
        f"• 💵 Monedas libres: <b>{ag['monedas_liquidas']:,}</b>\n"
        f"• 📦 Invertido en cartas: <b>{invertido:,}</b>\n"
        f"• 📈 Ganancia limpia acumulada: <b>+{ag['ganancia_total_historica']:,}</b> ({ag['operaciones_cerradas']} ventas)\n\n"
    )

    if ag["inventario"]:
        txt += "🛒 <b>LOTES ABIERTOS (Esperando venta):</b>\n"
        for item in ag["inventario"]:
            be = int((item["precio_compra"] / 0.95) + 49) // 50 * 50
            txt += (
                f"• <b>ID #{item['id']}</b> | <b>{item['nombre']}</b> (x{item['cantidad']})\n"
                f"  Compra: {item['precio_compra']:,} c/u | Empate: {be:,}\n"
                f"  <i>Cerrar con:</i> <code>/vendi {item['id']} PRECIO</code>\n\n"
            )
    else:
        txt += "<i>Sin lotes pendientes. Anotá compras con:</i>\n<code>/compre 10 1700 Exe Palacios</code>\n\n"

    if ag["historial"]:
        txt += "🏆 <b>ÚLTIMOS TRADEOS CERRADOS:</b>\n"
        for h in reversed(ag["historial"][-3:]):
            s = "+" if h["ganancia"] >= 0 else ""
            txt += f"• {h['nombre']} (x{h['cantidad']}): {h['compra']:,} ➡️ {h['venta']:,} (<b>{s}{h['ganancia']:,}</b>)\n"

    return txt

# --- 5. DETECTOR DE BOOM DE EVOLUCIONES (11:00 HS ARG) ---
def convertir_precio(texto):
    if not texto:
        return 0
    t = str(texto).upper().replace(",", "").replace(" ", "").strip()
    m = re.search(r'(\d+\.?\d*)([KM]?)', t)
    if not m:
        return 0
    val = float(m.group(1))
    mult = m.group(2)
    if mult == "K":
        return int(val * 1000)
    elif mult == "M":
        return int(valor * 1000000)
    return int(val)

def extraer_cartas_precisas(scraper, url, min_p, max_p, limite=5):
    cartas = []
    try:
        resp = scraper.get(url, timeout=10)
        if resp.status_code == 200:
            sopa = BeautifulSoup(resp.text, "html.parser")
            filas = sopa.select("tr.player_tr_1, tr.player_tr_2, tbody tr, div.player-item")
            for fila in filas:
                enlace = fila.select_one("a.player_name_players_table, a[href*='/players/']")
                if not enlace:
                    continue
                nombre = enlace.get_text(strip=True)
                if not nombre or len(nombre) < 3 or nombre.isdigit():
                    continue
                texto_fila = " ".join(fila.stripped_strings)
                # Detectar si tiene porcentaje de subida (+15%, +40%, etc.)
                subida_match = re.search(r'(\+\d+(?:\.\d+)?%)', texto_fila)
                subida_txt = subida_match.group(1) if subida_match else ""

                precios = re.findall(r'\b\d+(?:\.\d+)?K\b|\b\d{1,3}(?:,\d{3})+\b|\b[4-9]\d{2}\b', texto_fila.upper())
                precio_val = 0
                for p in precios:
                    v = convertir_precio(p)
                    if min_p <= v <= max_p:
                        precio_val = v
                        break
                if precio_val > 0 and not any(c["nombre"] == nombre for c in cartas):
                    cartas.append({"nombre": nombre, "precio": precio_val, "subida": subida_txt})
                if len(cartas) >= limite:
                    break
    except Exception:
        pass
    return cartas

def detectar_boom_evos():
    """Escanea las cartas baratas (<25k) que están en Top Trending o disparándose a la mañana por filtraciones de Evos"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'darwin', 'mobile': False})
    tz_arg = timezone(timedelta(hours=-3))
    hora_arg = datetime.now(tz_arg).strftime("%H:%M")

    # 1. Buscar jugadores de bajo costo (700 a 22.000 monedas) ordenados por popularidad/vistas del día
    urls_hype = [
        "https://www.futbin.com/popular",
        "https://www.futbin.com/players?page=1&ps_price=700-22000&sort=likes&order=desc",
        "https://www.fut.gg/players/?price__gte=700&price__lte=22000&sorts=-trending"
    ]

    detectadas = []
    for url in urls_hype:
        encontradas = extraer_cartas_precisas(scraper, url, 650, 25000, limite=6)
        for c in encontradas:
            if not any(d["nombre"] == c["nombre"] for d in detectadas):
                detectadas.append(c)
        if len(detectadas) >= 6:
            break

    msg = f"🧬 <b>ALERTA DE HYPE / POSIBLE EVO ({hora_arg} hs ARG)</b> 🧬\n"
    msg += "<i>Escaneo pre-contenido (15:00 hs) de cartas baratas con pico anormal de búsquedas por filtraciones:</i>\n\n"

    if detectadas:
        msg += "🔥 <b>CARTAS BARATAS EN TENDENCIA AHORA MISMO:</b>\n"
        for c in detectadas[:5]:
            p_actual = c["precio"]
            # En hype de Evo buscamos entrar rápido y vender +25% a +40% antes de las 15:00 hs
            target_hype = int((p_actual * 1.30) / 100) * 100
            ganancia_hype = int(target_hype * 0.95) - p_actual
            sub_str = f" 📈 <b>{c['subida']}</b>" if c["subida"] else ""
            msg += (
                f"• <b>{c['nombre']}</b>{sub_str} 👉 Actual: <b>{p_actual:,}</b> monedas\n"
                f"  ⚡ Si recién arranca el leak, comprar ya y listar en <b>{target_hype:,}</b> (+{ganancia_hype:,} c/u)\n"
            )
        msg += "\n"
    else:
        msg += (
            "📡 <b>Radar de Perfiles de Evo más filtrados hoy:</b>\n"
            "• <b>Oros / Platas Meta (74 a 82 de media)</b> de Premier, LaLiga, Serie A y LPF con +82 de Ritmo.\n"
            "• <b>IFs descartables (10.5k - 12k)</b> de laterales o extremos.\n\n"
        )

    msg += (
        "⚠️ <b>REGLA DE ORO DE LAS EVOS (LEER SIEMPRE):</b>\n"
        "1️⃣ <b>Chequeá el gráfico de hoy:</b> Si la carta valía 1.000 hace 1 hora y va por 1.800, todavía tiene recorrido hasta 3.500+. Si ya subió de 1.000 a 4.800, ¡NO ENTRES! Ya estás comprando en la cima.\n"
        "2️⃣ <b>VENDÉ ANTES DE LAS 14:50 HS (ARG):</b> Siempre se vende con el rumor. A las 15:00 hs cuando sale la Evo en el juego, todos los traders tiran sus cartas al mercado al mismo tiempo y el precio se destruye."
    )
    return msg

def generar_reporte_mercado():
    ag = cargar_agenda()
    disponible = ag["monedas_liquidas"]
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'darwin', 'mobile': False})

    tz_arg = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_arg)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    
    mensaje = f"⚡ <b>REPORTE EN VIVO ({dias[ahora.weekday()]} {ahora.strftime('%H:%M')} hs)</b>\n"
    mensaje += f"💰 <i>Capital libre para invertir hoy: <b>{disponible:,} monedas</b></i>\n\n"

    # 1. The Gallery Platas
    url_platas = "https://www.futbin.com/players?page=1&version=silver_all&ps_price=1500-9000&sort=ps_price&order=asc"
    platas = extraer_cartas_precisas(scraper, url_platas, 1400, 9500, limite=4)
    mensaje += "🥈 <b>THE GALLERY (Platas para Pujar / Snipear):</b>\n"
    if platas:
        for p in platas:
            c_ya = p["precio"]
            puja = int((c_ya * 0.45) / 50) * 50
            limpio = int(c_ya * 0.95) - puja
            mensaje += f"• <b>{p['nombre']}</b>: Compra Ya {c_ya:,} 👉 Pujar a <b>{puja:,}</b> (+{limpio:,})\n"
    else:
        mensaje += "• <b>Filtro rápido:</b> Plata Raro (Premier / LaLiga / LPF) 👉 Pujar a <b>450 - 600</b>, vender a <b>1.500+</b>.\n"
    mensaje += "\n"

    # 2. Medias y Lotes según tu saldo disponible real
    mensaje += "📦 <b>SEMÁFORO DE MEDIAS (Fodder SBC):</b>\n"
    presupuesto_lote = max(20000, int(disponible * 0.45))

    for media, cfg in CONFIG_MEDIAS.items():
        techo = cfg["techo_compra"]
        venta = cfg["venta_sbc"]
        url_m = f"https://www.futbin.com/players?page=1&version=gold_nr&player_rating={media}-{media}&sort=ps_price&order=asc"
        encontrados = extraer_cartas_precisas(scraper, url_m, 650, 90000, limite=2)
        
        if encontrados:
            top = encontrados[0]
            if top["precio"] <= techo:
                cant = presupuesto_lote // top["precio"]
                gan = int(venta * 0.95) - top["precio"]
                mensaje += f"🟢 <b>MEDIA {media} [COMPRAR]: {top['nombre']}</b> a <b>{top['precio']:,}</b> (Comprá {cant} -&gt; +{cant*gan:,})\n"
            else:
                mensaje += f"🔴 <b>Media {media}:</b> {top['nombre']} hoy a {top['precio']:,} (Esperar a &lt; <b>{techo:,}</b>)\n"
        else:
            mensaje += f"⏳ <b>Media {media}:</b> Comprar a &lt; <b>{techo:,}</b> | Vender en {venta:,} (<i>{cfg['target_fallback']}</i>)\n"
        time.sleep(0.2)

    if ag["inventario"]:
        mensaje += f"\n🔔 <i>Tenés <b>{len(ag['inventario'])} lote(s)</b> abiertos. Mandá <code>/agenda</code> para verlos.</i>"

    return mensaje

# --- 6. COMANDOS INTERACTIVOS DE TELEGRAM ---
def procesar_comando(texto):
    partes = texto.strip().split()
    if not partes:
        return None
    cmd = partes[0].lower()

    if cmd in ["/start", "/ayuda", "/menu", "hola"]:
        return (
            "🤖 <b>COMANDOS DE TU ASISTENTE FUT:</b>\n\n"
            "🧬 <code>/evo</code>\n"
            "Detecta cartas baratas en tendencia ahora mismo por posibles filtraciones de Evoluciones.\n\n"
            "📡 <code>/radar</code>\n"
            "Escanea el mercado en vivo (The Gallery + Medias + Lotes).\n\n"
            "🛒 <code>/compre [cant] [precio] [jugador]</code>\n"
            "Ej: <code>/compre 10 1700 Exe Palacios</code>\n\n"
            "🤑 <code>/vendi [ID] [precio_venta]</code>\n"
            "Ej: <code>/vendi 1 2400</code>\n\n"
            "📒 <code>/agenda</code>\n"
            "Muestra tus monedas libres, tus cartas compradas y tu ganancia total.\n\n"
            "🧮 <code>/calc [compra] [venta]</code>\n"
            "Calculadora rápida del 5% de EA.\n\n"
            "🔄 <code>/reset</code>\n"
            "Borra las pruebas y reinicia la agenda a 375.000 monedas limpias."
        )

    elif cmd in ["/evo", "/evos", "/hype", "evo"]:
        enviar_telegram("🧬 <i>Buscando picos de Hype y posibles filtraciones de Evos en vivo...</i>")
        return detectar_boom_evos()

    elif cmd in ["/radar", "/reporte", "radar"]:
        enviar_telegram("🔍 <i>Escaneando FUTBIN / FUT.GG en vivo, dame 5 segundos...</i>")
        return generar_reporte_mercado()

    elif cmd in ["/agenda", "/cartera", "agenda"]:
        return ver_resumen_agenda()

    elif cmd in ["/compre", "/compra"]:
        if len(partes) < 4:
            return "⚠️ <b>Formato:</b> <code>/compre [cantidad] [precio_unitario] [nombre]</code>\nEjemplo: <code>/compre 10 1700 Exe Palacios</code>"
        try:
            cant = int(partes[1])
            precio = int(partes[2].replace(".", "").replace(",", ""))
            nombre = " ".join(partes[3:])
            return registrar_compra(cant, precio, nombre)
        except ValueError:
            return "❌ La cantidad y el precio tienen que ser números."

    elif cmd in ["/vendi", "/venta"]:
        if len(partes) < 3:
            return "⚠️ <b>Formato:</b> <code>/vendi [ID_del_lote] [precio_unitario_venta]</code>\nEjemplo: <code>/vendi 1 2400</code>"
        try:
            id_lote = int(partes[1].replace("#", ""))
            precio_v = int(partes[2].replace(".", "").replace(",", ""))
            return registrar_venta(id_lote, precio_v)
        except ValueError:
            return "❌ El ID del lote y el precio tienen que ser números."

    elif cmd == "/reset":
        reiniciar_agenda()
        return "🔄 <b>¡Agenda reiniciada a cero!</b>\nTus monedas líquidas volvieron a <b>375.000</b> y se limpiaron los lotes de prueba."

    elif cmd == "/calc":
        if len(partes) < 3:
            return "⚠️ <b>Formato:</b> <code>/calc [precio_compra] [precio_venta]</code>"
        try:
            c = int(partes[1].replace(".", "").replace(",", ""))
            v = int(partes[2].replace(".", "").replace(",", ""))
            tax = int(v * IMPUESTO_EA)
            limpio = (v - tax) - c
            be = int((c / 0.95) + 49) // 50 * 50
            icono = "🟢 GANÁS" if limpio > 0 else "🔴 PERDÉS"
            return (
                f"🧮 <b>CALCULADORA 5% EA:</b>\n"
                f"• Compra: {c:,} | Venta: {v:,}\n"
                f"• Impuesto EA (5%): -{tax:,}\n"
                f"• Resultado: <b>{icono} {limpio:,} monedas por carta</b>\n"
                f"• <i>Empate en: {be:,}</i>"
            )
        except ValueError:
            return "❌ Ingresá solo números."

    elif cmd == "/saldo":
        if len(partes) < 2:
            return "⚠️ <b>Formato:</b> <code>/saldo [monedas_actuales]</code>"
        try:
            nuevo = int(partes[1].replace(".", "").replace(",", ""))
            ag = cargar_agenda()
            ag["monedas_liquidas"] = nuevo
            guardar_agenda(ag)
            return f"🏦 Saldo líquido actualizado a <b>{nuevo:,} monedas</b>."
        except ValueError:
            return "❌ Ingresá un número válido."

    return "🤖 Comando no reconocido. Mandá <code>/menu</code> para ver las opciones."

def procesar_mensajes_pendientes_una_vez():
    """Para cuando corre en la nube (GitHub): lee si le mandaste algún comando por Telegram, te responde y guarda la agenda"""
    url_updates = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    ag = cargar_agenda()
    ultimo_id = ag.get("ultimo_update_id", 0)

    try:
        params = {"offset": ultimo_id + 1} if ultimo_id else {}
        resp = requests.get(url_updates, params=params, timeout=10).json()
        hubo_cambios = False
        for item in resp.get("result", []):
            ultimo_id = item["update_id"]
            hubo_cambios = True
            msg = item.get("message", {})
            if str(msg.get("chat", {}).get("id", "")) == CHAT_ID and msg.get("text"):
                respuesta = procesar_comando(msg.get("text"))
                if respuesta:
                    enviar_telegram(respuesta)
        if hubo_cambios:
            ag = cargar_agenda()
            ag["ultimo_update_id"] = ultimo_id
            guardar_agenda(ag)
    except Exception:
        pass

def modo_interactivo():
    print("🎧 Bot con Radar de EVOS activo. Probá mandar /evo o /reset desde tu celular...")
    enviar_telegram(
        "🧬 <b>¡ACTUALIZACIÓN LISTA: DETECTOR DE EVOS (11:00 HS ARG)!</b>\n\n"
        "Probá mandarme ahora mismo:\n"
        "👉 <code>/evo</code> (Para ver las cartas baratas en tendencia hoy por posibles Evos)\n"
        "👉 <code>/reset</code> (Para dejar tu agenda limpia en 375.000 monedas reales)"
    )

    ultimo_update_id = None
    url_updates = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

    try:
        r_init = requests.get(url_updates, timeout=5).json()
        if r_init.get("result"):
            ultimo_update_id = r_init["result"][-1]["update_id"] + 1
    except Exception:
        pass

    while True:
        try:
            params = {"timeout": 20}
            if ultimo_update_id:
                params["offset"] = ultimo_update_id
            resp = requests.get(url_updates, params=params, timeout=25).json()

            for item in resp.get("result", []):
                ultimo_update_id = item["update_id"] + 1
                msg = item.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) == CHAT_ID and msg.get("text"):
                    print(f"📩 Comando recibido: {msg.get('text')}")
                    respuesta = procesar_comando(msg.get("text"))
                    if respuesta:
                        enviar_telegram(respuesta)
        except KeyboardInterrupt:
            print("\n🛑 Bot detenido.")
            break
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        modo = sys.argv[1]
        if modo == "--evo":
            enviar_telegram(detectar_boom_evos())
        elif modo == "--auto":
            enviar_telegram(generar_reporte_mercado())
        elif modo == "--check":
            procesar_mensajes_pendientes_una_vez()
    else:
        modo_interactivo()
