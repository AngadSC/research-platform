# Analysis runner image: GNU Octave for plain MATLAB-style .m scripts (VISION D2). Octave is GPL
# software; it runs here as a separate program in its own image, and none of its code is copied
# into labbenchos. Figures: print -dpngcairo out/figure.png (gnuplot, no display; no Ghostscript,
# which is AGPL, so -dpng and -dpdf are not available). Build from
# runner/images:
#   docker build -t labbench-runner-octave -f octave/Dockerfile .
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends octave gnuplot-nox fonts-freefont-otf \
    && rm -rf /var/lib/apt/lists/*
COPY --chmod=755 run-job /usr/local/bin/run-job
ENV LANG=C.UTF-8
USER 65534:65534
WORKDIR /work
