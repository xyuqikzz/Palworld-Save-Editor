ARG BASE_IMAGE=nikolaik/python-nodejs:python3.12-nodejs21-slim

FROM ${BASE_IMAGE} AS palooz-builder

ARG PALOOZ_COMMIT=c23ceebceca4a7ffe7ccc0c5084a20cbce353f50

RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ \
        git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python -m pip wheel --no-cache-dir --no-deps --wheel-dir /wheels \
    "palooz @ git+https://github.com/deafdudecomputers/PalworldSaveTools.git@${PALOOZ_COMMIT}#subdirectory=src/palsav/palooz"

FROM ${BASE_IMAGE}

ENV PATH=/usr/local/nginx/bin:$PATH
EXPOSE 58888
VOLUME [ "/mnt/gamesave" ]

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        tini \
        gosu \
    && apt-get clean && rm -rf /var/lib/apt/lists/* 

COPY --chown=pn:pn --chmod=777 ./ /app
COPY --from=palooz-builder /wheels /tmp/palooz-wheels

RUN cd "/app/frontend/palworld-pal-editor-webui" \
    && npm install \
    && npm run build \
    && mv "/app/frontend/palworld-pal-editor-webui/dist" "/app/src/palworld_pal_editor/webui" 

RUN python -m pip install --no-cache-dir /tmp/palooz-wheels/palooz-*.whl \
    && python -c "import palooz; assert callable(palooz.compress); assert callable(palooz.decompress)" \
    && python -m pip install --no-cache-dir --force-reinstall --upgrade -r requirements.txt \
    && python -m pip install -e . --no-cache-dir --force-reinstall --upgrade \
    && rm -rf /tmp/palooz-wheels

RUN sed -i 's/\r$//' /app/docker/app.sh \
    && chmod +x /app/docker/app.sh

ENTRYPOINT ["tini", "-g", "--"]

CMD ["/app/docker/app.sh"]
