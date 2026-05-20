FROM node:lts-alpine AS builder

WORKDIR /app

COPY ./keycloakify .

RUN apk add -q --no-cache maven 

RUN npm install
RUN npm run build-keycloak-theme
RUN ls dist_keycloak

FROM quay.io/keycloak/keycloak:24.0

COPY --from=builder /app/dist_keycloak/keycloak-theme-for-kc-all-other-versions.jar /opt/keycloak/providers/keycloak-theme.jar
