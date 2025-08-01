# PySLM Pipeline de Fabricação Aditiva Unificado

Este repositório contém um conjunto de scripts Python projetados para automatizar a preparação de modelos 3D (arquivos STL) para manufatura aditiva. O fluxo de trabalho principal, `unified_blocked.py`, foi refatorado para ser mais claro e modular, separando as constantes e funções de processamento em módulos dedicados.

## Estrutura do Projeto

A estrutura de pastas foi organizada para facilitar a localização e edição dos diferentes componentes do pipeline:

```
your_project_root/
├── unified_blocked.py           # O script principal que orquestra todo o processo.
├── modules/
│   ├── parameters.py            # Contém todas as constantes e parâmetros configuráveis.
│   └── geometry_processing.py   # Contém as funções de processamento de geometria e de arquivo.
├── models/
│   └── original/
│       ├── Peca/                # Local para os arquivos STL originais.
│       └── suporte/             # Local para os arquivos STL que já contêm suportes.
└── dxfs/                        # Pasta de saída para todos os arquivos DXF e de máquina.
    └── (e.g., MyPart_YYYYMMDDHHMM/dxf_bruto, dxf_clean, txt_maquina ou MyPart_combind_support.stl)
```

## Detalhe dos Módulos

### `unified_blocked.py`

Este é o script principal e o ponto de entrada do seu projeto. Ele atua como o orquestrador, importando as constantes e funções dos módulos auxiliares e chamando-as em sequência para executar os pipelines. A sua principal função é definir os fluxos de trabalho de alto nível, conectando os "blocos" de funcionalidade em uma ordem lógica.

* **Bloco 1**: Carrega um arquivo STL original usando a função `load_original_stl`.
* **Bloco 2**: Carrega um arquivo STL que já contém suportes através da função `load_supported_stl`.
* **Bloco 3**: Gera os suportes PySLM para a peça com a função `generate_pyslm_supports`.
* **Bloco 4**: Exporta a peça junto com os suportes para um novo arquivo STL com `export_supported_stl`.
* **Bloco 5**: Este bloco é o pipeline de fatiamento de DXF e é dividido em três estágios, utilizando funções do módulo `geometry_processing.py`.

### `modules/parameters.py`

Este módulo é dedicado a armazenar todas as constantes e parâmetros que você pode precisar ajustar. Isso torna a personalização do pipeline simples e centralizada, sem a necessidade de alterar a lógica de processamento em outros arquivos.

* **Constantes Globais**: Define parâmetros fundamentais como `OVERHANG_ANGLE` (ângulo de inclinação para suportes, em graus `[deg]`) e `LAYER_THICKNESS` (espessura de cada camada, em milímetros `[mm]`).
* **Parâmetros de Transformação da Peça**: Inclui a rotação (`PART_ROTATION`) e o fator de escala (`PART_SCALE_FACTOR`) da peça, ambos em unidades claras.
* **Parâmetros de Hatcher**: Contém todas as constantes que controlam o fatiamento e a estratégia de preenchimento (`hatching`), como `HATCH_ANGLE_INITIAL` (ângulo inicial, em graus `[deg]`) e `STRIPE_WIDTH` (largura das listras, em milímetros `[mm]`).
* **Configuração de Caminhos**: Define os caminhos base para os modelos de entrada e os arquivos de saída, usando uma lógica que determina a pasta raiz do projeto. Isso garante que o código funcione corretamente, independentemente de onde o script principal seja executado.
* **Função `get_pyslm_support_generator()`**: Centraliza a configuração do gerador de suportes do PySLM. Ao invés de espalhar esses parâmetros pelo código, eles são definidos aqui com comentários detalhados sobre suas unidades e propósitos.

### `modules/geometry_processing.py`

Este módulo funciona como uma biblioteca de utilitários, contendo as funções que realizam o trabalho pesado de processamento de geometria e conversão de arquivos. Ele é projetado para ser "agnóstico" em relação aos pipelines, o que significa que suas funções podem ser reutilizadas em diferentes fluxos de trabalho.

* `export_layer_to_dxf()`: Uma função fundamental que pega uma camada do PySLM e a salva como um arquivo DXF.
* `get_line_segments_from_dxf()`: Lê um arquivo DXF e extrai todas as entidades de linha, polilinha, etc.
* `create_simplified_dxf_for_laser()`: Simplifica a geometria de um DXF para torná-lo mais compatível com máquinas a laser ou outras máquinas de manufatura.
* `convert_dxf_to_lines_only_machine_format()`: Converte a geometria do DXF para um formato de texto simplificado, específico para a máquina.
* `generate_manufacturing_parameters_file()`: Analisa os arquivos DXF de saída para gerar um arquivo de texto com os parâmetros de fabricação (como contagem de camadas e limites).
* `slice_and_export_raw_dxfs()`: Esta é a função principal do fatiamento, que usa os parâmetros do `hatcher` e a espessura da camada para criar os arquivos DXF brutos.
* `clean_raw_dxfs_and_generate_stl()`: Processa os arquivos DXF brutos para criar versões "limpas" e, opcionalmente, reconstrói um modelo 3D a partir deles.

## Como Usar

### Pipeline Unificado (`unified_blocked.py`)

Para usar o script principal, navegue até o diretório raiz do seu projeto no terminal e execute o comando:

```
python unified_blocked.py <model_name> <pipeline_type> [start_stage_for_dxf_pipelines]
```

* `<model_name>`: O nome base do seu arquivo STL (ex: `Palet`).
* `<pipeline_type>`: O fluxo de trabalho a ser executado (`1-3-4`, `1-3-5`, ou `2-5`).
* `[start_stage_for_dxf_pipelines]`: (Opcional) Permite reiniciar um pipeline de DXF a partir de um estágio específico (`1`, `2` ou `3`).

**Exemplos**:

1. **Executar Pipeline 1-3-5 (Original para DXF de Máquina - Completo):**
   ```
   python unified_blocked.py Palet 1-3-5
   ```
2. **Executar Pipeline 1-3-4 (Original para STL com Suportes):**
   ```
   python unified_blocked.py Palet 1-3-4
   ```
3. **Executar Pipeline 2-5 (STL com Suportes para DXF de Máquina - Retomar da limpeza):**
   ```
   python unified_blocked.py SupportedPart 2-5 2
   