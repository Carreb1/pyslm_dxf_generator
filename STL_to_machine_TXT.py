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
import pyslm, pyslm.visualise
from pyslm import hatching
from pyslm.geometry import Layer, ContourGeometry, HatchGeometry, PointsGeometry

import trimesh
import trimesh.creation
import trimesh.util
import trimesh.exchange.gltf

"""
Configuração de Logging:
Define o nível de logging para o script e silencia mensagens INFO e WARNING do ezdxf para evitar verbosidade excessiva.
O WARNING sobre $INSUNITS em DXF R12 é comum e geralmente inofensivo para este fluxo.
"""
logging.getLogger().setLevel(logging.INFO)
logging.getLogger('ezdxf').setLevel(logging.ERROR) # Apenas erros críticos do ezdxf

## CONSTANTES ####
OVERHANG_ANGLE = 45  # [deg] - Ângulo de balanço. Reduza para suportar regiões mais curvas (e.g., para 45 ou 30).
LAYER_THICKNESS = 0.03 # [mm] - Espessura de cada camada fatiada, usada em todo o pipeline.

# -------------------- Funções Auxiliares --------------------

def export_layer_to_dxf(layer: Layer, path: pathlib.Path):
    """
    Converte um objeto PySLM Layer para um arquivo DXF usando a biblioteca ezdxf.
    Desenha contornos como polilinhas fechadas, hachuras como linhas individuais e pontos como círculos.
    """
    doc = ezdxf.new(dxfversion="R2010") # Cria um novo documento DXF.
    msp = doc.modelspace()              # Acessa o espaço do modelo.

    # Adiciona contornos como polilinhas fechadas.
    for geom in layer.getContourGeometry():
        pts = [tuple(p) for p in geom.coords]
        msp.add_lwpolyline(pts, close=True)

    # Adiciona hachuras como entidades de linha individuais.
    for geom in layer.getHatchGeometry():
        coords = geom.coords
        for i in range(0, len(coords), 2):
            start, end = map(tuple, coords[i:i+2])
            msp.add_line(start, end)

    # Adiciona pontos como pequenos círculos (opcional).
    for geom in layer.getPointsGeometry():
        for p in geom.coords:
            msp.add_circle(tuple(p), radius=0.02)

    doc.saveas(path) # Salva o documento DXF no caminho especificado.

def get_line_segments_from_dxf(dxf_path: pathlib.Path) -> list:
    """
    Lê um arquivo DXF e extrai todos os segmentos de linha de entidades
    LWPOLYLINE, POLYLINE e LINE.
    """
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except ezdxf.DXFStructureError:
        logging.error(f"Estrutura DXF inválida para '{dxf_path}'. Pulando.")
        return []
    except Exception as e:
        logging.error(f"Erro inesperado ao ler '{dxf_path}': {e}. Pulando.")
        return []

    line_segments = []

    for entity in msp.query('LWPOLYLINE'):
        points = entity.get_points()
        if len(points) >= 2:
            for i in range(len(points) - 1):
                start_point = (points[i][0], points[i][1])
                end_point = (points[i+1][0], points[i+1][1])
                line_segments.append([start_point, end_point])
            if entity.is_closed and len(points) > 2:
                start_point = (points[-1][0], points[-1][1])
                end_point = (points[0][0], points[0][1])
                line_segments.append([start_point, end_point])

    for entity in msp.query('POLYLINE'):
        current_polyline_points = []
        for vertex in entity.points():
            if hasattr(vertex, 'dxf') and hasattr(vertex.dxf, 'location'):
                current_polyline_points.append((vertex.dxf.location[0], vertex.dxf.location[1]))

        if len(current_polyline_points) >= 2:
            for i in range(len(current_polyline_points) - 1):
                start_point = (current_polyline_points[i][0], current_polyline_points[i][1])
                end_point = (current_polyline_points[i+1][0], current_polyline_points[i+1][1])
                line_segments.append([start_point, end_point])
            if entity.is_closed and len(current_polyline_points) > 2:
                start_point = (current_polyline_points[-1][0], current_polyline_points[-1][1])
                end_point = (current_polyline_points[0][0], current_polyline_points[0][1])
                line_segments.append([start_point, end_point])

    for entity in msp.query('LINE'):
        start_point = (entity.dxf.start[0], entity.dxf.start[1])
        end_point = (entity.dxf.end[0], entity.dxf.end[1])
        line_segments.append([start_point, end_point])

    return line_segments

def create_simplified_dxf_for_laser(line_segments: list, output_dxf_path: pathlib.Path):
    """
    Cria um novo arquivo DXF contendo apenas as entidades LINE dos segmentos fornecidos.
    Este formato é mais simples e pode ser preferido por algumas máquinas a laser ou CNC.
    """
    # Usamos 'AC1009' para DXF R12, que é um formato simplificado e amplamente compatível.
    # O aviso sobre $INSUNITS é esperado com este formato e geralmente inofensivo.
    doc = ezdxf.new('AC1009')
    msp = doc.modelspace()

    for segment in line_segments:
        start_point = segment[0]
        end_point = segment[1]
        # Arredonda as coordenadas para evitar problemas de precisão em algumas máquinas.
        start_point_rounded = (round(start_point[0], 6), round(start_point[1], 6))
        end_point_rounded = (round(end_point[0], 6), round(end_point[1], 6))
        msp.add_line(start_point_rounded, end_point_rounded)

    try:
        doc.saveas(output_dxf_path)
    except Exception as e:
        print(f"Erro ao salvar DXF simplificado {output_dxf_path}: {e}")

def convert_dxf_to_lines_only_machine_format(input_dxf_path: pathlib.Path, output_target_path: pathlib.Path):
    """
    Lê um arquivo DXF de entrada, extrai todos os segmentos de linha de entidades LWPOLYLINE,
    POLYLINE e LINE, e então cria um novo arquivo (texto puro ou DXF simplificado)
    contendo apenas os dados das entidades LINE no formato específico da máquina.
    """
    if not input_dxf_path.exists():
        print(f"Erro: Arquivo DXF de entrada não encontrado em '{input_dxf_path}'")
        return

    try:
        doc = ezdxf.readfile(input_dxf_path)
        msp = doc.modelspace()
    except ezdxf.DXFStructureError:
        print(f"Erro: Estrutura de arquivo DXF inválida para '{input_dxf_path}'. Pulando.")
        return
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao ler '{input_dxf_path}': {e}. Pulando.")
        return

    all_line_segments = []

    for entity in msp.query('LWPOLYLINE'):
        points = entity.get_points()
        if len(points) >= 2:
            for i in range(len(points) - 1):
                start_point = (points[i][0], points[i][1])
                end_point = (points[i+1][0], points[i+1][1])
                all_line_segments.append([start_point, end_point])
            if entity.is_closed and len(points) > 2:
                start_point = (points[-1][0], points[-1][1])
                end_point = (points[0][0], points[0][1])
                all_line_segments.append([start_point, end_point])

    for entity in msp.query('POLYLINE'):
        current_polyline_points = []
        for vertex in entity.points():
            if hasattr(vertex, 'dxf') and hasattr(vertex.dxf, 'location'):
                current_polyline_points.append((vertex.dxf.location[0], vertex.dxf.location[1]))

        if len(current_polyline_points) >= 2:
            for i in range(len(current_polyline_points) - 1):
                start_point = (current_polyline_points[i][0], current_polyline_points[i][1])
                end_point = (current_polyline_points[i+1][0], current_polyline_points[i+1][1])
                all_line_segments.append([start_point, end_point])
            if entity.is_closed and len(current_polyline_points) > 2:
                start_point = (current_polyline_points[-1][0], current_polyline_points[-1][1])
                end_point = (current_polyline_points[0][0], current_polyline_points[0][1])
                all_line_segments.append([start_point, end_point])

    for entity in msp.query('LINE'):
        start_point = (entity.dxf.start[0], entity.dxf.start[1])
        end_point = (entity.dxf.end[0], entity.dxf.end[1])
        all_line_segments.append([start_point, end_point])

    output_target_path.parent.mkdir(parents=True, exist_ok=True) # Garante que o diretório de saída exista.

    try:
        with open(output_target_path, 'w') as f:
            f.write("0\nSECTION\n2\nENTITIES\n") # Headers.
            for segment in all_line_segments:
                start_x, start_y = segment[0]
                end_x, end_y = segment[1]
                # Formato exato que a máquina espera:
                f.write(f"0\nLINE\n8\n0\n10\n{start_x:.3f}\n20\n{start_y:.3f}\n11\n{end_x:.3f}\n21\n{end_y:.3f}\n0\n")
            f.write("0\nENDSEC\n0\nEOF\n") # Footers.

    except Exception as e:
        print(f"Erro ao escrever em '{output_target_path}': {e}")

# -------------------- Fluxo Principal --------------------

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Uso: python STL_to_machine_TXT.py NomeDoModeloSTL [etapa]")
        print("Etapa: 1 (Geração Bruta), 2 (Limpeza DXF e STL), 3 (Máquina TXT/DXF)")
        print("Padrão: 1")
        sys.exit(1)

    model_name = sys.argv[1] # Nome do modelo STL sem a extensão
    start_step = 1 # Padrão para começar da Etapa 1
    if len(sys.argv) == 3:
        try:
            start_step = int(sys.argv[2])
            if start_step not in [1, 2, 3]:
                raise ValueError
        except ValueError:
            print("Erro: A etapa deve ser 1, 2 ou 3.")
            sys.exit(1)

    # Definir o caminho base para a pasta de modelos e saída
    base_models_path = pathlib.Path("models\original\Peca")
    base_dxfs_path = pathlib.Path("dxfs")

    # Constrói o caminho completo para o arquivo STL de entrada
    original_file_path = base_models_path / f"{model_name}.stl"

    if not original_file_path.exists() and start_step == 1:
        print(f"Erro: O arquivo STL '{original_file_path}' não foi encontrado. Necessário para a Etapa 1.")
        sys.exit(1)

    # Gerar o timestamp e definir as pastas de saída.
    # Se estiver pulando para a etapa 2 ou 3, tentamos encontrar uma pasta existente.
    # Caso contrário, cria uma nova.
    current_datetime = datetime.datetime.now().strftime("%d%m%Y%H%M")
    output_root_folder_name = f"{model_name}_{current_datetime}"
    output_root_folder = base_dxfs_path / output_root_folder_name

    # Se a etapa inicial não for 1, tentamos encontrar a pasta mais recente para o modelo
    if start_step > 1:
        existing_folders = sorted([f for f in base_dxfs_path.iterdir() if f.is_dir() and f.name.startswith(model_name)], reverse=True)
        if existing_folders:
            output_root_folder = existing_folders[0] # Usa a pasta mais recente
            output_root_folder_name = output_root_folder.name
            print(f"Reaproveitando pasta existente para '{model_name}': {output_root_folder}")
        else:
            print(f"Erro: Nenhuma pasta existente encontrada para '{model_name}'. Não é possível pular para a Etapa {start_step}.")
            sys.exit(1)
    else: # Se start_step é 1, sempre cria uma nova pasta
        output_root_folder.mkdir(parents=True, exist_ok=True)
        print(f"Criando nova pasta de saída: {output_root_folder}")


    output_dxf_bruto_folder = output_root_folder / "dxf_bruto"
    output_dxf_clean_folder = output_root_folder / "dxf_clean"
    output_txt_machine_folder = output_root_folder / "txt_maquina"

    # Garante que as subpastas existam, mesmo que tenhamos reaproveitado uma pasta pai
    output_dxf_bruto_folder.mkdir(parents=True, exist_ok=True)
    output_dxf_clean_folder.mkdir(parents=True, exist_ok=True)
    output_txt_machine_folder.mkdir(parents=True, exist_ok=True)

    print(f"Todos os arquivos de saída serão gerados em: {output_root_folder}")

    # --- Etapa 1: Geração de Suporte e DXF Bruto ---
    if start_step <= 1:
        print("\n--- Etapa 1: Gerando suportes e DXFs brutos ---")

        myPart = Part('Peca')
        myPart.setGeometry(str(original_file_path), fixGeometry=True)
        myPart.rotation = [0, 0, 0]  # rotação da peça [X, Y, Z]
        myPart.scaleFactor = 1.0
        myPart.dropToPlatform(5) # Distancia da peca até a base

        overhangMesh = pyslm.support.getOverhangMesh(myPart, OVERHANG_ANGLE, splitMesh=False, useConnectivity=True)
        overhangMesh.visual.face_colors = [254.0, 0., 0., 254]

        supportGenerator = pyslm.support.GridBlockSupportGenerator()
        supportGenerator.rayProjectionResolution = 0.07
        supportGenerator.innerSupportEdgeGap = 0.3
        supportGenerator.outerSupportEdgeGap = 0.3
        supportGenerator.simplifyPolygonFactor = 0.5
        supportGenerator.minimumAreaThreshold = 0.05
        supportGenerator.triangulationSpacing = 4
        supportGenerator.supportBorderDistance = 1.0  # (F) support boundary offsetting for strengthening
        supportGenerator.numSkinMeshSubdivideIterations = 2

        supportGenerator.useUpperSupportTeeth = True
        supportGenerator.useLowerSupportTeeth = True
        supportGenerator.supportWallThickness = 0.7
        supportGenerator.supportTeethTopLength = 0.1  # (C) teeth upper length
        supportGenerator.supportTeethHeight = 1      # (B) teeth height
        supportGenerator.supportTeethBaseInterval = 1.5 # (E) teeth base interval
        supportGenerator.supportTeethUpperPenetration = 0.05 # (G) teeth penetration

        supportGenerator.trussWidth = 0.5 # (A) truss width ão sei se é isso mesmo, tenho que testar

        supportGenerator.splineSimplificationFactor = 10
        supportGenerator.gridSpacing = [2.5, 2.5] 

        # Propriedade(s) adicionada(s) (faltando na sua implementação original, conforme documentação):
        supportGenerator.supportTeethBottomLength = 0.3 # (D) teeth lower length (exemplo de valor)

        supportBlockRegions = supportGenerator.identifySupportRegions(myPart, OVERHANG_ANGLE, True)
        for block in supportBlockRegions:
            block.trussWidth = 1.0
        blockSupports = [block.supportVolume for block in supportBlockRegions]

        # Visualização e Exportação da Geometria de Suporte (GLB)
        s1 = trimesh.Scene([myPart.geometry] + blockSupports)
        glb_output_path = output_root_folder / f"{model_name}_overhangSupport.glb"
        with open(glb_output_path, 'wb') as f:
            f.write(trimesh.exchange.gltf.export_glb(s1, include_normals=True))
        print(f"Visualização inicial dos suportes exportada para: {glb_output_path}")

        meshSupports = []
        for supportBlock in supportBlockRegions:
            supportBlock.mergeMesh = False
            supportBlock.useSupportSkin = True
            meshSupports.append(supportBlock.geometry())

        # Visualização Final da Peça e Suportes de Malha
        s2 = trimesh.Scene([overhangMesh, myPart.geometry] + meshSupports)
        print("Exibindo visualização final da peça com suportes. Feche a janela para continuar.")
        s2.show()

        # Processo de Fatiamento e Geração de Camadas DXF Brutas
        min_z_part = myPart.boundingBox[2]
        max_z_part = myPart.boundingBox[5]

        if meshSupports:
            support_combined_mesh = trimesh.util.concatenate(meshSupports)
            min_z_support = support_combined_mesh.bounds[0, 2]
            max_z_support = support_combined_mesh.bounds[1, 2]
        else:
            min_z_support = min_z_part
            max_z_support = max_z_part

        min_z_overall = min(min_z_part, min_z_support)
        max_z_overall = max(max_z_part, max_z_support)

        all_layers_combined = []
        h = hatching.Hatcher()
        h.hatchAngle = 10
        h.volumeOffsetHatch = 0.08
        h.spotCompensation = 0.06
        h.stripeWidth = 0.07
        h.numInnerContours = 2
        h.numOuterContours = 1
        h.hatchSortMethod = hatching.AlternateSort()

        print("Fatiando e processando camadas da peça e dos suportes (DXF Bruto)...")
        layer_idx = 0
        num_layers = int(np.ceil((max_z_overall - min_z_overall) / LAYER_THICKNESS))
        for zPos in tqdm(np.arange(min_z_overall, max_z_overall + LAYER_THICKNESS, LAYER_THICKNESS), total=num_layers, desc="Gerando DXF Bruto"):
            current_layer = Layer()
            current_layer.z = int(zPos * 1000)

            h.hatchAngle += 66.7
            slice_geom_part = myPart.getVectorSlice(zPos)

            if slice_geom_part:
                layer_hatch_part = h.hatch(slice_geom_part)
                for geom in layer_hatch_part.geometry:
                    current_layer.geometry.append(geom)

            innerHatchPaths_support, boundaryPaths_support = [], []
            if meshSupports:
                innerHatchPaths_support, boundaryPaths_support = pyslm.support.GridBlockSupport.slice(meshSupports, zPos)

            if innerHatchPaths_support:
                gridCoords_support = pyslm.hatching.simplifyBoundaries(innerHatchPaths_support, 0.1)
                for coords in gridCoords_support:
                    hatchGeom = HatchGeometry()
                    hatchGeom.coords = coords.reshape(-1, 2)
                    current_layer.geometry.append(hatchGeom)

            if boundaryPaths_support:
                boundaryCoords_support = pyslm.hatching.simplifyBoundaries(boundaryPaths_support, 0.1)
                for coords in boundaryCoords_support:
                    layerGeom = ContourGeometry()
                    if hasattr(coords, 'exterior') and hasattr(coords.exterior, 'coords'):
                         layerGeom.coords = np.array(coords.exterior.coords)[:-1].reshape(-1, 2)
                    else:
                         layerGeom.coords = coords.reshape(-1, 2)
                    current_layer.geometry.append(layerGeom)

            if current_layer.geometry:
                all_layers_combined.append(current_layer)
                dxf_name = output_dxf_bruto_folder / f"{model_name}_layer{layer_idx}_{current_layer.z}.dxf"
                export_layer_to_dxf(current_layer, dxf_name)
            layer_idx += 1

        print("\nPlotando uma amostra das camadas combinadas (brutas)...")
        if all_layers_combined:
            # Plota uma amostra das camadas (aproximadamente 20 camadas) para visualização
            pyslm.visualise.plotLayers(all_layers_combined[::max(1, len(all_layers_combined) // 20)])
            plt.show()
        else:
            print("Nenhuma camada bruta gerada para plotar.")

    # --- Etapa 2: Limpeza de DXF e Geração de STL Opcional ---
    if start_step <= 2:
        print("\n--- Etapa 2: Limpando DXFs brutos e gerando DXFs limpos (e STL opcional) ---")

        dxf_files_bruto = sorted([f for f in os.listdir(output_dxf_bruto_folder) if f.lower().endswith('.dxf')])
        all_meshes_for_stl = []
        z_offset = 0.0

        if not dxf_files_bruto:
            print(f"Nenhum arquivo DXF encontrado em: {output_dxf_bruto_folder}. Pulando limpeza.")
        else:
            print("Iniciando o processamento de camadas DXF (extraindo linhas e gerando DXFs limpos)...")
            for dxf_file in tqdm(dxf_files_bruto, desc="Gerando DXF Limpo"):
                dxf_path_bruto = output_dxf_bruto_folder / dxf_file

                line_segments_2d = get_line_segments_from_dxf(dxf_path_bruto)

                if not line_segments_2d:
                    print(f"Aviso: Nenhuma linha ou polilinha válida encontrada em {dxf_file}. Pulando esta camada.")
                    z_offset += LAYER_THICKNESS
                    continue

                output_clean_dxf_path = output_dxf_clean_folder / f"clean_{dxf_file}"
                create_simplified_dxf_for_laser(line_segments_2d, output_clean_dxf_path)

                # Geração do STL
                current_layer_meshes = []
                for segment_2d in line_segments_2d:
                    if len(segment_2d) < 2:
                        continue
                    try:
                        path_2d = trimesh.load_path(np.array(segment_2d), process=False)
                        extruded_result = path_2d.extrude(height=LAYER_THICKNESS)

                        if isinstance(extruded_result, list):
                            for extruded_slice in extruded_result:
                                if isinstance(extruded_slice, trimesh.Trimesh):
                                    extruded_slice.apply_translation([0, 0, z_offset])
                                    current_layer_meshes.append(extruded_slice)
                        elif isinstance(extruded_result, trimesh.Trimesh):
                            extruded_result.apply_translation([0, 0, z_offset])
                            current_layer_meshes.append(extruded_result)
                    except Exception as e:
                        logging.error(f"Erro ao extrudar segmento de linha em {dxf_file} para STL: {e}")
                all_meshes_for_stl.extend(current_layer_meshes)

                z_offset += LAYER_THICKNESS

            if not all_meshes_for_stl:
                print("Nenhum sólido 3D foi criado a partir dos arquivos DXF para o STL.")
            else:
                combined_mesh = trimesh.util.concatenate(all_meshes_for_stl)
                output_stl_path = output_root_folder / f"{model_name}_combined_cleaned.stl"
                combined_mesh.export(output_stl_path)
                print(f"\nModelo 3D '{output_stl_path.name}' gerado com sucesso em: {output_stl_path}")

        print("\nProcesso de limpeza de DXF concluído.")

    # --- Etapa 3: Conversão DXF para Formato de Máquina (TXT/DXF Simplificado) ---
    if start_step <= 3:
        print("\n--- Etapa 3: Convertendo DXFs limpos para formato de máquina (.dxf simplificado) ---")

        dxf_files_clean = sorted([f for f in os.listdir(output_dxf_clean_folder) if f.lower().endswith('.dxf')])

        if not dxf_files_clean:
            print(f"Nenhum arquivo DXF 'limpo' encontrado em '{output_dxf_clean_folder}'. Pulando conversão para formato de máquina.")
        else:
            print(f"Iniciando a conversão em lote de {len(dxf_files_clean)} arquivos DXF limpos...")
            for filename in tqdm(dxf_files_clean, desc="Gerando DXF para Máquina"):
                input_file_path = output_dxf_clean_folder / filename
                base_filename = input_file_path.stem
                output_file_path = output_txt_machine_folder / f"machine_{base_filename}.dxf" # Mantém a extensão .dxf, mas com conteúdo simplificado
                convert_dxf_to_lines_only_machine_format(input_file_path, output_file_path)

    print("\nProcessamento completo. Verifique as pastas de saída para os resultados.")