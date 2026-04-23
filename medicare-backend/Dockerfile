FROM python:3.11-slim-bookworm

WORKDIR /app

# 换阿里云 apt 镜像（bookworm 稳定版，不用清华）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 复制字体供 ReportLab 使用
RUN ln -sf /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc /usr/share/fonts/truetype/simhei.ttf

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --timeout 120 \
    --retries 5

COPY . .

RUN mkdir -p /app/models

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
