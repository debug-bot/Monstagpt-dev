FROM node:16.18.0-bullseye-slim AS assets
LABEL maintainer="Matt <matthew.james@airnow.com>"

WORKDIR /app/assets

ARG UID=1000
ARG GID=1000

ARG OPENAI_API_KEY

# Set OpenAI key as environment variable
ENV OPENAI_API_KEY=${OPENAI_API_KEY}

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean \
  && groupmod -g "${GID}" node && usermod -u "${UID}" -g "${GID}" node \
  && mkdir -p /node_modules && chown node:node -R /node_modules /app

USER node

COPY --chown=node:node assets/package.json assets/*yarn* ./

RUN yarn install && yarn cache clean

ARG NODE_ENV="production"
ENV NODE_ENV="${NODE_ENV}" \
    PATH="${PATH}:/node_modules/.bin" \
    USER="node"

COPY --chown=node:node . ..

RUN if [ "${NODE_ENV}" != "development" ]; then \
  yarn run build; else mkdir -p /app/public; fi

CMD ["bash"]

###############################################################################

FROM python:3.11.0-slim-bullseye AS app
LABEL maintainer="Matt <matthew.james@airnow.com>"

WORKDIR /app

ARG UID=1000
ARG GID=1000

ARG OPENAI_API_KEY

# Set OpenAI key as environment variable
ENV OPENAI_API_KEY=${OPENAI_API_KEY}

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential curl libpq-dev \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean \
  && groupadd -g "${GID}" python \
  && useradd --create-home --no-log-init -u "${UID}" -g "${GID}" python \
  && chown python:python -R /app

# Install git
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER python

COPY --chown=python:python requirements*.txt ./
COPY --chown=python:python bin/ ./bin

RUN chmod 0755 bin/* && bin/pip3-install

RUN pip install flask-httpauth

ARG FLASK_DEBUG="false"
ENV FLASK_DEBUG="${FLASK_DEBUG}" \
    FLASK_APP="monstagpt.app" \
    FLASK_SKIP_DOTENV="true" \
    PYTHONUNBUFFERED="true" \
    PYTHONPATH="." \
    PATH="${PATH}:/home/python/.local/bin" \
    USER="python"

COPY --chown=python:python --from=assets /app/public /public
COPY --chown=python:python . .

RUN if [ "${FLASK_DEBUG}" != "true" ]; then \
  ln -s /public /app/public && flask digest compile && rm -rf /app/public; fi

ENTRYPOINT ["/app/bin/docker-entrypoint-web"]

EXPOSE 80
EXPOSE 443

CMD ["gunicorn", "-c", "python:config.gunicorn", "monstagpt.app:create_app()"]
