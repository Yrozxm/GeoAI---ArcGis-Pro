
import arcpy

# Defina a camada do Funchal
funchal_layer = "Funchal"

# Defina o buffer
buffer_distance = 800  # em metros

# Crie o buffer
arcpy.Buffer_analysis(funchal_layer, "Funchal_Buffer", buffer_distance, "FULL", "ROUND", "NONE", "")

print("Buffer criado com sucesso!")
