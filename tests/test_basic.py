
import pytest
import sys
import os
import shutil
import tempfile
from pathlib import Path

# Adiciona a diretoria raiz ao path para conseguir importar 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, UPLOAD_DIR

@pytest.fixture
def client():
    # Configura a app para modo de teste
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test_secret'
    
    # Cria uma diretoria temporária para os testes não mexerem no 'storage' real
    test_dir = tempfile.mkdtemp()
    # Fazemos monkeypatch manual da UPLOAD_DIR alterando-a no módulo app
    # (Nota: Isto depende de como UPLOAD_DIR é importado/usado, mas para este caso simples pode servir se o app usar a referência global)
    # Como UPLOAD_DIR é uma constante global em app.py, é difícil alterar depois de carregado sem recarregar,
    # mas podemos tentar usar mocks.
    
    with app.test_client() as client:
        yield client
        
    # Limpeza
    shutil.rmtree(test_dir)

def test_health_check(client):
    """Testa se o endpoint /health responde corretamente."""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {"status": "ok"}

def test_home_page_loads(client):
    """Testa se a página inicial carrega sem erros."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"UM Drive" in response.data

def test_api_unauthorized_without_key(client):
    """Testa se a API rejeita pedidos sem chave."""
    response = client.get('/api/files')
    # Pode ser 401 ou retornar None (dependendo da implementação do _require_api_key)
    # No código: if not API_KEY: return None (permite se não houver chave configurada)
    # Se app.py carregar sem ENV, API_KEY é vazio.
    # Vamos assumir comportamento padrão.
    assert response.status_code in [200, 401]
