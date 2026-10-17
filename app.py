import os
os.makedirs('data', exist_ok=True)
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

# Importamos las funciones de búsqueda y generación creadas en main.py
from main import obtener_rango_elo, buscar_ejercicios_db, procesar_ejercicio, generar_pdf_hojas, buscar_ejercicios_apertura, obtener_teoria_gemini, generar_pdf_apertura

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def ver_formulario(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/generar-pdf")
async def crear_pdf_web(
    alumno: str = Form(...),
    categoria: str = Form(...),
    subnivel: str = Form(...),
    tema: str = Form(...),
    cantidad: int = Form(...)
):
    elo_min, elo_max = obtener_rango_elo(categoria, subnivel)
    puzzles_raw = buscar_ejercicios_db(elo_min, elo_max, tema, cantidad=cantidad)
    
    if not puzzles_raw:
        return {"error": "No se encontraron ejercicios para esa combinación."}

    ejercicios_procesados = []
    for p in puzzles_raw:
        ej_proc = procesar_ejercicio(p, f"{categoria.capitalize()} {subnivel}", tema)
        ejercicios_procesados.append(ej_proc)

    nombre_archivo = f"ejercicios_{alumno.replace(' ', '_')}.pdf"
    ruta_pdf = os.path.join("data", nombre_archivo)
    
    generar_pdf_hojas(ejercicios_procesados, alumno, categoria, subnivel, tema, ruta_pdf)

    return FileResponse(
        path=ruta_pdf, 
        filename=nombre_archivo, 
        media_type='application/pdf'
    )

@app.post("/generar-modulo")
async def crear_modulo_teorico(
    alumno: str = Form(...),
    categoria: str = Form(...),
    fase_juego: str = Form(...),
    familia_apertura: str = Form(...),
    variante_apertura: str = Form(...)
):
    # 1. Definimos el término de búsqueda para la base de datos y el título
    tag_busqueda = variante_apertura if variante_apertura != "general" else familia_apertura
    nombre_apertura = tag_busqueda.replace("_", " ")

    # 2. Obtenemos la teoría pedagógica desde Gemini AI
    print("Conectando con Gemini...")
    teoria_json = obtener_teoria_gemini(familia_apertura, variante_apertura, categoria)
    
    # 3. Buscamos ejercicios tácticos de esta apertura en Lichess
    print("Buscando ejercicios en la base de datos...")
    elo_min, elo_max = obtener_rango_elo(categoria, "I") # Dificultad base de la categoría
    puzzles_raw = buscar_ejercicios_apertura(elo_min, elo_max, tag_busqueda, fase_juego, cantidad=6)
    
    # 4. Convertimos los ejercicios a imágenes SVG y notación en español
    ejercicios_procesados = []
    for p in puzzles_raw:
        ej_proc = procesar_ejercicio(p, f"{categoria.capitalize()}", "Apertura")
        ejercicios_procesados.append(ej_proc)
        
    # 5. Generamos el PDF final con la Teoría + Ejercicios
    print("Generando PDF...")
    nombre_archivo = f"modulo_{alumno.replace(' ', '_')}.pdf"
    ruta_pdf = os.path.join("data", nombre_archivo)
    
    generar_pdf_apertura(teoria_json, ejercicios_procesados, alumno, categoria, nombre_apertura, ruta_pdf)

    # 6. Descargamos el archivo al navegador del usuario
    return FileResponse(
        path=ruta_pdf, 
        filename=nombre_archivo, 
        media_type='application/pdf'
    )