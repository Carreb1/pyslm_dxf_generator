import logging
import os
import pathlib
import ezdxf
import numpy as np
import trimesh
import trimesh.util
from tqdm import tqdm

from matplotlib import pyplot as plt
from pyslm.geometry import Layer, ContourGeometry, HatchGeometry
from pyslm import hatching
import pyslm.support
import pyslm.visualise

# Import constants from parameters module
from modules.parameters import (
    LAYER_THICKNESS,
    OVERHANG_ANGLE,
    get_pyslm_support_generator,
    HATCH_ANGLE_INITIAL,
    HATCH_ANGLE_INCREMENT, # New import
    VOLUME_OFFSET_HATCH,
    SPOT_COMPENSATION,
    STRIPE_WIDTH,
    NUM_INNER_CONTOURS,
    NUM_OUTER_CONTOURS,
    HATCH_SORT_METHOD
)

# --- Logging Configuration ---
logging.getLogger().setLevel(logging.INFO)
logging.getLogger('ezdxf').setLevel(logging.ERROR) # Suppress INFO/WARNING from ezdxf

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

def slice_and_export_raw_dxfs(part_to_slice, supports_to_slice: list, output_dxf_bruto_folder: pathlib.Path, model_name: str):
    """
    Slices the given part and (optional) supports into DXF layers.
    Exports raw DXF files to the specified bruto folder.
    This function was previously _slice_and_export_dxf_layers.
    """
    print("\n--- Slicing to Raw DXFs ---")
    min_z_part = part_to_slice.boundingBox[2]
    max_z_part = part_to_slice.boundingBox[5]

    if supports_to_slice:
        support_combined_mesh = trimesh.util.concatenate(supports_to_slice)
        min_z_support = support_combined_mesh.bounds[0, 2]
        max_z_support = support_combined_mesh.bounds[1, 2]
    else:
        min_z_support = min_z_part # If no supports, consider only part bounds
        max_z_support = max_z_part

    min_z_overall = min(min_z_part, min_z_support)
    max_z_overall = max(max_z_part, max_z_support)

    all_layers_combined = []
    h = hatching.Hatcher()
    h.hatchAngle = HATCH_ANGLE_INITIAL # Using constant
    h.volumeOffsetHatch = VOLUME_OFFSET_HATCH # Using constant
    h.spotCompensation = SPOT_COMPENSATION # Using constant
    h.stripeWidth = STRIPE_WIDTH # Using constant
    h.numInnerContours = NUM_INNER_CONTOURS # Using constant
    h.numOuterContours = NUM_OUTER_CONTOURS # Using constant
    h.hatchSortMethod = HATCH_SORT_METHOD # Using constant

    print(f"Slicing and processing layers for '{model_name}' (Raw DXF)...")
    layer_idx = 0
    num_layers = int(np.ceil((max_z_overall - min_z_overall) / LAYER_THICKNESS))
    if num_layers == 0 and max_z_overall > min_z_overall:
        num_layers = 1
    elif max_z_overall <= min_z_overall:
        print(f"Warning: Part '{model_name}' has zero or negative height. No layers will be generated.")
        return

    z_positions = np.arange(min_z_overall, max_z_overall + LAYER_THICKNESS / 2, LAYER_THICKNESS)
    if len(z_positions) == 0 and num_layers == 1:
         z_positions = [min_z_overall]
    
    for zPos in tqdm(z_positions, total=num_layers, desc="Generating Raw DXF"):
        current_layer = Layer()
        current_layer.z = int(zPos * 1000)

        h.hatchAngle += HATCH_ANGLE_INCREMENT # Using constant
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
            dxf_name = output_dxf_bruto_folder / f"{model_name}_layer{layer_idx}.dxf"
            export_layer_to_dxf(current_layer, dxf_name)
        layer_idx += 1

    print("\nPlotting a sample of combined layers (raw DXFs)...")
    if all_layers_combined:
        pyslm.visualise.plotLayers(all_layers_combined[::max(1, len(all_layers_combined) // 20)])
        plt.show()
    else:
        print("No raw layers generated to plot.")

def clean_raw_dxfs_and_generate_stl(output_dxf_bruto_folder: pathlib.Path, output_dxf_clean_folder: pathlib.Path, output_root_folder: pathlib.Path, model_name: str, current_datetime_str: str):
    """
    Reads raw DXF files, extracts and simplifies line entities,
    and creates new "cleaned" DXF files. Optionally reconstructs a 3D STL model.
    """
    print("\n--- Cleaning Raw DXFs & Generating Clean DXFs (and optional combined STL) ---")
    dxf_files_bruto = sorted([f for f in os.listdir(output_dxf_bruto_folder) if f.lower().endswith('.dxf')])
    all_meshes_for_stl = []
    z_offset = 0.0 # for STL generation

    if not dxf_files_bruto:
        print(f"No raw DXF files found in: {output_dxf_bruto_folder}. Skipping cleaning.")
        return

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
                path_2d = trimesh.load_path(np.array(segment_2d).reshape(-1, 2), process=False)
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

def convert_clean_dxfs_to_machine_format(output_dxf_clean_folder: pathlib.Path, output_txt_machine_folder: pathlib.Path):
    """
    Converts clean DXF files to a simplified machine-readable format.
    """
    print("\n--- Converting Clean DXFs to Machine Format (.dxf simplified) ---")
    dxf_files_clean = sorted([f for f in os.listdir(output_dxf_clean_folder) if f.lower().endswith('.dxf')])

    if not dxf_files_clean:
        print(f"No 'clean' DXF files found in '{output_dxf_clean_folder}'. Skipping conversion to machine format.")
        return

    print(f"Starting batch conversion of {len(dxf_files_clean)} clean DXF files...")
    for filename in tqdm(dxf_files_clean, desc="Generating Machine DXF"):
        input_file_path = output_dxf_clean_folder / filename
        base_filename = input_file_path.stem
        output_file_path = output_txt_machine_folder / f"machine_{base_filename}.dxf"
        convert_dxf_to_lines_only_machine_format(input_file_path, output_file_path)
    print("\nMachine format conversion completed.")
