FROM python:3.12-slim AS base

# --- System dependencies ---

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        gnupg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Node.js 20 LTS (needed by Claude Code CLI) ---

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- GitHub CLI ---

RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# --- uv (Python package manager) ---

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# --- Claude Code CLI ---

RUN npm install -g @anthropic-ai/claude-code

# --- Entrypoint (must be world-accessible for UID override in compose) ---

COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# --- Non-root user ---

RUN groupadd --gid 1000 aigov \
    && useradd --uid 1000 --gid aigov --create-home aigov

USER aigov
WORKDIR /home/aigov

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
