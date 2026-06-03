PROJECTS_BASE_DIR = "./projects"

ALLOWED_PACKAGES = [
    "fastapi", "pydantic", "httpx", "sqlalchemy",
    "click", "typer", "pytest", "aiofiles"
]

PROJECT_MIME_TYPES = {
    '.py': 'text/x-python',
    '.js': 'text/javascript',
    '.ts': 'text/typescript',
    '.jsx': 'text/javascript',
    '.tsx': 'text/typescript',
    '.vue': 'text/x-vue',
    '.html': 'text/html',
    '.css': 'text/css',
    '.scss': 'text/x-scss',
    '.sass': 'text/x-sass',
    '.less': 'text/x-less',
    '.md': 'text/markdown',
    '.markdown': 'text/markdown',
    '.json': 'application/json',
    '.yaml': 'application/x-yaml',
    '.yml': 'application/x-yaml',
    '.txt': 'text/plain',
    '.log': 'text/plain',
    '.sh': 'text/x-sh',
    '.bash': 'text/x-sh',
    '.env': 'text/plain',
    '.gitignore': 'text/plain',
    '.dockerfile': 'text/plain',
    '.toml': 'application/x-toml',
    '.xml': 'application/xml',
    '.sql': 'application/x-sql',
    '.graphql': 'application/graphql',
    '.mdx': 'text/mdx'
}

SKIP_DIRS = {'__pycache__', 'node_modules', '.git', 'venv', '.venv', 'dist', 'build', '.next', 'coverage'}

MAX_TEXT_FILE_SIZE = 1024 * 1024