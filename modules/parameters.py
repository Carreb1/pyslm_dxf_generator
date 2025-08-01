import pathlib
import pyslm.support
from pyslm import hatching # Added for hatchSortMethod

# --- GLOBAL CONSTANTS ---
# All linear units are in millimeters [mm], and angles are in degrees [deg].
OVERHANG_ANGLE = 55  # [deg] - Overhang angle for support generation.
LAYER_THICKNESS = 0.03 # [mm] - Thickness of each sliced layer.

# --- PART TRANSFORMATION PARAMETERS ---
PART_ROTATION = [0, 0, 0] # [deg] - Rotation of the part around X, Y, Z axes.
PART_SCALE_FACTOR = 1.0 # Multiplicative factor to adjust part size (e.g., 1.0 for original).

# --- HATCHING PARAMETERS (Block 5 Slicing) ---
# All linear units are in millimeters [mm], and angles are in degrees [deg].
HATCH_ANGLE_INITIAL = 10.0 # [deg] - Initial hatch angle for the first layer.
HATCH_ANGLE_INCREMENT = 66.7 # [deg] - Increment for hatch angle per layer.
VOLUME_OFFSET_HATCH = 0.08 # [mm] - Offset distance for volume hatching.
SPOT_COMPENSATION = 0.06 # [mm] - Compensation for laser spot size.
STRIPE_WIDTH = 0.07 # [mm] - Width of the hatching stripes.
NUM_INNER_CONTOURS = 2 # Number of inner contours.
NUM_OUTER_CONTOURS = 1 # Number of outer contours.
HATCH_SORT_METHOD = hatching.AlternateSort() # Instance of the sorting method for hatching.

# --- PATH CONFIGURATION ---
# You can edit these paths to point to your folders.
# The script will try to determine the base directory automatically for relative paths.

# Default: Paths relative to the script's own directory
# This is the default configuration if you don't uncomment any of the options below.
# _script_dir_ now refers to the directory of parameters.py (modules/)
_module_dir_ = pathlib.Path(__file__).parent
# To get to the project root, we go up one level from the modules directory
_project_root_ = _module_dir_.parent

BASE_MODELS_ORIGINAL_PECA = _project_root_ / "models" / "original" / "Peca"
BASE_MODELS_ORIGINAL_SUPORTE = _project_root_ / "models" / "original" / "suporte"
BASE_DXFS_PATH = _project_root_ / "dxfs"

# Option 1: Use absolute paths (uncomment and edit for your actual path)
# BASE_MODELS_ORIGINAL_PECA = pathlib.Path(r"C:\Users\YourUser\Documents\My3DModels\OriginalParts")
# BASE_MODELS_ORIGINAL_SUPORTE = pathlib.Path(r"C:\Users\YourUser\Documents\My3DModels\SupportedModels")
# BASE_DXFS_PATH = pathlib.Path(r"C:\Users\YourUser\Documents\DXFOutputs")

# Option 2: Use paths relative to the user's HOME directory (uncomment and edit)
# home_dir = pathlib.Path.home()
# BASE_MODELS_ORIGINAL_PECA = home_dir / "IPT_Pipeline_Data" / "models" / "original" / "Peca"
# BASE_MODELS_ORIGINAL_SUPORTE = home_dir / "IPT_Pipeline_Data" / "models" / "original" / "suporte"
# BASE_DXFS_PATH = home_dir / "IPT_Pipeline_Data" / "dxfs"

# --- Centralized Support Parameters (Block 3 Parameters) ---
def get_pyslm_support_generator():
    """
    Returns a pre-configured pyslm.support.GridBlockSupportGenerator with consistent parameters.
    All linear units for support generation are in millimeters [mm].
    """
    supportGenerator = pyslm.support.GridBlockSupportGenerator()
    supportGenerator.rayProjectionResolution = 0.07 # [mm] - Resolution for ray projection.
    supportGenerator.innerSupportEdgeGap = 0.3 # [mm] - Gap between inner support edges.
    supportGenerator.outerSupportEdgeGap = 0.3 # [mm] - Gap between outer support edges.
    supportGenerator.simplifyPolygonFactor = 0.5 # Factor for simplifying polygons.
    supportGenerator.minimumAreaThreshold = 0.05 # [mm^2] - Minimum area threshold for support regions.
    supportGenerator.triangulationSpacing = 4 # [mm] - Spacing for triangulation.
    supportGenerator.supportBorderDistance = 1.0 # [mm] - Distance from part border to support.
    supportGenerator.numSkinMeshSubdivideIterations = 2 # Number of iterations for skin mesh subdivision.

    supportGenerator.useUpperSupportTeeth = True # Boolean - Use teeth on upper support.
    supportGenerator.useLowerSupportTeeth = True # Boolean - Use teeth on lower support.
    supportGenerator.supportWallThickness = 0.7 # [mm] - Thickness of support walls.
    supportGenerator.supportTeethTopLength = 0.1 # [mm] - Length of support teeth at the top.
    supportGenerator.supportTeethHeight = 1 # [mm] - Height of support teeth.
    supportGenerator.supportTeethBaseInterval = 1.5 # [mm] - Interval between support teeth bases.
    supportGenerator.supportTeethUpperPenetration = 0.05 # [mm] - Upper penetration of support teeth.
    supportGenerator.trussWidth = 0.5 # [mm] - Width of the truss structure in block supports.
    supportGenerator.supportTeethBottomLength = 0.3 # [mm] - Length of support teeth at the bottom.

    supportGenerator.splineSimplificationFactor = 10 # Factor for spline simplification.
    supportGenerator.gridSpacing = [1.5, 1.5] # [mm, mm] - Spacing of the support grid in X and Y.
    return supportGenerator
