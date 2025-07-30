"""
Script de Conversão DXF para Formato de Máquina (TXT/DXF Simplificado):
Lê arquivos DXF de uma pasta de entrada, extrai apenas segmentos de linha de várias entidades
(LWPOLYLINE, POLYLINE, LINE) e os reescreve em um novo arquivo (TXT ou DXF) com um formato
simplificado, ideal para máquinas de fabricação com requisitos específicos.

Este script agora utiliza caminhos relativos e aceita argumentos de linha de comando:
python support_DXF_to_machine_TXT_or_DXF.py {nome da peca} {bruto ou clean}
"""

import ezdxf
import os
import logging
import numpy as np
from tqdm import tqdm # Importa tqdm para exibir uma barra de progresso
import sys # Importa sys para acessar argumentos de linha de comando
import pathlib # Importa pathlib para manipulação de caminhos

# Configura o logger do ezdxf para suprimir avisos, mantendo a saída limpa.
# Isso evita poluir o console com mensagens que não são erros críticos.
logging.getLogger('ezdxf').setLevel(logging.ERROR)

def convert_dxf_to_lines_only(input_dxf_path: str, output_target_path: str, output_extension: str):
    """
    Lê um arquivo DXF de entrada, extrai todos os segmentos de linha de entidades LWPOLYLINE,
    POLYLINE e LINE, e então cria um novo arquivo (texto puro ou DXF simplificado)
    contendo apenas os dados das entidades LINE. O formato de saída inclui os marcadores
    necessários SECTION ENTITIES, ENDSEC e EOF.

    Args:
        input_dxf_path (str): O caminho completo para o arquivo DXF de entrada.
        output_target_path (str): O caminho completo onde o novo arquivo simplificado será salvo.
        output_extension (str): A extensão desejada para o arquivo de saída (e.g., '.txt', '.dxf').
    """
    # Verifica se o arquivo DXF de entrada existe antes de tentar lê-lo.
    if not os.path.exists(input_dxf_path):
        print(f"Erro: Arquivo DXF de entrada não encontrado em '{input_dxf_path}'")
        return

    try:
        # Tenta ler o arquivo DXF usando ezdxf.
        doc = ezdxf.readfile(input_dxf_path)
        msp = doc.modelspace() # Acessa o espaço do modelo onde as entidades de desenho residem.
    except ezdxf.DXFStructureError:
        print(f"Erro: Estrutura de arquivo DXF inválida para '{input_dxf_path}'. Pulando.")
        return
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao ler '{input_dxf_path}': {e}. Pulando.")
        return

    all_line_segments = [] # Lista para armazenar todos os segmentos de linha extraídos.

    # 1. Extrai segmentos de entidades LWPOLYLINE (polilinhas leves)
    # LWPOLYLINE é uma entidade de polilinha otimizada que armazena pontos 2D ou 3D.
    for entity in msp.query('LWPOLYLINE'):
        points = entity.get_points() # Obtém os pontos da polilinha.
        if len(points) >= 2: # Uma polilinha precisa de pelo menos dois pontos para formar um segmento.
            for i in range(len(points) - 1):
                start_point = (points[i][0], points[i][1])
                end_point = (points[i+1][0], points[i+1][1])
                all_line_segments.append([start_point, end_point])
            # Se a polilinha for fechada, adiciona o segmento do último ponto ao primeiro.
            if entity.is_closed and len(points) > 2:
                start_point = (points[-1][0], points[-1][1])
                end_point = (points[0][0], points[0][1])
                all_line_segments.append([start_point, end_point])

    # 2. Extrai segmentos de entidades POLYLINE (polilinhas legadas)
    # POLYLINE é uma entidade de polilinha mais antiga que usa entidades VERTEX aninhadas.
    for entity in msp.query('POLYLINE'):
        current_polyline_points = []
        # Itera sobre os vértices da polilinha para extrair suas coordenadas.
        for vertex in entity.points():
            if hasattr(vertex, 'dxf') and hasattr(vertex.dxf, 'location'):
                current_polyline_points.append((vertex.dxf.location[0], vertex.dxf.location[1]))

        if len(current_polyline_points) >= 2:
            for i in range(len(current_polyline_points) - 1):
                start_point = (current_polyline_points[i][0], current_polyline_points[i][1])
                end_point = (current_polyline_points[i+1][0], current_polyline_points[i+1][1])
                all_line_segments.append([start_point, end_point])
            # Se a polilinha for fechada, adiciona o segmento do último ponto ao primeiro.
            if entity.is_closed and len(current_polyline_points) > 2:
                start_point = (current_polyline_points[-1][0], current_polyline_points[-1][1])
                end_point = (current_polyline_points[0][0], current_polyline_points[0][1])
                all_line_segments.append([start_point, end_point])

    # 3. Extrai segmentos de entidades LINE (linhas simples)
    # LINE é a entidade mais básica para um segmento de linha reta.
    for entity in msp.query('LINE'):
        start_point = (entity.dxf.start[0], entity.dxf.start[1])
        end_point = (entity.dxf.end[0], entity.dxf.end[1])
        all_line_segments.append([start_point, end_point])

    # 4. Escreve os segmentos de linha extraídos para o arquivo de saída
    # Garante que o diretório de saída exista antes de tentar escrever o arquivo.
    output_dir = os.path.dirname(output_target_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        # A lógica de escrita aqui mantém o formato de texto puro que você confirmou que funciona,
        # independentemente da extensão final (txt ou dxf).
        # Este é o "hack" para garantir o formato simplificado mesmo para arquivos .dxf.
        
        with open(output_target_path, 'w') as f:
            # Escreve os marcadores de cabeçalho necessários para o formato de máquina.
            f.write("0\n")
            f.write("SECTION\n")
            f.write("2\n")
            f.write("ENTITIES\n")

            # Escreve cada segmento de linha no formato específico da máquina.
            # Cada linha é definida por um par de coordenadas (x_start, y_start) e (x_end, y_end).
            for segment in all_line_segments:
                start_x, start_y = segment[0]
                end_x, end_y = segment[1]
                
                # Formato exato que a máquina espera:
                f.write("0\n")          # Código de grupo para o tipo de entidade (LINE)
                f.write("LINE\n")       # Nome da entidade
                f.write("8\n")          # Código de grupo para o nome da camada
                f.write("0\n")          # Nome da camada (geralmente '0' para camadas padrão)
                f.write("10\n")         # Código de grupo para a coordenada X inicial
                f.write(f"{start_x:.3f}\n") # Coordenada X inicial, arredondada para 3 casas decimais
                f.write("20\n")         # Código de grupo para a coordenada Y inicial
                f.write(f"{start_y:.3f}\n") # Coordenada Y inicial, arredondada para 3 casas decimais
                f.write("11\n")         # Código de grupo para a coordenada X final
                f.write(f"{end_x:.3f}\n") # Coordenada X final, arredondada para 3 casas decimais
                f.write("21\n")         # Código de grupo para a coordenada Y final
                f.write(f"{end_y:.3f}\n") # Coordenada Y final, arredondada para 3 casas decimais
                f.write("0\n")          # Marcador de fim de entidade (para LINE)

            # Escreve os marcadores de rodapé necessários para o formato de máquina.
            f.write("0\n")
            f.write("ENDSEC\n")
            f.write("0\n")
            f.write("EOF\n")
            
    except Exception as e:
        print(f"Erro ao escrever em '{output_target_path}': {e}")

def process_dxf_folder(input_folder_path: str, output_folder_path: str, output_extension: str = '.txt'):
    """
    Processa todos os arquivos DXF em uma determinada pasta de entrada, converte-os para
    um formato simplificado (apenas linhas, em texto puro ou DXF), e os salva em uma pasta de saída.

    Args:
        input_folder_path (str): O caminho para a pasta que contém os arquivos DXF de entrada.
        output_folder_path (str): O caminho para a pasta onde os arquivos limpos serão salvos.
        output_extension (str): A extensão de arquivo desejada para os arquivos de saída (e.g., '.txt', '.dxf').
    """
    # Verifica se a pasta de entrada existe.
    if not os.path.exists(input_folder_path):
        print(f"Erro: Pasta de entrada não encontrada em '{input_folder_path}'")
        return

    # Cria a pasta de saída se ela não existir.
    if not os.path.exists(output_folder_path):
        os.makedirs(output_folder_path)
        print(f"Pasta de saída criada: '{output_folder_path}'")

    # Lista todos os arquivos DXF na pasta de entrada (ignorando maiúsculas/minúsculas).
    dxf_files = [f for f in os.listdir(input_folder_path) if f.lower().endswith('.dxf')]

    if not dxf_files:
        print(f"Nenhum arquivo DXF encontrado em '{input_folder_path}'.")
        return

    print(f"Iniciando a conversão em lote de {len(dxf_files)} arquivos DXF de '{input_folder_path}' para '{output_folder_path}'...")

    # Itera sobre cada arquivo DXF, exibindo uma barra de progresso.
    for filename in tqdm(dxf_files, desc="Convertendo arquivos DXF"):
        input_file_path = os.path.join(input_folder_path, filename)
        
        # Gera o nome do arquivo de saída, mantendo o nome base e mudando a extensão.
        base_filename = os.path.splitext(filename)[0]
        output_file_path = os.path.join(output_folder_path, f"cleaned_{base_filename}{output_extension}")

        # Chama a função de conversão para cada arquivo.
        convert_dxf_to_lines_only(input_file_path, output_file_path, output_extension)

    print("\nConversão em lote concluída!")

# --- Exemplo de Uso do Script com Argumentos de Linha de Comando ---
if __name__ == "__main__":
    # Verifica se o número correto de argumentos foi fornecido
    if len(sys.argv) != 3:
        print("Uso: python support_DXF_to_machine_TXT_or_DXF.py {nome_da_peca} {bruto_ou_clean}")
        print("Exemplo: python support_DXF_to_machine_TXT_or_DXF.py Aleta_mini bruto")
        sys.exit(1)

    piece_name = sys.argv[1] # Nome da peça (e.g., Aleta_mini)
    folder_type = sys.argv[2].lower() # Tipo de pasta (bruto ou clean), convertido para minúsculas

    # Define o diretório base do script.
    # Assumindo que o script está em C:\Users\ckubota\Desktop\IPT\Final_pipeline\
    script_dir = pathlib.Path(__file__).parent 

    # --- CONFIGURAÇÃO DAS PASTAS DE ENTRADA E SAÍDA (Caminhos Relativos) ---
    # Os DXFs de entrada estão em C:\Users\ckubota\Desktop\IPT\Final_pipeline\dxfs\{nome_da_peca}\dxf_bruto
    input_dxf_folder = script_dir / "dxfs" / piece_name / f"dxf_{folder_type}"

    # A pasta de saída para os arquivos TXT/DXF simplificados.
    # Por padrão, vamos para uma pasta 'txt_machine' dentro da pasta da peça.
    output_dxf_folder = script_dir / "dxfs" / piece_name / "txt_machine"

    # --- EXTENSÃO DO ARQUIVO DE SAÍDA ---
    # Mantemos como '.dxf' para que os arquivos resultantes tenham a extensão .dxf,
    # mas lembrando que o conteúdo será o DXF ASCII simplificado gerado pelo script.
    output_file_extension = '.dxf' # Ou '.txt' se a máquina realmente requer essa extensão

    # Converte os objetos Path para strings, pois os os.path métodos geralmente esperam strings
    process_dxf_folder(str(input_dxf_folder), str(output_dxf_folder), output_file_extension)

    print("\nScript finalizado.")
    print(f"Verifique a pasta de saída '{output_dxf_folder}' para os novos arquivos com a extensão '{output_file_extension}'.")