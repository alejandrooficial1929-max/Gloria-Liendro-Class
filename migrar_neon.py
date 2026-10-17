import pandas as pd
from sqlalchemy import create_engine, inspect
import os
from dotenv import load_dotenv

# Cargar las variables del .env
load_dotenv()

print("Configurando conexiones...")
# Obtener la URL y adaptarla para el motor de migración
url_neon = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+psycopg2://")

# Conectar a la base local (SQLite) y a la nube (Neon)
motor_local = create_engine('sqlite:///data/puzzles.db')
motor_neon = create_engine(url_neon)

# Detectar automáticamente el nombre de tu tabla en SQLite
inspector = inspect(motor_local)
tabla_nombre = inspector.get_table_names()[0]

print(f"Iniciando la transferencia de la tabla '{tabla_nombre}'...")
print("Esto puede tardar varios minutos dependiendo de tu internet. No cierres la terminal.")

bloque_num = 1
# Leer de SQLite y enviar a Postgres en paquetes de 50,000 para no saturar la memoria
for bloque in pd.read_sql(f"SELECT * FROM {tabla_nombre}", motor_local, chunksize=50000):
    print(f"Subiendo paquete {bloque_num} (50,000 ejercicios)...")
    bloque.to_sql(tabla_nombre, motor_neon, if_exists='append', index=False)
    bloque_num += 1

print("¡Base de datos migrada a la nube exitosamente!")