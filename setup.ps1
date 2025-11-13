# Setup script for Secure Hospital AI LLM Integration
# Run with: powershell -ExecutionPolicy Bypass -File setup.ps1

Write-Host "Installing Python dependencies..." -ForegroundColor Green
python -m pip install -q djangorestframework djangorestframework-simplejwt django-cors-headers openai anthropic

Write-Host "Creating database migrations..." -ForegroundColor Green
python manage.py makemigrations

Write-Host "Applying migrations..." -ForegroundColor Green
python manage.py migrate

Write-Host "Creating .env file template..." -ForegroundColor Green
if (!(Test-Path .env)) {
    @"
# LLM Configuration
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo
LLM_API_KEY=your-api-key-here

# Optional: Anthropic
# LLM_PROVIDER=anthropic
# LLM_MODEL=claude-3-5-sonnet-20241022
# LLM_API_KEY=your-anthropic-api-key

# Optional: Azure OpenAI
# LLM_PROVIDER=azure
# AZURE_API_KEY=your-azure-key
# AZURE_ENDPOINT=https://your-resource.openai.azure.com/

# Database (if not using env vars)
DATABASE_URL=

# Security (keep secret)
JWT_SECRET=your-secret-key-here

# MCP Server
MCP_SERVER_URL=http://127.0.0.1:9000/mcp/
"@ | Out-File -FilePath .env -Encoding UTF8
    Write-Host ".env file created. EDIT IT NOW with your API keys!" -ForegroundColor Yellow
}

Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit .env file with your LLM API key"
Write-Host "2. Run: python manage.py runserver"
Write-Host "3. Test with: curl http://localhost:8000/api/chat/sessions/"
