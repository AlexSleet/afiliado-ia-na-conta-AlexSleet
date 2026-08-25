
# Afiliado IA — versão online

Versão preparada para deploy no Railway.

## Já incluído
- Login administrativo
- Cadastro de produtos
- Links rastreados de afiliado
- Página pública de pré-venda
- Captura de leads
- Cliques
- Vendas e comissões
- Dashboard
- Assistente de copy
- Gunicorn para produção
- Configuração Railway

## Variáveis obrigatórias
SECRET_KEY = uma chave longa e aleatória
ADMIN_USER = seu usuário de administrador
ADMIN_PASSWORD = uma senha forte
DB_PATH = /app/data/afiliado_ia.db

## Persistência
No Railway, crie um Volume e monte em `/app/data`.
Isso mantém o banco SQLite mesmo quando houver novo deploy.

## Próximas integrações
Hotmart/Digistore24, webhooks de vendas, WhatsApp Cloud API, OpenAI, Meta Ads e Google Ads.

## Segurança
Não coloque senhas ou chaves diretamente no código. Use variáveis de ambiente.
