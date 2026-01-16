
import arcpy

# Carregar a camada da estrada (supondo que esteja em um arquivo de shapefile chamado "estradas.shp")
estradas_camada = "estradas.shp"

# Definir o buffer
distancia_buffer = 500  # em metros

# Executar a ferramenta Buffer
arcpy.Buffer_analysis(estradas_camada, "estradas_buffer.shp", distancia_buffer)

print("Buffer de 500 metros criado com sucesso!")
