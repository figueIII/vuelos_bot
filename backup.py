import os
import time
import requests
from datetime import datetime
import gspread
from serpapi import GoogleSearch


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
        print("   📱 Notificación enviada a Telegram.")
    except Exception as e:
        print(f"   ⚠️ Error enviando Telegram: {e}")

def obtener_minimo_historico(sheet, tipo_vuelo):
    """Lee la columna de precios del Excel para saber el récord actual"""
    try:
        registros = sheet.get_all_values()
        precios = []
        
        # Asumimos estructura: [Fecha, TIPO, FechaVuelo, Origen, Destino, Aerolinea, PRECIO]
        # El precio está en la columna 7 (índice 6)
        # El TIPO está en la columna 2 (índice 1)
        
        for fila in registros[1:]: # Saltamos encabezados
            if len(fila) > 6 and fila[1] == tipo_vuelo:
                try:
                    # Limpiamos el símbolo de euro si existe
                    precio_limpio = float(str(fila[6]).replace("€", "").strip())
                    precios.append(precio_limpio)
                except ValueError:
                    continue 
        
        if precios:
            return min(precios)
        else:
            return 999999.0 # Si es la primera vez, ponemos un precio muy alto
    except Exception as e:
        print(f"   ⚠️ No se pudo leer histórico (es normal si la hoja está vacía): {e}")
        return 999999.0

def buscar_vuelo_one_way(origen, destino, fecha):
    print(f"✈️ Buscando: {origen} -> {destino} | {fecha}...")
    params = {
      "engine": "google_flights",
      "departure_id": origen,
      "arrival_id": destino,
      "outbound_date": fecha,
      "type": "2", # Solo ida
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
    
    # Conexión a Sheets
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
        
        # 1. Obtenemos el precio récord ANTES de guardar lo nuevo
        precio_record = obtener_minimo_historico(worksheet, tipo_analisis)
        print(f"   📊 Récord actual ({tipo_analisis}): {precio_record}€")

        # 2. Guardamos los nuevos datos
        worksheet.append_rows(datos)
        print(f"   💾 Guardado en Excel.")

        # 3. Comprobamos si hay CHOLLO
        mensaje_acumulado = ""
        encontrado_chollo = False

        for fila in datos:
            # fila = [FechaHoy, TIPO, FechaVuelo, Origen, Destino, Aerolinea, Precio]
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

# --- EJECUCIÓN ---
if __name__ == "__main__":
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1. BARRIDO DE IDAS
    datos_ida = []
    print("\n--- 1. BUSCANDO IDAS ---")
    for fecha in FECHAS_IDA:
        precio, aerolinea = buscar_vuelo_one_way("BCN", "DUB", fecha)
        if precio:
            datos_ida.append([fecha_hoy, "IDA", fecha, "BCN", "DUB", aerolinea, precio])
        time.sleep(1)
    
    if datos_ida:
        guardar_y_avisar(datos_ida, "IDA")

    # 2. BARRIDO DE VUELTAS
    datos_vuelta = []
    print("\n--- 2. BUSCANDO VUELTAS ---")
    for fecha in FECHAS_VUELTA:
        precio, aerolinea = buscar_vuelo_one_way("DUB", "BCN", fecha)
        if precio:
            datos_vuelta.append([fecha_hoy, "VUELTA", fecha, "DUB", "BCN", aerolinea, precio])
        time.sleep(1)

    if datos_vuelta:
        guardar_y_avisar(datos_vuelta, "VUELTA")