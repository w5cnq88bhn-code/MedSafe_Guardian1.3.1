FROM python:3.11-slim

WORKDIR /app

# 换成国内 apt 镜像源（清华），解决 deb.debian.org 访问慢/断线问题
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 复制字体供 ReportLab 使用
RUN ln -sf /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc /usr/share/fonts/truetype/simhei.ttf

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

COPY . .

RUN mkdir -p /app/models

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
