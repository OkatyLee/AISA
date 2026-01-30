FROM python:3.12-slim AS builder

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Обновляем pip
RUN pip install --upgrade pip setuptools wheel

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем PyTorch CPU-версию ПЕРВЫМ
#RUN pip install --no-cache-dir --prefix=/install \
#    torch torchvision torchaudio \
#    --index-url https://download.pytorch.org/whl/cpu

# Устанавливаем остальные пакеты, указывая тот же индекс для PyTorch-зависимых пакетов
RUN pip install --no-cache-dir --prefix=/install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Финальный образ
FROM python:3.12-slim

WORKDIR /app

# Устанавливаем curl для healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем только установленные библиотеки из builder
COPY --from=builder /install /usr/local

# Копируем код
COPY . .

ENV PYTHONUNBUFFERED=1

# Удаляем кэш python внутри контейнера
RUN find . -type d -name "__pycache__" -exec rm -rf {} +