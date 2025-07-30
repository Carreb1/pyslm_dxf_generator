"""
Script de Geração de Suporte e Exportação DXF:
Gera estruturas de suporte para um modelo STL, fatia a peça e os suportes em camadas 2D,
e exporta cada camada para um arquivo DXF para fabricação aditiva.
"""

import numpy as np
import logging
import os
from tqdm import tqdm
import pathlib
import ezdxf
import sys
import datetime 

from matplotlib import pyplot as plt
from pyslm.core import Part
import pyslm.support

import trimesh
import trimesh.creation

import pyslm, pyslm.visualise
from pyslm import hatching
from pyslm.geometry import Layer, ContourGeometry, HatchGeometry, PointsGeometry

"""
Configuração de Logging:
Define o nível de logging para o script e silencia mensagens INFO do ezdxf para evitar verbosidade excessiva.
"""
# vispy.set_log_level('debug') # Descomente para depuração OpenGL
logging.getLogger().setLevel(logging.INFO)
logging.getLogger('ezdxf').setLevel(logging.WARNING) # Silencia mensagens INFO do ezdxf

## CONSTANTES ####
OVERHANG_ANGLE = 55  # [deg] - Ângulo de balanço. Reduza para suportar regiões mais curvas (e.g., para 45 ou 30).

# -------------------- paths --------------------
# Definir o caminho base para a pasta de modelos
base_models_path = r"C:\Users\ckubota\Desktop\IPT\Final_pipeline\models\original\Peca"
# Definir o caminho base para a pasta de saída DXF
base_dxfs_path = r"C:\Users\ckubota\Desktop\IPT\Final_pipeline\dxfs"

# Verificar se o nome do modelo foi fornecido como argumento de linha de comando
if len(sys.argv) > 1:
    model_name = sys.argv[1] # O nome do modelo é o primeiro argumento
else:
    # Fallback ou erro se nenhum nome de modelo for fornecido
    print("Erro: Por favor, forneça o nome do modelo como argumento (ex: python script.py NomeDoModelo)")
    sys.exit(1) # Sai do script com um erro

# Constrói o caminho completo para o arquivo STL de entrada
original_file_path = pathlib.Path(base_models_path) / f"{model_name}.stl"

# Define o diretório de saída para os arquivos DXF com base no nome do modelo
# Este será o seu output para "dxfs\{nome}\dxf_bruto"
output_dxf_folder = pathlib.Path(base_dxfs_path) / model_name / "dxf_bruto"
current_datetime = datetime.datetime.now().strftime("%d%m%Y%H%M")
out_root = pathlib.Path(base_dxfs_path) / f"{model_name}_{current_datetime}" / "dxf_bruto"
out_root.mkdir(parents=True, exist_ok=True) # Cria o diretório se não existir
print(f"Arquivos DXF serão gravados em {out_root}")


"""
Configuração da Peça:
Carrega o modelo STL, aplica rotação e escala, e posiciona a peça na plataforma de construção.
"""
myPart = Part('Peca')
myPart.setGeometry(str(original_file_path), fixGeometry=True)
myPart.rotation = [1, 0, 0]  # Rotação da peça no espaço 3D
myPart.scaleFactor = 1.0      # Fator de escala da peça
myPart.dropToPlatform(10)     # A peça é deslocada para 10mm acima da plataforma.

"""
Extração da Malha de Balanço:
Identifica e extrai a geometria da peça que excede o ângulo de balanço especificado.
Esta malha é usada para visualizar as áreas que requerem suporte.
"""
overhangMesh = pyslm.support.getOverhangMesh(myPart, OVERHANG_ANGLE,
                                            splitMesh=False, useConnectivity=True)
overhangMesh.visual.face_colors = [254.0, 0., 0., 254] # Define a cor da malha de balanço para visualização

"""
Geração Inicial de Suportes (Pontos e Bordas):
Detecta pontos e bordas em balanço na peça, que servem como base para a geração de suportes mais complexos.
"""
pointOverhangs = pyslm.support.BaseSupportGenerator.findOverhangPoints(myPart)
overhangEdges = pyslm.support.BaseSupportGenerator.findOverhangEdges(myPart)

print(f"Número de pontos de balanço: {len(pointOverhangs)}")
print(f"Número de bordas de balanço: {len(overhangEdges)}")

"""
Configuração do Gerador de Suportes de Bloco em Grade:
Inicializa e configura o gerador de suportes. Este gerador cria estruturas de suporte tipo treliça.
Os parâmetros são ajustados para controlar a densidade, forma e interface dos suportes com a peça.
"""
supportGenerator = pyslm.support.GridBlockSupportGenerator()
supportGenerator.rayProjectionResolution = 0.03  # [mm] - Resolução da grade para projeção de raios
supportGenerator.innerSupportEdgeGap = 0.1       # [mm] - Offset interno entre suportes adjacentes
supportGenerator.outerSupportEdgeGap = 0.1       # [mm] - Offset externo para limites de regiões de balanço
supportGenerator.minimumAreaThreshold = 0.001    # [mm^2] - Área mínima para processar uma região de suporte
supportGenerator.triangulationSpacing = 1.0      # [mm^2] - Espaçamento interno para triangulação da malha de volume
supportGenerator.simplifyPolygonFactor = 0.5     # Fator para simplificar a forma geral do suporte
supportGenerator.supportBorderDistance = 1.0     # [mm]
supportGenerator.numSkinMeshSubdivideIterations = 2 # Iterações de subdivisão da malha da "pele" do suporte

# Parâmetros dos dentes de suporte (conexão entre suporte e peça)
supportGenerator.useUpperSupportTeeth = True
supportGenerator.useLowerSupportTeeth = True
supportGenerator.supportWallThickness = 1.0          # [mm] - Espessura das paredes de suporte para fortalecer dentes
supportGenerator.supportTeethTopLength = 0.1         # [mm] - Comprimento da aba dos dentes de suporte
supportGenerator.supportTeethHeight = 1.5            # [mm] - Altura dos dentes de suporte
supportGenerator.supportTeethBaseInterval = 1.5      # [mm] - Intervalo entre os dentes de suporte na base
supportGenerator.supportTeethUpperPenetration = 0.2  # [mm] - Penetração dos dentes na peça

supportGenerator.splineSimplificationFactor = 10 # Fator de suavização de spline para limites de suporte
supportGenerator.gridSpacing = [2.5, 2.5]            # [mm] - Espaçamento da grade interna dos suportes

"""
Geração das Regiões de Suporte de Bloco:
Identifica as áreas onde os suportes serão colocados e gera os volumes iniciais de suporte.
"""
supportBlockRegions = supportGenerator.identifySupportRegions(myPart, OVERHANG_ANGLE, True)

for block in supportBlockRegions:
    block.trussWidth = 1.0

blockSupports = [block.supportVolume for block in supportBlockRegions]

"""
Visualização da Geometria de Suporte (Pontos e Bordas - Opcional):
Esta seção gera e exibe visualizações das bordas e pontos que requerem suporte.
É útil para depuração e para entender as áreas de aplicação dos suportes.
"""
if overhangEdges:
    meshVerts = myPart.geometry.vertices
    edgeRays = np.vstack([meshVerts[edge] for edge in overhangEdges])
    visualize_support_edges = trimesh.load_path((edgeRays).reshape(-1, 2, 3))

    edge_supports = []
    for edge in overhangEdges:
        coords = np.vstack([meshVerts[edge, :]] * 2)
        coords[2:, 2] = 0.0
        extrudeFace = np.array([(0, 1, 3), (3, 2, 0)])
        edge_supports.append(trimesh.Trimesh(vertices=coords, faces=extrudeFace))

    point_supports = []
    cylinder_rad = 0.5 # mm
    for pnt in pointOverhangs:
        coords = np.zeros((2, 3))
        coords[:, :] = meshVerts[pnt]
        coords[1, 2] = 0.0
        point_supports += trimesh.creation.cylinder(radius=cylinder_rad, segment=coords)

    rays = np.hstack([meshVerts[pointOverhangs]] * 2).reshape(-1, 2, 3)
    rays[:, 1, 2] = 0.0
    visualize_support_pnts = trimesh.load_path(rays)
else:
    print("Nenhuma borda de balanço encontrada. Ajuste a rotação da peça ou o ângulo de balanço.")

# Torna a parte principal transparente para melhor visualização dos suportes
myPart.geometry.visual.vertex_colors = [80, 80, 80, 125]

"""
Visualização e Exportação da Geometria de Suporte (GLB):
Cria uma cena 3D com a peça e os volumes de suporte.
Exporta esta cena para um arquivo GLB para visualização externa e depuração.
"""
s1 = trimesh.Scene([myPart.geometry] + blockSupports)
with open('overhangSupport.glb', 'wb') as f:
    f.write(trimesh.exchange.gltf.export_glb(s1, include_normals=True))

"""
Exibição do Volume Bruto do Bloco de Suporte (Opcional):
Permite visualizar os volumes de suporte intermediários antes da geração da estrutura de treliça.
"""
DISPLAY_BLOCK_VOLUME = True # Definir para True para depuração

if DISPLAY_BLOCK_VOLUME:
    s2 = trimesh.Scene([myPart.geometry, overhangMesh, blockSupports])
    # s2.show() # Descomente para exibir esta visualização

"""
Geração da Malha Final dos Suportes (Estrutura de Treliça):
Transforma os volumes de suporte de bloco em malhas com uma estrutura interna de treliça,
conforme definido pelos parâmetros do `GridBlockSupportGenerator`.
"""
meshSupports = []
for supportBlock in supportBlockRegions:
    supportBlock.mergeMesh = False      # Não mescla a malha do bloco com outras
    supportBlock.useSupportSkin = True  # Usa uma "pele" para o suporte
    meshSupports.append(supportBlock.geometry()) # Gera a geometria da treliça

"""
Visualização Final da Peça e Suportes de Malha:
Exibe a cena completa com a malha de balanço, a peça original e as estruturas de suporte de treliça finalizadas.
"""
s2 = trimesh.Scene([overhangMesh, myPart.geometry] + meshSupports)
s2.show()

# --- Função para Exportar Camada para DXF ---
def export_layer_to_dxf(layer, path):
    """
    Converte um objeto PySLM Layer para um arquivo DXF usando a biblioteca ezdxf.
    Desenha contornos como polilinhas fechadas, hachuras como linhas individuais e pontos como círculos.
    """
    doc = ezdxf.new(dxfversion="R2010") # Cria um novo documento DXF
    msp = doc.modelspace()              # Acessa o espaço do modelo

    # Adiciona contornos como polilinhas fechadas
    for geom in layer.getContourGeometry():
        pts = [tuple(p) for p in geom.coords]
        msp.add_lwpolyline(pts, close=True)

    # Adiciona hachuras como entidades de linha individuais
    for geom in layer.getHatchGeometry():
        coords = geom.coords
        for i in range(0, len(coords), 2):
            start, end = map(tuple, coords[i:i+2])
            msp.add_line(start, end)

    # Adiciona pontos como pequenos círculos (opcional)
    for geom in layer.getPointsGeometry():
        for p in geom.coords:
            msp.add_circle(tuple(p), radius=0.02)

    doc.saveas(path) # Salva o documento DXF no caminho especificado

"""
Processo de Fatiamento e Geração de Camadas DXF:
Itera através da altura total da peça e dos suportes, fatiando ambos em camadas finas.
Cada camada é processada para gerar contornos e hachuras (para a peça) e hachuras/contornos (para os suportes).
As geometrias de peça e suporte são combinadas em uma única `Layer` PySLM, que é então exportada para um arquivo DXF.
"""
# Determina os limites Z mínimos e máximos para o fatiamento, cobrindo peça e suportes
if meshSupports:
    support_combined_mesh = trimesh.util.concatenate(meshSupports)
    min_z_support = support_combined_mesh.bounds[0, 2]
    max_z_support = support_combined_mesh.bounds[1, 2]
else:
    # Se não houver suportes, usa os limites Z da peça
    min_z_support = myPart.boundingBox[2]
    max_z_support = myPart.boundingBox[5]

min_z_overall = min(myPart.boundingBox[2], min_z_support)
max_z_overall = max(myPart.boundingBox[5], max_z_support)

layer_thickness = 0.03  # [mm] - Espessura de cada camada fatiada
all_layers_combined = [] # Lista para armazenar todas as camadas geradas

# Inicializa o hachurador para a peça
h = hatching.Hatcher()
h.hatchAngle = 10
h.volumeOffsetHatch = 0.08
h.spotCompensation = 0.06
h.stripeWidth = 0.07
h.numInnerContours = 2
h.numOuterContours = 1
h.hatchSortMethod = hatching.AlternateSort()

print("Fatiando e processando camadas da peça e dos suportes…")
layer_idx = 0 # Índice da camada para nomear os arquivos DXF
# Itera sobre as posições Z para criar cada camada
for zPos in tqdm(np.arange(min_z_overall, max_z_overall + layer_thickness, layer_thickness)):

    current_layer = Layer()                 # Cria uma nova camada para a posição Z atual
    current_layer.z = int(zPos * 1000)      # Armazena a posição Z em micrômetros

    # --- Fatiamento e Hachura da Peça ---
    h.hatchAngle += 66.7 # Ajusta o ângulo de hachura para a próxima camada da peça
    slice_geom_part = myPart.getVectorSlice(zPos) # Obtém o slice vetorial da peça na Z atual

    if slice_geom_part: # Apenas processa se houver geometria da peça nesta camada
        layer_hatch_part = h.hatch(slice_geom_part) # Aplica hachura à geometria da peça
        for geom in layer_hatch_part.geometry:
            current_layer.geometry.append(geom) # Adiciona a geometria hachurada da peça à camada combinada

    # --- Fatiamento e Hachura dos Suportes ---
    innerHatchPaths_support, boundaryPaths_support = pyslm.support.GridBlockSupport.slice(meshSupports, zPos)

    # Processa os caminhos de hachura internos dos suportes
    if innerHatchPaths_support:
        gridCoords_support = pyslm.hatching.simplifyBoundaries(innerHatchPaths_support, 0.1)
        for coords in gridCoords_support:
            hatchGeom = HatchGeometry() # Usa HatchGeometry para hachuras internas
            hatchGeom.coords = coords.reshape(-1, 2)
            current_layer.geometry.append(hatchGeom)

    # Processa os caminhos de contorno dos suportes
    if boundaryPaths_support:
        boundaryCoords_support = pyslm.hatching.simplifyBoundaries(boundaryPaths_support, 0.1)
        for coords in boundaryCoords_support:
            layerGeom = ContourGeometry() # Usa ContourGeometry para contornos
            if hasattr(coords, 'exterior') and hasattr(coords.exterior, 'coords'):
                 # Remove o ponto de fechamento duplicado se for um polígono shapely
                 layerGeom.coords = np.array(coords.exterior.coords)[:-1].reshape(-1, 2)
            else:
                 layerGeom.coords = coords.reshape(-1, 2)
            current_layer.geometry.append(layerGeom)

    # Adiciona a camada combinada à lista e exporta para DXF se ela contiver alguma geometria
    if current_layer.geometry:
        all_layers_combined.append(current_layer)

        # Gera o nome do arquivo DXF usando o nome original do STL e o índice da camada
        stl_name = pathlib.Path(original_file_path).stem
        dxf_name = out_root / f"{stl_name}_layer{layer_idx}_{current_layer.z}.dxf"
        export_layer_to_dxf(current_layer, dxf_name) # Chama a função para exportar a camada para DXF
        layer_idx += 1 # Incrementa o índice da camada

"""
Visualização das Camadas Combinadas:
Plota uma amostra das camadas geradas para visualização (a cada 20 camadas).
"""
print("Plotando a cada 20ª camada combinada...")
if all_layers_combined:
    pyslm.visualise.plotLayers(all_layers_combined[::20])
    plt.show()
else:
    print("Nenhuma camada combinada gerada para plotar.")