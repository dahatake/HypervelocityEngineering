FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 必要ツールをインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    gnupg \
    jq \
    lsb-release \
    shellcheck \
    software-properties-common \
    tar \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Python 3.12 + pip + pytest
RUN add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      python3.12 \
      python3.12-dev \
      python3.12-venv \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && python3 -m ensurepip --upgrade \
    && python3 -m pip install --no-cache-dir --upgrade pip pytest

# Azure CLI（apt リポジトリ + 署名検証）
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg \
    && chmod 644 /etc/apt/keyrings/microsoft.gpg \
    && AZ_REPO="$(lsb_release -cs)" \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/azure-cli/ ${AZ_REPO} main" \
      > /etc/apt/sources.list.d/azure-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends azure-cli \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh) — apt リポジトリ + 署名検証
# self-hosted runner 上で assign-copilot.sh 等が `gh api graphql` を呼び出すため必須。
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod 644 /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# sudo（setup-python / setup-node / apt-get 系インストール用）
# self-hosted runner では USER runner で実行されるため、
# 公式 setup-* アクションが内部で必要とする sudo がないと失敗するケースがある。
RUN apt-get update \
    && apt-get install -y --no-install-recommends sudo \
    && rm -rf /var/lib/apt/lists/* \
    && echo "runner ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/runner \
    && chmod 0440 /etc/sudoers.d/runner

# Node.js 20 + npm（NodeSource 公式リポジトリ）
# Self-Improve step が `npm install -g markdownlint-cli` を実行するため事前同梱。
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && chmod 644 /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g markdownlint-cli

# Self-Improve で毎回入れる Python ツールを事前同梱（pytest は既存 step で導入済み）
RUN python3 -m pip install --no-cache-dir ruff pytest-cov

# 実行ユーザー
RUN useradd --create-home --shell /bin/bash runner

WORKDIR /home/runner/actions-runner

# GitHub Actions Runner
# 最新版は必ず https://github.com/actions/runner/releases で確認してください。
# 注意: GitHub は古い Runner バージョンを deprecate し、メッセージ受信を停止することがあります。
#       deprecate された版を使用していると Runner は登録には成功しますが、
#       "Runner version vX.Y.Z is deprecated and cannot receive messages." エラーで
#       Listening for Jobs 開始直後に終了し、ジョブを 1 件も拾えなくなります。
#       目安として 3 か月に 1 回はこの値を最新化してください。
ARG RUNNER_VERSION=2.334.0
ARG RUNNER_ARCH=x64
RUN curl -fsSL -o actions-runner.tar.gz \
      "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz" \
    && tar -xzf actions-runner.tar.gz \
    && rm actions-runner.tar.gz \
    && ./bin/installdependencies.sh

COPY tools/runner/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && chown -R runner:runner /home/runner /entrypoint.sh

USER runner

ENTRYPOINT ["/entrypoint.sh"]
