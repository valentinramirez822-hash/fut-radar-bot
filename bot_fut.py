import requests
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
MEDIAS_OBJETIVO = [84, 85, 86, 87, 88, 89]

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# --- 2. AGENDA Y CONTABILIDAD ---
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
    for intento in range(3):
        try:
            r = requests.post(url, data=datos, timeout=20)
            if r.status_code == 200:
                return True
        except Exception as e:
            time.sleep(1)
    return False

# --- 3. CONEXIÓN DIRECTA A LA API OFICIAL DE EASYSBC (FC 27) ---
def obtener_fodder_real_por_media(media):
    """
    Consulta directo la API JSON de EasySBC usando ratingMin y ratingMax
    y ordena por el precio de mercado más bajo real.
    """
    jugadores_validos = []
    # Pedimos las primeras 2 páginas de esa media en rango de precio de fodder (650 a 45.000 monedas)
    for pagina in [1, 2]:
        url = (
            f"https://api-fc27.easysbc.io/players?v2&page={pagina}"
            f"&ratingMin={media}&ratingMax={media}&priceMin=650&priceMax=45000"
        )
        try:
            r = requests.get(url, headers=HEADERS_API, timeout=8)
            if r.status_code == 200:
                lista = r.json().get("players", [])
                for p in lista:
                    precio = p.get("price", 0)
                    # Filtramos solo cartas transferibles de mercado con precio real > 0
                    if (
                        precio and precio >= 650
                        and not p.get("isSbcPlayer", False)
                        and not p.get("isObjectivePlayer", False)
                        and not p.get("untradeable", False)
                    ):
                        nombre = p.get("cardName") or p.get("name", "Jugador")
                        pos = p.get("preferredPosition", "")
                        etiqueta = f"{nombre} ({pos})" if pos else nombre
                        if not any(j["nombre"] == etiqueta for j in jugadores_validos):
                            jugadores_validos.append({
                                "nombre": etiqueta,
                                "precio": int(precio)
                            })
        except Exception:
            continue

    # Ordenamos estrictamente de menor a mayor precio
    jugadores_validos.sort(key=lambda x: x["precio"])
    return jugadores_validos[:4]

def obtener_platas_gallery_reales():
    """Busca cartas Plata (rating 65 a 74) que hoy cotizan entre 1.300 y 8.000 monedas por The Gallery"""
    platas = []
    url = (
        "https://api-fc27.easysbc.io/players?v2&page=1&sort-trending"
        "&ratingMin=65&ratingMax=74&priceMin=1300&priceMax=8000"
    )
    try:
        r = requests.get(url, headers=HEADERS_API, timeout=8)
        if r.status_code == 200:
            for p in r.json().get("players", []):
                precio = p.get("price", 0)
                if precio >= 1300 and not p.get("isSbcPlayer") and not p.get("isObjectivePlayer"):
                    nombre = p.get("cardName") or p.get("name", "Plata")
                    pos = p.get("preferredPosition", "")
                    platas.append({
                        "nombre": f"{nombre} ({pos})",
                        "precio": int(precio)
                    })
                if len(platas) >= 5:
                    break
    except Exception:
        pass
    return platas

def detectar_boom_evos():
    """Usa el índice evoPopularity y sort-trending oficial de la API para detectar filtraciones de Evos"""
    tz_arg = timezone(timedelta(hours=-3))
    hora_arg = datetime.now(tz_arg).strftime("%H:%M")
    candidatos_evo = []

    urls = [
        "https://api-fc27.easysbc.io/players?v2&page=1&sort-trending&priceMin=700&priceMax=30000&ratingMax=86",
        "https://api-fc27.easysbc.io/players?v2&page=1&sort-meta-rating&priceMin=700&priceMax=25000&ratingMax=85"
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS_API, timeout=8)
            if r.status_code == 200:
                for p in r.json().get("players", []):
                    precio = p.get("price", 0)
                    if (
                        700 <= precio <= 30000
                        and p.get("canEvolve", False)
                        and not p.get("isSbcPlayer")
                        and not p.get("isObjectivePlayer")
                    ):
                        nombre = f"{p.get('cardName') or p.get('name')} ({p.get('rating')} {p.get('preferredPosition', '')})"
                        evo_pop = p.get("evoPopularity", 0)
                        if not any(c["nombre"] == nombre for c in candidatos_evo):
                            candidatos_evo.append({
                                "nombre": nombre,
                                "precio": int(precio),
                                "evo_pop": evo_pop
                            })
        except Exception:
            continue

    # Priorizamos los que tienen mayor popularidad de Evolución (evoPopularity)
    candidatos_evo.sort(key=lambda x: x["evo_pop"], reverse=True)

    msg = f"🧬 <b>RADAR DE EVOS & TENDENCIAS ({hora_arg} hs ARG)</b>\n"
    msg += "<i>Datos directos de la API de FC 27 (Cartas evolucionables en tendencia):</i>\n\n"

    if candidatos_evo:
        for c in candidatos_evo[:6]:
            p = c["precio"]
            venta_hype = int((p * 1.28) / 100) * 100
            ganancia = int(venta_hype * 0.95) - p
            fuego = f" 🔥(Hype Evo: {c['evo_pop']})" if c["evo_pop"] > 0 else ""
            msg += (
                f"• <b>{c['nombre']}</b>{fuego}\n"
                f"  💰 Precio actual: <b>{p:,}</b> 👉 Vender en hype pre-15hs: <b>{venta_hype:,}</b> (+{ganancia:,})\n"
            )
    else:
        msg += "<i>No hay picos anormales en este minuto.</i>\n"

    msg += "\n⚠️ <b>Regla de oro:</b> Vender siempre antes de las 14:50 hs ARG (antes de que salga el contenido oficial)."
    return msg

# --- 4. GENERADOR DE REPORTE DE MERCADO EN VIVO ---
def generar_reporte_mercado():
    ag = cargar_agenda()
    disponible = ag["monedas_liquidas"]
    tz_arg = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_arg)

    mensaje = f"⚡ <b>MERCADO EN VIVO FC 27 ({ahora.strftime('%H:%M')} hs ARG)</b>\n"
    mensaje += f"💰 <i>Capital libre hoy: <b>{disponible:,} monedas</b></i>\n\n"
    mensaje += "📦 <b>PISO REAL DE MEDIAS (Datos directos API):</b>\n\n"

    for media in MEDIAS_OBJETIVO:
        top_baratas = obtener_fodder_real_por_media(media)
        if top_baratas:
            mas_barata = top_baratas[0]
            precio_hoy = mas_barata["precio"]
            nombre_top = mas_barata["nombre"]
            otros = ", ".join([f"{x['nombre']} ({x['precio']:,})" for x in top_baratas[1:4]])

            # Cálculo sobre el precio real de hoy:
            # Pujar/Snipear un 8% abajo del precio actual de Compra Ya
            compra_objetivo = int((precio_hoy * 0.92) / 100) * 100
            if precio_hoy < 3500:
                compra_objetivo = int((precio_hoy * 0.90) / 50) * 50

            # Venta en rebote de SBC (+18% sobre el piso actual)
            venta_sbc = int((precio_hoy * 1.18) / 100) * 100
            ganancia_unit = int(venta_sbc * (1 - IMPUESTO_EA)) - compra_objetivo

            mensaje += (
                f"🔹 <b>MEDIA {media}</b> 👉 Hoy está a <b>{precio_hoy:,}</b> (<b>{nombre_top}</b>)\n"
                f"   🟢 Pujar/Snipear a: <b>&lt; {compra_objetivo:,}</b> | Venta SBC: <b>{venta_sbc:,}</b> (Limpio: <b>+{ganancia_unit:,}</b>)\n"
            )
            if otros:
                mensaje += f"   👟 <i>Otras baratas hoy: {otros}</i>\n"
            mensaje += "\n"
        else:
            mensaje += f"• <b>Media {media}:</b> Sin cartas en rango fodder.\n\n"

    # Platas de The Gallery
    platas = obtener_platas_gallery_reales()
    mensaje += "🥈 <b>THE GALLERY (Platas cotizando alto hoy):</b>\n"
    if platas:
        for pl in platas:
            c_ya = pl["precio"]
            puja_max = int((c_ya * 0.45) / 50) * 50
            limpio = int(c_ya * 0.95) - puja_max
            mensaje += f"• <b>{pl['nombre']}</b>: Compra Ya <b>{c_ya:,}</b> 👉 Pujar a <b>{puja_max:,}</b> (+{limpio:,})\n"
    else:
        mensaje += "• <b>Filtro rápido Web App:</b> Plata Raro (Premier/LaLiga/LPF) 👉 Pujar a <b>450 - 600</b>, vender a <b>1.400+</b>.\n"

    return mensaje

# --- 5. FUNCIONES CONTABLES ---
def registrar_compra(cantidad, precio_unit, nombre_carta):
    ag = cargar_agenda()
    costo_total = cantidad * precio_unit
    id_op = ag["proximo_id"]
    break_even = int((precio_unit / (1 - IMPUESTO_EA)) + 49) // 50 * 50
    venta_sugerida = int((precio_unit * 1.18) + 49) // 50 * 50
    ganancia_est = int(venta_sugerida * (1 - IMPUESTO_EA) * cantidad) - costo_total

    tz_arg = timezone(timedelta(hours=-3))
    ag["inventario"].append({
        "id": id_op, "nombre": nombre_carta, "cantidad": cantidad,
        "precio_compra": precio_unit, "costo_total": costo_total,
        "fecha": datetime.now(tz_arg).strftime("%d/%m %H:%M")
    })
    ag["monedas_liquidas"] -= costo_total
    ag["proximo_id"] += 1
    guardar_agenda(ag)

    return (
        f"✅ <b>COMPRA ANOTADA (Lote #{id_op})</b>\n"
        f"🃏 <b>{nombre_carta}</b> (x{cantidad}) a <b>{precio_unit:,}</b> c/u (Total: {costo_total:,})\n"
        f"⚠️ Empate post 5% EA: <b>{break_even:,}</b> | 🎯 Sugerida: <b>{venta_sugerida:,}</b> (+{ganancia_est:,})\n"
        f"💰 Monedas libres: <b>{ag['monedas_liquidas']:,}</b>"
    )

def registrar_venta(id_lote, precio_venta_unit):
    ag = cargar_agenda()
    lote = next((item for item in ag["inventario"] if item["id"] == id_lote), None)
    if not lote:
        return f"❌ No existe el lote #{id_lote}. Mandá <code>/agenda</code>."
    cantidad = lote["cantidad"]
    costo_total = lote["costo_total"]
    bruto = cantidad * precio_venta_unit
    neto = bruto - int(bruto * IMPUESTO_EA)
    ganancia = neto - costo_total

    ag["inventario"].remove(lote)
    ag["monedas_liquidas"] += neto
    ag["ganancia_total_historica"] += ganancia
    ag["operaciones_cerradas"] += 1
    ag["historial"].append({
        "nombre": lote["nombre"], "cantidad": cantidad,
        "compra": lote["precio_compra"], "venta": precio_venta_unit, "ganancia": ganancia
    })
    guardar_agenda(ag)
    signo = "+" if ganancia >= 0 else ""
    return (
        f"🤑 <b>VENTA CERRADA (Lote #{id_lote} - {lote['nombre']})</b>\n"
        f"• Compra: {lote['precio_compra']:,} ➡️ Venta: {precio_venta_unit:,} (x{cantidad})\n"
        f"• <b>GANANCIA LIMPIA: {signo}{ganancia:,} monedas</b>\n"
        f"🏦 Monedas libres: <b>{ag['monedas_liquidas']:,}</b> | 📈 Acumulada: <b>+{ag['ganancia_total_historica']:,}</b>"
    )

def ver_resumen_agenda():
    ag = cargar_agenda()
    inv = sum(i["costo_total"] for i in ag["inventario"])
    txt = (
        f"📒 <b>AGENDA FUT (Patrimonio: {ag['monedas_liquidas'] + inv:,})</b>\n"
        f"💵 Libres: <b>{ag['monedas_liquidas']:,}</b> | 📦 En cartas: <b>{inv:,}</b>\n"
        f"📈 Ganancia histórica: <b>+{ag['ganancia_total_historica']:,}</b>\n\n"
    )
    if ag["inventario"]:
        txt += "🛒 <b>LOTES ABIERTOS:</b>\n"
        for i in ag["inventario"]:
            be = int((i["precio_compra"] / 0.95) + 49) // 50 * 50
            txt += f"• <b>#{i['id']} {i['nombre']}</b> (x{i['cantidad']}) a {i['precio_compra']:,} | Empate: {be:,} 👉 <code>/vendi {i['id']} PRECIO</code>\n"
    else:
        txt += "<i>Sin lotes abiertos.</i>"
    return txt

# --- 6. COMANDOS INSTANTÁNEOS ---
def procesar_comando(texto):
    partes = texto.strip().split()
    if not partes:
        return None
    cmd = partes[0].lower()

    if cmd in ["/start", "/menu", "/ayuda", "hola"]:
        return (
            "⚡ <b>COMANDOS EN TIEMPO REAL (API FC 27):</b>\n"
            "• <code>/radar</code> (Precios reales en 2 seg)\n"
            "• <code>/evo</code> (Cartas en tendencia de Evolución)\n"
            "• <code>/compre 10 1700 Exe Palacios</code>\n"
            "• <code>/vendi 1 2400</code>\n"
            "• <code>/agenda</code> | <code>/calc 12000 14000</code> | <code>/reset</code>"
        )
    elif cmd in ["/radar", "radar"]:
        return generar_reporte_mercado()
    elif cmd in ["/evo", "evo"]:
        return detectar_boom_evos()
    elif cmd in ["/agenda", "agenda"]:
        return ver_resumen_agenda()
    elif cmd in ["/compre", "/compra"]:
        if len(partes) < 4:
            return "⚠️ Usá: <code>/compre [cantidad] [precio] [jugador]</code>"
        try:
            return registrar_compra(int(partes[1]), int(partes[2].replace(".", "").replace(",", "")), " ".join(partes[3:]))
        except ValueError:
            return "❌ Cantidad y precio deben ser números."
    elif cmd in ["/vendi", "/venta"]:
        if len(partes) < 3:
            return "⚠️ Usá: <code>/vendi [ID] [precio_venta]</code>"
        try:
            return registrar_venta(int(partes[1].replace("#", "")), int(partes[2].replace(".", "").replace(",", "")))
        except ValueError:
            return "❌ ID y precio deben ser números."
    elif cmd == "/calc":
        if len(partes) < 3:
            return "⚠️ Usá: <code>/calc [compra] [venta]</code>"
        try:
            c, v = int(partes[1].replace(".", "")), int(partes[2].replace(".", ""))
            limpio = int(v * 0.95) - c
            be = int((c / 0.95) + 49) // 50 * 50
            return f"🧮 Compra {c:,} ➡️ Venta {v:,}\nPost 5%: <b>{'+' if limpio>=0 else ''}{limpio:,} monedas</b> (Empate: {be:,})"
        except ValueError:
            return "❌ Poné solo números."
    elif cmd == "/saldo":
        if len(partes) >= 2 and partes[1].isdigit():
            ag = cargar_agenda()
            ag["monedas_liquidas"] = int(partes[1])
            guardar_agenda(ag)
            return f"🏦 Saldo actualizado a <b>{ag['monedas_liquidas']:,}</b>."
    elif cmd == "/reset":
        reiniciar_agenda()
        return "🔄 Agenda reiniciada a <b>375.000 monedas</b>."
    return "🤖 Mandá <code>/menu</code> para ver los comandos."

def escuchar_tiempo_real(segundos_maximos=None):
    print("🚀 Bot conectado a API-FC27 activo (Respuesta instantánea)...")
    url_updates = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    ag = cargar_agenda()
    ultimo_id = ag.get("ultimo_update_id", None)

    inicio = time.time()
    while True:
        if segundos_maximos and (time.time() - inicio) >= segundos_maximos:
            break
        try:
            params = {"timeout": 15}
            if ultimo_id:
                params["offset"] = ultimo_id + 1
            resp = requests.get(url_updates, params=params, timeout=20).json()

            for item in resp.get("result", []):
                ultimo_id = item["update_id"]
                ag = cargar_agenda()
                ag["ultimo_update_id"] = ultimo_id
                guardar_agenda(ag)

                msg = item.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) == CHAT_ID and msg.get("text"):
                    t0 = time.time()
                    respuesta = procesar_comando(msg.get("text"))
                    if respuesta:
                        enviar_telegram(respuesta)
                    print(f"✅ Comando '{msg.get('text')}' respondido en {time.time() - t0:.2f} seg.")
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        modo = sys.argv[1]
        if modo == "--evo":
            enviar_telegram(detectar_boom_evos())
        elif modo == "--auto":
            enviar_telegram(generar_reporte_mercado())
        elif modo == "--cloud-live":
            escuchar_tiempo_real(segundos_maximos=800)
    else:
        enviar_telegram("🎯 <b>¡CONECTADO DIRECTO A LA API DE FC 27!</b>\nMandá <code>/radar</code> o <code>/evo</code> ahora mismo y mirá la velocidad y los precios reales.")
        escuchar_tiempo_real()
