FROM node:lts-alpine

WORKDIR /app

COPY . .

EXPOSE 5173

RUN npm install

CMD [ "npm" , "run" , "dev" , "--" , "--host" , "0.0.0.0" ]