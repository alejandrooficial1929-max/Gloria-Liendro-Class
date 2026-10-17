import os
import urllib.request
import sqlite3
import csv
import zstandard as zstd

# Definición de rutas
DATA_DIR = 'data'
DB_PATH = os.path.join(DATA_DIR, 'puzzles.db')
CSV_ZST_PATH = os.path.join(DATA_DIR, 'lichess_db_puzzle.csv.zst')
CSV_PATH = os.path.join(DATA_DIR, 'lichess_db_puzzle.csv')
LICHESS_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

def preparar_base_datos():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if os.path.exists(DB_PATH):
        print("✓ La base de datos ya existe y está lista para usarse.")
        return

    print("--- INICIANDO CONFIGURACIÓN DE BASE DE DATOS ---")

    if not os.path.exists(CSV_ZST_PATH) and not os.path.exists(CSV_PATH):
        print("1/4 Descargando base de datos de Lichess (~250MB)... Por favor espera.")
        urllib.request.urlretrieve(LICHESS_URL, CSV_ZST_PATH)
        print("✓ Descarga completada.")

    if not os.path.exists(CSV_PATH):
        print("2/4 Descomprimiendo archivo...")
        dctx = zstd.ZstdDecompressor()
        with open(CSV_ZST_PATH, 'rb') as ifh, open(CSV_PATH, 'wb') as ofh:
            dctx.copy_stream(ifh, ofh)
        print("✓ Descompresión completada.")

    print("3/4 Creando base de datos SQLite...")
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS puzzles (
            PuzzleId TEXT PRIMARY KEY,
            FEN TEXT,
            Moves TEXT,
            Rating INTEGER,
            RatingDeviation INTEGER,
            Popularity INTEGER,
            NbPlays INTEGER,
            Themes TEXT,
            GameUrl TEXT,
            OpeningTags TEXT
        )
    ''')
    
    print("4/4 Importando ejercicios... (Esto puede tomar entre 1 y 3 minutos)")
    with open(CSV_PATH, 'r', encoding='utf-8') as archivo_csv:
        lector_csv = csv.reader(archivo_csv)
        bloque = []
        for contador, fila in enumerate(lector_csv, 1):
            bloque.append(fila[:10])
            if len(bloque) == 100000:
                cursor.executemany('INSERT OR IGNORE INTO puzzles VALUES (?,?,?,?,?,?,?,?,?,?)', bloque)
                bloque = []
                print(f"   -> {contador} ejercicios procesados...")
        if bloque:
            cursor.executemany('INSERT OR IGNORE INTO puzzles VALUES (?,?,?,?,?,?,?,?,?,?)', bloque)

    print("Creando índice de búsqueda por ELO (Rating)...")
    cursor.execute('CREATE INDEX idx_rating ON puzzles (Rating);')
    conexion.commit()
    conexion.close()

    # Limpieza de archivos pesados temporales
    print("Limpiando archivos temporales...")
    if os.path.exists(CSV_PATH): os.remove(CSV_PATH)
    if os.path.exists(CSV_ZST_PATH): os.remove(CSV_ZST_PATH)

    print("--- ¡PROCESO COMPLETADO CON ÉXITO! ---")
    print(f"Base de datos guardada en: {DB_PATH}")

if __name__ == '__main__':
    preparar_base_datos()