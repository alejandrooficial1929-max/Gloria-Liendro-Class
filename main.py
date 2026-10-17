import psycopg2
import os
import sqlite3
import json
import io
import json
import chess
import chess.svg
from svglib.svglib import svg2rlg
from dotenv import load_dotenv
import google.generativeai as genai

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# 1. Cargar variables de entorno y configurar Gemini
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key or api_key == "tu_api_key_de_gemini_aqui":
    print("❌ ERROR: Configura tu GEMINI_API_KEY en el archivo .env antes de continuar.")
    exit()

genai.configure(api_key=api_key)

# 2. Diccionarios de Mapeo (Niveles y Temas de Lichess)
RANGOS_ELO = {
    "iniciante":   {"I": (600, 680), "II": (680, 760), "III": (760, 840), "IV": (840, 920), "V": (920, 1000)},
    "novato":      {"I": (1000, 1080), "II": (1080, 1160), "III": (1160, 1240), "IV": (1240, 1320), "V": (1320, 1400)},
    "intermedio":  {"I": (1400, 1480), "II": (1480, 1560), "III": (1560, 1640), "IV": (1640, 1720), "V": (1720, 1800)},
    "avanzado":    {"I": (1800, 1900), "II": (1900, 2000), "III": (2000, 2100), "IV": (2100, 2200), "V": (2200, 2300)}
}

MAPEO_TEMAS = {
    # Táctica Fundamental y Avanzada
    "celada": "trappedPiece",
    "clavada": "pin",
    "doble": "fork",
    "enfilada": "skewer",
    "desviacion": "deflection",
    "atraccion": "attraction",
    "descubierto": "discoveredAttack",
    "interferencia": "interference",
    "despeje": "clearance",
    "sacrificio": "sacrifice",
    "rayos_x": "xRayAttack",
    "zugzwang": "zugzwang",
    "sobrecarga": "overloading",
    "eliminacion_defensor": "removeTheDefender",
    "pieza_indefensa": "hangingPiece",
    "simplificacion": "simplification",
    "jugada_tranquila": "quietMove",
    "jugada_defensiva": "defensiveMove",
    "contraataque": "counterAttack",
    "jugada_intermedia": "intermediateMove",
    "captura_defensor": "capturingDefender",

    # Promociones y Reglas Especiales
    "promocion": "promotion",
    "subpromocion": "underPromotion",
    "al_paso": "enPassant",

    # Secuencias de Jaque Mate
    "mate_1": "mateIn1",
    "mate_2": "mateIn2",
    "mate_3": "mateIn3",
    "mate_4": "mateIn4",
    "mate_5": "mateIn5",

    # Patrones de Mate Famosos
    "mate_pasillo": "backRankMate",
    "mate_anastasia": "anastasiaMate",
    "mate_arabe": "arabianMate",
    "mate_boden": "bodenMate",
    "mate_coz": "smotheredMate",
    "mate_gancho": "hookMate",
    "mate_palomita": "dovetailMate",
    "mate_balestra": "balestraMate",
    "mate_cerdos_ciegos": "blindSwineMate",
    "mate_dos_alfiles": "doubleBishopMate",
    "mate_charreteras": "epauletteMate",
    "mate_greco": "grecoMate",
    "mate_caja_mortal": "killBoxMate",
    "mate_escalera": "lawnMowerMate",
    "mate_morphy": "morphyMate",
    "mate_opera": "operaMate",
    "mate_pillsbury": "pillsburyMate",
    "mate_sofocacion": "suffocationMate",
    "mate_vukovic": "vukovicMate",

    # Finales por Tipo de Pieza
    "final_peones": "pawnEndgame",
    "final_torres": "rookEndgame",
    "final_caballos": "knightEndgame",
    "final_alfiles": "bishopEndgame",
    "final_damas": "queenEndgame",
    "final_dama_torre": "queenRookEndgame",

    # Fases del Juego
    "apertura": "opening",
    "medio_juego": "middlegame",
    "final_juego": "endgame",
    "combinado": ""
}

def obtener_rango_elo(categoria, subnivel):
    cat = categoria.lower()
    sub = subnivel.upper()
    if cat in RANGOS_ELO and sub in RANGOS_ELO[cat]:
        return RANGOS_ELO[cat][sub]
    return (1200, 1400) # Rango por defecto

def buscar_ejercicios_db(elo_min, elo_max, tema_key, cantidad=4):
    tema_tag = MAPEO_TEMAS.get(tema_key.lower(), tema_key)
    
    conexion = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conexion.cursor()

    # Usamos CAST para convertir el texto a número durante la búsqueda
    query = '''
        SELECT "PuzzleId", "FEN", "Moves", "Rating", "Themes"
        FROM puzzles
        WHERE CAST("Rating" AS INTEGER) BETWEEN %s AND %s
        AND "Themes" LIKE %s
        ORDER BY "Popularity" DESC
        LIMIT %s
    '''
    parametros = [elo_min, elo_max, f"%{tema_tag}%", cantidad]
    cursor.execute(query, parametros)
    resultados = cursor.fetchall()
    conexion.close()

    return resultados

def buscar_ejercicios_apertura(elo_min, elo_max, opening_tag, fase_juego="todos", cantidad=6):
    conexion = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conexion.cursor()

    tag_busqueda = f"%{opening_tag}%"

    # Usamos CAST para convertir el texto a número durante la búsqueda
    query = '''
        SELECT "PuzzleId", "FEN", "Moves", "Rating", "Themes"
        FROM puzzles
        WHERE CAST("Rating" AS INTEGER) BETWEEN %s AND %s
        AND "OpeningTags" LIKE %s
    '''
    parametros = [elo_min, elo_max, tag_busqueda]

    if fase_juego != "todos":
        query += ' AND "Themes" LIKE %s'
        parametros.append(f"%{fase_juego}%")

    query += " ORDER BY RANDOM() LIMIT %s"
    parametros.append(cantidad)

    cursor.execute(query, parametros)
    resultados = cursor.fetchall()
    conexion.close()

    return resultados

def obtener_teoria_gemini(apertura_id, variante_id, categoria):
    """Conecta con Gemini para redactar la clase teórica en formato JSON"""
    nombre_apertura = apertura_id.replace("_", " ")
    nombre_variante = variante_id.replace("_", " ") if variante_id != "general" else "Líneas principales"
    
    prompt = f"""
    Eres el Maestro Legendario de Checkmate Lab. Analiza la apertura: '{nombre_apertura}' (Variante: '{nombre_variante}') para un alumno de nivel '{categoria}'.
    Responde ÚNICAMENTE con un JSON válido y estricto. Usa esta estructura exacta:
    {{
      "titulo_epico": "Título corto",
      "idea_principal": "Explicación de 2 oraciones.",
      "analisis_estrategico": "Explicación profunda de 1 párrafo.",
      "misiones_blancas": ["Plan blanco 1", "Plan blanco 2"],
      "misiones_negras": ["Plan negro 1", "Plan negro 2"],
      "alerta_de_trampa": "Aviso sobre error común.",
      "partida_modelo": "Ejemplo: Kasparov vs Karpov - Breve explicación."
    }}
    """
    try:
        model = genai.GenerativeModel('gemini-3.6-flash')
        respuesta = model.generate_content(prompt)
        
        texto_limpio = respuesta.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio[7:-3].strip()
        elif texto_limpio.startswith("```"):
            texto_limpio = texto_limpio[3:-3].strip()
            
        return json.loads(texto_limpio)
    except Exception as e:
        print(f"\n--- ERROR DE GEMINI --- \n{e}\n-----------------------\n")
        return {
            "titulo_epico": f"Estrategia en la {nombre_apertura}",
            "idea_principal": "Controlar el centro y desarrollar las piezas.",
            "analisis_estrategico": "Error de conexión con la IA. No se pudo generar el análisis profundo en este momento.",
            "misiones_blancas": ["Dominar el centro."],
            "misiones_negras": ["Luchar por el centro."],
            "alerta_de_trampa": "Revisa tu conexión a internet o los límites de la API de Gemini.",
            "partida_modelo": "No disponible sin conexión a la IA."
        }

def generar_pdf_apertura(teoria_json, ejercicios, alumno, categoria, apertura_nombre, archivo_salida="modulo_apertura.pdf"):
    """Dibuja el PDF de 3 páginas con la Teoría avanzada de Gemini y los ejercicios"""
    doc = SimpleDocTemplate(archivo_salida, pagesize=letter, rightMargin=15, leftMargin=15, topMargin=15, bottomMargin=15)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, leading=17, textColor=colors.HexColor('#1a365d'), spaceAfter=2)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.HexColor('#4a5568'), spaceAfter=15)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.black)
    epic_title = ParagraphStyle('EpicTitle', parent=styles['Heading2'], fontSize=16, textColor=colors.HexColor('#d4af37'), spaceAfter=10)
    mission_title = ParagraphStyle('MissionTitle', parent=styles['Heading3'], fontSize=12, textColor=colors.HexColor('#1a365d'), spaceAfter=6, spaceBefore=10)
    alert_style = ParagraphStyle('AlertStyle', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.white, backColor=colors.HexColor('#e53e3e'), borderPadding=10)
    label_style = ParagraphStyle('LabelStyle', parent=styles['Normal'], fontSize=10.5, leading=30, textColor=colors.HexColor('#2d3748'))

    story = []

    # ==================== PÁGINA 1: TEORÍA ====================
    story.append(Paragraph("<b>CHECKMATE LAB</b> — Módulo Teórico de Aperturas", title_style))
    story.append(Paragraph(f"<b>Alumno:</b> {alumno} | <b>Nivel:</b> {categoria.capitalize()} | <b>Apertura:</b> {apertura_nombre}", subtitle_style))
    
    story.append(Paragraph(teoria_json.get("titulo_epico", "La Batalla de la Apertura"), epic_title))
    story.append(Paragraph(f"<i>{teoria_json.get('idea_principal', '')}</i>", body_style))
    
    story.append(Paragraph("<b>Análisis Estratégico</b>", mission_title))
    story.append(Paragraph(teoria_json.get("analisis_estrategico", ""), body_style))
    
    story.append(Paragraph("<b>♟️ Partida Modelo Histórica</b>", mission_title))
    story.append(Paragraph(teoria_json.get("partida_modelo", ""), body_style))
    story.append(Spacer(1, 15))

    # Misiones (Tabla de dos columnas)
    misiones_b = [Paragraph(f"• {m}", body_style) for m in teoria_json.get("misiones_blancas", [])]
    misiones_n = [Paragraph(f"• {m}", body_style) for m in teoria_json.get("misiones_negras", [])]
    
    datos_misiones = [
        [Paragraph("<b>Misiones de las Blancas ♖</b>", mission_title), Paragraph("<b>Misiones de las Negras ♜</b>", mission_title)],
        [misiones_b, misiones_n]
    ]
    t_misiones = Table(datos_misiones, colWidths=[280, 280])
    t_misiones.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f7fafc')),
        ('BACKGROUND', (1,0), (1,-1), colors.HexColor('#edf2f7')),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_misiones)
    story.append(Spacer(1, 20))

    # Alerta
    story.append(Paragraph(f"<b>⚠️ ALERTA DE TRAMPA:</b> {teoria_json.get('alerta_de_trampa', '')}", alert_style))
    
    # ==================== PÁGINA 2: EJERCICIOS ====================
    story.append(PageBreak())
    story.append(Paragraph("<b>CHECKMATE LAB</b> — Hoja de Ejercicios", title_style))
    story.append(Paragraph(f"<b>Aplica la teoría de:</b> {apertura_nombre}", subtitle_style))

    tabla_filas_p1 = []
    for i in range(0, len(ejercicios), 2):
        fila_par = []
        for j in range(2):
            if i + j < len(ejercicios):
                ej = ejercicios[i + j]
                txt_info = f"<b>#{i+j+1}</b> ({ej['turno']})<br/><br/>1. ______________________<br/>2. ______________________<br/>3. ______________________"
                mini_tabla = Table([[ej['drawing'], Paragraph(txt_info, label_style)]], colWidths=[140, 145])
                mini_tabla.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 1), ('RIGHTPADDING', (0,0), (-1,-1), 1)]))
                fila_par.append(mini_tabla)
            else:
                fila_par.append("")
        tabla_filas_p1.append(fila_par)

    if tabla_filas_p1:
        t1 = Table(tabla_filas_p1, colWidths=[287, 287])
        t1.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        story.append(t1)
    else:
        story.append(Paragraph("<i>No se encontraron ejercicios tácticos.</i>", body_style))

    # ==================== PÁGINA 3: SOLUCIONARIO ====================
    story.append(PageBreak())
    story.append(Paragraph("<b>CHECKMATE LAB</b> — Solucionario", title_style))
    story.append(Spacer(1, 10))

    tabla_filas_p2 = []
    for i in range(0, len(ejercicios), 2):
        fila_par = []
        for j in range(2):
            if i + j < len(ejercicios):
                ej = ejercicios[i + j]
                txt_sol = f"<b>#{i+j+1}</b> ({ej['turno']})<br/><br/><b>Sol:</b> {ej['solucion']}"
                mini_tabla = Table([[ej['drawing'], Paragraph(txt_sol, label_style)]], colWidths=[140, 145])
                mini_tabla.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 1), ('RIGHTPADDING', (0,0), (-1,-1), 1)]))
                fila_par.append(mini_tabla)
            else:
                fila_par.append("")
        tabla_filas_p2.append(fila_par)

    if tabla_filas_p2:
        t2 = Table(tabla_filas_p2, colWidths=[287, 287])
        t2.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        story.append(t2)

    doc.build(story)

def procesar_ejercicio(puzzle_raw, nivel_texto, tema_texto):
    puzzle_id, fen_inicial, moves_str, rating, themes = puzzle_raw
    
    board = chess.Board(fen_inicial)
    moves_list = moves_str.split()
    
    # Aplicar la jugada del oponente para llegar a la posición del ejercicio
    opponent_move = chess.Move.from_uci(moves_list[0])
    board.push(opponent_move)
    
    # Calcular solución en notación algebraica (SAN) y traducir al español (D, T, A, C, R)
    temp_board = board.copy()
    solucion_san = []
    traduccion_piezas = {'K': 'R', 'Q': 'D', 'R': 'T', 'B': 'A', 'N': 'C'}
    
    for m in moves_list[1:]:
        move_obj = chess.Move.from_uci(m)
        san_en = temp_board.san(move_obj)
        san_es = "".join(traduccion_piezas.get(c, c) for c in san_en)
        solucion_san.append(san_es)
        temp_board.push(move_obj)
    
    solucion_texto = " ".join(solucion_san)
    turno_jugador = "Blancas" if board.turn == chess.WHITE else "Negras"
    
    # Generar la imagen vectorial (SVG) del tablero con orientación adecuada
    svg_data = chess.svg.board(board=board, orientation=board.turn, size=150)
    drawing = svg2rlg(io.StringIO(svg_data))

    # Consultar a Gemini para la pista y la explicación pedagógica
    prompt = f"""
    Eres un profesor experto de ajedrez en Checkmate Lab.
    Analiza este ejercicio para un alumno de nivel '{nivel_texto}' sobre el tema '{tema_texto}':
    - Posición FEN actual: {board.fen()}
    - Mueven: {turno_jugador}
    - Secuencia correcta: {solucion_texto}

    Responde ÚNICAMENTE en formato JSON estricto sin bloques ```json ni texto adicional:
    {{
      "pista": "Corta",
      "explicacion": "Una explicación didáctica ultra-corta de máximo 12 palabras sobre la idea táctica."
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-3.6-flash')
        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        if text_resp.startswith("```"):
            text_resp = text_resp.split("\n", 1)[1].rsplit("\n", 1)[0]
        data_ai = json.loads(text_resp)
        pista = data_ai.get("pista", "Encuentra el mejor movimiento.")
        explicacion = data_ai.get("explicacion", f"La jugada correcta es {solucion_texto}.")
    except Exception as e:
        pista = "Pon atención a las piezas desprotegidas y combinaciones."
        explicacion = f"La secuencia ganadora es: {solucion_texto}."

    return {
        "id": puzzle_id,
        "drawing": drawing,
        "turno": turno_jugador,
        "pista": pista,
        "solucion": solucion_texto,
        "explicacion": explicacion
    }

def generar_pdf_hojas(ejercicios, alumno, categoria, subnivel, tema, archivo_salida="ejercicios_alumno.pdf"):
    doc = SimpleDocTemplate(archivo_salida, pagesize=letter, rightMargin=15, leftMargin=15, topMargin=15, bottomMargin=15)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, leading=17, textColor=colors.HexColor('#1a365d'), spaceAfter=2)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.HexColor('#4a5568'), spaceAfter=4)
    label_style = ParagraphStyle('LabelStyle', parent=styles['Normal'], fontSize=8.5, leading=12, textColor=colors.HexColor('#2d3748'))

    story = []

    # ==================== PÁGINA 1: HOJA DEL ALUMNO ====================
    story.append(Paragraph("<b>CHECKMATE LAB</b> — Hoja de Ejercicios", title_style))
    story.append(Paragraph(f"<b>Alumno:</b> {alumno} | <b>Nivel:</b> {categoria.capitalize()} {subnivel.upper()} | <b>Tema:</b> {tema.capitalize()}", subtitle_style))

    tabla_filas_p1 = []
    for i in range(0, len(ejercicios), 2):
        fila_par = []
        for j in range(2):
            if i + j < len(ejercicios):
                ej = ejercicios[i + j]
                txt_info = f"<b>#{i+j+1}</b> ({ej['turno']})<br/><br/>" \
                           f"1. ___________________<br/>" \
                           f"2. ___________________<br/>" \
                           f"3. ___________________<br/>" \
                           f"4. ___________________<br/>" \
                           f"5. ___________________"
                
                mini_tabla = Table(
                    [[ej['drawing'], Paragraph(txt_info, label_style)]],
                    colWidths=[142, 145] # El 142 jala el texto hacia la izquierda
                )
                mini_tabla.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('LEFTPADDING', (0,0), (-1,-1), 1),
                    ('RIGHTPADDING', (0,0), (-1,-1), 1),
                    ('TOPPADDING', (0,0), (-1,-1), 0),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ]))
                fila_par.append(mini_tabla)
            else:
                fila_par.append("")
        tabla_filas_p1.append(fila_par)

    t1 = Table(tabla_filas_p1, colWidths=[287, 287])
    t1.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),     # Más espacio vertical
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),  # Más espacio vertical
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(t1)

    # ==================== PÁGINA 2: SOLUCIONARIO (PROFESOR) ====================
    story.append(PageBreak())
    story.append(Paragraph("<b>CHECKMATE LAB</b> — Solucionario y Explicación", title_style))
    story.append(Paragraph(f"<b>Respuestas para:</b> {alumno} | <b>Nivel:</b> {categoria.capitalize()} {subnivel.upper()} | <b>Tema:</b> {tema.capitalize()}", subtitle_style))

    tabla_filas_p2 = []
    for i in range(0, len(ejercicios), 2):
        fila_par = []
        for j in range(2):
            if i + j < len(ejercicios):
                ej = ejercicios[i + j]
                txt_sol = f"<b>#{i+j+1}</b> ({ej['turno']})<br/><br/>" \
                          f"<b>Sol:</b> {ej['solucion']}"
                
                mini_tabla = Table(
                    [[ej['drawing'], Paragraph(txt_sol, label_style)]],
                    colWidths=[142, 145]
                )
                mini_tabla.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('LEFTPADDING', (0,0), (-1,-1), 1),
                    ('RIGHTPADDING', (0,0), (-1,-1), 1),
                    ('TOPPADDING', (0,0), (-1,-1), 0),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ]))
                fila_par.append(mini_tabla)
            else:
                fila_par.append("")
        tabla_filas_p2.append(fila_par)

    t2 = Table(tabla_filas_p2, colWidths=[287, 287])
    t2.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(t2)

    doc.build(story)
    print(f"✓ PDF generado exitosamente: {archivo_salida}")

# 3. Función Principal de Prueba
if __name__ == '__main__':
    # Configuración de prueba:
    NOMBRE_ALUMNO = "Carlos Ruiz"
    CATEGORIA = "intermedio"
    SUBNIVEL = "IV"
    TEMA = "celada"

    elo_min, elo_max = obtener_rango_elo(CATEGORIA, SUBNIVEL)
    print(f"Buscando ejercicios para Nivel {CATEGORIA.capitalize()} {SUBNIVEL} (ELO {elo_min}-{elo_max}) sobre '{TEMA}'...")
    
    puzzles_raw = buscar_ejercicios_db(elo_min, elo_max, TEMA, cantidad=4)
    
    print(f"Se encontraron {len(puzzles_raw)} ejercicios. Procesando con Gemini...")
    if len(puzzles_raw) == 0:
        print("❌ No se encontraron ejercicios con esas opciones. Verifica la base de datos o cambia el tema.")
        exit()
    ejercicios_procesados = []
    for p in puzzles_raw:
        ej_proc = procesar_ejercicio(p, f"{CATEGORIA.capitalize()} {SUBNIVEL}", TEMA)
        ejercicios_procesados.append(ej_proc)

    print("Generando el PDF de 2 páginas...")
    generar_pdf_hojas(ejercicios_procesados, NOMBRE_ALUMNO, CATEGORIA, SUBNIVEL, TEMA, "ejercicios_alumno.pdf")
