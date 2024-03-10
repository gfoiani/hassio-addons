export IMG_VERSION=$(git describe HEAD --always)
export CONTAINER_NAME=duino-miner
export BUILD_FROM=homeassistant/amd64-base:3.13

docker build --platform=linux/amd64 --build-arg BUILD_FROM=${BUILD_FROM} -t ${CONTAINER_NAME}:${IMG_VERSION} .
docker tag ${CONTAINER_NAME}:${IMG_VERSION} ${CONTAINER_NAME}:latest

# remove container if exist
CONTAINER_EXISTS="$(docker ps -a | grep -c ${CONTAINER_NAME})"
if [[ $CONTAINER_EXISTS -eq "1" ]]; then
  echo "container ${CONTAINER_NAME} exists, remove it"
  docker rm -f ${CONTAINER_NAME}
fi

docker run -dit --name ${CONTAINER_NAME} -v ${CONTAINER_NAME}:/usr/src/app/storage --env-file .env --restart=no --log-opt max-size=100m ${CONTAINER_NAME}:latest

docker ps
