import requests
import time
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# --- 1. TUS DATOS DE TELEGRAM ---
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8908344399:AAGeC35sIxMJZ3pFhyr3seUfp24KftyJcLU")
CHAT_ID = "1656016116"

IMPUESTO_EA = 0.05
ARCHIVO_AGENDA = "mi_agenda_fut.json"
PRESUPUESTO_INICIAL = 375000
MEDIAS_OBJETIVO = [84, 85, 86, 87, 88, 89]

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# --- 2. AGENDA, CONTABILIDAD Y MEMORIA DE SEGUIMIENTO ---
def cargar_agenda():
    if os.path.exists(ARCHIVO_AGENDA):
        try:
            with open(ARCHIVO_AGENDA, "r", encoding="utf-8") as f:
                datos = json.load(f)
                if "seguimientos" not in datos:
                    datos["seguimientos"] = []
                return datos
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
        "historial": [],
        "seguimientos": []
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
    for _ in range(3):
        try:
            r = requests.post(url, data=datos, timeout=20)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(1)
    return False

# --- 3. BUSCADOR INTELIGENTE DE JUGADORES Y ALTERNATIVAS EN LA API ---
def buscar_jugador_api(nombre_buscado):
    """
    Busca un jugador por nombre (ej. 'Carreras') en la API de EasySBC
    o en las listas de tendencias/mercado y devuelve su ficha completa con precio en vivo.
    """
    q = nombre_buscado.strip().lower()
    candidatos = []

    # 1. Intentamos endpoints de búsqueda directa y páginas de tendencias/populares
    urls_busqueda = [
        f"https://api-fc27.easysbc.io/players?v2&page=1&search={requests.utils.quote(nombre_buscado)}",
        f"https://api-fc27.easysbc.io/players?v2&page=1&name={requests.utils.quote(nombre_buscado)}",
        "https://api-fc27.easysbc.io/players?v2&page=1&sort-trending&priceMin=200&priceMax=150000",
        "https://api-fc27.easysbc.io/players?v2&page=2&sort-trending&priceMin=200&priceMax=150000",
        "https://api-fc27.easysbc.io/players?v2&page=1&sort-meta-rating&priceMin=200&priceMax=100000&ratingMax=86"
    ]

    for url in urls_busqueda:
        try:
            r = requests.get(url, headers=HEADERS_API, timeout=8)
            if r.status_code == 200:
                for p in r.json().get("players", []):
                    nom_completo = (p.get("name") or "").lower()
                    nom_carta = (p.get("cardName") or "").lower()
                    if q in nom_completo or q in nom_carta:
                        if p.get("price", 0) > 0 and not p.get("isSbcPlayer") and not p.get("isObjectivePlayer"):
                            if not any(c.get("resourceId") == p.get("resourceId") for c in candidatos):
                                candidatos.append(p)
            if candidatos:
                break
        except Exception:
            continue

    # Priorizamos cartas transferibles con mayor popularidad de Evo
    candidatos.sort(key=lambda x: (x.get("evoPopularity", 0), x.get("price", 0)), reverse=True)
    return candidatos[0] if candidatos else None

def obtener_precio_por_resource_id(resource_id, nombre_respaldo, rating_respaldo):
    """Consulta el precio fresco en vivo de una carta seguida"""
    # Buscamos en el rango exacto de rating de esa carta para traer el precio actualizado al segundo
    for pag in [1, 2, 3]:
        url = f"https://api-fc27.easysbc.io/players?v2&page={pag}&ratingMin={rating_respaldo}&ratingMax={rating_respaldo}&sort-trending"
        try:
            r = requests.get(url, headers=HEADERS_API, timeout=8)
            if r.status_code == 200:
                for p in r.json().get("players", []):
                    if p.get("resourceId") == resource_id and p.get("price", 0) > 0:
                        return int(p["price"])
        except Exception:
            pass

    # Respaldo por búsqueda de nombre
    ficha = buscar_jugador_api(nombre_respaldo)
    if ficha and ficha.get("price", 0) > 0:
        return int(ficha["price"])
    return None

def buscar_alternativas_evo(posicion, rating_base, excluir_nombre=""):
    """
    Busca otros jugadores de la MISMA posición y media parecida (+/- 3 puntos)
    que sean evolucionables y estén en tendencia para diversificar compras.
    """
    r_min = max(65, rating_base - 3)
    r_max = min(87, rating_base + 2)
    alternativas = []

    urls = [
        f"https://api-fc27.easysbc.io/players?v2&page=1&sort-trending&ratingMin={r_min}&ratingMax={r_max}&priceMin=350&priceMax=35000",
        f"https://api-fc27.easysbc.io/players?v2&page=2&sort-trending&ratingMin={r_min}&ratingMax={r_max}&priceMin=350&priceMax=35000",
        f"https://api-fc27.easysbc.io/players?v2&page=1&sort-meta-rating&ratingMin={r_min}&ratingMax={r_max}&priceMin=350&priceMax=35000"
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS_API, timeout=8)
            if r.status_code == 200:
                for p in r.json().get("players", []):
                    precio = p.get("price", 0)
                    pos_jug = p.get("preferredPosition", "")
                    posibles_pos = p.get("possiblePositions", [])
                    nom = p.get("cardName") or p.get("name", "")

                    if (
                        precio >= 350
                        and p.get("canEvolve", False)
                        and not p.get("isSbcPlayer")
                        and not p.get("isObjectivePlayer")
                        and nom.lower() != excluir_nombre.lower()
                        and (posicion == pos_jug or posicion in posibles_pos)
                    ):
                        etiqueta = f"{nom} ({p.get('rating')} {pos_jug})"
                        if not any(a["nombre"] == etiqueta for a in alternativas):
                            alternativas.append({
                                "nombre": etiqueta,
                                "nombre_corto": nom,
                                "precio": int(precio),
                                "evo_pop": p.get("evoPopularity", 0),
                                "rating": p.get("rating")
                            })
        except Exception:
            continue

    alternativas.sort(key=lambda x: (x["evo_pop"], x["precio"]), reverse=True)
    return alternativas[:5]

# --- 4. SISTEMA DE SEGUIMIENTO POR HORA (/seguir) ---
def iniciar_seguimiento(nombre_buscado, minutos=60):
    ficha = buscar_jugador_api(nombre_buscado)
    if not ficha:
        return (
            f"❌ No encontré a <b>{nombre_buscado}</b> con precio activo en este segundo.\n"
            f"💡 Probá escribir solo el apellido (ej: <code>/seguir Carreras</code>) o mirá cómo figura en <code>/evo</code>."
        )

    ag = cargar_agenda()
    ahora_ts = time.time()
    fin_ts = ahora_ts + (minutos * 60)

    nombre_mostrar = f"{ficha.get('cardName') or ficha.get('name')} ({ficha.get('rating')} {ficha.get('preferredPosition', '')})"
    precio_inicial = int(ficha.get("price", 0))
    pos = ficha.get("preferredPosition", "ST")
    rat = int(ficha.get("rating", 80))

    nuevo_seg = {
        "resourceId": ficha.get("resourceId"),
        "nombre_corto": ficha.get("cardName") or ficha.get("name"),
        "nombre_mostrar": nombre_mostrar,
        "rating": rat,
        "posicion": pos,
        "precio_inicial": precio_inicial,
        "precio_maximo": precio_inicial,
        "ultimo_precio": precio_inicial,
        "inicio_ts": ahora_ts,
        "fin_ts": fin_ts,
        "ultimo_aviso_ts": ahora_ts,
        "minutos_totales": minutos
    }

    # Reemplazar si ya lo estábamos siguiendo
    ag["seguimientos"] = [s for s in ag["seguimientos"] if s.get("resourceId") != nuevo_seg["resourceId"]]
    ag["seguimientos"].append(nuevo_seg)
    guardar_agenda(ag)

    # Además, ya mismo le buscamos alternativas de la misma Evo por si quiere diversificar
    alternativas = buscar_alternativas_evo(pos, rat, excluir_nombre=nuevo_seg["nombre_corto"])
    txt_alt = ""
    if alternativas:
        txt_alt = "\n\n🧬 <b>OTROS JUGADORES PARA LA MISMA EVO (Misma posición/rango):</b>\n"
        for a in alternativas[:4]:
            txt_alt += f"• <b>{a['nombre']}</b> 👉 <b>{a['precio']:,} monedas</b> (Hype Evo: {a['evo_pop']})\n"

    venta_empate = int((precio_inicial / 0.95) + 49) // 50 * 50
    return (
        f"🎯 <b>SEGUIMIENTO ACTIVADO POR {minutos} MINUTOS</b>\n\n"
        f"🏃‍♂️ Jugador: <b>{nombre_mostrar}</b>\n"
        f"💰 Precio base (Minuto 0): <b>{precio_inicial:,} monedas</b>\n"
        f"⚠️ Empate post 5% EA (si comprás hoy): <b>{venta_empate:,}</b>\n"
        f"⏱ <i>Te voy a mandar alertas automáticas cada 10 min con cuánto subió o bajó para decidir cuándo vender.</i>"
        f"{txt_alt}"
    )

def revisar_seguimientos_activos(forzar_reporte=False):
    """Revisa el precio actual de todos los jugadores seguidos y avisa subas, bajas o fin de hora"""
    ag = cargar_agenda()
    seguimientos = ag.get("seguimientos", [])
    if not seguimientos:
        return "📭 No tenés ningún jugador en seguimiento ahora. Usá <code>/seguir Carreras</code>." if forzar_reporte else None

    ahora = time.time()
    quedan_activos = []
    mensajes_alerta = []

    for s in seguimientos:
        # Si queremos avisar cada 10 minutos (600 seg) o si el usuario pidió /siguiendo o si terminó la hora
        tiempo_desde_ultimo = ahora - s.get("ultimo_aviso_ts", 0)
        termino_tiempo = ahora >= s.get("fin_ts", 0)

        if forzar_reporte or termino_tiempo or tiempo_desde_ultimo >= 600:
            precio_actual = obtener_precio_por_resource_id(s["resourceId"], s["nombre_corto"], s["rating"]) or s["ultimo_precio"]
            p_ini = s["precio_inicial"]
            p_ant = s["ultimo_precio"]
            p_max = max(s.get("precio_maximo", p_ini), precio_actual)

            dif_total = precio_actual - p_ini
            pct_total = (dif_total / p_ini * 100) if p_ini > 0 else 0
            dif_10m = precio_actual - p_ant

            min_transcurridos = int((ahora - s["inicio_ts"]) / 60)
            min_totales = s["minutos_totales"]

            signo = "+" if dif_total >= 0 else ""
            icono = "📈" if dif_total > 0 else ("📉" if dif_total < 0 else "➖")

            # Consejo automático de venta según el movimiento
            if precio_actual < p_max * 0.93 and dif_total > 0:
                consejo = f"⚠️ <b>¡ATENCIÓN TECHO!</b> Tocó un máximo de {p_max:,} y empezó a bajar ({precio_actual:,}). <b>¡Momento ideal para vender y asegurar ganancia!</b>"
            elif pct_total >= 20:
                consejo = f"🔥 <b>¡SUBIÓ +{pct_total:.1f}%!</b> Ya tenés excelente margen post-impuesto. Podés ir vendiendo o asegurar mitad del lote."
            elif dif_10m > 0:
                consejo = f"🟢 Sigue firme en subida (+{dif_10m:,} en los últimos minutos). Podés aguantar un poco más."
            elif dif_total < 0:
                consejo = f"🔻 Está {abs(dif_total):,} abajo de cuando empezamos a mirarlo."
            else:
                consejo = f"⏳ Precio estable sin cambios bruscos todavía."

            encabezado = "🏁 <b>FIN DEL SEGUIMIENTO PACTADO</b>" if termino_tiempo else f"⏱ <b>TRACKER EN VIVO ({min_transcurridos}/{min_totales} min)</b>"

            mensajes_alerta.append(
                f"{encabezado}\n"
                f"🃏 <b>{s['nombre_mostrar']}</b>\n"
                f"• Precio inicial: <b>{p_ini:,}</b> ➡️ Ahora: <b>{precio_actual:,}</b>\n"
                f"• Variación acumulada: {icono} <b>{signo}{dif_total:,} monedas ({signo}{pct_total:.1f}%)</b>\n"
                f"• Pico máximo alcanzado: <b>{p_max:,}</b>\n"
                f"💡 {consejo}"
            )

            s["ultimo_precio"] = precio_actual
            s["precio_maximo"] = p_max
            s["ultimo_aviso_ts"] = ahora

        if not termino_tiempo:
            quedan_activos.append(s)

    ag["seguimientos"] = quedan_activos
    guardar_agenda(ag)

    if mensajes_alerta:
        return "\n\n".join(mensajes_alerta)
    return None

# --- 5. RADAR DE EVOS CON ALTERNATIVAS DE LA MISMA EVO ---
def detectar_boom_evos():
    tz_arg = timezone(timedelta(hours=-3))
    hora_arg = datetime.now(tz_arg).strftime("%H:%M")
    candidatos_evo = []

    urls = [
        "https://api-fc27.easysbc.io/players?v2&page=1&sort-trending&priceMin=650&priceMax=35000&ratingMax=86",
        "https://api-fc27.easysbc.io/players?v2&page=2&sort-trending&priceMin=650&priceMax=35000&ratingMax=86",
        "https://api-fc27.easysbc.io/players?v2&page=1&sort-meta-rating&priceMin=650&priceMax=25000&ratingMax=85"
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS_API, timeout=8)
            if r.status_code == 200:
                for p in r.json().get("players", []):
                    precio = p.get("price", 0)
                    if (
                        650 <= precio <= 35000
                        and p.get("canEvolve", False)
                        and not p.get("isSbcPlayer")
                        and not p.get("isObjectivePlayer")
                    ):
                        nom_corto = p.get("cardName") or p.get("name", "Jugador")
                        pos = p.get("preferredPosition", "")
                        rat = int(p.get("rating", 80))
                        etiqueta = f"{nom_corto} ({rat} {pos})"
                        evo_pop = p.get("evoPopularity", 0)
                        if not any(c["nombre"] == etiqueta for c in candidatos_evo):
                            candidatos_evo.append({
                                "nombre": etiqueta,
                                "nombre_corto": nom_corto,
                                "posicion": pos,
                                "rating": rat,
                                "precio": int(precio),
                                "evo_pop": evo_pop
                            })
        except Exception:
            continue

    candidatos_evo.sort(key=lambda x: (x["evo_pop"], x["precio"]), reverse=True)

    msg = f"🧬 <b>RADAR DE EVOS + ALTERNATIVAS ({hora_arg} hs ARG)</b>\n"
    msg += "<i>Cartas disparadas hoy y sus variantes de la misma posición/media para diversificar:</i>\n\n"

    if candidatos_evo:
        principales = candidatos_evo[:6]
        for c in principales:
            p = c["precio"]
            venta_hype = int((p * 1.28) / 100) * 100
            ganancia = int(venta_hype * 0.95) - p
            fuego = f" 🔥(Hype: {c['evo_pop']})" if c["evo_pop"] > 0 else ""

            # Buscamos de la misma lista o de la API otros jugadores de la misma posición para esa misma Evo
            similares = [
                f"{x['nombre_corto']} ({x['precio']:,})"
                for x in candidatos_evo
                if x["posicion"] == c["posicion"] and x["nombre"] != c["nombre"]
            ][:3]

            if not similares:
                extra = buscar_alternativas_evo(c["posicion"], c["rating"], excluir_nombre=c["nombre_corto"])
                similares = [f"{x['nombre_corto']} ({x['precio']:,})" for x in extra[:3]]

            msg += (
                f"🚀 <b>{c['nombre']}</b>{fuego}\n"
                f"   💰 Hoy: <b>{p:,}</b> 👉 Target pre-15hs: <b>{venta_hype:,}</b> (+{ganancia:,})\n"
            )
            if similares:
                msg += f"   🔄 <i>Variantes misma Evo ({c['posicion']}): {', '.join(similares)}</i>\n"
            msg += f"   📲 <i>Vigilar 1h:</i> <code>/seguir {c['nombre_corto']}</code>\n\n"
    else:
        msg += "<i>No hay picos anormales en este minuto.</i>\n"

    msg += "💡 <b>Tip:</b> Mandá <code>/alt [jugador]</code> (ej: <code>/alt Carreras</code>) para ver 5 jugadores alternativos de esa misma Evo."
    return msg

# --- 6. REPORTE DE MEDIAS Y GALLERY ---
def obtener_fodder_real_por_media(media):
    jugadores_validos = []
    for pagina in [1, 2]:
        url = (
            f"https://api-fc27.easysbc.io/players?v2&page={pagina}"
            f"&ratingMin={media}&ratingMax={media}&priceMin=650&priceMax=45000"
        )
        try:
            r = requests.get(url, headers=HEADERS_API, timeout=8)
            if r.status_code == 200:
                for p in r.json().get("players", []):
                    precio = p.get("price", 0)
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
                            jugadores_validos.append({"nombre": etiqueta, "precio": int(precio)})
        except Exception:
            continue
    jugadores_validos.sort(key=lambda x: x["precio"])
    return jugadores_validos[:4]

def obtener_platas_gallery_reales():
    platas = []
    url = "https://api-fc27.easysbc.io/players?v2&page=1&sort-trending&ratingMin=65&ratingMax=74&priceMin=1300&priceMax=8000"
    try:
        r = requests.get(url, headers=HEADERS_API, timeout=8)
        if r.status_code == 200:
            for p in r.json().get("players", []):
                precio = p.get("price", 0)
                if precio >= 1300 and not p.get("isSbcPlayer") and not p.get("isObjectivePlayer"):
                    nombre = p.get("cardName") or p.get("name", "Plata")
                    pos = p.get("preferredPosition", "")
                    platas.append({"nombre": f"{nombre} ({pos})", "precio": int(precio)})
                if len(platas) >= 5:
                    break
    except Exception:
        pass
    return platas

def generar_reporte_mercado():
    ag = cargar_agenda()
    disponible = ag["monedas_liquidas"]
    tz_arg = timezone(timedelta(hours=-3))
    ahora = datetime.now(tz_arg)

    mensaje = f"⚡ <b>MERCADO EN VIVO FC 27 ({ahora.strftime('%H:%M')} hs ARG)</b>\n"
    mensaje += f"💰 <i>Capital libre hoy: <b>{disponible:,} monedas</b></i>\n\n"
    mensaje += "📦 <b>PISO REAL DE MEDIAS (API Directa):</b>\n\n"

    for media in MEDIAS_OBJETIVO:
        top_baratas = obtener_fodder_real_por_media(media)
        if top_baratas:
            mas_barata = top_baratas[0]
            precio_hoy = mas_barata["precio"]
            nombre_top = mas_barata["nombre"]
            otros = ", ".join([f"{x['nombre']} ({x['precio']:,})" for x in top_baratas[1:4]])

            compra_objetivo = int((precio_hoy * 0.92) / 100) * 100
            if precio_hoy < 3500:
                compra_objetivo = int((precio_hoy * 0.90) / 50) * 50
            venta_sbc = int((precio_hoy * 1.18) / 100) * 100
            ganancia_unit = int(venta_sbc * (1 - IMPUESTO_EA)) - compra_objetivo

            mensaje += (
                f"🔹 <b>MEDIA {media}</b> 👉 Hoy: <b>{precio_hoy:,}</b> (<b>{nombre_top}</b>)\n"
                f"   🟢 Pujar/Snipear: <b>&lt; {compra_objetivo:,}</b> | Venta SBC: <b>{venta_sbc:,}</b> (+{ganancia_unit:,})\n"
            )
            if otros:
                mensaje += f"   👟 <i>Otras baratas: {otros}</i>\n"
            mensaje += "\n"

    platas = obtener_platas_gallery_reales()
    mensaje += "🥈 <b>THE GALLERY (Platas cotizando alto):</b>\n"
    if platas:
        for pl in platas:
            c_ya = pl["precio"]
            puja_max = int((c_ya * 0.45) / 50) * 50
            limpio = int(c_ya * 0.95) - puja_max
            mensaje += f"• <b>{pl['nombre']}</b>: Compra Ya <b>{c_ya:,}</b> 👉 Pujar a <b>{puja_max:,}</b> (+{limpio:,})\n"
    return mensaje

# --- 7. CONTABILIDAD ---
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
            txt += f"• <b>#{i['id']} {i['nombre']}</b> (x{i['cantidad']}) a {i['precio_compra']:,} | Empate: {be:,}\n"
    else:
        txt += "<i>Sin lotes abiertos.</i>"
    return txt

# --- 8. PROCESADOR DE COMANDOS ---
def procesar_comando(texto):
    partes = texto.strip().split()
    if not partes:
        return None
    cmd = partes[0].lower()

    if cmd in ["/start", "/menu", "/ayuda", "hola"]:
        return (
            "⚡ <b>COMANDOS PRO (API FC 27):</b>\n"
            "• <code>/evo</code> (Evos en hype + variantes misma posición)\n"
            "• <code>/seguir Carreras</code> (Sigue su precio por 1h y avisa cada 10m)\n"
            "• <code>/seguir Carreras 90</code> (Seguir por 90 minutos)\n"
            "• <code>/siguiendo</code> (Ver cuánto subieron/bajaron ahora mismo)\n"
            "• <code>/parar</code> (Frenar seguimientos activos)\n"
            "• <code>/alt Carreras</code> (Ver otros jugadores para la misma Evo)\n"
            "• <code>/radar</code> (Piso real de Medias 84-89 y Platas)\n"
            "• <code>/compre 10 1700 Carreras</code> | <code>/vendi 1 2400</code>\n"
            "• <code>/agenda</code> | <code>/calc 4000 5200</code>"
        )
    elif cmd in ["/radar", "radar"]:
        return generar_reporte_mercado()
    elif cmd in ["/evo", "evo"]:
        return detectar_boom_evos()
    elif cmd == "/seguir":
        if len(partes) < 2:
            return "⚠️ Usá: <code>/seguir [jugador]</code> (ej: <code>/seguir Carreras</code> o <code>/seguir Carreras 90</code>)"
        # Si el último parámetro es un número de minutos (ej: /seguir Carreras 90)
        if len(partes) >= 3 and partes[-1].isdigit():
            minutos = int(partes[-1])
            nombre = " ".join(partes[1:-1])
        else:
            minutos = 60
            nombre = " ".join(partes[1:])
        return iniciar_seguimiento(nombre, minutos)
    elif cmd in ["/siguiendo", "/tracker"]:
        return revisar_seguimientos_activos(forzar_reporte=True)
    elif cmd == "/parar":
        ag = cargar_agenda()
        ag["seguimientos"] = []
        guardar_agenda(ag)
        return "🛑 Todos los seguimientos por hora fueron detenidos."
    elif cmd in ["/alt", "/similares"]:
        if len(partes) < 2:
            return "⚠️ Usá: <code>/alt [jugador]</code> (ej: <code>/alt Carreras</code>)"
        nom_b = " ".join(partes[1:])
        ficha = buscar_jugador_api(nom_b)
        if not ficha:
            return f"❌ No encontré a <b>{nom_b}</b> para buscarle similares."
        pos = ficha.get("preferredPosition", "ST")
        rat = int(ficha.get("rating", 80))
        nom_c = ficha.get("cardName") or ficha.get("name")
        alts = buscar_alternativas_evo(pos, rat, excluir_nombre=nom_c)
        if not alts:
            return f"No encontré otras cartas en tendencia para {pos} de media ~{rat}."
        msg = f"🔄 <b>ALTERNATIVAS DE EVO PARA {nom_c.upper()} ({rat} {pos} - {ficha.get('price',0):,} monedas):</b>\n<i>Otras cartas de la misma posición y rango que entran en Evos parecidas:</i>\n\n"
        for a in alts:
            msg += f"• <b>{a['nombre']}</b> 👉 Precio hoy: <b>{a['precio']:,}</b> 🔥(Hype Evo: {a['evo_pop']})\n"
        return msg
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
    return "🤖 Mandá <code>/menu</code> para ver los comandos nuevos."

def escuchar_tiempo_real(segundos_maximos=None):
    print("🚀 Bot Pro Activo (Escuchando comandos y vigilando jugadores seguidos)...")
    url_updates = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    ag = cargar_agenda()
    ultimo_id = ag.get("ultimo_update_id", None)

    inicio = time.time()
    ultimo_chequeo_tracker = 0

    while True:
        ahora = time.time()
        if segundos_maximos and (ahora - inicio) >= segundos_maximos:
            break

        # Cada 60 segundos verificamos si algún jugador seguido cumplió sus 10 min para mandar alerta
        if ahora - ultimo_chequeo_tracker >= 60:
            alerta_tracker = revisar_seguimientos_activos(forzar_reporte=False)
            if alerta_tracker:
                enviar_telegram(alerta_tracker)
            ultimo_chequeo_tracker = ahora

        try:
            params = {"timeout": 10}
            if ultimo_id:
                params["offset"] = ultimo_id + 1
            resp = requests.get(url_updates, params=params, timeout=15).json()

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
                    print(f"⚡ Comando '{msg.get('text')}' respondido en {time.time() - t0:.2f} seg.")
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
            # En GitHub ahora se queda despierto 55 minutos continuos (3300 seg) para evitar baches de espera
            escuchar_tiempo_real(segundos_maximos=3300)
    else:
        enviar_telegram(
            "🔥 <b>¡ACTUALIZACIÓN LISTA!</b>\n"
            "Probá mandar ahora mismo:\n"
            "• <code>/seguir Carreras</code> (Lo vigila por 1 hora)\n"
            "• <code>/alt Carreras</code> (Te da otros jugadores de la misma Evo)\n"
            "• <code>/evo</code> (Ahora incluye variantes por posición)"
        )
        escuchar_tiempo_real()
