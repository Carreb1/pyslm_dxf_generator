import os, pathlib, ezdxf
import pyslm, pyslm.visualise
from pyslm import hatching
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
import sys
import logging # Mova esta importação para o topo, se não estiver lá

# Configura o logger do ezdxf para suprimir avisos, mantendo a saída limpa.
# Isso evita poluir o console com mensagens que não são erros críticos.
logging.getLogger('ezdxf').setLevel(logging.ERROR)

# -------------------- paths --------------------
# Definir o caminho base para a pasta de modelos
base_models_path = "models\original\suporte"
# Definir o caminho base para a pasta de saída DXF
base_dxfs_path = "Final_pipeline\dxfs"

# Verificar se o nome do modelo foi fornecido como argumento de linha de comando
if len(sys.argv) > 1:
    model_name = sys.argv[1] # O nome do modelo é o primeiro argumento
else:
    # Fallback ou erro se nenhum nome de modelo for fornecido
    print("Erro: Por favor, forneça o nome do modelo como argumento (ex: python script.py NomeDoModelo)")
    sys.exit(1) # Sai do script com um erro

# Constrói o caminho completo para o arquivo STL de entrada
stl_path = pathlib.Path(base_models_path) / f"{model_name}.stl"
stl_name = model_name # O nome da peça é o nome do modelo fornecido

# Define o diretório de saída para os arquivos DXF com base no nome do modelo
# Ele criará a pasta "dxfs\{nome}\dxf_bruto"
out_root = pathlib.Path(base_dxfs_path) / stl_name / "dxf_bruto"
out_root.mkdir(parents=True, exist_ok=True) # Cria o diretório se não existir

# -------------------- part & hatcher -----------
part = pyslm.Part("inversePyramid")
part.setGeometry(str(stl_path)) # Convertendo o objeto Path para string
part.origin[0], part.origin[1] = 5.0, 2.5 # x, y. Aparentemente também funciona part.origin = [x, y]
part.rotation, part.scaleFactor = [0,0,0], 1.0
part.dropToPlatform()

h = hatching.Hatcher()
h.hatchAngle = 10
h.volumeOffsetHatch = 0.08
h.spotCompensation  = 0.06
h.stripeWidth       = 0.07
h.numInnerContours  = 2
h.numOuterContours  = 1
h.hatchSortMethod   = hatching.AlternateSort()

layer_thickness = 0.03  # mm
layers = []

def export_layer_to_dxf(layer, path):
    """Convert PySLM Layer → ezdxf file."""
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    # --- contours as closed polylines
    for geom in layer.getContourGeometry():
        pts = [tuple(p) for p in geom.coords]
        msp.add_lwpolyline(pts, close=True)

    # --- hatches as individual LINE entities
    for geom in layer.getHatchGeometry():
        coords = geom.coords
        for i in range(0, len(coords), 2):
            start, end = map(tuple, coords[i:i+2])
            msp.add_line(start, end)

    # --- points as small circles (optional)
    for geom in layer.getPointsGeometry():
        for p in geom.coords:
            msp.add_circle(tuple(p), radius=0.02)

    doc.saveas(path)

print("Hatching & DXF export …")
for z in tqdm(np.arange(0, part.boundingBox[5], layer_thickness)):
    h.hatchAngle += 66.7
    slice_geom   = part.getVectorSlice(z)
    layer        = h.hatch(slice_geom)
    layer.z      = int(z*1000)          # μm integer
    layers.append(layer)

    dxf_name = out_root / f"layer_{layer.z}.dxf"
    export_layer_to_dxf(layer, dxf_name)

print(f"DXF written to {out_root}")
# --- optional preview every 10th layer
pyslm.visualise.plotLayers(layers[::10])
plt.show()