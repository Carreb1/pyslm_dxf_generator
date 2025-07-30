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

# --- Logging Configuration ---
logging.getLogger().setLevel(logging.INFO)
# Suppress INFO and WARNING messages from ezdxf to keep output clean
logging.getLogger('ezdxf').setLevel(logging.ERROR)

# --- GLOBAL CONSTANTS AND PATH CONFIGURATION ---
OVERHANG_ANGLE = 45  # [deg] - Overhang angle for support generation.
LAYER_THICKNESS = 0.03 # [mm] - Thickness of each sliced layer.

# --- PATH CONFIGURATION ---
# Você pode editar esses caminhos para apontar para as suas pastas
# O script tentará determinar o diretório base automaticamente para caminhos relativos.

# Opção 1: Usar caminhos relativos ao diretório ONDE O SCRIPT ESTÁ.
# Útil se você mantiver uma estrutura de pastas fixa em relação ao script.
# script_dir = pathlib.Path(__file__).parent # Já definido na seção de execução

# BASE_MODELS_ORIGINAL_PECA = script_dir / "models" / "original" / "Peca"
# BASE_MODELS_ORIGINAL_SUPORTE = script_dir / "models" / "original" / "suporte"
# BASE_DXFS_PATH = script_dir / "dxfs"


# Opção 2: Definir caminhos absolutos ou relativos a partir do local de execução,
# ou do diretório home do usuário. Escolha apenas UMA das opções abaixo descomentando.

# Exemplo de caminho absoluto (altere para o seu caminho real):
# BASE_MODELS_ORIGINAL_PECA = pathlib.Path(r"C:\Users\SeuUsuario\Documentos\MeusModelos\PecaOriginal")
# BASE_MODELS_ORIGINAL_SUPORTE = pathlib.Path(r"C:\Users\SeuUsuario\Documentos\MeusModelos\ModelosComSuporte")
# BASE_DXFS_PATH = pathlib.Path(r"C:\Users\SeuUsuario\Documentos\SaidasDXF")

# Exemplo de caminho relativo ao diretório ATUAL de execução do script:
# (Se você executar o script de uma pasta acima da sua 'Final_pipeline')
# BASE_MODELS_ORIGINAL_PECA = pathlib.Path("Final_pipeline") / "models" / "original" / "Peca"
# BASE_MODELS_ORIGINAL_SUPORTE = pathlib.Path("Final_pipeline") / "models" / "original" / "suporte"
# BASE_DXFS_PATH = pathlib.Path("Final_pipeline") / "dxfs"

# Exemplo de caminho relativo ao diretório HOME do usuário (mais portável entre máquinas):
# home_dir = pathlib.Path.home() # Obtém o diretório home do usuário
# BASE_MODELS_ORIGINAL_PECA = home_dir / "IPT_Pipeline_Data" / "models" / "original" / "Peca"
# BASE_MODELS_ORIGINAL_SUPORTE = home_dir / "IPT_Pipeline_Data" / "models" / "original" / "suporte"
# BASE_DXFS_PATH = home_dir / "IPT_Pipeline_Data" / "dxfs"

# Padrão: Caminhos relativos ao diretório do próprio script (como era antes, mas agora explícito)
# Esta é a configuração padrão se você não descomentar nenhuma das opções acima.
_script_dir_ = pathlib.Path(__file__).parent
BASE_MODELS_ORIGINAL_PECA = _script_dir_ / "models" / "original" / "Peca"
BASE_MODELS_ORIGINAL_SUPORTE = _script_dir_ / "models" / "original" / "suporte"
BASE_DXFS_PATH = _script_dir_ / "dxfs"

# --- Centralized Support Parameters (Block 3 Parameters) ---
def get_pyslm_support_generator():
    """
    Returns a pre-configured pyslm.support.GridBlockSupportGenerator with consistent parameters.
    """
    supportGenerator = pyslm.support.GridBlockSupportGenerator()
    supportGenerator.rayProjectionResolution = 0.07
    supportGenerator.innerSupportEdgeGap = 0.3
    supportGenerator.outerSupportEdgeGap = 0.3
    supportGenerator.simplifyPolygonFactor = 0.5
    supportGenerator.minimumAreaThreshold = 0.05
    supportGenerator.triangulationSpacing = 4
    supportGenerator.supportBorderDistance = 1.0
    supportGenerator.numSkinMeshSubdivideIterations = 2

    supportGenerator.useUpperSupportTeeth = True
    supportGenerator.useLowerSupportTeeth = True
    supportGenerator.supportWallThickness = 0.7
    supportGenerator.supportTeethTopLength = 0.1
    supportGenerator.supportTeethHeight = 1
    supportGenerator.supportTeethBaseInterval = 1.5
    supportGenerator.supportTeethUpperPenetration = 0.05
    supportGenerator.trussWidth = 0.5
    supportGenerator.supportTeethBottomLength = 0.3

    supportGenerator.splineSimplificationFactor = 10
    supportGenerator.gridSpacing = [2.5, 2.5]
    return supportGenerator

# --- Auxiliary DXF/Geometry Functions ---
def export_layer_to_dxf(layer: Layer, path: pathlib.Path):
    """
    Converts a PySLM Layer object to a DXF file using ezdxf.
    Draws contours as closed polylines, hatches as individual lines, and points as circles.
    """
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    for geom in layer.getContourGeometry():
        pts = [tuple(p) for p in geom.coords]
        msp.add_lwpolyline(pts, close=True)

    for geom in layer.getHatchGeometry():
        coords = geom.coords
        for i in range(0, len(coords), 2):
            start, end = map(tuple, coords[i:i+2])
            msp.add_line(start, end)

    for geom in layer.getPointsGeometry():
        for p in geom.coords:
            msp.add_circle(tuple(p), radius=0.02)

    doc.saveas(path)

def get_line_segments_from_dxf(dxf_path: pathlib.Path) -> list:
    """
    Reads a DXF file and extracts all line segments from LWPOLYLINE, POLYLINE, and LINE entities.
    Returns a list of segments: [((x1, y1), (x2, y2)), ...].
    """
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except ezdxf.DXFStructureError:
        logging.error(f"Invalid DXF structure for '{dxf_path}'. Skipping.")
        return []
    except Exception as e:
        logging.error(f"Unexpected error reading '{dxf_path}': {e}. Skipping.")
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
    Creates a new DXF file containing only LINE entities from the provided segments.
    """
    doc = ezdxf.new('AC1009') # DXF R12 for wide compatibility
    msp = doc.modelspace()
    for segment in line_segments:
        start_point = segment[0]
        end_point = segment[1]
        start_point_rounded = (round(start_point[0], 6), round(start_point[1], 6))
        end_point_rounded = (round(end_point[0], 6), round(end_point[1], 6))
        msp.add_line(start_point_rounded, end_point_rounded)
    try:
        doc.saveas(output_dxf_path)
    except Exception as e:
        print(f"Error saving simplified DXF {output_dxf_path}: {e}")

def convert_dxf_to_lines_only_machine_format(input_dxf_path: pathlib.Path, output_target_path: pathlib.Path):
    """
    Reads a DXF, extracts line segments, and writes them to a new file in a machine-specific TXT/DXF format.
    """
    if not input_dxf_path.exists():
        print(f"Error: Input DXF file not found at '{input_dxf_path}'")
        return

    try:
        doc = ezdxf.readfile(input_dxf_path)
        msp = doc.modelspace()
    except ezdxf.DXFStructureError:
        print(f"Error: Invalid DXF file structure for '{input_dxf_path}'. Skipping.")
        return
    except Exception as e:
        print(f"An unexpected error occurred reading '{input_dxf_path}': {e}. Skipping.")
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
                start_point = (points[-1][0], points[0][1])
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

    output_target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(output_target_path, 'w') as f:
            f.write("0\nSECTION\n2\nENTITIES\n")
            for segment in all_line_segments:
                start_x, start_y = segment[0]
                end_x, end_y = segment[1]
                f.write(f"0\nLINE\n8\n0\n10\n{start_x:.3f}\n20\n{start_y:.3f}\n11\n{end_x:.3f}\n21\n{end_y:.3f}\n0\n")
            f.write("0\nENDSEC\n0\nEOF\n")
    except Exception as e:
        print(f"Error writing to '{output_target_path}': {e}")

def generate_manufacturing_parameters_file(
    input_dxf_folder: pathlib.Path,
    output_folder: pathlib.Path,
    part_name: str,
    layer_thickness: float,
):
    """
    Analyzes DXF files in a folder to automatically generate some manufacturing parameters,
    and combines them with user-provided/default settings into a .txt file.
    """
    if not input_dxf_folder.exists():
        print(f"Error: Input DXF folder not found at '{input_dxf_folder}'. Cannot generate parameters file.")
        return

    dxf_files = sorted([f for f in os.listdir(input_dxf_folder) if f.lower().endswith(('.dxf', '.txt'))])
    if not dxf_files:
        print(f"No DXF or TXT files found in '{input_dxf_folder}'. Cannot generate parameters file.")
        return

    number_of_layers = len(dxf_files)

    # These values are typically fixed by the machine or set based on part size.
    # Hardcoding them as per your original manufacture_parameters.py example.
    min_x = -7.9
    max_x = 7.9
    min_y = -7.9
    max_y = 7.9

    final_parameters = {
        "PART NAME": part_name,
        "MINX": min_x,
        "MAXX": max_x,
        "MINY": min_y,
        "MAXY": max_y,
        "NUMBER OF LAYERS": number_of_layers,
        "LAYER THICKNESS": layer_thickness,
        "HATCH POWER 1": 40,
        "HATCH SPEED 1": 170,
        "VBPP1": 1,
        "MAGNIFICATION 1": 1.0,
        "HATCH POWER 2": 42,
        "HATCH SPEED 2": 1202,
        "VBPP2": 2,
        "MAGNIFICATION 2": 1.0,
        "HATCH POWER 3": 43,
        "HATCH SPEED 3": 1203,
        "VBPP3": 3,
        "MAGNIFICATION 3": 1.0,
        "NUMBER OF PASSES": 1,
        "CONTOUR POWER": 11,
        "CONTOUR SPEED": 1001,
    }

    output_file_path = output_folder / f"{part_name}_auto_machine_parameters.txt"
    output_folder.mkdir(parents=True, exist_ok=True)

    try:
        with open(output_file_path, 'w') as f:
            for key, value in final_parameters.items():
                f.write(f"[{key}]\n")
                f.write(f"{value}\n")
        print(f"\nSuccessfully generated manufacturing parameters file: {output_file_path}")
    except Exception as e:
        print(f"Error generating the file '{output_file_path}': {e}")


# --- Core Pipeline Functions ---

def _slice_and_export_dxf_layers(part_to_slice: Part, supports_to_slice: list, output_dxf_bruto_folder: pathlib.Path, model_name: str):
    """
    Helper function to slice the given part and supports into DXF layers.
    (Block 5 logic, for 'bruto' DXF generation)
    """
    min_z_part = part_to_slice.boundingBox[2]
    max_z_part = part_to_slice.boundingBox[5]

    if supports_to_slice:
        support_combined_mesh = trimesh.util.concatenate(supports_to_slice)
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

    print(f"Slicing and processing layers for '{model_name}' (Raw DXF)...")
    layer_idx = 0
    num_layers = int(np.ceil((max_z_overall - min_z_overall) / LAYER_THICKNESS))
    for zPos in tqdm(np.arange(min_z_overall, max_z_overall + LAYER_THICKNESS, LAYER_THICKNESS), total=num_layers, desc="Generating Raw DXF"):
        current_layer = Layer()
        current_layer.z = int(zPos * 1000)

        h.hatchAngle += 66.7
        slice_geom_part = part_to_slice.getVectorSlice(zPos)

        if slice_geom_part:
            layer_hatch_part = h.hatch(slice_geom_part)
            for geom in layer_hatch_part.geometry:
                current_layer.geometry.append(geom)

        innerHatchPaths_support, boundaryPaths_support = [], []
        if supports_to_slice:
            innerHatchPaths_support, boundaryPaths_support = pyslm.support.GridBlockSupport.slice(supports_to_slice, zPos)

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

    print("\nPlotting a sample of combined layers (raw DXFs)...")
    if all_layers_combined:
        pyslm.visualise.plotLayers(all_layers_combined[::max(1, len(all_layers_combined) // 20)])
        plt.show()
    else:
        print("No raw layers generated to plot.")

def run_original_stl_to_supported_stl(model_name: str, output_root_folder: pathlib.Path, current_datetime_str: str):
    """
    Executes Pipeline 1-3-4: Original STL -> Create PySLM Supports -> Export Supported STL.
    """
    print(f"\n--- Running Pipeline 1-3-4: '{model_name}' (Original STL to Supported STL) ---")
    # Use a variável de caminho configurada globalmente
    original_file_path = BASE_MODELS_ORIGINAL_PECA / f"{model_name}.stl" 

    if not original_file_path.exists():
        print(f"Error: Original STL file '{original_file_path}' not found. Exiting.")
        return

    myPart = Part('Peca')
    myPart.setGeometry(str(original_file_path), fixGeometry=True)
    myPart.rotation = [0, 0, 0]
    myPart.scaleFactor = 1.0
    myPart.dropToPlatform(5)

    overhangMesh = pyslm.support.getOverhangMesh(myPart, OVERHANG_ANGLE, splitMesh=False, useConnectivity=True)
    overhangMesh.visual.face_colors = [254.0, 0., 0., 254]

    supportGenerator = get_pyslm_support_generator()

    supportBlockRegions = supportGenerator.identifySupportRegions(myPart, OVERHANG_ANGLE, True)
    for block in supportBlockRegions:
        block.trussWidth = 1.0
    blockSupports = [block.supportVolume for block in supportBlockRegions]

    # Export GLB for initial visualization
    glb_output_path = output_root_folder / f"{model_name}_overhangSupport.glb"
    s1 = trimesh.Scene([myPart.geometry] + blockSupports)
    with open(glb_output_path, 'wb') as f:
        f.write(trimesh.exchange.gltf.export_glb(s1, include_normals=True))
    print(f"Initial support visualization exported to: {glb_output_path}")

    # Show initial block support visualization
    if blockSupports:
        s_block_viz = trimesh.Scene([myPart.geometry, overhangMesh] + blockSupports)
        print("Displaying initial block support visualization. Close window to continue.")
        s_block_viz.show()

    meshSupports = []
    for supportBlock in supportBlockRegions:
        supportBlock.mergeMesh = False
        supportBlock.useSupportSkin = True
        meshSupports.append(supportBlock.geometry())

    # Final visualization of part and mesh supports
    s2 = trimesh.Scene([overhangMesh, myPart.geometry] + meshSupports)
    print("Displaying final visualization of part with supports. Close window to continue.")
    s2.show()

    # Save combined model (Part + Supports) as STL (Block 4)
    combined_scene = trimesh.Scene()
    combined_scene.add_geometry(myPart.geometry)
    for support_mesh in meshSupports:
        combined_scene.add_geometry(support_mesh)

    # Add timestamp to the output STL filename
    output_stl_full_path = output_root_folder / f"{model_name}_combined_supported_{current_datetime_str}.stl"
    try:
        combined_scene.export(output_stl_full_path)
        print(f"Combined part and supports successfully saved to {output_stl_full_path}")
    except Exception as e:
        print(f"Error saving the combined STL file: {e}")

    print(f"Pipeline 1-3-4 for '{model_name}' completed.")


def run_original_stl_to_dxf_pipeline(model_name: str, output_root_folder: pathlib.Path, current_datetime_str: str, start_stage: int = 1):
    """
    Executes Pipeline 1-3-5: Original STL -> Create PySLM Supports -> Slice to DXF -> Clean DXF -> Machine TXT/DXF.
    This pipeline includes all 3 stages.
    """
    print(f"\n--- Running Pipeline 1-3-5: '{model_name}' (Original STL to Machine DXF) ---")

    output_dxf_bruto_folder = output_root_folder / "dxf_bruto"
    output_dxf_clean_folder = output_root_folder / "dxf_clean"
    output_txt_machine_folder = output_root_folder / "txt_maquina"

    output_dxf_bruto_folder.mkdir(parents=True, exist_ok=True)
    output_dxf_clean_folder.mkdir(parents=True, exist_ok=True)
    output_txt_machine_folder.mkdir(parents=True, exist_ok=True)

    # --- Stage 1: Generate Supports and Raw DXFs ---
    if start_stage <= 1:
        print("\n--- Stage 1: Generating supports and raw DXFs ---")
        # Use a variável de caminho configurada globalmente
        original_file_path = BASE_MODELS_ORIGINAL_PECA / f"{model_name}.stl"

        if not original_file_path.exists():
            print(f"Error: Original STL file '{original_file_path}' not found. Exiting.")
            return

        myPart = Part('Peca')
        myPart.setGeometry(str(original_file_path), fixGeometry=True)
        myPart.rotation = [0, 0, 0]
        myPart.scaleFactor = 1.0
        myPart.dropToPlatform(5)

        overhangMesh = pyslm.support.getOverhangMesh(myPart, OVERHANG_ANGLE, splitMesh=False, useConnectivity=True)
        overhangMesh.visual.face_colors = [254.0, 0., 0., 254]

        supportGenerator = get_pyslm_support_generator()

        supportBlockRegions = supportGenerator.identifySupportRegions(myPart, OVERHANG_ANGLE, True)
        for block in supportBlockRegions:
            block.trussWidth = 1.0
        blockSupports = [block.supportVolume for block in supportBlockRegions]

        # Show initial block support visualization (Block 3 preview)
        if blockSupports:
            s_block_viz = trimesh.Scene([myPart.geometry, overhangMesh] + blockSupports)
            print("Displaying initial block support visualization. Close window to continue.")
            s_block_viz.show()

        meshSupports = []
        for supportBlock in supportBlockRegions:
            supportBlock.mergeMesh = False
            supportBlock.useSupportSkin = True
            meshSupports.append(supportBlock.geometry())

        # Show final mesh support visualization (Block 3 preview)
        s_final_viz = trimesh.Scene([overhangMesh, myPart.geometry] + meshSupports)
        print("Displaying final mesh support visualization. Close window to continue.")
        s_final_viz.show()

        # Slice and export raw DXF layers (Block 5)
        _slice_and_export_dxf_layers(myPart, meshSupports, output_dxf_bruto_folder, model_name)

    # --- Stage 2: Clean Raw DXFs and Generate Optional Combined STL ---
    if start_stage <= 2:
        print("\n--- Stage 2: Cleaning raw DXFs and generating clean DXFs (and optional combined STL) ---")
        dxf_files_bruto = sorted([f for f in os.listdir(output_dxf_bruto_folder) if f.lower().endswith('.dxf')])
        all_meshes_for_stl = []
        z_offset = 0.0 # for STL generation

        if not dxf_files_bruto:
            print(f"No raw DXF files found in: {output_dxf_bruto_folder}. Skipping cleaning.")
        else:
            print("Starting processing of DXF layers (extracting lines and generating clean DXFs)...")
            for dxf_file in tqdm(dxf_files_bruto, desc="Generating Clean DXF"):
                dxf_path_bruto = output_dxf_bruto_folder / dxf_file
                line_segments_2d = get_line_segments_from_dxf(dxf_path_bruto)

                if not line_segments_2d:
                    print(f"Warning: No valid lines or polylines found in {dxf_file}. Skipping this layer.")
                    z_offset += LAYER_THICKNESS
                    continue

                output_clean_dxf_path = output_dxf_clean_folder / f"clean_{dxf_file}"
                create_simplified_dxf_for_laser(line_segments_2d, output_clean_dxf_path)

                # Generate STL from clean DXF (optional)
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
                        logging.error(f"Error extruding line segment in {dxf_file} for STL: {e}")
                all_meshes_for_stl.extend(current_layer_meshes)
                z_offset += LAYER_THICKNESS

            if not all_meshes_for_stl:
                print("No 3D solid created from DXF files for STL (possibly due to empty layers).")
            else:
                output_stl_path = output_root_folder / f"{model_name}_combined_cleaned_{current_datetime_str}.stl"
                combined_mesh = trimesh.util.concatenate(all_meshes_for_stl)
                combined_mesh.export(output_stl_path)
                print(f"\n3D Model '{output_stl_path.name}' successfully generated at: {output_stl_path}")
        print("\nDXF cleaning process completed.")

    # --- Stage 3: Convert Clean DXFs to Machine Format (TXT/DXF) ---
    if start_stage <= 3:
        print("\n--- Stage 3: Converting clean DXFs to machine format (.dxf simplified) ---")
        dxf_files_clean = sorted([f for f in os.listdir(output_dxf_clean_folder) if f.lower().endswith('.dxf')])

        if not dxf_files_clean:
            print(f"No 'clean' DXF files found in '{output_dxf_clean_folder}'. Skipping conversion to machine format.")
        else:
            print(f"Starting batch conversion of {len(dxf_files_clean)} clean DXF files...")
            for filename in tqdm(dxf_files_clean, desc="Generating Machine DXF"):
                input_file_path = output_dxf_clean_folder / filename
                base_filename = input_file_path.stem
                output_file_path = output_txt_machine_folder / f"machine_{base_filename}.dxf"
                convert_dxf_to_lines_only_machine_format(input_file_path, output_file_path)
        print("\nMachine format conversion completed.")

        # Generate manufacturing parameters file at the end of the DXF pipeline
        generate_manufacturing_parameters_file(
            output_txt_machine_folder,
            output_root_folder,
            model_name,
            LAYER_THICKNESS
        )

    print(f"Pipeline 1-3-5 for '{model_name}' completed.")

def run_supported_stl_to_dxf_pipeline(model_name: str, output_root_folder: pathlib.Path, current_datetime_str: str, start_stage: int = 1):
    """
    Executes Pipeline 2-5: Already Supported STL -> Slice to DXF -> Clean DXF -> Machine TXT/DXF.
    This pipeline assumes the input STL already contains supports.
    """
    print(f"\n--- Running Pipeline 2-5: '{model_name}' (Supported STL to Machine DXF) ---")

    output_dxf_bruto_folder = output_root_folder / "dxf_bruto"
    output_dxf_clean_folder = output_root_folder / "dxf_clean"
    output_txt_machine_folder = output_root_folder / "txt_maquina"

    output_dxf_bruto_folder.mkdir(parents=True, exist_ok=True)
    output_dxf_clean_folder.mkdir(parents=True, exist_ok=True)
    output_txt_machine_folder.mkdir(parents=True, exist_ok=True)

    # --- Stage 1: Slice Supported STL to Raw DXFs ---
    if start_stage <= 1:
        print("\n--- Stage 1: Slicing supported STL to raw DXFs ---")
        # Use a variável de caminho configurada globalmente
        supported_stl_path = BASE_MODELS_ORIGINAL_SUPORTE / f"{model_name}.stl"

        # Explicitly state the input folder for Block 2
        print(f"Loading supported STL from: {supported_stl_path}")

        if not supported_stl_path.exists():
            print(f"Error: Supported STL file '{supported_stl_path}' not found. Exiting.")
            return

        # Load the pre-supported STL as the main part
        supported_part = Part(model_name)
        supported_part.setGeometry(str(supported_stl_path), fixGeometry=True)
        # myPart.rotation e myPart.scaleFactor podem ser adicionados aqui se necessário para o STL já suportado
        # supported_part.origin[0], supported_part.origin[1] = 5.0, 2.5 # Exemplo de origem de STL_solid_support_to_DXF.py
        supported_part.dropToPlatform() # Adjust as needed for your specific STL positioning

        # No additional PySLM supports are generated here as the STL is assumed to be pre-supported
        _slice_and_export_dxf_layers(supported_part, [], output_dxf_bruto_folder, model_name)

    # --- Stage 2 & 3: DXF Cleaning and Machine Format Conversion (Same as 1-3-5 pipeline) ---
    if start_stage <= 2:
        print("\n--- Stage 2: Cleaning raw DXFs and generating clean DXFs (and optional combined STL) ---")
        dxf_files_bruto = sorted([f for f in os.listdir(output_dxf_bruto_folder) if f.lower().endswith('.dxf')])
        all_meshes_for_stl = []
        z_offset = 0.0

        if not dxf_files_bruto:
            print(f"No raw DXF files found in: {output_dxf_bruto_folder}. Skipping cleaning.")
        else:
            print("Starting processing of DXF layers (extracting lines and generating clean DXFs)...")
            for dxf_file in tqdm(dxf_files_bruto, desc="Generating Clean DXF"):
                dxf_path_bruto = output_dxf_bruto_folder / dxf_file
                line_segments_2d = get_line_segments_from_dxf(dxf_path_bruto)

                if not line_segments_2d:
                    print(f"Warning: No valid lines or polylines found in {dxf_file}. Skipping this layer.")
                    z_offset += LAYER_THICKNESS
                    continue

                output_clean_dxf_path = output_dxf_clean_folder / f"clean_{dxf_file}"
                create_simplified_dxf_for_laser(line_segments_2d, output_clean_dxf_path)

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
                        logging.error(f"Error extruding line segment in {dxf_file} for STL: {e}")
                all_meshes_for_stl.extend(current_layer_meshes)
                z_offset += LAYER_THICKNESS

            if not all_meshes_for_stl:
                print("No 3D solid created from DXF files for STL (possibly due to empty layers).")
            else:
                output_stl_path = output_root_folder / f"{model_name}_combined_cleaned_{current_datetime_str}.stl"
                combined_mesh = trimesh.util.concatenate(all_meshes_for_stl)
                combined_mesh.export(output_stl_path)
                print(f"\n3D Model '{output_stl_path.name}' successfully generated at: {output_stl_path}")
        print("\nDXF cleaning process completed.")

    if start_stage <= 3:
        print("\n--- Stage 3: Converting clean DXFs to machine format (.dxf simplified) ---")
        dxf_files_clean = sorted([f for f in os.listdir(output_dxf_clean_folder) if f.lower().endswith('.dxf')])

        if not dxf_files_clean:
            print(f"No 'clean' DXF files found in '{output_dxf_clean_folder}'. Skipping conversion to machine format.")
        else:
            print(f"Starting batch conversion of {len(dxf_files_clean)} clean DXF files...")
            for filename in tqdm(dxf_files_clean, desc="Generating Machine DXF"):
                input_file_path = output_dxf_clean_folder / filename
                base_filename = input_file_path.stem
                output_file_path = output_txt_machine_folder / f"machine_{base_filename}.dxf"
                convert_dxf_to_lines_only_machine_format(input_file_path, output_file_path)
        print("\nMachine format conversion completed.")

        generate_manufacturing_parameters_file(
            output_txt_machine_folder,
            output_root_folder,
            model_name,
            LAYER_THICKNESS
        )

    print(f"Pipeline 2-5 for '{model_name}' completed.")

# --- Main Execution Logic ---
if __name__ == "__main__":
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("Usage: python unified_pyslm_pipeline.py <model_name> <pipeline_type> [start_stage_for_dxf_pipelines]")
        print("  <model_name>: Name of the STL file (e.g., 'Aleta_mini')")
        print("  <pipeline_type>: '1-3-4', '1-3-5', or '2-5'")
        print("  [start_stage_for_dxf_pipelines]: Optional, 1, 2, or 3 (for '1-3-5' and '2-5' pipelines only, defaults to 1)")
        print("Example: python unified_pyslm_pipeline.py MyPart 1-3-5")
        sys.exit(1)

    model_name = sys.argv[1]
    pipeline_type = sys.argv[2]
    start_stage = 1 # Default for DXF pipelines

    if len(sys.argv) == 4:
        try:
            start_stage = int(sys.argv[3])
            if start_stage not in [1, 2, 3]:
                raise ValueError
        except ValueError:
            print("Error: start_stage_for_dxf_pipelines must be 1, 2, or 3.")
            sys.exit(1)

    # Determina o diretório do script para caminhos relativos padrão
    # Se você optou por caminhos absolutos ou relativos ao HOME_DIR, esta linha ainda é inofensiva.
    # A variável _script_dir_ já foi definida no bloco de configuração de caminhos.
    # script_dir = pathlib.Path(__file__).parent 
    
    # Use as variáveis de caminho globalmente definidas
    # base_models_original_peca já é BASE_MODELS_ORIGINAL_PECA, etc.
    # Não precisamos mais destas redefinições aqui:
    # base_models_original_peca = script_dir / "models" / "original" / "Peca"
    # base_models_original_suporte = script_dir / "models" / "original" / "suporte"
    # base_dxfs_path = script_dir / "dxfs"

    # Generate timestamp for the output folder and filenames
    current_datetime_str = datetime.datetime.now().strftime("%Y%m%d%H%M")
    output_root_folder_name = f"{model_name}_{current_datetime_str}"
    output_root_folder = BASE_DXFS_PATH / output_root_folder_name # Usa BASE_DXFS_PATH
    output_root_folder.mkdir(parents=True, exist_ok=True) # Ensure main output folder exists

    print(f"All output files for '{model_name}' will be generated in: {output_root_folder}")

    if pipeline_type == "1-3-4":
        run_original_stl_to_supported_stl(model_name, output_root_folder, current_datetime_str)
    elif pipeline_type == "1-3-5":
        run_original_stl_to_dxf_pipeline(model_name, output_root_folder, current_datetime_str, start_stage)
    elif pipeline_type == "2-5":
        run_supported_stl_to_dxf_pipeline(model_name, output_root_folder, current_datetime_str, start_stage)
    else:
        print(f"Error: Invalid pipeline type '{pipeline_type}'. Choose '1-3-4', '1-3-5', or '2-5'.")
        sys.exit(1)

    print("\nUnified PySLM pipeline finished.")