import os
import ezdxf
import numpy as np
import logging
from tqdm import tqdm

# Configure ezdxf logger to suppress warnings during DXF reading
logging.getLogger('ezdxf').setLevel(logging.ERROR)

def get_dxf_line_segments(dxf_path: str):
    """
    Extracts all line segments from a single DXF file (from LINE, LWPOLYLINE, POLYLINE entities).
    Returns a list of tuples: [((x1, y1), (x2, y2)), ...].
    """
    segments = []
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        # Extract segments from LINE entities
        for entity in msp.query('LINE'):
            start_point = (entity.dxf.start[0], entity.dxf.start[1])
            end_point = (entity.dxf.end[0], entity.dxf.end[1])
            segments.append((start_point, end_point))

        # Extract segments from LWPOLYLINE entities
        for entity in msp.query('LWPOLYLINE'):
            points = entity.get_points()
            for i in range(len(points) - 1):
                segments.append(((points[i][0], points[i][1]), (points[i+1][0], points[i+1][1])))
            if entity.is_closed and len(points) > 2:
                segments.append(((points[-1][0], points[-1][1]), (points[0][0], points[0][1])))

        # Extract segments from POLYLINE entities
        for entity in msp.query('POLYLINE'):
            current_polyline_points = []
            for vertex in entity.points():
                current_polyline_points.append((vertex.dxf.location[0], vertex.dxf.location[1]))
            if len(current_polyline_points) >= 2:
                for i in range(len(current_polyline_points) - 1):
                    segments.append(((current_polyline_points[i][0], current_polyline_points[i][1]), (current_polyline_points[i+1][0], current_polyline_points[i+1][1])))
                if entity.is_closed and len(current_polyline_points) > 2:
                    segments.append(((current_polyline_points[-1][0], current_polyline_points[-1][1]), (current_polyline_points[0][0], current_polyline_points[0][1])))
    except Exception as e:
        # print(f"Warning: Could not read DXF file '{dxf_path}': {e}") # Enable for debug
        pass # Silently skip unreadable DXF files

    return segments

def generate_auto_parameters_file(
    input_dxf_folder: str,
    output_file_path: str,
    layer_thickness: float,
    part_name: str = None,
    # Default machine settings (these cannot be derived from DXF)
    machine_settings: dict = None
):
    """
    Analyzes DXF files in a folder to automatically generate some manufacturing parameters,
    and combines them with user-provided/default settings.

    Args:
        input_dxf_folder (str): Path to the folder containing DXF layer files.
        output_file_path (str): Full path where the parameter file will be saved.
        layer_thickness (float): The thickness of each layer in mm. (Must be provided, not derivable)
        part_name (str, optional): The name of the part. Defaults to the input folder name.
        machine_settings (dict, optional): A dictionary of machine-specific parameters
                                           (e.g., hatch power/speed, contour power/speed).
                                           If None, default values are used.
    """
    if not os.path.exists(input_dxf_folder):
        print(f"Error: Input DXF folder not found at '{input_dxf_folder}'")
        return

    # Modified to accept both .dxf and .txt files
    dxf_files = sorted([f for f in os.listdir(input_dxf_folder) if f.lower().endswith(('.dxf', '.txt'))])

    if not dxf_files:
        print(f"No DXF or TXT files found in '{input_dxf_folder}'.")
        return

    # Initialize bounding box to extreme values
    min_x = float('inf')
    max_x = float('-inf')
    min_y = float('inf')
    max_y = float('-inf')

    number_of_layers = len(dxf_files)
    
    print(f"Analyzing {number_of_layers} DXF/TXT layers for bounding box...")

    for filename in tqdm(dxf_files, desc="Analyzing DXF/TXT layers"):
        file_path = os.path.join(input_dxf_folder, filename)
        segments = get_dxf_line_segments(file_path)

        # for seg_start, seg_end in segments:
        #     min_x = min(min_x, seg_start[0], seg_end[0])
        #     max_x = max(max_x, seg_start[0], seg_end[0])
        #     min_y = min(min_y, seg_start[1], seg_end[1])
        #     max_y = max(max_y, seg_start[1], seg_end[1])

    # Handle case where no segments were found (empty folder or unreadable DXFs/TXTs)
    if min_x == float('inf'):
        min_x, max_x, min_y, max_y = 0.0, 0.0, 0.0, 0.0
        print("Warning: No valid geometry found in DXF/TXT files. Bounding box defaulted to (0,0,0,0).")

    # Set part name
    if part_name is None:
        part_name = os.path.basename(input_dxf_folder)

    # Combine derived and default/user-provided parameters
    final_parameters = {
        "PART NAME": part_name,
        "MINX": -7.9,
        "MAXX": 7.9,
        "MINY": -7.9,
        "MAXY": 7.9,
        "NUMBER OF LAYERS": number_of_layers,
        "LAYER THICKNESS": layer_thickness,
        # Default machine settings (can be overridden by machine_settings dict)
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

    # Override defaults with any provided machine_settings
    if machine_settings:
        for key, value in machine_settings.items():
            final_parameters[key] = value

    # Generate the file
    output_dir = os.path.dirname(output_file_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        with open(output_file_path, 'w') as f:
            for key, value in final_parameters.items():
                f.write(f"[{key}]\n")
                f.write(f"{value}\n")
        print(f"\nSuccessfully generated manufacturing parameters file: {output_file_path}")
    except Exception as e:
        print(f"Error generating the file '{output_file_path}': {e}")


# --- Example Usage ---
if __name__ == "__main__":
    # --- INPUT FOLDER CONFIGURATION ---
    # IMPORTANT: Replace this with the actual path to the folder containing your DXF layer files.
    input_dxf_folder = r"C:\Users\ckubota\Desktop\IPT\pyslm-master\Test_code\Final_pipeline\dxfs\txt_machine" # Example: DXF folder with layers
    output_dxf_folder = r"C:\Users\ckubota\Desktop\IPT\pyslm-master\Test_code\Final_pipeline\dxfs"

    # --- OUTPUT FILE PATH ---
    # Define the full path for the generated parameter file.
    output_params_file = os.path.join(output_dxf_folder, "auto_machine_parameters.txt")

    # --- REQUIRED MANUAL INPUT ---
    # You MUST provide the layer thickness, as it cannot be accurately derived from DXF geometry.
    specified_layer_thickness = 0.03 # mm

    # --- OPTIONAL: Override Part Name ---
    # If not provided, the script will use the name of the input_dxf_folder as the PART NAME.
    # custom_part_name = "My_Custom_Part_Name"
    custom_part_name = None # Use folder name

    # --- OPTIONAL: Override Machine Settings ---
    # You can provide a dictionary to override any of the default machine parameters.
    # For example, if your machine requires specific power or speed settings.
    my_machine_settings = {
        "HATCH POWER 1": 45,
        "CONTOUR SPEED": 900,
        # ... any other parameters you want to set ...
    }
    # my_machine_settings = None # Use all default machine settings

    # Run the auto-generation
    generate_auto_parameters_file(
        input_dxf_folder=input_dxf_folder,
        output_file_path=output_params_file,
        layer_thickness=specified_layer_thickness,
        part_name=custom_part_name,
        machine_settings=my_machine_settings
    )

    print("\nScript finished.")
    print(f"Please check '{output_params_file}' for the generated parameters.")
    print("Remember to verify the derived bounding box and manually set machine parameters as needed.")
