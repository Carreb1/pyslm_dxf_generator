"""
Script de Limpeza de DXF:
Lê arquivos DXF de uma pasta de entrada (e.g., 'dxf_bruto'), extrai apenas segmentos de linha
de todas as entidades (LWPOLYLINE, POLYLINE, LINE) e reescreve esses segmentos em novos
arquivos DXF "limpos" (contendo apenas entidades LINE) em uma pasta de saída (e.g., 'dxf_clean').
Opcionalmente, pode também construir um modelo 3D (STL) a partir dessas camadas.

Este script agora utiliza caminhos relativos e aceita um argumento de linha de comando:
python support_DXF_to_clean_DXF.py {nome_da_pasta_da_peca}

Exemplo de uso (assumindo que "Aleta_mini_230720251253" está dentro de "dxfs"):
python support_DXF_to_clean_DXF.py Aleta_mini_230720251253
"""

import ezdxf
import trimesh
import numpy as np
import os
from tqdm import tqdm
import logging
import sys # Importa sys para acessar argumentos de linha de comando
import pathlib # Importa pathlib para manipulação de caminhos
from datetime import datetime # Para gerar a timestamp

# Configura o logger do ezdxf para suprimir avisos.
# Você pode ajustar o nível de WARNING para ERROR se quiser ver apenas erros críticos.
logging.getLogger('ezdxf').setLevel(logging.ERROR)

def get_line_segments_from_dxf(dxf_path):
    """
    Lê um arquivo DXF e extrai todos os segmentos de linha de entidades
    LWPOLYLINE, POLYLINE e LINE.
    
    Args:
        dxf_path (str): O caminho completo para o arquivo DXF.
        
    Returns:
        list: Uma lista de segmentos de linha, onde cada segmento é uma lista
              de dois pontos [(x1, y1), (x2, y2)]. Retorna uma lista vazia em caso de erro.
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

    # Processa LWPOLYLINE: converte cada segmento da polilinha em uma linha individual.
    for entity in msp.query('LWPOLYLINE'): 
        points = entity.get_points() 
        if len(points) >= 2:
            for i in range(len(points) - 1):
                start_point = (points[i][0], points[i][1])
                end_point = (points[i+1][0], points[i+1][1])
                line_segments.append([start_point, end_point])
            # Se a polilinha for fechada, adicione o segmento final do último ponto ao primeiro.
            if entity.is_closed and len(points) > 2:
                start_point = (points[-1][0], points[-1][1])
                end_point = (points[0][0], points[0][1])
                line_segments.append([start_point, end_point])

    # Processa POLYLINE (entidade mais antiga, com vértices separadas): converte cada segmento.
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
            # Se a polilinha for fechada, adicione o segmento final do último ponto ao primeiro.
            if entity.is_closed and len(current_polyline_points) > 2:
                start_point = (current_polyline_points[-1][0], current_polyline_points[-1][1])
                end_point = (current_polyline_points[0][0], current_polyline_points[0][1])
                line_segments.append([start_point, end_point])

    # Adiciona suporte para LINE: já são linhas individuais.
    for entity in msp.query('LINE'): 
        start_point = (entity.dxf.start[0], entity.dxf.start[1])
        end_point = (entity.dxf.end[0], entity.dxf.end[1])
        line_segments.append([start_point, end_point])

    return line_segments

def create_simplified_dxf_for_laser(line_segments, output_dxf_path):
    """
    Cria um novo arquivo DXF contendo apenas as entidades LINE dos segmentos fornecidos.
    Este formato é mais simples e pode ser preferido por algumas máquinas a laser ou CNC.
    
    Args:
        line_segments (list): Uma lista de segmentos de linha [(x1,y1), (x2,y2)].
        output_dxf_path (str): O caminho completo para o arquivo DXF de saída.
    """
    doc = ezdxf.new('AC1009') # Cria um novo documento DXF no formato R12 (compatibilidade ampla).
    msp = doc.modelspace() # Acessa o espaço do modelo.

    for segment in line_segments:
        start_point = segment[0]
        end_point = segment[1]
        # Arredonda as coordenadas para evitar problemas de precisão em algumas máquinas.
        start_point_rounded = (round(start_point[0], 6), round(start_point[1], 6))
        end_point_rounded = (round(end_point[0], 6), round(end_point[1], 6))
        msp.add_line(start_point_rounded, end_point_rounded)

    try:
        doc.saveas(output_dxf_path) # Salva o novo arquivo DXF.
    except Exception as e:
        print(f"Erro ao salvar DXF simplificado {output_dxf_path}: {e}")

def process_dxf_to_clean_dxf_and_optional_stl(
    input_dxf_folder: str,
    output_clean_dxf_folder: str,
    layer_height: float = 0.03,
    output_stl_filename: str = None, # Alterado para ser opcional
):
    """
    Processa arquivos DXF de uma pasta de entrada para gerar DXFs "limpos" (apenas linhas).
    Opcionalmente, pode também construir um modelo 3D (STL) a partir dessas camadas.

    Args:
        input_dxf_folder (str): Caminho para a pasta contendo os arquivos DXF "brutos".
        output_clean_dxf_folder (str): Caminho para a pasta onde os DXFs "limpos" serão salvos.
        layer_height (float): A altura de cada camada para extrusão (usado se STL for gerado).
        output_stl_filename (str, optional): Nome do arquivo STL de saída. Se None, o STL não é gerado.
    """
    # Verifica se a pasta de entrada existe.
    if not os.path.exists(input_dxf_folder):
        print(f"Erro: Pasta de entrada de DXFs 'brutos' não encontrada em '{input_dxf_folder}'")
        return

    # Cria a pasta de saída para DXFs limpos se não existir.
    if not os.path.exists(output_clean_dxf_folder):
        os.makedirs(output_clean_dxf_folder)
        print(f"Pasta de DXF 'limpos' criada: '{output_clean_dxf_folder}'")

    # Lista e ordena os arquivos DXF para garantir a ordem correta das camadas.
    dxf_files = sorted([f for f in os.listdir(input_dxf_folder) if f.lower().endswith('.dxf')]) 

    if not dxf_files:
        print(f"Nenhum arquivo DXF encontrado na pasta: {input_dxf_folder}")
        return

    all_meshes = [] # Lista para acumular as malhas para a geração do STL (se ativada).
    z_offset = 0.0 # Controla a posição Z atual para empilhar as camadas extrudadas.

    print("Iniciando o processamento de camadas DXF (extraindo linhas e gerando DXFs limpos)...")
    for dxf_file in tqdm(dxf_files, desc="Processando camadas DXF"):
        dxf_path = os.path.join(input_dxf_folder, dxf_file)
        
        line_segments_2d = get_line_segments_from_dxf(dxf_path)

        if not line_segments_2d:
            print(f"Aviso: Nenhuma linha ou polilinha válida encontrada em {dxf_file}. Pulando esta camada.")
            # Aumenta o offset mesmo se a camada estiver vazia para manter a altura correta do STL.
            z_offset += layer_height 
            continue

        # Sempre gera o DXF "limpo" para cada camada
        output_clean_dxf_path = os.path.join(output_clean_dxf_folder, f"clean_{dxf_file}")
        create_simplified_dxf_for_laser(line_segments_2d, output_clean_dxf_path)

        # Se a geração do STL estiver ativada, extruda e acumula as malhas.
        if output_stl_filename:
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
                    logging.error(f"Erro ao extrudar segmento de linha em {dxf_file} para STL: {e}")
            all_meshes.extend(current_layer_meshes)

        z_offset += layer_height # Incrementa o offset Z para a próxima camada.

    # Finaliza a geração do STL, se ativada.
    if output_stl_filename:
        if not all_meshes:
            print("Nenhum sólido 3D foi criado a partir dos arquivos DXF para o STL.")
        else:
            combined_mesh = trimesh.util.concatenate(all_meshes)
            # Salva o STL na pasta onde os DXFs "limpos" estão sendo gerados ou na pasta pai.
            output_stl_path = os.path.join(output_clean_dxf_folder, output_stl_filename) 
            combined_mesh.export(output_stl_path)
            print(f"\nModelo 3D '{output_stl_filename}' gerado com sucesso em: {output_stl_path}")
    
    print("\nProcesso de limpeza de DXF concluído.")


# --- Execução Principal do Script ---
if __name__ == "__main__":
    # Verifica se o número correto de argumentos foi fornecido.
    if len(sys.argv) != 2:
        print("Uso: python support_DXF_to_clean_DXF.py {nome_da_pasta_da_peca}")
        print("Exemplo: python support_DXF_to_clean_DXF.py Aleta_mini_230720251253")
        sys.exit(1)

    piece_folder_name = sys.argv[1] # Nome da pasta da peça (e.g., Aleta_mini_230720251253)

    # Define o diretório base do script.
    # Assumindo que o script está em C:\Users\ckubota\Desktop\IPT\Final_pipeline\
    script_dir = pathlib.Path(__file__).parent 

    # --- CONFIGURAÇÃO DOS CAMINHOS DE ENTRADA E SAÍDA (Relativos) ---
    # Caminho para a pasta de entrada dos DXFs "brutos".
    # Ex: C:\Users\ckubota\Desktop\IPT\Final_pipeline\dxfs\{nome_da_pasta_da_peca}\dxf_bruto
    input_dxf_folder = script_dir / "dxfs" / piece_folder_name / "dxf_bruto"

    # Caminho para a pasta onde os DXFs "limpos" serão salvos.
    # Ex: C:\Users\ckubota\Desktop\IPT\Final_pipeline\dxfs\{nome_da_pasta_da_peca}\dxf_clean
    output_clean_dxf_folder = script_dir / "dxfs" / piece_folder_name / "dxf_clean"

    # --- CONFIGURAÇÃO DA GERAÇÃO DO STL (Opcional) ---
    # Defina como None se você *não* quiser gerar o STL neste passo.
    # Se quiser gerar, forneça um nome de arquivo (ex: f"{piece_folder_name}_model.stl").
    generate_stl = True # Defina como True para gerar o STL, False para apenas limpar DXFs
    
    if generate_stl:
        output_stl_filename = f"{piece_folder_name}_combined_cleaned.stl"
        layer_thickness = 0.03 # Espessura da camada para a extrusão do STL
    else:
        output_stl_filename = None
        layer_thickness = 0.03 # A espessura da camada ainda é usada para o z_offset, mesmo sem STL.

    # Chama a função principal de processamento.
    process_dxf_to_clean_dxf_and_optional_stl(
        input_dxf_folder=str(input_dxf_folder), # Converte Path para string
        output_clean_dxf_folder=str(output_clean_dxf_folder), # Converte Path para string
        layer_height=layer_thickness,
        output_stl_filename=output_stl_filename
    )

    print("Processamento finalizado. Verifique as pastas de saída.")