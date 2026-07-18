FROM python:3.11-slim

LABEL org.opencontainers.image.title="Data Analysis Agent"
LABEL org.opencontainers.image.description="LLM-powered data analysis agent with LangGraph"
LABEL org.opencontainers.image.url="https://github.com/Hong-lf0719/data-analysis-agent"

WORKDIR /app

# 安装系统依赖（中文字体支持）
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 默认入口：CLI 模式
ENTRYPOINT ["python", "agent.py"]

# Web UI 模式：docker run -p 8501:8501 data-analysis-agent streamlit run app.py
CMD ["data/sample_sales.csv"]
