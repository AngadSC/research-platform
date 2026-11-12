# Analysis runner image: R (VISION C2). R is GPL software; it runs here as a separate program in
# its own image, and none of its code is copied into labbenchos. Build from runner/images:
#   docker build -t labbench-runner-r -f r/Dockerfile .
FROM r-base:4.4.2
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        r-cran-ggplot2 r-cran-data.table r-cran-readxl r-cran-jsonlite r-cran-lme4 \
    && rm -rf /var/lib/apt/lists/*
COPY --chmod=755 run-job /usr/local/bin/run-job
USER 65534:65534
WORKDIR /work
