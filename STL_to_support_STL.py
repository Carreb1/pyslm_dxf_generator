"""
Script de Geração de Suporte - Demonstra como gerar suportes de bloco básicos usando PySLM.
"""

import numpy as np
import logging
import os
import sys # Adicionado para aceitar argumentos de linha de comando

from matplotlib import pyplot as plt
from pyslm.core import Part
import pyslm.support

import vispy
import trimesh
import trimesh.creation

"""
Descomente a linha abaixo para fornecer mensagens de depuração para OpenGL - se surgirem problemas.
"""
# vispy.set_log_level('debug')

logging.getLogger().setLevel(logging.INFO)

## CONSTANTES ####
OVERHANG_ANGLE = 55  # deg - Ângulo de balanço. Se a região curva ainda não estiver suportada, tente reduzir isso (por exemplo, para 45 ou 30).

# -------------------- paths --------------------
# Definir o caminho base para a pasta de modelos
base_models_path = "models\original\Peca"
# Definir o caminho base para a pasta de saída STL com suportes
base_support_stl_output_path = "models\support"

# Verificar se o nome do modelo foi fornecido como argumento de linha de comando
if len(sys.argv) > 1:
    model_name = sys.argv[1] # O nome do modelo é o primeiro argumento
else:
    # Fallback ou erro se nenhum nome de modelo for fornecido
    print("Erro: Por favor, forneça o nome do modelo como argumento (ex: python script.py NomeDoModelo)")
    sys.exit(1) # Sai do script com um erro

# Constrói o caminho completo para o arquivo STL de entrada
original_file_path = os.path.join(base_models_path, f"{model_name}.stl")

# 2. Define o diretório de saída desejado para o STL com suportes
# Ele criará uma subpasta com o nome do modelo dentro de base_support_stl_output_path
output_directory = os.path.join(base_support_stl_output_path, model_name)

# Garante que o diretório de saída exista
os.makedirs(output_directory, exist_ok=True)

"""
Configuração da Peça:
Carrega o modelo STL, aplica rotação e escala, e o "solta" na plataforma de construção.
"""
myPart = Part('Peca')
myPart.setGeometry(str(original_file_path), fixGeometry=True) # Convertido para string
myPart.rotation = [0, 0, 0]
myPart.scaleFactor = 1.0
myPart.dropToPlatform(10)

"""
Extração da Malha de Balanço:
Identifica e extrai a parte da malha que forma as regiões de balanço com base no ângulo de balanço definido.
Esta malha é usada para visualização, mostrando onde os suportes são necessários.
"""
overhangMesh = pyslm.support.getOverhangMesh(myPart, OVERHANG_ANGLE,
                                            splitMesh=False, useConnectivity=True)
overhangMesh.visual.face_colors = [254.0, 0., 0., 254]

"""
Geração de Geometria de Suporte (Pontos e Bordas):
Primeiro, são identificados os pontos e as bordas que estão em balanço. Estes são a base para a geração de suportes mais complexos.
"""
pointOverhangs = pyslm.support.BaseSupportGenerator.findOverhangPoints(myPart)
overhangEdges = pyslm.support.BaseSupportGenerator.findOverhangEdges(myPart)

print(f"Número de pontos de balanço: {len(pointOverhangs)}")
print(f"Número de bordas de balanço: {len(overhangEdges)}")

"""
Configuração do Gerador de Suportes de Bloco em Grade:
Inicializa o gerador de suportes de bloco, definindo vários parâmetros que controlam a forma e o comportamento dos suportes.
Parâmetros como resolução, lacunas, limites de área e espaçamento de triangulação são ajustados para otimizar a geração.
"""
supportGenerator = pyslm.support.GridBlockSupportGenerator()
supportGenerator.rayProjectionResolution = 0.05  # [mm] - Resolução da grade usada para a projeção de raios
supportGenerator.innerSupportEdgeGap = 0.1       # [mm] - Offset interno do suporte usado entre distâncias de suporte adjacentes
supportGenerator.outerSupportEdgeGap = 0.1       # [mm] - Offset externo do suporte usado para os limites das regiões de balanço
supportGenerator.minimumAreaThreshold = 0.001    # Limite mínimo de área para não processar a região de suporte (reduzido significativamente)
supportGenerator.triangulationSpacing = 1.0      # [mm^2] - Parâmetro interno usado para gerar a malha do volume (reduzido para detalhes mais finos)
supportGenerator.simplifyPolygonFactor = 0.5     # Fator usado para simplificar a forma geral do suporte
supportGenerator.supportBorderDistance = 1.0     # [mm]
supportGenerator.numSkinMeshSubdivideIterations = 2

"""
Parâmetros dos Dentes de Suporte:
Configurações para os "dentes" que conectam os suportes à peça, garantindo uma aderência adequada e facilitando a remoção.
"""
supportGenerator.useUpperSupportTeeth = True
supportGenerator.useLowerSupportTeeth = True
supportGenerator.supportWallThickness = 1.0          # [mm] - Espessura das paredes superior e inferior para fortalecer as regiões dos dentes
supportGenerator.supportTeethTopLength = 0.1         # [mm] - Comprimento da aba para os dentes de suporte
supportGenerator.supportTeethHeight = 1.5            # [mm] - Comprimento dos dentes de suporte
supportGenerator.supportTeethBaseInterval = 1.5      # [mm] - O intervalo entre os dentes de suporte
supportGenerator.supportTeethUpperPenetration = 0.2  # [mm] - A penetração dos dentes de suporte na peça

supportGenerator.splineSimplificationFactor = 10  # Especifica o fator de suavização usando interpolação spline para os limites do suporte
supportGenerator.gridSpacing = [2.5, 2.5]             # [mm] O espaçamento da grade

"""
Identificação e Geração de Regiões de Suporte de Bloco:
O gerador identifica as regiões onde os suportes de bloco são necessários e cria os volumes de suporte correspondentes.
"""
supportBlockRegions = supportGenerator.identifySupportRegions(myPart, OVERHANG_ANGLE, True)

for block in supportBlockRegions:
    block.trussWidth = 1.0

blockSupports = [block.supportVolume for block in supportBlockRegions]

"""
Visualização de Bordas e Pontos de Balanço (Opcional):
Esta seção gera e visualiza as bordas e pontos que estão em balanço.
É útil para depuração e para entender onde os suportes estão sendo aplicados.
"""
if overhangEdges:
    """ Visualiza bordas que potencialmente requerem suporte """
    meshVerts = myPart.geometry.vertices
    edgeRays = np.vstack([meshVerts[edge] for edge in overhangEdges])
    visualize_support_edges = trimesh.load_path((edgeRays).reshape(-1, 2, 3))

    edge_supports = []
    for edge in overhangEdges:
        coords = np.vstack([meshVerts[edge, :]] * 2)
        coords[2:, 2] = 0.0
        extrudeFace = np.array([(0, 1, 3), (3, 2, 0)])
        edge_supports.append(trimesh.Trimesh(vertices=coords, faces=extrudeFace))

    """ Visualiza suportes de pontos """
    point_supports = []
    cylinder_rad = 0.5  # mm
    rays = []
    for pnt in pointOverhangs:
        coords = np.zeros((2, 3))
        coords[:, :] = meshVerts[pnt]
        coords[1, 2] = 0.0
        point_supports += trimesh.creation.cylinder(radius=cylinder_rad, segment=coords)
        rays.append(coords)

    # Alternativamente, pode ser visualizado por linhas
    rays = np.hstack([meshVerts[pointOverhangs]] * 2).reshape(-1, 2, 3)
    rays[:, 1, 2] = 0.0
    visualize_support_pnts = trimesh.load_path(rays)
else:
    print("Nenhuma borda de balanço encontrada. Ajuste a rotação da peça ou o ângulo de balanço.")

# Torna a parte normal transparente para melhor visualização dos suportes
myPart.geometry.visual.vertex_colors = [80, 80, 80, 125]

"""
Visualização de Todo o Suporte Gerado:
Exibe a cena com a peça original e os volumes de suporte de bloco gerados.
"""
s1 = trimesh.Scene([myPart.geometry] + blockSupports)

"""
Exporta a cena combinada (peça e suportes) para um arquivo GLB para visualização.
"""
with open('overhangSupport.glb', 'wb') as f:
    f.write(trimesh.exchange.gltf.export_glb(s1, include_normals=True))

"""
Exibição do Volume do Bloco de Suporte (Opcional):
Define para True para depuração: mostra os volumes de bloco intermediários.
"""
DISPLAY_BLOCK_VOLUME = True  # Definir para True para depuração: mostra os volumes de bloco intermediários.

if DISPLAY_BLOCK_VOLUME:
    s2 = trimesh.Scene([myPart.geometry, overhangMesh, blockSupports])
    s2.show()

"""
Geração da Estrutura de Treliça (Mesh Supports):
Para cada região de suporte de bloco, a estrutura de treliça é gerada, criando a geometria final dos suportes.
Isso envolve a criação de seções transversais e a extrusão de uma estrutura de grade.
"""
meshSupports = []
for supportBlock in supportBlockRegions:
    supportBlock.mergeMesh = False
    supportBlock.useSupportSkin = True
    meshSupports.append(supportBlock.geometry())

"""
Visualização Final da Peça com Suportes de Treliça:
Exibe a cena com a malha de balanço, a peça original e os suportes de treliça gerados.
"""
s2 = trimesh.Scene([overhangMesh, myPart.geometry] + meshSupports)
s2.show()

"""
Salvamento do Modelo Combinado (Peça + Suportes) como STL:
Esta seção combina a geometria da peça original e as malhas de suporte geradas em uma única cena
e as exporta para um novo arquivo STL com um nome descritivo em um diretório especificado.
"""
# Cria uma única cena trimesh contendo tanto a peça quanto os suportes gerados
combined_scene = trimesh.Scene()
combined_scene.add_geometry(myPart.geometry)  # Adiciona a peça original
for support_mesh in meshSupports:
    combined_scene.add_geometry(support_mesh)  # Adiciona cada malha de suporte gerada

# 3. Constrói o novo nome do arquivo com o sufixo "_support.stl"
new_filename = f"{model_name}_support.stl"

# 4. Combina o diretório e o novo nome do arquivo para obter o caminho de saída completo
output_stl_full_path = os.path.join(output_directory, new_filename)

# Exporta a cena combinada para um arquivo STL
try:
    combined_scene.export(output_stl_full_path)
    print(f"Peça combinada e suportes salvos com sucesso em {output_stl_full_path}")
except Exception as e:
    print(f"Erro ao salvar o arquivo STL: {e}")