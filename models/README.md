# Fluxo de Trabalho de Manufatura Aditiva

Este repositório contém um conjunto de scripts Python projetados para automatizar e auxiliar no processo de preparação de modelos 3D (STL) para manufatura aditiva, incluindo a geração de suportes, fatiamento em camadas 2D (DXF) e geração de parâmetros de máquina.

## Scripts e Suas Funções

Os scripts devem ser executados em uma sequência lógica para preparar seu modelo para a fabricação.

### 1. `STL_to_support_STL.py`
* **Propósito:** Gera estruturas de suporte de bloco para seu modelo STL original e salva o modelo combinado (peça + suportes) em um novo arquivo STL.
* **Como Usar:** Execute o script com o nome do modelo como argumento:
    ```bash
    python STL_to_support_STL.py <NomeDoModelo>
    ```
    Exemplo: `python STL_to_support_STL.py Aleta_mini`
* **Entrada:** Arquivo STL original localizado em `models\original\Peca\<NomeDoModelo>.stl`.
* **Saída:** Um novo arquivo STL contendo a peça e os suportes, salvo em `models\support\<NomeDoModelo>\<NomeDoModelo>_support.stl`. Este é o seu **STL_support**.
* **Parâmetros Chave a Definir no Script:**
    * `base_models_path`: O caminho base para sua pasta de modelos STL originais.
    * `base_support_stl_output_path`: O caminho base para a pasta de saída dos STLs com suporte.
    * `OVERHANG_ANGLE`: Ângulo para a detecção de balanços (ajuste para suportar mais ou menos).

### 2. `STL_to_support_DXF.py`
* **Propósito:** Gera suportes para seu modelo STL original, fatia tanto a peça quanto os suportes em camadas 2D e exporta cada camada como um arquivo DXF separado. Este é o caminho mais direto para obter suas camadas DXF com suportes.
* **Como Usar:** Execute o script com o nome do modelo como argumento:
    ```bash
    python STL_to_support_DXF.py <NomeDoModelo>
    ```
    Exemplo: `python STL_to_support_DXF.py Aleta_mini`
* **Entrada:** Arquivo STL original localizado em `models\original\Peca\<NomeDoModelo>.stl`.
* **Saída:** Uma pasta contendo múltiplos arquivos DXF, cada um representando uma fatia da peça e seus suportes, salvo em `dxfs\<NomeDoModelo>\dxf_bruto`. Estes são seus arquivos **DXF_support**.
* **Parâmetros Chave a Definir no Script:**
    * `base_models_path`: O caminho base para sua pasta de modelos STL originais.
    * `base_dxfs_path`: O caminho base para a pasta raiz dos DXFs.
    * `OVERHANG_ANGLE`: Ângulo para a geração de suportes.
    * `layer_thickness`: A espessura de cada camada fatiada (e.g., `0.03`).

### 3. `STL_solid_support_to_DXF.py`
* **Propósito:** Este é um script de fatiamento mais genérico. Ele pega um arquivo STL existente (que pode ser uma peça sólida **ou um STL que já inclui suportes, como o gerado por `STL_to_support_STL.py`**) e o fatia em camadas 2D, exportando cada camada como um arquivo DXF.
* **Como Usar:** Execute o script com o nome do modelo como argumento:
    ```bash
    python STL_solid_support_to_DXF.py <NomeDoModelo>
    ```
    Exemplo: `python STL_solid_support_to_DXF.py Palet_block_pin`
* **Entrada:** Arquivo STL (peça sólida ou já com suportes) localizado em `models\original\Peca\<NomeDoModelo>.stl` ou o **STL_support** gerado anteriormente (se você ajustar `base_models_path` no script para a pasta `models\support`).
* **Saída:** Uma pasta contendo arquivos DXF para cada camada do STL de entrada, salvo em `dxfs\<NomeDoModelo>\dxf_bruto`.
* **Parâmetros Chave a Definir no Script:**
    * `base_models_path`: O caminho base para sua pasta de modelos STL de entrada. **Ajuste este caminho se estiver fatiando um STL_support.**
    * `base_dxfs_path`: O caminho base para a pasta raiz dos DXFs.
    * `layer_thickness`: A espessura de cada camada fatiada.

### 4. `support_DXF_to_clean_DXF.py`
* **Propósito:** Processa uma pasta de arquivos DXF brutos ou limpos. Ele extrai e simplifica as entidades de linha, criando novos arquivos DXF "limpos" que são mais adequados para processamento posterior. Opcionalmente, pode criar um modelo 3D a partir das camadas DXF.
* **Como Usar:** Execute o script com o nome do modelo e o tipo de pasta de entrada:
    ```bash
    python support_DXF_to_clean_DXF.py <NomeDoModelo> <TipoDePasta>
    ```
    `<TipoDePasta>` pode ser `bruto` (para `dxfs\<NomeDoModelo>\dxf_bruto`) ou `clean` (para `dxfs\<NomeDoModelo>\dxf_clean`).
    Exemplo: `python support_DXF_to_clean_DXF.py Aleta_mini bruto`
* **Entrada:** Uma pasta contendo seus arquivos DXF de camadas (seus arquivos **DXF_support** ou **DXF_clean**).
* **Saída:**
    * Uma nova pasta contendo arquivos DXF simplificados em `dxfs\<NomeDoModelo>\dxf_clean`. Este é o seu **DXF_clean**.
    * Um modelo 3D combinado (STL) salvo em `models\output_3d\<NomeDoModelo>_3d_model_from_<TipoDePasta>.stl`.
* **Parâmetros Chave a Definir no Script:**
    * `base_dxfs_path`: O caminho base para a pasta raiz dos DXFs.
    * `base_models_output_path`: O caminho base para a pasta de saída dos modelos 3D.
    * `layer_thickness`: A espessura da camada (deve ser a mesma usada no fatiamento original).

### 5. `support_DXF_to_machine_TXT_or_DXF.py`
* **Propósito:** Converte os arquivos de camada DXF (limpos ou brutos) para um formato textual altamente simplificado, específico para determinadas máquinas a laser ou de manufatura. Você pode escolher a extensão do arquivo como `.txt` ou `.dxf`, mas o conteúdo será sempre no formato de texto simples compatível com a máquina.
* **Como Usar:** Execute o script com o nome do modelo e o tipo de pasta de entrada:
    ```bash
    python support_DXF_to_machine_TXT_or_DXF.py <NomeDoModelo> <TipoDePasta>
    ```
    `<TipoDePasta>` pode ser `bruto` (para `dxfs\<NomeDoModelo>\dxf_bruto`) ou `clean` (para `dxfs\<NomeDoModelo>\dxf_clean`).
    Exemplo: `python support_DXF_to_machine_TXT_or_DXF.py Aleta_mini clean`
* **Entrada:** Uma pasta contendo seus arquivos DXF de camadas (preferencialmente seus arquivos **DXF_clean**, ou diretamente **DXF_support** se a limpeza não for necessária).
* **Saída:** Uma nova pasta contendo arquivos prontos para a máquina, com extensão `.txt` ou `.dxf` (e.g., `cleaned_sua_peca_layer0_0.txt`), salvo em `dxfs\<NomeDoModelo>\txt_machine`. Este é o seu **DXF_machine_TXT_or_DXF**.
* **Parâmetros Chave a Definir no Script:**
    * `base_dxfs_path`: O caminho base para a pasta raiz dos DXFs.
    * `output_file_extension`: A extensão de arquivo desejada (`.txt` ou `.dxf`).

### 6. `manufacture_parameters.py`
* **Propósito:** Analisa os arquivos de camada DXF/TXT prontos para a máquina e gera automaticamente um arquivo de parâmetros de fabricação. Este arquivo incluirá informações como dimensões da caixa delimitadora e número de camadas, combinadas com configurações de máquina predefinidas ou personalizadas.
* **Como Usar:** Não foi modificado para argumentos de linha de comando. Use ajustando os caminhos diretamente no script.
* **Entrada:** Uma pasta contendo seus arquivos DXF/TXT de camadas prontos para a máquina (seus arquivos **DXF_machine_TXT_or_DXF**).
* **Saída:** Um único arquivo de texto contendo todos os parâmetros de fabricação (e.g., `auto_machine_parameters.txt`).
* **Parâmetros Chave a Definir no Script:**
    * `input_dxf_folder`: Caminho para a pasta com seus arquivos DXF/TXT prontos para a máquina.
    * `output_file_path`: O caminho completo e o nome do arquivo para o arquivo de parâmetros gerado.
    * `specified_layer_thickness`: A espessura da camada (muito importante e deve ser fornecida manualmente).
    * `part_name` (opcional): O nome da sua peça.
    * `machine_settings` (opcional): Um dicionário para sobrescrever parâmetros padrão da máquina (e.g., potência de hachura, velocidade de contorno).

---

**Fluxo de Trabalho Recomendado:**

1.  **Modelo Original (STL)**
    * (`models\original\Peca\<NomeDoModelo>.stl`)

2.  **Gerar Camadas DXF (com Suporte)**
    * **Opção 1 (Recomendada - Suporte e Fatiamento Integrados):**
        * Use `STL_to_support_DXF.py`.
        * Execute: `python STL_to_support_DXF.py <NomeDoModelo>`
        * Output: `dxfs\<NomeDoModelo>\dxf_bruto` (**DXF_support**)
    * **Opção 2 (Se você já possui um STL com suporte SÓLIDO):**
        * Primeiro, certifique-se de ter um STL com suporte (e.g., gerado por `STL_to_support_STL.py` em `models\support\<NomeDoModelo>\<NomeDoModelo>_support.stl` ou de outra fonte).
        * **Ajuste manual necessário:** Edite o script `STL_solid_support_to_DXF.py` para que a variável `base_models_path` aponte para a pasta onde seu STL já suportado está localizado (e.g., `r"C:\Users\ckubota\Desktop\IPT\Final_pipeline\models\support\<NomeDoModelo>"`).
        * Execute: `python STL_solid_support_to_DXF.py <NomeDoModelo>` (o `<NomeDoModelo>` é usado para organizar a saída DXF).
        * Output: `dxfs\<NomeDoModelo>\dxf_bruto` (**DXF_support**)

3.  **(Opcional) Limpar e Otimizar Camadas DXF**
    * Use `support_DXF_to_clean_DXF.py`.
    * Execute: `python support_DXF_to_clean_DXF.py <NomeDoModelo> bruto`
    * Output: `dxfs\<NomeDoModelo>\dxf_clean` (**DXF_clean**) e um STL 3D de visualização.

4.  **Converter Camadas DXF para Formato de Máquina**
    * Use `support_DXF_to_machine_TXT_or_DXF.py`.
    * Execute: `python support_DXF_to_machine_TXT_or_DXF.py <NomeDoModelo> clean` (ou `bruto` se pulou a limpeza).
    * Output: `dxfs\<NomeDoModelo>\txt_machine` (**DXF_machine_TXT_or_DXF**)

5.  **Gerar Arquivo de Parâmetros de Fabricação**
    * Use `manufacture_parameters.py`.
    * **Ajuste manual necessário:** Edite o script para que `input_dxf_folder` aponte para `dxfs\<NomeDoModelo>\txt_machine`.
    * Output: `auto_machine_parameters.txt`.

**Dica:** Antes de executar cada script, verifique e ajuste os `base_paths` definidos no início de cada script para corresponder à sua estrutura de pastas local.