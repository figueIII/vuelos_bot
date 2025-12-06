import os
import time
import requests
from datetime import datetime
import gspread
from serpapi import GoogleSearch

# --- CONFIGURACIÓN ---
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID") or "1myuJ5i6jN8rnYD3EpDkLyOs-RYRaG0T9_emOwqmAJ54" 
SERPAPI_KEY = os.environ.get("SERPAPI_KEY") or "d82d8ac259deb4cf3f730e4f722ad0c67ecfe1e8e4d3b72eb61c645eb1092a81"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "8460226319:AAG_rQRSFImtrKSA15QD4b61yfr_daIFgFU"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "1859072962"

# --- FECHAS ---
FECHAS_IDA = ["2026-02-01", "2026-02-02", "2026-02-03"] 
FECHAS_VUELTA = ["2026-02-04", "2026-02-05", "2026-02-06"]

# --- FUNCIONES ---

def enviar_telegram(mensaje):
    """Envía un mensaje a tu chat de Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
        requests.post(url, data=data)
    except Exception as e:
        print(f"   ⚠️ Error enviando Telegram: {e}")

def obtener_minimo_historico(sheet, tipo_vuelo):
    """Lee la columna de precios del Excel para saber el récord actual"""
    try:
        registros = sheet.get_all_values()
        precios = []
        for fila in registros[1:]: 
            if len(fila) > 6 and fila[1] == tipo_vuelo:
                try:
                    precio_limpio = float(str(fila[6]).replace("€", "").strip())
                    precios.append(precio_limpio)
                except ValueError:
                    continue 
        return min(precios) if precios else 999999.0
    except Exception:
        return 999999.0

def buscar_vuelo_one_way(origen, destino, fecha):
    print(f"✈️ Buscando: {origen} -> {destino} | {fecha}...")
    params = {
      "engine": "google_flights",
      "departure_id": origen,
      "arrival_id": destino,
      "outbound_date": fecha,
      "type": "2", 
      "currency": "EUR",
      "hl": "es",
      "api_key": SERPAPI_KEY
    }
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        vuelos = results.get("best_flights", [])
        if not vuelos: vuelos = results.get("other_flights", [])
        
        if vuelos:
            mejor = vuelos[0]
            precio = mejor.get("price")
            aerolinea = mejor.get("flights", [{}])[0].get("airline")
            print(f"   ✅ {precio}€ ({aerolinea})")
            return precio, aerolinea
        return None, None
    except Exception:
        return None, None

def guardar_y_avisar(datos, tipo_analisis):
    print(f"💾 Procesando datos de {tipo_analisis}...")
    
    archivo_creds = 'credentials.json'
    if not os.path.exists(archivo_creds):
        creds = os.environ.get("GCP_CREDENTIALS")
        if creds:
            with open(archivo_creds, 'w') as f: f.write(creds)
        else: return

    try:
        gc = gspread.service_account(filename=archivo_creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1
        
        precio_record = obtener_minimo_historico(worksheet, tipo_analisis)
        worksheet.append_rows(datos)
        print(f"   💾 Guardado en Excel.")

        mensaje_acumulado = ""
        encontrado_chollo = False

        for fila in datos:
            precio_nuevo = fila[6]
            if precio_nuevo < precio_record:
                encontrado_chollo = True
                mensaje_acumulado += (
                    f"📅 *{fila[2]}* ({fila[5]}): *{precio_nuevo}€* "
                    f"(Antes: {precio_record}€)\n"
                )

        if encontrado_chollo:
            cabecera = f"🚨 *¡BAJADA DE PRECIO ({tipo_analisis})!* 🚨\n\n"
            pie = "\n🔗 [Ir a Google Flights](https://www.google.com/travel/flights)"
            enviar_telegram(cabecera + mensaje_acumulado + pie)

    except Exception as e:
        print(f"❌ Error en guardado/aviso: {e}")

# --- NUEVA FUNCIÓN: LEER RESUMEN DE HOY ---
def generar_resumen_hoy():
    """Lee la hoja y devuelve los precios guardados HOY"""
    print("🔎 Generando resumen bajo demanda...")
    archivo_creds = 'credentials.json'
    if not os.path.exists(archivo_creds): return "❌ Error: No hay credenciales."

    try:
        gc = gspread.service_account(filename=archivo_creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1
        registros = worksheet.get_all_values()
        
        hoy_str = datetime.now().strftime("%Y-%m-%d") # Ej: 2025-10-25
        mensaje = f"📊 *RESUMEN DE PRECIOS ({hoy_str})*\n\n"
        encontrado = False

        # Estructura: [FechaHoy, TIPO, FechaVuelo, Origen, Destino, Aerolinea, Precio]
        for fila in registros[1:]:
            # Comprobamos si la columna 0 (Fecha Búsqueda) contiene la fecha de hoy
            if len(fila) > 6 and hoy_str in str(fila[0]):
                encontrado = True
                tipo = fila[1] # IDA o VUELTA
                fecha_vuelo = fila[2]
                aerolinea = fila[5]
                precio = fila[6]
                icon = "🛫" if tipo == "IDA" else "🛬"
                
                mensaje += f"{icon} *{tipo}* ({fecha_vuelo}): *{precio}€* - {aerolinea}\n"

        if not encontrado:
            return "⚠️ No he encontrado datos guardados con fecha de hoy."
        
        return mensaje

    except Exception as e:
        return f"❌ Error leyendo la hoja: {e}"

# --- NUEVA FUNCIÓN: ESCUCHAR TELEGRAM ---
def escuchar_telegram(offset=None):
    """Consulta si hay mensajes nuevos"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 10, "offset": offset}
    try:
        response = requests.get(url, params=params).json()
        return response.get("result", [])
    except Exception as e:
        print(f"Error polling Telegram: {e}")
        return []

# --- EJECUCIÓN PRINCIPAL ---
if __name__ == "__main__":
    
    # 1. EJECUCIÓN INICIAL (BÚSQUEDA)
    # -------------------------------------------------
    print("🚀 Iniciando escaneo diario...")
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

    # IDAS
    datos_ida = []
    print("\n--- 1. BUSCANDO IDAS ---")
    for fecha in FECHAS_IDA:
        precio, aerolinea = buscar_vuelo_one_way("BCN", "DUB", fecha)
        if precio:
            datos_ida.append([fecha_hoy, "IDA", fecha, "BCN", "DUB", aerolinea, precio])
        time.sleep(1)
    if datos_ida: guardar_y_avisar(datos_ida, "IDA")

    # VUELTAS
    datos_vuelta = []
    print("\n--- 2. BUSCANDO VUELTAS ---")
    for fecha in FECHAS_VUELTA:
        precio, aerolinea = buscar_vuelo_one_way("DUB", "BCN", fecha)
        if precio:
            datos_vuelta.append([fecha_hoy, "VUELTA", fecha, "DUB", "BCN", aerolinea, precio])
        time.sleep(1)
    if datos_vuelta: guardar_y_avisar(datos_vuelta, "VUELTA")
    
    print("\n✅ Escaneo completado.")

    # 2. MODO ESCUCHA (RESPONDER A /PRICES)
    # -------------------------------------------------
    print("\n👂 Escuchando comandos de Telegram (Ctrl+C para salir)...")
    ultimo_update_id = None
    
    while True:
        updates = escuchar_telegram(ultimo_update_id)
        
        for update in updates:
            ultimo_update_id = update["update_id"] + 1
            
            # Verificamos si es un mensaje de texto
            if "message" in update and "text" in update["message"]:
                texto = update["message"]["text"]
                chat_id_usuario = str(update["message"]["chat"]["id"])
                
                # Solo respondemos si eres tú (seguridad básica)
                if chat_id_usuario == TELEGRAM_CHAT_ID:
                    if texto.strip() == "/prices":
                        print("   📩 Recibido comando /prices")
                        enviar_telegram("🔎 Buscando precios de hoy en la hoja...")
                        resumen = generar_resumen_hoy()
                        enviar_telegram(resumen)
                    else:
                        print(f"   Mensaje ignorado: {texto}")
        
        time.sleep(2) # Espera 2 segundos antes de volver a comprobar