import logging
import sys
import datetime
import pathlib

import trimesh
import trimesh.exchange.gltf
import pyslm.support
from pyslm.core import Part

# Import modules
from modules.parameters import (
    OVERHANG_ANGLE,
    LAYER_THICKNESS,
    BASE_MODELS_ORIGINAL_PECA,
    BASE_MODELS_ORIGINAL_SUPORTE,
    BASE_DXFS_PATH,
    get_pyslm_support_generator,
    PART_ROTATION, # New import
    PART_SCALE_FACTOR # New import
)
from modules.geometry_processing import (
    slice_and_export_raw_dxfs,
    clean_raw_dxfs_and_generate_stl,
    convert_clean_dxfs_to_machine_format,
    generate_manufacturing_parameters_file
)

# --- Logging Configuration ---
logging.getLogger().setLevel(logging.INFO)
logging.getLogger('ezdxf').setLevel(logging.ERROR)

# --- Block-specific Functions (High-level steps of the pipelines) ---

def load_original_stl(model_name: str) -> Part:
    """
    Block 1: Loads an original STL file and initializes a PySLM Part object.
    Applies rotation and scale factor from parameters.
    """
    print(f"\n--- Block 1: Reading Pure STL (Original) for '{model_name}.stl' ---")
    original_file_path = BASE_MODELS_ORIGINAL_PECA / f"{model_name}.stl"
    if not original_file_path.exists():
        raise FileNotFoundError(f"Error: Original STL file '{original_file_path}' not found.")

    myPart = Part('Peca')
    myPart.setGeometry(str(original_file_path), fixGeometry=True)
    myPart.rotation = PART_ROTATION # Using constant
    myPart.scaleFactor = PART_SCALE_FACTOR # Using constant
    myPart.dropToPlatform(5) # Adjust drop height as needed
    return myPart

def load_supported_stl(model_name: str) -> Part:
    """
    Block 2: Loads an STL file that is assumed to already contain supports,
    and initializes a PySLM Part object.
    Applies rotation and scale factor from parameters.
    """
    print(f"\n--- Block 2: Reading Already Supported STL for '{model_name}.stl' ---")
    supported_stl_path = BASE_MODELS_ORIGINAL_SUPORTE / f"{model_name}.stl"
    print(f"Loading supported STL from: {supported_stl_path}")
    if not supported_stl_path.exists():
        raise FileNotFoundError(f"Error: Supported STL file '{supported_stl_path}' not found.")

    supported_part = Part(model_name)
    supported_part.setGeometry(str(supported_stl_path), fixGeometry=True)
    # Apply rotation and scale factor also to supported parts if needed,
    # assuming they might be positioned differently or need scaling.
    supported_part.rotation = PART_ROTATION
    supported_part.scaleFactor = PART_SCALE_FACTOR
    supported_part.dropToPlatform() # Adjust as needed for your specific STL positioning
    return supported_part

def generate_pyslm_supports(myPart: Part) -> (list, trimesh.Trimesh):
    """
    Block 3: Generates PySLM block and mesh supports for the given part.
    Includes visualization steps.
    Returns meshSupports (list of trimesh objects) and overhangMesh.
    """
    print("\n--- Block 3: Creating PySLM Supports ---")
    overhangMesh = pyslm.support.getOverhangMesh(myPart, OVERHANG_ANGLE, splitMesh=False, useConnectivity=True)
    overhangMesh.visual.face_colors = [254.0, 0., 0., 254] # Red color for overhangs

    supportGenerator = get_pyslm_support_generator()

    supportBlockRegions = supportGenerator.identifySupportRegions(myPart, OVERHANG_ANGLE, True)
    for block in supportBlockRegions:
        block.trussWidth = 1.0
    blockSupports = [block.supportVolume for block in supportBlockRegions]

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
    s_final_viz = trimesh.Scene([overhangMesh, myPart.geometry] + meshSupports)
    print("Displaying final visualization of part with supports. Close window to continue.")
    s_final_viz.show()
    
    return meshSupports, overhangMesh

def export_supported_stl(myPart: Part, mesh_supports: list, output_folder: pathlib.Path, model_name: str, current_datetime_str: str):
    """
    Block 4: Combines the original part with generated mesh supports and exports as an STL.
    Also exports a GLB for initial visualization.
    """
    print("\n--- Block 4: Exporting STL with PySLM Supports ---")
    # Export GLB for initial visualization
    glb_output_path = output_folder / f"{model_name}_overhangSupport.glb"
    s1 = trimesh.Scene([myPart.geometry] + mesh_supports)
    with open(glb_output_path, 'wb') as f:
        f.write(trimesh.exchange.gltf.export_glb(s1, include_normals=True))
    print(f"Initial support visualization exported to: {glb_output_path}")

    # Save combined model (Part + Supports) as STL
    combined_scene = trimesh.Scene()
    combined_scene.add_geometry(myPart.geometry)
    for support_mesh in mesh_supports:
        combined_scene.add_geometry(support_mesh)

    output_stl_full_path = output_folder / f"{model_name}_combined_supported_{current_datetime_str}.stl"
    try:
        combined_scene.export(output_stl_full_path)
        print(f"Combined part and supports successfully saved to {output_stl_full_path}")
    except Exception as e:
        print(f"Error saving the combined STL file: {e}")

# --- Core Pipeline Functions ---

def run_original_stl_to_supported_stl(model_name: str, output_root_folder: pathlib.Path, current_datetime_str: str):
    """
    Executes Pipeline 1-3-4: Original STL -> Create PySLM Supports -> Export Supported STL.
    """
    print(f"\n--- Running Pipeline 1-3-4: '{model_name}' (Original STL to Supported STL) ---")
    
    # Call Block 1: Load Original STL
    try:
        myPart = load_original_stl(model_name)
    except FileNotFoundError as e:
        print(e)
        return

    # Call Block 3: Generate PySLM Supports
    meshSupports, _ = generate_pyslm_supports(myPart)

    # Call Block 4: Export STL with PySLM Supports
    export_supported_stl(myPart, meshSupports, output_root_folder, model_name, current_datetime_str)

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
        print("\n--- Starting Stage 1 of 1-3-5 Pipeline: Generate Supports and Raw DXFs ---")
        try:
            # Call Block 1: Load Original STL
            myPart = load_original_stl(model_name)
        except FileNotFoundError as e:
            print(e)
            return
        
        # Call Block 3: Generate PySLM Supports
        meshSupports, _ = generate_pyslm_supports(myPart)
        
        # Call Block 5 - Stage 1: Slice and Export Raw DXFs
        slice_and_export_raw_dxfs(myPart, meshSupports, output_dxf_bruto_folder, model_name)
    else:
        print(f"\n--- Skipping Stage 1, starting from Stage {start_stage} ---")


    # --- Stage 2: Clean Raw DXFs and Generate Optional Combined STL ---
    if start_stage <= 2:
        print("\n--- Starting Stage 2 of 1-3-5 Pipeline: Clean Raw DXFs and Generate Optional Combined STL ---")
        # Call Block 5 - Stage 2: Clean Raw DXFs and Generate STL
        clean_raw_dxfs_and_generate_stl(output_dxf_bruto_folder, output_dxf_clean_folder, output_root_folder, model_name, current_datetime_str)
    else:
        print(f"\n--- Skipping Stage 2, starting from Stage {start_stage} ---")


    # --- Stage 3: Convert Clean DXFs to Machine Format (TXT/DXF) ---
    if start_stage <= 3:
        print("\n--- Starting Stage 3 of 1-3-5 Pipeline: Convert Clean DXFs to Machine Format ---")
        # Call Block 5 - Stage 3: Convert Clean DXFs to Machine Format
        convert_clean_dxfs_to_machine_format(output_dxf_clean_folder, output_txt_machine_folder)
        
        # Generate manufacturing parameters file (related to Block 5 output)
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
        print("\n--- Starting Stage 1 of 2-5 Pipeline: Slice Supported STL to Raw DXFs ---")
        try:
            # Call Block 2: Load Supported STL
            supported_part = load_supported_stl(model_name)
        except FileNotFoundError as e:
            print(e)
            return
        
        # Call Block 5 - Stage 1: Slice and Export Raw DXFs (no new supports generated here)
        slice_and_export_raw_dxfs(supported_part, [], output_dxf_bruto_folder, model_name)
    else:
        print(f"\n--- Skipping Stage 1, starting from Stage {start_stage} ---")


    # --- Stage 2: DXF Cleaning and Optional Combined STL Generation ---
    if start_stage <= 2:
        print("\n--- Starting Stage 2 of 2-5 Pipeline: Clean Raw DXFs and Generate Optional Combined STL ---")
        # Call Block 5 - Stage 2: Clean Raw DXFs and Generate STL
        clean_raw_dxfs_and_generate_stl(output_dxf_bruto_folder, output_dxf_clean_folder, output_root_folder, model_name, current_datetime_str)
    else:
        print(f"\n--- Skipping Stage 2, starting from Stage {start_stage} ---")

    # --- Stage 3: Convert Clean DXFs to Machine Format (TXT/DXF) ---
    if start_stage <= 3:
        print("\n--- Starting Stage 3 of 2-5 Pipeline: Convert Clean DXFs to Machine Format ---")
        # Call Block 5 - Stage 3: Convert Clean DXFs to Machine Format
        convert_clean_dxfs_to_machine_format(output_dxf_clean_folder, output_txt_machine_folder)
        
        # Generate manufacturing parameters file (related to Block 5 output)
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
    
    # Generate timestamp for the output folder and filenames
    current_datetime_str = datetime.datetime.now().strftime("%Y%m%d%H%M")
    output_root_folder_name = f"{model_name}_{current_datetime_str}"
    output_root_folder = BASE_DXFS_PATH / output_root_folder_name
    output_root_folder.mkdir(parents=True, exist_ok=True)

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
