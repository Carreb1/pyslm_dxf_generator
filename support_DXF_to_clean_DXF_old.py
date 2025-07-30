import ezdxf
import trimesh
import numpy as np
import os
from tqdm import tqdm
import logging # Importa o módulo logging

# Configura o logger do ezdxf para suprimir avisos
# Você pode ajustar o nível de WARNING para ERROR se quiser ver apenas erros críticos
logging.getLogger('ezdxf').setLevel(logging.ERROR) 

# Resto do seu código...

# Função para extrair segmentos de linha de um arquivo DXF
def get_line_segments_from_dxf(dxf_path):
    doc = ezdxf.readfile(dxf_path) 
    msp = doc.modelspace() 
    line_segments = []

    # Lida com LWPOLYLINE: converte cada segmento da polilinha em uma linha individual
    for entity in msp.query('LWPOLYLINE'): 
        points = entity.get_points() 
        if len(points) >= 2:
            for i in range(len(points) - 1):
                start_point = (points[i][0], points[i][1])
                end_point = (points[i+1][0], points[i+1][1])
                line_segments.append([start_point, end_point])
        # Se a polilinha for fechada, adicione o segmento final do último ponto ao primeiro
        if entity.is_closed and len(points) > 2:
            start_point = (points[-1][0], points[-1][1])
            end_point = (points[0][0], points[0][1])
            line_segments.append([start_point, end_point])

    # Lida com POLYLINE (entidade mais antiga, com vértices separadas): converte cada segmento
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
        # Se a polilinha for fechada, adicione o segmento final do último ponto ao primeiro
        if entity.is_closed and len(current_polyline_points) > 2:
            start_point = (current_polyline_points[-1][0], current_polyline_points[-1][1])
            end_point = (current_polyline_points[0][0], current_polyline_points[0][1])
            line_segments.append([start_point, end_point])

    # Adicionar suporte para LINE: já são linhas individuais
    for entity in msp.query('LINE'): 
        start_point = (entity.dxf.start[0], entity.dxf.start[1])
        end_point = (entity.dxf.end[0], entity.dxf.end[1])
        line_segments.append([start_point, end_point])

    return line_segments

def create_3d_model_from_dxf_layers_v3(dxf_folder, layer_height=0.1, output_filename="output.stl", output_dxf_clean_folder=None):
    dxf_files = sorted([f for f in os.listdir(dxf_folder) if f.endswith('.dxf')]) 

    if not dxf_files:
        print(f"Nenhum arquivo DXF encontrado na pasta: {dxf_folder}")
        return

    all_meshes = []
    z_offset = 0

    if output_dxf_clean_folder and not os.path.exists(output_dxf_clean_folder):
        os.makedirs(output_dxf_clean_folder)

    # Usa tqdm para mostrar o progresso do processamento de cada camada DXF
    for dxf_file in tqdm(dxf_files, desc="Processando camadas DXF"):
        dxf_path = os.path.join(dxf_folder, dxf_file)
        
        line_segments_2d = get_line_segments_from_dxf(dxf_path)

        if not line_segments_2d:
            print(f"Aviso: Nenhuma linha ou polilinha válida encontrada em {dxf_file}. Pulando esta camada.")
            z_offset += layer_height
            continue

        current_layer_meshes = []
        for segment_2d in line_segments_2d:
            if len(segment_2d) < 2: 
                continue
            
            try:
                path_2d = trimesh.load_path(np.array(segment_2d), process=False)
                
                extruded_result = path_2d.extrude(height=layer_height)
                
                if isinstance(extruded_result, list):
                    for extruded_slice in extruded_result:
                        if isinstance(extruded_slice, trimesh.Trimesh):
                            extruded_slice.apply_translation([0, 0, z_offset])
                            current_layer_meshes.append(extruded_slice)
                elif isinstance(extruded_result, trimesh.Trimesh):
                    extruded_result.apply_translation([0, 0, z_offset])
                    current_layer_meshes.append(extruded_result)

            except Exception as e:
                print(f"Erro ao processar segmento de linha em {dxf_file}: {e}")

        all_meshes.extend(current_layer_meshes)

        if output_dxf_clean_folder:
            output_clean_dxf_path = os.path.join(output_dxf_clean_folder, f"clean_{dxf_file}")
            create_simplified_dxf_for_laser(line_segments_2d, output_clean_dxf_path)


        z_offset += layer_height

    if not all_meshes:
        print("Nenhum sólido 3D foi criado a partir dos arquivos DXF.")
        return

    combined_mesh = trimesh.util.concatenate(all_meshes)

    output_path = os.path.join(dxf_folder, output_filename)
    combined_mesh.export(output_path)
    print(f"\nModelo 3D '{output_filename}' gerado com sucesso em: {output_path}")

# Nova função para criar um DXF simplificado (apenas linhas e seções essenciais)
def create_simplified_dxf_for_laser(line_segments, output_dxf_path):
    doc = ezdxf.new('AC1009') 
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
        print(f"Erro ao salvar DXF simplificado {output_dxf_path}: {e}")


# --- Exemplo de Uso ---
# Certifique-se de que esta pasta existe e contém seus arquivos DXF
dxf_input_dir = r"C:\Users\ckubota\Desktop\IPT\pyslm-master\Test_code\Final_pipeline\dxfs\dxf_bruto" 
output_stl_file = "Aleta_mini_3d_model_v3.stl"
layer_thickness = 0.03

# Defina uma pasta para os DXFs limpos/simplificados (opcional)
#output_clean_dxf_folder = os.path.join(dxf_input_dir, "clean_dxfs_v3") 
output_clean_dxf_folder = r"C:\Users\ckubota\Desktop\IPT\pyslm-master\Test_code\Final_pipeline\dxfs\dxf_clean"

print("Iniciando a geração do modelo 3D e DXFs simplificados...")
create_3d_model_from_dxf_layers_v3(
    dxf_folder=dxf_input_dir, 
    layer_height=layer_thickness, 
    output_filename=output_stl_file,
    output_dxf_clean_folder=output_clean_dxf_folder 
)
print("Processo concluído.")