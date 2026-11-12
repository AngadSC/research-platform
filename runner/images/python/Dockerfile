# Analysis runner image: Python (VISION C2). Build on the runner server from runner/images:
#   docker build -t labbench-runner-python -f python/Dockerfile .
FROM python:3.12-slim
RUN pip install --no-cache-dir \
        numpy==2.1.3 pandas==2.2.3 scipy==1.14.1 matplotlib==3.9.2 statsmodels==0.14.4 \
        seaborn==0.13.2 openpyxl==3.1.5 \
    && MPLCONFIGDIR=/tmp/mpl python -c "import matplotlib.pyplot"
COPY --chmod=755 run-job /usr/local/bin/run-job
ENV MPLBACKEND=Agg MPLCONFIGDIR=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65534:65534
WORKDIR /work
