import arcpy

# Definir camada do Funchal
funchal_camada = "Funchal.shp"

# Definir distancia do buffer (600m)
buffer_distancia = 600

# Criar buffer
arcpy.Buffer_analysis(funchal_camada, "Funchal_Buffer.shp", str(buffer_distancia) + " Meters")

print("Buffer criado com sucesso!")