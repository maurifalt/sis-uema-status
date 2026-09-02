import sys
from pathlib import Path

# scripts/check.py não é um pacote instalado em dev; adicionamos o diretório
# ao sys.path para `import check` funcionar nos testes.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
